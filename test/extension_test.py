import asyncio
import logging
import sys
import unittest

from dango import core

loop = asyncio.get_event_loop()


def setup_logging():
    if hasattr(setup_logging, 'once'):
        return
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "[%(asctime)s][%(name)s][%(levelname)s] %(message)s")

    stdouthandler = logging.StreamHandler(sys.stdout)
    stdouthandler.setFormatter(formatter)
    root.addHandler(stdouthandler)
    setattr(setup_logging, 'once', None)


class PluginDirLoadTest(unittest.TestCase):

    def setUpClass():
        """Print logs to output."""
        setup_logging()

    def setUp(self):
        self.b = core.DangoBot(conf="sample_config.yml")

    def tearDown(self):
        loop.run_until_complete(self.b.close())

    def test_sanity(self):
        b = self.b

        b._loader.watch_spec("extension_test_data.*")

        self.assertIn("UsesCommon", b.cogs)
        self.assertIn("extension_test_data.extension", b.extensions)
        self.assertIn("extension_test_data.common", b.extensions)

    def test_unload_dependants(self):
        b = self.b
        b._loader.watch_spec("extension_test_data.*")

        unloaded_deps = b._loader._register.unload_extension(
            "extension_test_data.common", unload_dependants=True)

        self.assertNotIn("extension_test_data.common", b.extensions)
        self.assertNotIn("extension_test_data.extension", b.extensions)
        self.assertNotIn("UsesCommon", b.cogs)
        self.assertIn("UnrelatedVictim", b.cogs)

    def test_reload_dependants(self):
        b = self.b
        b._loader.watch_spec("extension_test_data.*")

        reloaded_deps = b._loader._register.reload_extension(
            "extension_test_data.common")

        self.assertIn("extension_test_data.common", b.extensions)
        self.assertIn("extension_test_data.extension", b.extensions)
        self.assertIn("UsesCommon", b.cogs)


if __name__ == "__main__":
    unittest.main()
