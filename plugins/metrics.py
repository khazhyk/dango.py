"""Metrics.

Exposes an http endpoint.
"""
import asyncio
import logging
import os
import time

from aiohttp import web
from dango import dcog
import psutil

log = logging.getLogger(__name__)


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
        http.add_handler("GET", "/metrics", self.handle_metrics)

    async def handle_metrics(self, req):
        return web.Response(text="No metrics")

    async def on_socket_raw_receive(self, msg):
        pass

    async def on_command(self, ctx):
        pass

    async def on_command_completion(self, ctx):
        pass

    async def on_command_error(self, ctx, error):
        pass
