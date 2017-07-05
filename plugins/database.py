import asyncio
import logging

from aiopg.sa import create_engine
import config  # TODO
from dango import dcog
from dango.utils import AsyncContextWrapper


log = logging.getLogger(__name__)


@dcog()
class Database:

    def __init__(self):
        self._connect_task = asyncio.ensure_future(self._connect())
        self._ready = asyncio.Event()

    async def _connect(self):
        self._engine = await create_engine(config.database)
        self._ready.set()

    async def _acquire(self):
        await self._ready.wait()
        return await self._engine._acquire()

    def acquire(self):
        ctx = self._engine.acquire()
        return AsyncContextWrapper(self._ready.wait(), ctx)

    def __unload(self):
        self._connect_task.cancel()
        if self._ready.is_set():
            self._engine.close()
