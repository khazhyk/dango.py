import asyncio
import copy
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import itertools
import struct
import random
import unittest

from dango import config
import discord
from dango.plugins import database
from dango.plugins import redis
from dango.plugins import tracking


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

def dobject():
    return discord.Object(random.randint(1 << 10, 1 << 58))

def user():
    m = dobject()
    m.name = str(random.randint(1 << 20, 1 << 30))
    return m


def member(user_override=None, guild_override=None):
    m = user_override or user()
    m.guild = guild_override or dobject()
    m.nick = None if random.randint(0, 3) > 2 else str(random.randint(1 << 20, 1 << 30))
    return m

def member_last_seen(m):
    return tracking.LastSeenTuple(
        last_seen=datetime.fromtimestamp(m.id & 0xFFFFFFFF + 3, timezone.utc),
        last_spoke=datetime.fromtimestamp(m.id & 0xFFFFFFFF + 2, timezone.utc),
        server_last_spoke=datetime.fromtimestamp(m.id & 0xFFFFFFFF + 1, timezone.utc)
        )


class TestPresenceTracking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = database.Database(conf.root.add_group("database"))
        cls.rds = redis.Redis(conf.root.add_group("redis"))

    @async_test
    async def setUp(self):
        async with self.db.acquire() as conn:
            await conn.execute("delete from last_seen")
            await conn.execute("delete from last_spoke")
        async with self.rds.acquire() as conn:
            await conn.flushdb()
        self.tracking = tracking.Tracking(None, conf, self.db, self.rds)

    def assertWithinThreshold(self, value, expected, threshold, *args, **kwargs):
        """Assert expected - threshold < value < expected + threshold."""
        self.assertLessEqual(value, expected + threshold, *args, **kwargs)
        self.assertGreaterEqual(value, expected - threshold, *args, **kwargs)

    @async_test
    async def test_never_seen(self):
        m = member()
        self.assertEqual(await self.tracking.last_seen(m), tracking.LastSeenTuple())


    @async_test
    async def test_last_seen(self):
        """Test single last_seen lookup."""
        m = member()
        self.tracking.queue_batch_last_update(m)
        self.tracking.queue_batch_last_spoke_update(m)
        await self.tracking.do_batch_presence_update()
        now = datetime.now(timezone.utc)
        threshold = timedelta(seconds=2)

        last_seen_data = await self.tracking.last_seen(m)

        self.assertWithinThreshold(last_seen_data.last_seen, now, threshold)
        self.assertWithinThreshold(last_seen_data.last_spoke, now, threshold)
        self.assertWithinThreshold(last_seen_data.server_last_spoke, now, threshold)

    @async_test
    async def test_redis_upconvert(self):
        """Move redis to postgresql."""
        def last_seen_deprecated_key(member):
            return "spoo:last_seen:{0.id}".format(member)

        def last_spoke_deprecated_key(member):
            return "spoo:last_spoke:{0.id}".format(member)

        def member_last_spoke_deprecated_key(member):
            return "spoo:last_spoke:{0.id}:{0.guild.id}".format(member)

        def datetime_to_redis(datetime_obj):
            """Pass in datetime in UTC, gives timestamp in UTC"""
            return struct.pack('q', int(datetime_obj.replace(tzinfo=timezone.utc).timestamp() * 1000))

        common_user = user()
        members = [member() for _ in range(1000)] + [member(user_override=common_user) for _ in range(100)]

        async with self.rds.acquire() as conn:
            await conn.mset(dict([
                (
                    last_seen_deprecated_key(m),
                    datetime_to_redis(member_last_seen(m).last_seen))
                for m in members]))
            await conn.mset(dict([
                (
                    last_spoke_deprecated_key(m),
                    datetime_to_redis(member_last_seen(m).last_spoke))
                for m in members]))
            await conn.mset(dict([
                (
                    member_last_spoke_deprecated_key(m),
                    datetime_to_redis(member_last_seen(m).server_last_spoke))
                for m in members]))

        await self.tracking.queue_migrate_redis()
        await self.tracking.do_batch_presence_update()

        for m in members:
            self.assertEqual(await self.tracking.last_seen(m), member_last_seen(m))


    @async_test
    async def test_batch_shared_server_spam(self):
        """Simulate a single member spamming us from 100 shared guilds."""
        u = user()
        members = [member(user_override=u) for _ in range(100)]

    @async_test
    async def test_batch_multiple_updates_one_batch(self):
        """Simulate a single member spamming us with many updates."""
        m = member()

        for _ in range(10):
            now = datetime.now(timezone.utc)
            self.tracking.queue_batch_last_update(m, at_time=now)
            self.tracking.queue_batch_last_spoke_update(m, at_time=now)
        later = datetime.now(timezone.utc) + timedelta(days=1)
        self.tracking.queue_batch_last_update(m, at_time=later)
        await self.tracking.do_batch_presence_update()

        lsd = await self.tracking.last_seen(m)
        self.assertEqual(lsd.last_seen, later)
        self.assertEqual(lsd.last_spoke, now)

    @async_test
    async def test_batch_last_seen_update(self):
        """Simulate batch update of single guild mixed w/ idk whatever.

        Use a single guild so we can use bulk_last_seen
        """
        single_guild = dobject()
        only_members = [member(guild_override=single_guild) for _ in range(10000)]
        members = only_members + [user() for _ in range(10000)]
        for m in members:
            self.tracking.queue_batch_last_spoke_update(m)
            self.tracking.queue_batch_last_update(m)
        now = datetime.now(timezone.utc)
        threshold = timedelta(seconds=2)

        await self.tracking.do_batch_presence_update()

        last_seen_data = await self.tracking.bulk_last_seen(only_members)

        for m, last_seen_data in zip(only_members, last_seen_data):
            self.assertWithinThreshold(last_seen_data.last_seen, now, threshold)
            self.assertWithinThreshold(last_seen_data.last_spoke, now, threshold)
            if hasattr(m, "guild"):
                self.assertWithinThreshold(last_seen_data.server_last_spoke, now, threshold)
            else:
                self.assertEqual(last_seen_data.server_last_spoke, datetime.fromtimestamp(0, timezone.utc))

        async with self.db.acquire() as dbc:
            self.assertEqual(20000, await dbc.fetchval(
                "SELECT count(*) from last_seen"))
            self.assertEqual(30000, await dbc.fetchval(
                "SELECT count(*) from last_spoke"))

    @async_test
    async def test_bulk_last_seen_preserves_order(self):
        """idk."""
        single_guild = dobject()
        members = [member(guild_override=single_guild) for _ in range(10000)]
        for m in members:
            lst = member_last_seen(m)
            self.tracking.queue_batch_last_spoke_update(m, lst.last_spoke)
            self.tracking.queue_batch_last_update(m, lst.last_seen)

        await self.tracking.do_batch_presence_update()

        last_seen_data = await self.tracking.bulk_last_seen(members)

        for m, last_seen_data in zip(members, last_seen_data):
            lst = member_last_seen(m)
            self.assertEqual(last_seen_data.last_seen, lst.last_seen)
            self.assertEqual(last_seen_data.last_spoke, lst.last_spoke)
            self.assertEqual(last_seen_data.server_last_spoke, lst.last_spoke)

    @async_test
    async def test_bulk_last_seen(self):
        """idk."""
        single_guild = dobject()
        members = [member(guild_override=single_guild) for _ in range(10000)]
        for m in members:
            self.tracking.queue_batch_last_spoke_update(m)
            self.tracking.queue_batch_last_update(m)
        now = datetime.now(timezone.utc)
        threshold = timedelta(seconds=2)

        await self.tracking.do_batch_presence_update()

        last_seen_data = await self.tracking.bulk_last_seen(members)

        for m, last_seen_data in zip(members, last_seen_data):
            self.assertWithinThreshold(last_seen_data.last_seen, now, threshold)
            self.assertWithinThreshold(last_seen_data.last_spoke, now, threshold)
            self.assertWithinThreshold(last_seen_data.server_last_spoke, now, threshold)

    @async_test
    async def test_bulk_last_seen_missing_entries(self):
        """idk."""
        single_guild = dobject()
        missing_members = [member(guild_override=single_guild) for _ in range(10000)]

        last_seen_data = await self.tracking.bulk_last_seen(missing_members)

        for m, last_seen_data in zip(missing_members, last_seen_data):
            self.assertEqual(last_seen_data.last_seen, datetime.fromtimestamp(0, timezone.utc))
            self.assertEqual(last_seen_data.last_spoke, datetime.fromtimestamp(0, timezone.utc))
            self.assertEqual(last_seen_data.server_last_spoke, datetime.fromtimestamp(0, timezone.utc))


class TestNameTracking(unittest.TestCase):

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
