import asyncio
import logging

import asyncpg
from dango import dcog
from dango.utils import AsyncContextWrapper


log = logging.getLogger(__name__)


@dcog(pass_bot=True)
class Database:

    def __init__(self, bot):
        self._connect_task = asyncio.ensure_future(self._connect())
        self._ready = asyncio.Event()
        self.bot = bot

    async def _connect(self):
        try:
            self._engine = await asyncpg.create_pool(self.bot.config.sa_database)
            self._ready.set()
        except:
            log.exception("Exception connecting to database!")
            raise

    async def _acquire(self):
        await self._ready.wait()
        return self._engine.acquire()

    def acquire(self):
        return AsyncContextWrapper(self._acquire())

    def __unload(self):
        self._connect_task.cancel()
        if self._ready.is_set():
            asyncio.ensure_future(self._engine.close())
