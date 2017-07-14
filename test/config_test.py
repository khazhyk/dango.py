import unittest

from dango import config


class ConfigTest(unittest.TestCase):

    def test_simple(self):
        c = config.Configuration()

        e = config.ConfigEntry("stuff", int)
        c.add_entry(e)

        c.load_str("stuff: 1")

        self.assertEquals(e.value, 1)

    def test_class(self):
        class A:
            conf = config.ConfigEntry("stuff", int)

        c = config.Configuration()
        a = A()
        c.add_cog(a)
        c.load_str("a:\n  stuff: 1")

        self.assertEquals(a.conf.value, 1)

    @unittest.skip
    def test_class_multi(self):
        class A:
            conf = config.ConfigEntry("stuff", int)

        c = config.Configuration()
        a = A()
        c.add_cog(a)
        c.load_str("a:\n  stuff: 1")

        d = config.Configuration()
        b = A()
        d.add_cog(b)
        d.load_str("a:\n  stuff: 2")
        self.assertEquals(a.conf.value, 1)
        self.assertEquals(b.conf.value, 2)
