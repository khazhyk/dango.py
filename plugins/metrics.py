"""Metrics.

Exposes an http endpoint.
"""
import asyncio
import collections
from enum import Enum
import logging
import os
import time

from aiohttp import web
from dango import dcog
from dango import utils
import discord
import prometheus_client
import psutil

log = logging.getLogger(__name__)


OPCODE_NAMES = {
    0:  "DISPATCH",
    1:  "HEARTBEAT",
    2:  "IDENTIFY",
    3:  "PRESENCE",
    4:  "VOICE_STATE",
    5:  "VOICE_PING",
    6:  "RESUME",
    7:  "RECONNECT",
    8:  "REQUEST_MEMBERS",
    9:  "INVALIDATE_SESSION",
    10: "HELLO",
    11: "HEARTBEAT_ACK",
    12: "GUILD_SYNC",
}


def _opcode_name(opcode):
    return OPCODE_NAMES.get(opcode, opcode)


def uptime():
    """Returns uptime in seconds."""
    p = psutil.Process(os.getpid())
    return time.time() - p.create_time()


async def default_handler(request):
    return web.Response(
        text="Hello! Bot has been up for %s" % uptime())


def log_task(fut):
    if fut.exception():
        log.warn(fut.exception())

def render_counter(counter):
    return "TOTAL: %s\n" % sum(counter.values()) + "\n".join("%s: %s" % (k, v) for k, v in counter.most_common())


def render_metrics(metrics):
    return "\n".join(name + "::\n" + render.lookup(type(metric))(metric) + "\n"
        for name, metric in metrics.items())

render = utils.TypeMap({
        collections.Counter: render_counter,
        dict: render_metrics
    })

@dcog(pass_bot=True)
class HTTP:
    """Launch an aiohttp web server, allow registration etc."""

    def __init__(self, bot, config):
        self.loop = bot.loop
        self.app = web.Application(loop=self.loop)
        self.handlers = {}
        self._ready = asyncio.Event()

        self.add_handler('GET', '/', default_handler)
        task = asyncio.ensure_future(self.start_app())
        task.add_done_callback(log_task)

    def add_handler(self, method, location, handler):
        self.handlers[method, location] = handler

        if self._ready.is_set():  # TODO - test
            task = asyncio.ensure_future(self.reload())
            task.add_done_callback(log_task)

    async def reload(self):
        await self.stop_app()
        await self.start_app()

    async def start_app(self):
        log.debug("Webserver starting.")

        for (method, location), handler in self.handlers.items():
            self.app.router.add_route(method, location, handler)

        await self.app.startup()

        self.handler = self.app.make_handler()
        self.server = await self.loop.create_server(
            self.handler, '0.0.0.0', 8080)
        log.debug("Webserver created.")
        self._ready.set()

    async def stop_app(self):
        log.debug("Shutting down web server.")
        await self._ready.wait()
        self.server.close()
        await self.server.wait_closed()
        await self.app.shutdown()
        await self.handler.shutdown(10)
        await self.app.cleanup()
        self._ready.clear()
        log.debug("Shutdown complete")

    def __unload(self):
        """d.py cog cleanup fn."""
        task = asyncio.ensure_future(self.stop_app())
        task.add_done_callback(log_task)


@dcog(['HTTP'])
class PrometheusMetrics:

    def get_prom(self, name):
        try:
            return prometheus_client.REGISTRY._names_to_collectors[name]
        except KeyError:
            for key, value in prometheus_client.REGISTRY._collector_to_names.items():
                for val in value:
                    if val.startswith(name):
                        return key
        raise KeyError

    def declare_metric(self, name, type, *args, namespace="dango", **kwargs):
        try:
            setattr(self, name, type(*args, namespace=namespace, **kwargs))
        except:
            setattr(self, name, self.get_prom(namespace + "_" + name))

    def __init__(self, config, http):
        self.declare_metric("opcodes", prometheus_client.Counter,
            'opcodes', 'Opcodes', ['opcode'])
        self.declare_metric("dispatch_events", prometheus_client.Counter,
            'dispatch_events', 'Dispatch Events', ['event'])
        self.declare_metric("command_triggers", prometheus_client.Counter,
            'command_triggers', 'Command Triggers', ['command'])
        self.declare_metric("command_completions", prometheus_client.Counter,
            'command_completions', 'Command Completions', ['command'])
        self.declare_metric("command_errors", prometheus_client.Counter,
            'command_errors', 'Command Errors', ['command', 'error'])
        self.declare_metric("command_timing", prometheus_client.Histogram,
            'command_timing', 'Command Timing', ['command'])

        self._in_flight_ctx = {}

        http.add_handler("GET", "/metrics", self.handle_metrics)

    async def handle_metrics(self, req):
        """aiohttp handler for Prometheus metrics."""
        
        registry = prometheus_client.REGISTRY

        if 'name[]' in req.query:
            registry = registry.restricted_registry(params['name[]'])
        
        output = prometheus_client.generate_latest(registry)

        return web.Response(
            body=output,
            headers={'Content-Type':prometheus_client.CONTENT_TYPE_LATEST})

    async def on_socket_response(self, data):
        opcode = data['op']
        self.opcodes.labels(opcode=_opcode_name(opcode)).inc()

        if opcode == 0:
            self.dispatch_events.labels(event=data.get('t')).inc()

    async def on_command(self, ctx):
        self.command_triggers.labels(command=ctx.command.qualified_name).inc()
        self._in_flight_ctx[ctx] = time.time()

    async def on_command_completion(self, ctx):
        self.command_completions.labels(command=ctx.command.qualified_name).inc()
        self.command_timing.labels(command=ctx.command.qualified_name).observe(time.time() - self._in_flight_ctx[ctx])
        del self._in_flight_ctx[ctx]

    async def on_command_error(self, ctx, error):
        self.command_errors.labels(
            command=ctx.command.qualified_name,
            error=type(error)).inc()
        del self._in_flight_ctx[ctx]
