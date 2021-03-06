import asyncio
import sys
import unittest

from dango import core
from dango import dcog, Cog

from common import setup_logging

loop = asyncio.get_event_loop()


@dcog()
class A(Cog):
    def __init__(self, config):
        pass


@dcog(depends=["A"])
class B(Cog):
    def __init__(self, config, a):
        self.a = a


@dcog(depends=["B"])
class C(Cog):
    def __init__(self, config, b):
        self.b = b


class TestPluginLoading(unittest.TestCase):

    def setUp(self):
        self.b = core.DangoBot(conf="sample_config.yml")

    def tearDown(self):
        loop.run_until_complete(self.b.close())

    def test_depends_loading(self):
        b = self.b

        b.add_cog(A)

        self.assertIn("A", b.cogs)
        b.add_cog(B)
        self.assertIn("B", b.cogs)
        self.assertEqual(0, len(b._dango_unloaded_cogs))

    def test_depends_unloading(self):
        b = self.b

        b.add_cog(A)
        b.add_cog(B)

        b.remove_cog("A")

        self.assertNotIn("A", b.cogs)
        self.assertNotIn("B", b.cogs)
        self.assertIn(B, b._dango_unloaded_cogs.values())

    def test_depends_reloading(self):
        b = self.b

        b.add_cog(A)
        b.add_cog(B)

        b.remove_cog("A")

        self.assertNotIn("A", b.cogs)
        self.assertNotIn("B", b.cogs)
        self.assertIn(B, b._dango_unloaded_cogs.values())

        b.add_cog(A)

        self.assertIn("A", b.cogs)
        self.assertIn("B", b.cogs)
        self.assertEqual(0, len(b._dango_unloaded_cogs))

    def test_nodepends_reloading(self):
        b = self.b

        b.add_cog(A)
        b.add_cog(B)

        b.remove_cog("B")

        self.assertIn("A", b.cogs)
        self.assertNotIn("B", b.cogs)
        self.assertEqual(0, len(b._dango_unloaded_cogs))

        b.remove_cog("A")
        b.add_cog(B)

        self.assertNotIn("A", b.cogs)
        self.assertNotIn("B", b.cogs)
        self.assertIn(B, b._dango_unloaded_cogs.values())

        b.add_cog(A)
        self.assertIn("A", b.cogs)
        self.assertIn("B", b.cogs)
        self.assertEqual(0, len(b._dango_unloaded_cogs))

    def test_recursive_depends(self):
        b = self.b

        b.add_cog(C)
        b.add_cog(A)
        b.add_cog(B)

        self.assertIn("A", b.cogs)
        self.assertIn("B", b.cogs)
        self.assertIn("C", b.cogs)

        b.remove_cog("A")

        self.assertNotIn("A", b.cogs)
        self.assertNotIn("B", b.cogs)
        self.assertNotIn("C", b.cogs)
        self.assertIn(B, b._dango_unloaded_cogs.values())
        self.assertIn(C, b._dango_unloaded_cogs.values())

        b.add_cog(A)
        self.assertIn("A", b.cogs)
        self.assertIn("B", b.cogs)
        self.assertIn("C", b.cogs)
        self.assertEqual(0, len(b._dango_unloaded_cogs))


class TestExtensionLoading(unittest.TestCase):

    def setUpClass():
        setup_logging()

    def setUp(self):
        self.b = core.DangoBot(conf="sample_config.yml")

    def tearDown(self):
        loop.run_until_complete(self.b.close())

    def test_load(self):
        b = self.b

        b.load_extension("test_data.core_test_extension")

        self.assertIn("A", b.cogs)
        self.assertIn("B", b.cogs)
        self.assertIn("C", b.cogs)
        self.assertEqual(0, len(b._dango_unloaded_cogs))

    def test_load2(self):
        b = self.b

        b.load_extension("test_data.core_test_extension")
        b.load_extension("test_data.core_test_extension2")

        self.assertIn("A", b.cogs)
        self.assertIn("B", b.cogs)
        self.assertIn("C", b.cogs)
        self.assertIn("D", b.cogs)
        self.assertIn("E", b.cogs)
        self.assertEqual(0, len(b._dango_unloaded_cogs))

    def test_unload(self):
        b = self.b

        b.load_extension("test_data.core_test_extension")
        b.unload_extension("test_data.core_test_extension")

        self.assertNotIn("A", b.cogs)
        self.assertNotIn("B", b.cogs)
        self.assertNotIn("C", b.cogs)
        self.assertEqual(0, len(b._dango_unloaded_cogs), b._dango_unloaded_cogs)

    def test_depend_unload(self):
        b = self.b

        b.load_extension("test_data.core_test_extension")
        b.load_extension("test_data.core_test_extension2")

        b.unload_extension("test_data.core_test_extension")

        self.assertNotIn("A", b.cogs)
        self.assertNotIn("B", b.cogs)
        self.assertNotIn("C", b.cogs)
        self.assertNotIn("D", b.cogs)
        self.assertNotIn("E", b.cogs)
        self.assertEqual(2, len(b._dango_unloaded_cogs), b._dango_unloaded_cogs)

    def test_depend_reload(self):
        b = self.b

        b.load_extension("test_data.core_test_extension")
        b.load_extension("test_data.core_test_extension2")

        b.unload_extension("test_data.core_test_extension")
        b.load_extension("test_data.core_test_extension")

        self.assertIn("A", b.cogs)
        self.assertIn("B", b.cogs)
        self.assertIn("C", b.cogs)
        self.assertIn("D", b.cogs)
        self.assertIn("E", b.cogs)
        self.assertEqual(0, len(b._dango_unloaded_cogs), b._dango_unloaded_cogs)

    def test_submodule_unload(self):
        """This test case checks we do unload cogs in submodules."""
        b = self.b

        b.load_extension("test_data.recursive_test_extension")

        self.assertIn("InModule", b.cogs)
        self.assertIn("SubModule", b.cogs)

        b.unload_extension("test_data.recursive_test_extension")

        self.assertNotIn("InModule", b.cogs)
        self.assertNotIn("SubModule", b.cogs)

    def test_multiple_extension_unload(self):
        """Tests the case we unload multiple extensions at once, then readd.

        In particular, test that when unloading extensions in strange orders
        we never hold references to cogs in unloaded extensions.
        """
        b = self.b

        b.load_extension("test_data.core_test_extension")
        b.load_extension("test_data.core_test_extension2")

        b.unload_extension("test_data.core_test_extension")
        b.unload_extension("test_data.core_test_extension2")

        b.load_extension("test_data.core_test_extension")
        b.load_extension("test_data.core_test_extension2")

        self.assertIn("A", b.cogs)
        self.assertIn("B", b.cogs)
        self.assertIn("C", b.cogs)
        self.assertIn("D", b.cogs)
        self.assertIn("E", b.cogs)


class PluginDirLoadTest(unittest.TestCase):

    def setUpClass():
        setup_logging()

    def setUp(self):
        self.b = core.DangoBot(conf="sample_config.yml")

    def tearDown(self):
        loop.run_until_complete(self.b.close())

    def test_load_folder(self):
        b = self.b

        b._loader.watch_spec("test_data.*")

        self.assertIn("InModule", b.cogs)
        self.assertIn("SubModule", b.cogs)
        self.assertIn("A", b.cogs)
        self.assertIn("B", b.cogs)
        self.assertIn("C", b.cogs)
        self.assertIn("D", b.cogs)
        self.assertIn("E", b.cogs)


if __name__ == "__main__":
    unittest.main()
