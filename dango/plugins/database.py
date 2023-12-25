import asyncio
import logging

import asyncpg
from dango import dcog, Cog

from .common.utils import AsyncContextWrapper
from .common import utils


log = logging.getLogger(__name__)


def multi_insert_str(lst):
    count = len(lst)
    size = len(lst[0])
    elems = ["$%d" % (i + 1) for i in range(count * size)]
    indiv = ["(%s)" % (", ".join(elems[i:i + size])) for i in range(0, count * size, size)]
    return ", ".join(indiv)


@dcog()
class Database(Cog):

    def __init__(self, config):
        self.dsn = config.register("dsn")

    async def cog_load(self):
        self._engine = await asyncpg.create_pool(self.dsn())

    async def cog_unload(self):
        await self._engine.close()

    async def _acquire(self):
        return self._engine.acquire()

    def acquire(self):
        return AsyncContextWrapper(self._acquire())
