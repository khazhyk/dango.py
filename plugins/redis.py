import asyncio
import aioredis
from dango import dcog
from dango.utils import AsyncContextWrapper


@dcog(pass_bot=True)
class Redis:

    def __init__(self, bot):
        self._ready = asyncio.Event()
        self._connect_task = asyncio.ensure_future(self._connect())
        self.bot = bot

    async def _connect(self):
        self._pool = await aioredis.create_pool(
                self.bot.config.redis_host,
                minsize=self.bot.config.redis_minsize,
                maxsize=self.bot.config.redis_maxsize
            )
        self._ready.set()

    async def _acquire(self):
        await self._ready.wait()
        return self._pool.get()

    def acquire(self):
        return AsyncContextWrapper(self._acquire())

    def __unload(self):
        self._connect_task.cancel()
        if self._ready.is_set():
            self._pool.close()
