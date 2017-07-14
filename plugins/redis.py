import asyncio
import logging

import aioredis
from dango import config
from dango import dcog
from dango.utils import AsyncContextWrapper

log = logging.getLogger(__name__)


@dcog()
class Redis:

    host = config.ConfigEntry("host", default="localhost")
    port = config.ConfigEntry("port", default=6379)
    db = config.ConfigEntry("db", default=0)
    minsize = config.ConfigEntry("minsize", default=1)
    maxsize = config.ConfigEntry("maxsize", default=10)

    def __init__(self):
        self._ready = asyncio.Event()
        self._connect_task = asyncio.ensure_future(self._connect())

    async def _connect(self):
        try:
            self._pool = await aioredis.create_pool(
                (self.host.value, self.port.value),
                db=self.db.value,
                minsize=self.minsize.value,
                maxsize=self.maxsize.value
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
