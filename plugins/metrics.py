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
import psutil

log = logging.getLogger(__name__)


class DiscordOpCode(Enum):
    DISPATCH           = 0
    HEARTBEAT          = 1
    IDENTIFY           = 2
    PRESENCE           = 3
    VOICE_STATE        = 4
    VOICE_PING         = 5
    RESUME             = 6
    RECONNECT          = 7
    REQUEST_MEMBERS    = 8
    INVALIDATE_SESSION = 9
    HELLO              = 10
    HEARTBEAT_ACK      = 11
    GUILD_SYNC         = 12


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
class Metrics:
    """Gathers various metrics and exposes via HTTP.

    Also provides utils for other cogs to provide metrics.
    """

    def __init__(self, config, http):
        self.socket_events = collections.Counter()
        self.dispatch_events = collections.Counter()
        self.command_triggers = collections.Counter()
        self.command_failures = collections.defaultdict(collections.Counter)
        self.command_errors = collections.Counter()
        self.command_completions = collections.Counter()
        http.add_handler("GET", "/metrics", self.handle_metrics)

    async def handle_metrics(self, req):
        return web.Response(text=render_metrics({
                'Dispatch': self.dispatch_events,
                'Socket': self.socket_events,
                'Command Triggers': self.command_triggers,
                'Command Completions': self.command_completions,
                'Command Failures': self.command_failures,
                'Command Errors': self.command_errors
            }))

    async def on_socket_response(self, data):
        self.socket_events[DiscordOpCode(data['op'])] += 1

        if data['op'] == DiscordOpCode.DISPATCH.value:
            self.dispatch_events[data.get('t')] += 1

    async def on_command(self, ctx):
        self.command_triggers[ctx.command.qualified_name] += 1

    async def on_command_completion(self, ctx):
        self.command_completions[ctx.command.qualified_name] += 1

    async def on_command_error(self, ctx, error):
        self.command_failures[ctx.command.qualified_name][type(error)] += 1
        self.command_errors[type(error)] += 1
