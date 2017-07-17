import asyncio
import logging

import aioredis
from dango import dcog
from dango.utils import AsyncContextWrapper

log = logging.getLogger(__name__)


@dcog()
class Redis:

    def __init__(self, config):
        self.host = config.register("host", default="localhost")
        self.port = config.register("port", default=6379)
        self.db = config.register("db", default=0)
        self.minsize = config.register("minsize", default=1)
        self.maxsize = config.register("maxsize", default=10)
        self._ready = asyncio.Event()
        self._connect_task = asyncio.ensure_future(self._connect())

    async def _connect(self):
        try:
            self._pool = await aioredis.create_pool(
                (self.host(), self.port()),
                db=self.db(),
                minsize=self.minsize(),
                maxsize=self.maxsize()
                )
            self._ready.set()
        except:
            log.exception("Exception connecting to database!")
            raise

    async def _acquire(self):
        await self._ready.wait()
        return self._pool.get()

    def acquire(self):
        return AsyncContextWrapper(self._acquire())

    def __unload(self):
        self._connect_task.cancel()
        if self._ready.is_set():
            self._pool.close()
