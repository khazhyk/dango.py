import asyncio
import logging

import asyncpg
from dango import dcog
from dango.utils import AsyncContextWrapper


log = logging.getLogger(__name__)


def multi_insert_str(lst):
    count = len(lst)
    size = len(lst[0])
    elems = ["$%d" % (i + 1) for i in range(count * size)]
    indiv = ["(%s)" % (", ".join(elems[i:i+size])) for i in range(0, count * size, size)]
    return ", ".join(indiv)


@dcog()
class Database:

    def __init__(self, config):
        self.dsn = config.register("dsn")
        self._connect_task = asyncio.ensure_future(self._connect())
        self._ready = asyncio.Event()

    async def _connect(self):
        try:
            self._engine = await asyncpg.create_pool(self.dsn())
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
