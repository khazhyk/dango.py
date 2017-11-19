import asyncio
import copy
import random
import unittest

from dango import config
import discord
from plugins import database
from plugins import redis
from plugins import tracking


conf = config.StringConfiguration("""
database:
  dsn: postgresql://@localhost/spootest
redis:
  db: 5
""")


def async_test(f):
    def wrapper(*args, **kwargs):
        coro = f(*args, **kwargs)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(coro)
    return wrapper


def user():
    m = discord.Object(random.randint(1 << 10, 1 << 58))
    m.name = str(random.randint(1 << 20, 1 << 30))
    return m


def member():
    m = user()
    m.guild = discord.Object(random.randint(1 << 10, 1 << 58))
    m.nick = None if random.randint(0, 3) > 2 else str(random.randint(1 << 20, 1 << 30))
    return m


class TestTracking(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db = database.Database(conf.root.add_group("database"))
        cls.rds = redis.Redis(conf.root.add_group("redis"))

    @async_test
    async def setUp(self):
        async with self.db.acquire() as conn:
            await conn.execute("delete from namechanges")
            await conn.execute("delete from nickchanges")
        async with self.rds.acquire() as conn:
            await conn.flushdb()
        self.tracking = tracking.Tracking(None, conf, self.db, self.rds)

    async def red_name(self, rdc, m):
        res = await rdc.get(tracking.name_key(m))
        if res:
            return tracking.name_from_redis(res)

    async def db_name(self, dbc, m):
        res = await dbc.fetchval(
            "select name from namechanges where id = $1 "
            "order by idx desc limit 1", str(m.id))
        if res:
            return res.decode('utf8')

    @async_test
    async def test_update_first(self):
        m = member()
        await self.tracking.update_name_change(m)

        async with self.db.acquire() as dbc, self.rds.acquire() as rdc:
            self.assertEqual(m.name, await self.red_name(rdc, m))
            self.assertEqual(m.name, await self.db_name(dbc, m))

    @async_test
    async def test_repop_redis_name_unchanged(self):
        m = member()
        await self.tracking.update_name_change(m)

        async with self.db.acquire() as dbc, self.rds.acquire() as rdc:
            await rdc.flushdb()

            self.assertEqual(None, await self.red_name(rdc, m))
            self.assertEqual(m.name, await self.db_name(dbc, m))

            await self.tracking.update_name_change(m)

            self.assertEqual(m.name, await self.red_name(rdc, m))
            self.assertEqual(m.name, await self.db_name(dbc, m))
            self.assertEqual(1, await dbc.fetchval(
                "select count(*) from namechanges"))

    @async_test
    async def test_repop_redis_on_lookup(self):
        m = member()
        await self.tracking.update_name_change(m)

        async with self.rds.acquire() as rdc:
            await rdc.flushdb()
            self.assertEqual(None, await self.red_name(rdc, m))
            self.assertEqual(m.name, await self.tracking._last_username(m))
            self.assertEqual(m.name, await self.red_name(rdc, m))

    @async_test
    async def test_pop_redis_on_miss(self):
        m = member()

        async with self.rds.acquire() as rdc:
            self.assertEqual(None, await rdc.get(tracking.name_key(m)))
            self.assertEqual(None, await self.tracking._last_username(m))
            self.assertEqual(tracking.REDIS_NICK_NONE,
                             await rdc.get(tracking.name_key(m)))

    @async_test
    async def test_name_changed(self):
        m = member()
        await self.tracking.update_name_change(m)

        m.name = "now it's different"
        await self.tracking.update_name_change(m)

        async with self.db.acquire() as dbc, self.rds.acquire() as rdc:
            self.assertEqual(m.name, await self.red_name(rdc, m))
            self.assertEqual(m.name, await self.db_name(dbc, m))
            self.assertEqual(2, await dbc.fetchval(
                "select count(*) from namechanges"))

    @async_test
    async def test_batch_name_update(self):
        members = [member() for _ in range(1000)]
        for m in members:
            self.tracking.queue_batch_names_update(m)

        await self.tracking.do_batch_names_update()

        for m in members:
            self.assertEqual(m.name, await self.tracking._last_username(m))
            self.assertEqual(m.nick, await self.tracking._last_nickname(m))

        async with self.db.acquire() as dbc:
            self.assertEqual(1000, await dbc.fetchval(
                "SELECT count(*) from namechanges"))
            num_nicks = sum(1 for m in members if m.nick)
            self.assertEqual(num_nicks, await dbc.fetchval(
                "SELECT count(*) from nickchanges"))

    @async_test
    async def test_batch_large_name_update(self):
        members = [member() for _ in range(10000)]
        for m in members:
            self.tracking.queue_batch_names_update(m)

        await self.tracking.do_batch_names_update()

        for m in members:
            self.assertEqual(m.name, await self.tracking._last_username(m))
            self.assertEqual(m.nick, await self.tracking._last_nickname(m))

        async with self.db.acquire() as dbc:
            self.assertEqual(10000, await dbc.fetchval(
                "SELECT count(*) from namechanges"))
            num_nicks = sum(1 for m in members if m.nick)
            self.assertEqual(num_nicks, await dbc.fetchval(
                "SELECT count(*) from nickchanges"))

    @async_test
    async def test_batch_name_update_updates_redis(self):
        members = [member() for _ in range(1000)]
        for m in members:
            self.tracking.queue_batch_names_update(m)

        await self.tracking.do_batch_names_update()

        async with self.rds.acquire() as rdc:
            for m in members:
                self.assertIsNotNone(await rdc.get(tracking.name_key(m)))
                self.assertIsNotNone(await rdc.get(tracking.nick_key(m)))

    @async_test
    async def test_batch_name_update_user_double(self):
        m = member()
        self.tracking.queue_batch_names_update(m)
        m_copy = copy.copy(m)
        m_copy.name = "Updated twice!"
        self.tracking.queue_batch_names_update(m_copy)

        await self.tracking.do_batch_names_update()

        self.assertEqual([m_copy.name, m.name], await self.tracking.names_for(m))
        self.assertEqual(m_copy.name, await self.tracking._last_username(m))
        self.assertEqual(m_copy.nick, await self.tracking._last_nickname(m))

    @async_test
    @unittest.skip("soon(tm)")
    async def test_batch_quick_switch(self):
        m = member()
        self.tracking.queue_batch_names_update(m)
        await self.tracking.do_batch_names_update()  # Populate caches
        m_copy1 = copy.copy(m)
        m_copy1.name = "Updated twice!"
        self.tracking.queue_batch_names_update(m_copy1)
        m_copy2 = copy.copy(m)
        self.tracking.queue_batch_names_update(m_copy2)
        m_copy3 = copy.copy(m)
        m_copy3.name = "Updated twice!"
        self.tracking.queue_batch_names_update(m_copy3)

        await self.tracking.do_batch_names_update()

        self.assertEqual([m_copy3.name, m_copy2.name, m_copy1.name, m.name],
                         await self.tracking.names_for(m))
        self.assertEqual(m_copy3.name, await self.tracking._last_username(m))
        self.assertEqual(m_copy3.nick, await self.tracking._last_nickname(m))


if __name__ == '__main__':
    unittest.main()
