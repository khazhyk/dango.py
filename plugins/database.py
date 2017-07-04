import asyncio
import logging

import aiopg
from aiopg.sa import create_engine
import config  # TODO
from dango import dcog


log = logging.getLogger(__name__)


@dcog(pass_bot=True)
class Database:

    def __init__(self, bot):
        self._connect = asyncio.ensure_future(self.connect(), loop=bot.loop)
        self._ready = asyncio.Event()
        self.bot = bot

    async def connect(self):
        self._engine = await create_engine(config.database)
        self._ready.set()

    async def _acquire(self):
        await self._ready.wait()
        return await self._engine._acquire()

    def acquire(self):
        return aiopg.sa.engine._EngineAcquireContextManager(
            self._acquire(), self._engine)

    def __unload(self):
        self._connect.cancel()
        if self._ready.is_set():
            self._engine.close()
