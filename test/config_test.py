import unittest

from dango import config
from dango import utils


SAMPLE_CONFIG = """
a:
  stuff: 1
"""


class ConfigTest(unittest.TestCase):

    def test_simple(self):
        c = config.StringConfiguration(SAMPLE_CONFIG)
        a = c.root.add_group("a")
        stuff = a.register("stuff", default=2)

        self.assertEquals(stuff(), 1)

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
