import asyncio
import logging

import aioredis
from dango import dcog, Cog

from .common import utils

log = logging.getLogger(__name__)


class ContextWrapper:
    """Turns `with await` into `async with`."""

    def __init__(self, coro):
        self.coro = coro

    async def __aenter__(self):
        self.instance = await self.coro
        return self.instance.__enter__()

    async def __aexit__(self, *args, **kwargs):
        return self.instance.__exit__(*args, **kwargs)


@dcog()
class Redis(Cog):

    def __init__(self, config):
        self.host = config.register("host", default="localhost")
        self.port = config.register("port", default=6379)
        self.db = config.register("db", default=0)
        self.minsize = config.register("minsize", default=1)
        self.maxsize = config.register("maxsize", default=10)
        self._ready = asyncio.Event()
        self._connect_task = utils.create_task(self._connect())

    async def _connect(self):
        try:
            self._pool = await aioredis.create_redis_pool(
                (self.host(), self.port()),
                db=self.db(),
                minsize=self.minsize(),
                maxsize=self.maxsize()
            )
            self._ready.set()
        except Exception:
            log.exception("Exception connecting to database!")
            raise

    async def _acquire(self):
        await self._ready.wait()
        # Bizzare interface, awaiting the pool gives us a context manager
        # for an individual connection.
        return await self._pool

    def acquire(self):
        return ContextWrapper(self._acquire())

    def cog_unload(self):
        self._connect_task.cancel()
        if self._ready.is_set():
            self._pool.close()
