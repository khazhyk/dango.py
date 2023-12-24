import asyncio
import sys
import unittest

from dango import core
from common import setup_logging

loop = asyncio.get_event_loop()



def async_test(f):
    def wrapper(*args, **kwargs):
        coro = f(*args, **kwargs)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(coro)
    return wrapper


class PluginDirLoadTest(unittest.TestCase):

    def setUpClass():
        """Print logs to output."""
        setup_logging()

    def setUp(self):
        self.b = core.DangoBot(conf="sample_config.yml")

    def tearDown(self):
        loop.run_until_complete(self.b.close())

    @async_test
    async def test_sanity(self):
        b = self.b

        await b._loader.watch_spec("extension_test_data.*")

        self.assertIn("UsesCommon", b.cogs)
        self.assertIn("extension_test_data.extension", b.extensions)
        self.assertIn("extension_test_data.common", b.extensions)

    @async_test
    async def test_unload_dependants(self):
        b = self.b
        await b._loader.watch_spec("extension_test_data.*")

        unloaded_deps = await b._loader._register.unload_extension(
            "extension_test_data.common", unload_dependants=True)

        self.assertNotIn("extension_test_data.common", b.extensions)
        self.assertNotIn("extension_test_data.extension", b.extensions)
        self.assertNotIn("UsesCommon", b.cogs)
        self.assertIn("UnrelatedVictim", b.cogs)

    @async_test
    async def test_reload_dependants(self):
        b = self.b
        await b._loader.watch_spec("extension_test_data.*")

        reloaded_deps = await b._loader._register.reload_extension(
            "extension_test_data.common")

        self.assertIn("extension_test_data.common", b.extensions)
        self.assertIn("extension_test_data.extension", b.extensions)
        self.assertIn("UsesCommon", b.cogs)


if __name__ == "__main__":
    unittest.main()
