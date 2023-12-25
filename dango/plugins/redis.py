import asyncio
import logging

import aioredis
from dango import dcog, Cog

from .common import utils

log = logging.getLogger(__name__)


@dcog()
class Redis(Cog):

    def __init__(self, config):
        self.host = config.register("host", default="localhost")
        self.port = config.register("port", default=6379)
        self.db = config.register("db", default=0)
        self.minsize = config.register("minsize", default=1)
        self.maxsize = config.register("maxsize", default=10)

    async def cog_load(self):
        self._pool = await aioredis.from_url(
            f"redis://{self.host()}:{self.port()}/{self.db()}",
            decode_responses=False
        )

    async def cog_unload(self):
        await self._pool.close()

    async def _acquire(self):
        return self._pool.client()

    def acquire(self):
        return utils.AsyncContextWrapper(self._acquire())
