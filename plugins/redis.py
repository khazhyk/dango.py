import asyncio
import aioredis
import config  # TODO
from dango import dcog
from dango.utils import AsyncContextWrapper


@dcog()
class Redis:

    def __init__(self):
        self._ready = asyncio.Event()
        self._connect_task = asyncio.ensure_future(self._connect())

    async def _connect(self):
        self._pool = await aioredis.create_pool(
                config.redis_host,
                minsize=config.redis_minsize,
                maxsize=config.redis_maxsize
            )

    def acquire(self):
        ctx = self._pool.get()
        return AsyncContextWrapper(self._ready.wait(), ctx)

    def __unload(self):
        self._connect_task.cancel()
        if self._ready.is_set():
            self._pool.close()
