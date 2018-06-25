"""Metrics.

Exposes an http endpoint.
"""
import asyncio
import logging
import os
import time

from aiohttp import web
from dango import dcog
import discord
import prometheus_client
import psutil

from .common import utils

log = logging.getLogger(__name__)

logging.getLogger("aiohttp.access").setLevel(logging.WARN)  # TODO


OPCODE_NAMES = {
    0: "DISPATCH",
    1: "HEARTBEAT",
    2: "IDENTIFY",
    3: "PRESENCE",
    4: "VOICE_STATE",
    5: "VOICE_PING",
    6: "RESUME",
    7: "RECONNECT",
    8: "REQUEST_MEMBERS",
    9: "INVALIDATE_SESSION",
    10: "HELLO",
    11: "HEARTBEAT_ACK",
    12: "GUILD_SYNC",
}

DISPATCH_NAMES = [
    "READY",
    "RESUMED",
    "MESSAGE_ACK",
    "MESSAGE_CREATE",
    "MESSAGE_DELETE",
    "MESSAGE_DELETE_BULK",
    "MESSAGE_UPDATE",
    "MESSAGE_REACTION_ADD",
    "MESSAGE_REACTION_REMOVE_ALL",
    "MESSAGE_REACTION_REMOVE",
    "PRESENCE_UPDATE",
    "USER_UPDATE",
    "CHANNEL_DELETE",
    "CHANNEL_UPDATE",
    "CHANNEL_CREATE",
    "CHANNEL_PINS_ACK",
    "CHANNEL_PINS_UPDATE",
    "CHANNEL_RECIPIENT_ADD",
    "CHANNEL_RECIPIENT_REMOVE",
    "GUILD_INTEGRATIONS_UPDATE",
    "GUILD_MEMBER_ADD",
    "GUILD_MEMBER_REMOVE",
    "GUILD_MEMBER_UPDATE",
    "GUILD_EMOJIS_UPDATE",
    "GUILD_CREATE",
    "GUILD_SYNC",
    "GUILD_UPDATE",
    "GUILD_DELETE",
    "GUILD_BAN_ADD",
    "GUILD_BAN_REMOVE",
    "GUILD_ROLE_CREATE",
    "GUILD_ROLE_DELETE",
    "GUILD_ROLE_UPDATE",
    "GUILD_MEMBERS_CHUNK",
    "VOICE_STATE_UPDATE",
    "VOICE_SERVER_UPDATE",
    "WEBHOOKS_UPDATE",
    "TYPING_START",
    "RELATIONSHIP_ADD",
    "RELATIONSHIP_REMOVE",
]


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


@dcog(pass_bot=True)
class HTTP:
    """Launch an aiohttp web server, allow registration etc."""

    def __init__(self, bot, config):
        self.loop = bot.loop
        self.app = web.Application(loop=self.loop)
        self.handlers = {}
        self._ready = asyncio.Event()

        self.add_handler('GET', '/', default_handler)
        utils.create_task(self.start_app())
        

    def add_handler(self, method, location, handler):
        self.handlers[method, location] = handler

        if self._ready.is_set():  # TODO - test
            utils.create_task(self.reload())

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
        utils.create_task(self.stop_app())


@dcog(['HTTP'], pass_bot=True)
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

    def declare_metric(self, name, type, *args, namespace="dango", function=None, **kwargs):
        try:
            setattr(self, name, type(name, *args, namespace=namespace, **kwargs))
        except ValueError:  # Already exists
            setattr(self, name, self.get_prom(namespace + "_" + name))

        if function:
            getattr(self, name).set_function(function)

    def __init__(self, bot, config, http):
        self.declare_metric(
            "opcodes", prometheus_client.Counter, 'Opcodes', ['opcode'])
        self.declare_metric(
            "dispatch_events", prometheus_client.Counter, 'Dispatch Events', ['event'])
        self.declare_metric(
            "command_triggers", prometheus_client.Counter, 'Command Triggers', ['command'])
        self.declare_metric(
            "command_completions", prometheus_client.Counter, 'Command Completions', ['command'])
        self.declare_metric(
            "command_errors", prometheus_client.Counter, 'Command Errors', ['command', 'error'])
        self.declare_metric(
            "command_timing", prometheus_client.Histogram, 'Command Timing', ['command'],
            buckets=[0.001, 0.003, 0.006, 0.016, 0.039, 0.098, 0.244, 0.61, 1.526, 3.815, 9.537, 23.842, 59.605, 149.012, 372.529, 931.323, 2328.306])
        self.declare_metric(
            "server_count", prometheus_client.Gauge, "Server Count",
            function=lambda: len(self.bot.guilds))
        self.declare_metric(
            "member_count", prometheus_client.Gauge, "Member Count", ['status'])
        for status in discord.Status:
            self.member_count.labels(status=status.name).set_function(
                self._member_count_factory(status))

        self._member_counts = {
            status: 0 for status in discord.Status
        }
        for member in bot.get_all_members():
            self._member_counts[member.status] += 1

        for opcode in OPCODE_NAMES.values():
            self.opcodes.labels(opcode=opcode)

        for dispatch_name in DISPATCH_NAMES:
            self.dispatch_events.labels(event=dispatch_name)

        self._in_flight_ctx = {}
        self.bot = bot

        http.add_handler("GET", "/metrics", self.handle_metrics)

    def _member_count_factory(self, status):
        return lambda: self._member_counts[status]

    async def on_member_update(self, before, member):
        if before.status != member.status:
            self._member_counts[member.status] += 1
            self._member_counts[before.status] -= 1

    async def on_member_join(self, member):
        self._member_counts[member.status] += 1

    async def on_member_remove(self, member):
        self._member_counts[member.status] -= 1

    async def on_guild_available(self, guild):
        for member in guild.members:
            self._member_counts[member.status] += 1

    async def on_guild_unavailable(self, guild):
        for member in guild.members:
            self._member_counts[member.status] += 1

    async def on_guild_join(self, guild):
        for member in guild.members:
            self._member_counts[member.status] += 1

    async def on_guild_remove(self, guild):
        for member in guild.members:
            self._member_counts[member.status] -= 1

    async def handle_metrics(self, req):
        """aiohttp handler for Prometheus metrics."""

        registry = prometheus_client.REGISTRY

        if 'name[]' in req.query:
            registry = registry.restricted_registry(req.query['name[]'])

        output = prometheus_client.generate_latest(registry)

        return web.Response(
            body=output,
            headers={'Content-Type': prometheus_client.CONTENT_TYPE_LATEST})

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
        self.command_timing.labels(command=ctx.command.qualified_name).observe(
            time.time() - self._in_flight_ctx[ctx])
        del self._in_flight_ctx[ctx]

    async def on_command_error(self, ctx, error):
        self.command_errors.labels(
            command=ctx.command and ctx.command.qualified_name,
            error=type(error)).inc()
        try:
            del self._in_flight_ctx[ctx]
        except KeyError:
            log.debug("command_error for command never invoked: %s", ctx)
