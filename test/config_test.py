import os
import tempfile
import unittest

from dango import config
from dango import utils
import ruamel.yaml


SAMPLE_CONFIG = """
a:
  stuff: 1
  unicode: ( ͡° ͜ʖ ͡°)
"""

SAMPLE_COMMENTED_CONFIG="""
# Header comment
a: 1
b:
- one
- two # Comment
# commented: 123
unicode: ( ͡° ͜ʖ ͡°)
"""[1:]


class ConfigTest(unittest.TestCase):

    def test_simple(self):
        c = config.StringConfiguration(SAMPLE_CONFIG)
        a = c.root.add_group("a")
        stuff = a.register("stuff", default=2)

        self.assertEquals(stuff(), 1)

    def test_unicode(self):
        c = config.StringConfiguration(SAMPLE_CONFIG)
        a = c.root.add_group("a")
        stuff = a.register("unicode", default=2)

        self.assertEquals(stuff(), "( ͡° ͜ʖ ͡°)")

    def test_default(self):
        c = config.StringConfiguration("")
        a = c.root.add_group("a")
        stuff = a.register("stuff", default=2)

        self.assertEquals(stuff(), 2)

    def test_default_dump(self):
        c = config.StringConfiguration("")
        a = c.root.add_group("a")
        a.register("stuff", default=2)

        self.assertEquals("a:\n  stuff: 2  # Default value\n", c.dumps())

    def test_invalid_dump(self):
        c = config.StringConfiguration("")
        a = c.root.add_group("a")
        with self.assertRaises(config.InvalidConfig):
            a.register("stuff")

        self.assertEquals("a:\n  stuff:  # Required value\n", c.dumps())

    def test_simple_change(self):
        c = config.StringConfiguration(SAMPLE_CONFIG)
        a = c.root.add_group("a")
        stuff = a.register("stuff", default=2)

        self.assertEquals(stuff(), 1)

        c._data['a']['stuff'] = 3

        self.assertEquals(stuff(), 3)

    def test_class(self):
        class A:
            def __init__(self, config):
                self.stuff = config.register("stuff")

        c = config.StringConfiguration(SAMPLE_CONFIG)
        a_group = c.root.add_group(utils.snakify(A.__name__))

        a = A(a_group)

        self.assertEquals(a.stuff(), 1)

        c._data['a']['stuff'] = 3

        self.assertEquals(a.stuff(), 3)


class FileConfigurationTest(unittest.TestCase):

    def setUp(self):
        self.tmpfile = tempfile.mktemp()

    def tearDown(self):
        os.remove(self.tmpfile)

    def test_roundtrip(self):
        with open(self.tmpfile, 'w', encoding="utf8") as f:
            f.write(SAMPLE_COMMENTED_CONFIG)

        fconf = config.FileConfiguration(self.tmpfile)
        fconf.load()
        fconf.save()

        with open(self.tmpfile, encoding="utf8") as f:
            self.assertEquals(SAMPLE_COMMENTED_CONFIG, f.read())
