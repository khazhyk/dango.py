import asyncio
import itertools
import random
import unittest

from dango import config
from plugins import database


conf = config.StringConfiguration("""
database:
  dsn: postgresql://@localhost/spootest
""")


def async_test(f):
    def wrapper(*args, **kwargs):
        coro = f(*args, **kwargs)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(coro)
    return wrapper


class TestDatabase(unittest.TestCase):

    @async_test
    async def setUp(self):
        self.db = database.Database(conf.root.add_group("database"))

        async with self.db.acquire() as conn:
            await conn.execute("drop table if exists multi_insert_test")
            await conn.execute(
                "CREATE TABLE multi_insert_test "
                "( id bigint primary key, value bigint )")

    def test_multi_insert_str(self):
        items = [('a', 'b', 'c'), ('d', 'e', 'f')]
        self.assertEqual(
            "($1, $2, $3), ($4, $5, $6)", database.multi_insert_str(items))

    @async_test
    async def test_multi_insert(self):
        items = [(i, random.randint(0, 2 << 32))
                 for i in range(32767//2)]

        async with self.db.acquire() as conn:
            await conn.execute(
                "INSERT INTO multi_insert_test "
                "VALUES %s ON CONFLICT DO NOTHING" % (
                    database.multi_insert_str(items)),
                *itertools.chain(*items))

    @async_test
    async def test_multi_insert_max(self):
        """We can have a max of 32767 arguments."""
        items = [(i, random.randint(0, 2 << 32))
                 for i in range(32767//2 + 1)]

        with self.assertRaises(ValueError):
            async with self.db.acquire() as conn:
                await conn.execute(
                    "INSERT INTO multi_insert_test "
                    "VALUES %s ON CONFLICT DO NOTHING" % (
                        database.multi_insert_str(items)),
                    *itertools.chain(*items))

if __name__ == '__main__':
    unittest.main()
