import asyncio
import logging
import sys
import unittest

from dango import core
from dango import dcog

loop = asyncio.get_event_loop()


@dcog()
class A:
    pass


@dcog(depends=["A"])
class B:
    def __init__(self, a):
        self.a = a


@dcog(depends=["B"])
class C:
    def __init__(self, b):
        self.b = b


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


class TestPluginLoading(unittest.TestCase):

    def setUp(self):
        self.b = core.DangoBot()

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
        self.b = core.DangoBot()

    def tearDown(self):
        loop.run_until_complete(self.b.close())

    def test_load(self):
        b = self.b

        b.load_extension("test_data._core_test_extension")

        self.assertIn("A", b.cogs)
        self.assertIn("B", b.cogs)
        self.assertIn("C", b.cogs)
        self.assertEqual(0, len(b._dango_unloaded_cogs))

    def test_load2(self):
        b = self.b

        b.load_extension("test_data._core_test_extension")
        b.load_extension("test_data._core_test_extension2")

        self.assertIn("A", b.cogs)
        self.assertIn("B", b.cogs)
        self.assertIn("C", b.cogs)
        self.assertIn("D", b.cogs)
        self.assertIn("E", b.cogs)
        self.assertEqual(0, len(b._dango_unloaded_cogs))

    def test_unload(self):
        b = self.b

        b.load_extension("test_data._core_test_extension")
        b.unload_extension("test_data._core_test_extension")

        self.assertNotIn("A", b.cogs)
        self.assertNotIn("B", b.cogs)
        self.assertNotIn("C", b.cogs)
        self.assertEqual(0, len(b._dango_unloaded_cogs), b._dango_unloaded_cogs)

    def test_depend_unload(self):
        b = self.b

        b.load_extension("test_data._core_test_extension")
        b.load_extension("test_data._core_test_extension2")

        b.unload_extension("test_data._core_test_extension")

        self.assertNotIn("A", b.cogs)
        self.assertNotIn("B", b.cogs)
        self.assertNotIn("C", b.cogs)
        self.assertNotIn("D", b.cogs)
        self.assertNotIn("E", b.cogs)
        self.assertEqual(2, len(b._dango_unloaded_cogs), b._dango_unloaded_cogs)

    def test_depend_reload(self):
        b = self.b

        b.load_extension("test_data._core_test_extension")
        b.load_extension("test_data._core_test_extension2")

        b.unload_extension("test_data._core_test_extension")
        b.load_extension("test_data._core_test_extension")

        self.assertIn("A", b.cogs)
        self.assertIn("B", b.cogs)
        self.assertIn("C", b.cogs)
        self.assertIn("D", b.cogs)
        self.assertIn("E", b.cogs)
        self.assertEqual(0, len(b._dango_unloaded_cogs), b._dango_unloaded_cogs)

    def test_submodule_unload(self):
        """This test case checks we do unload cogs in submodules."""
        b = self.b

        b.load_extension("test_data._recursive_test_extension")

        self.assertIn("InModule", b.cogs)
        self.assertIn("SubModule", b.cogs)

        b.unload_extension("test_data._recursive_test_extension")

        self.assertNotIn("InModule", b.cogs)
        self.assertNotIn("SubModule", b.cogs)


class PluginDirLoadTest(unittest.TestCase):

    def setUpClass():
        setup_logging()

    def setUp(self):
        self.b = core.DangoBot()

    def tearDown(self):
        loop.run_until_complete(self.b.close())

    def test_load_folder(self):
        b = self.b

        b.watch_plugin_dir("test_data")

        self.assertIn("InModule", b.cogs)
        self.assertIn("SubModule", b.cogs)
        self.assertIn("A", b.cogs)
        self.assertIn("B", b.cogs)
        self.assertIn("C", b.cogs)
        self.assertIn("D", b.cogs)
        self.assertIn("E", b.cogs)


if __name__ == "__main__":
    unittest.main()
