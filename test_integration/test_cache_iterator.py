import asyncio
import logging
import os
import unittest
import discord
from dango.plugins.common.utils import cached_history

def async_test(f):
    def wrapper(*args, **kwargs):
        coro = f(*args, **kwargs)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(coro)
    return wrapper


class CachedHistoryTest(unittest.TestCase):
    """history iterator tests."""

    @classmethod
    @async_test
    async def setUpClass(cls):
        logging.getLogger("discord").setLevel(logging.ERROR)
        logging.getLogger("websockets").setLevel(logging.ERROR)

        bot = discord.Client(fetch_offline_members=False, intents=discord.Intents.all())
        await bot.login(os.environ['DISCORD_TOKEN'])
        cls.bot = bot
        cls.task = asyncio.ensure_future(bot.connect())
        await cls.bot.wait_until_ready()
        cls.channel = bot.get_channel(182580524743655424)
        cls.guild = cls.channel.guild
        async for msg in cls.channel.history(limit=100):
            cls.bot._connection._messages.insert(0, msg)

    @classmethod
    @async_test
    async def tearDownClass(cls):
        await cls.bot.close()
        await cls.task

    @async_test
    async def test_split_cached(self):
        """most recent 100 cached, next 100 uncached"""
        lis = []
        async for msg in cached_history(self.bot, self.channel, limit=200):
            lis.append(msg)

        for x, i in enumerate(reversed(range(200))):
            assert(str(i) in lis[x].content)

    @async_test
    async def test_nomoreitems(self):
        """run out of messages"""
        lis = []
        async for msg in cached_history(self.bot, self.channel, limit=20000):
            lis.append(msg)

        assert(len(lis) == 200)
        for x, i in enumerate(reversed(range(200))):
            assert(str(i) in lis[x].content)

    @async_test
    async def test_all_cached(self):
        """most recent 16 cached"""
        lis = []
        async for msg in cached_history(self.bot, self.channel, limit=16):
            lis.append(msg)

        for x, i in enumerate(reversed(range(200-16, 200))):
            assert(str(i) in lis[x].content)

    @async_test
    async def test_before(self):
        """explicit before handling"""
        lis = []
        async for msg in cached_history(self.bot, self.channel,
                limit=175, before=discord.Object(182581887242338305)):
            lis.append(msg)

        for x, i in enumerate(reversed(range(175))):
            assert(str(i) in lis[x].content)

if __name__ == '__main__':
    unittest.main()
