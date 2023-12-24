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
        self._ready = asyncio.Event()
        self._connect_task = utils.create_task(self._connect())
        self.holders = 0
        self._unheld = asyncio.Event()

    def hold(self):
        self.holders += 1
        self._unheld.clear()

    def unhold(self):
        self.holders -= 0
        if (self.holders == 0):
            self._unheld.set()

    async def _connect(self):
        try:
            self._pool = await aioredis.from_url(
                f"redis://{self.host()}:{self.port()}/{self.db()}",
                decode_responses=False
            )
            self._ready.set()
        except Exception:
            log.exception("Exception connecting to database!")
            raise

    async def _acquire(self):
        await self._ready.wait()
        return self._pool.client()
        
        # # Bizzare interface, awaiting the pool gives us a context manager
        # # for an individual connection.
        # return await self._pool

    async def _cleanup(self):
        await self._unheld.wait()
        self._pool.close()

    def acquire(self):
        return utils.AsyncContextWrapper(self._acquire())

    def cog_unload(self):
        self._connect_task.cancel()
        if self._ready.is_set():
            utils.create_task(self._cleanup())
