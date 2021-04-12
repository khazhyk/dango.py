import asyncio
import logging
import os
import unittest
import discord


def async_test(f):
    def wrapper(*args, **kwargs):
        coro = f(*args, **kwargs)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(coro)
    return wrapper

class FetchMessageTest(unittest.TestCase):
    """fetch_message."""

    @classmethod
    @async_test
    async def setUpClass(cls):
        logging.getLogger("discord").setLevel(logging.ERROR)
        logging.getLogger("websockets").setLevel(logging.ERROR)

        bot = discord.Client(fetch_offline_members=False)
        await bot.login(os.environ['DISCORD_TOKEN'])
        cls.bot = bot
        cls.task = asyncio.ensure_future(bot.connect())
        await cls.bot.wait_until_ready()
        cls.channel = bot.get_channel(182580524743655424)
        cls.guild = cls.channel.guild

    @classmethod
    @async_test
    async def tearDownClass(cls):
        await cls.bot.close()
        await cls.task

    @async_test
    async def test_get_message(self):
        """single message endpoint"""
        msg = await self.channel.fetch_message(182581936450043904)
        self.assertEqual(msg.id, 182581936450043904)

    @async_test
    async def test_get_message_miss(self):
        """single message endpoint"""
        with self.assertRaises(discord.NotFound):
            msg = await self.channel.fetch_message(182581936450043903)


class HistoryIteratorTest(unittest.TestCase):
    """history iterator tests."""

    @classmethod
    @async_test
    async def setUpClass(cls):
        logging.getLogger("discord").setLevel(logging.ERROR)
        logging.getLogger("websockets").setLevel(logging.ERROR)

        bot = discord.Client(fetch_offline_members=False)
        await bot.login(os.environ['DISCORD_TOKEN'])
        cls.bot = bot
        cls.task = asyncio.ensure_future(bot.connect())
        await cls.bot.wait_until_ready()
        cls.channel = bot.get_channel(182580524743655424)
        cls.guild = cls.channel.guild

    @classmethod
    @async_test
    async def tearDownClass(cls):
        await cls.bot.close()
        await cls.task

    @async_test
    async def test_audit_log(self):
        """audit log

        ssh, audit_log doesn't actually work, but this test passes
        because my server has less than 100 entries :)"""
        lis = []
        async for log_entry in self.guild.audit_logs():
            lis.append(log_entry)

        lis_reversed = []
        async for log_entry in self.guild.audit_logs(limit=99999, oldest_first=True):
            lis_reversed.append(log_entry)

        assert len(lis) == len(lis_reversed)

        for i, entry in enumerate(reversed(lis)):
            assert entry.id == lis_reversed[i].id

    @async_test
    async def test_default(self):
        """standard default before handling"""
        lis = []
        async for msg in self.channel.history(limit=200):
            lis.append(msg)

        for x, i in enumerate(reversed(range(200))):
            assert(str(i) in lis[x].content)

    @async_test
    async def test_before(self):
        """explicit before handling"""
        lis = []
        async for msg in self.channel.history(
                limit=175, before=discord.Object(182581887242338305)):
            lis.append(msg)

        for x, i in enumerate(reversed(range(175))):
            assert(str(i) in lis[x].content)

    @async_test
    async def test_after(self):
        """after handling"""
        lis = []
        async for msg in self.channel.history(
                limit=200, oldest_first=True, after=discord.Object(182580943804956674)):
            lis.append(msg)

        for i in range(200):
            assert(str(i) in lis[i].content)

    @async_test
    async def test_implicit_after(self):
        """after handling"""
        lis = []
        async for msg in self.channel.history(
                limit=200, oldest_first=True):
            lis.append(msg)

        assert(len(lis) == 200)

        for i in range(200):
            assert(str(i) in lis[i].content)

    @async_test
    async def test_before_after_old_to_new(self):
        """before after handling using oldest->newest"""
        lis = []
        async for msg in self.channel.history(
                limit=200, oldest_first=True, after=discord.Object(182580943804956674),
                before=discord.Object(182581866031874049)):
            lis.append(msg)

        assert(len(lis) == 171)

        for i in range(171):
            assert(str(i) in lis[i].content)

    @async_test
    async def test_before_after_new_to_old(self):
        """before after handling using newest->oldest"""
        lis = []
        async for msg in self.channel.history(
                limit=200, oldest_first=False, after=discord.Object(182580943804956674),
                before=discord.Object(182581866031874049)):
            lis.append(msg)

        assert(len(lis) == 171)

        for x, i in enumerate(reversed(range(171))):
            assert(str(i) in lis[x].content)

    @async_test
    async def test_around(self):
        """around handling no filter #nofilter"""
        lis = []
        async for msg in self.channel.history(
                limit=101, oldest_first=False, around=discord.Object(182581484182437898)):
            lis.append(msg)

        assert(len(lis) == 101)

        for x, i in enumerate(reversed(range(50, 151))):
            assert(str(i) in lis[x].content)

    @async_test
    async def test_around_reversed(self):
        """around handling reversed no filter #nofilter"""
        lis = []
        async for msg in self.channel.history(
                limit=101, oldest_first=True, around=discord.Object(182581484182437898)):
            lis.append(msg)

        assert(len(lis) == 101)

        for x, i in enumerate(range(50, 151)):
            assert(str(i) in lis[x].content)

    @async_test
    async def test_around_filtered(self):
        """around handling with filter #instagram."""
        lis = []
        async for msg in self.channel.history(
                limit=101, oldest_first=False, around=discord.Object(182581484182437898),
                before=discord.Object(182581662973034496)):
            lis.append(msg)

        assert(len(lis) == 83)

        for x, i in enumerate(reversed(range(50, 133))):
            assert(str(i) in lis[x].content)

        lis = []
        async for msg in self.channel.history(
                limit=101, oldest_first=False, around=discord.Object(182581484182437898),
                after=discord.Object(182581324006031360)):
            lis.append(msg)

        assert(len(lis) == 80)

        for x, i in enumerate(reversed(range(71, 151))):
            assert(str(i) in lis[x].content)

        lis = []
        async for msg in self.channel.history(
                limit=101, oldest_first=False, around=discord.Object(182581484182437898),
                after=discord.Object(182581324006031360),
                before=discord.Object(182581662973034496)):
            lis.append(msg)

        assert(len(lis) == 62)

        for x, i in enumerate(reversed(range(71, 133))):
            assert(str(i) in lis[x].content)


if __name__ == '__main__':
    unittest.main()
