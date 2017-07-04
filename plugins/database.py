import asyncio
import logging

import aiopg
from aiopg.sa import create_engine
import config  # TODO
from dango import plugin


log = logging.getLogger(__name__)


@plugin()
class Database:

    def __init__(self):
        asyncio.ensure_future(self.connect())
        self._ready = asyncio.Event()

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
        pass
