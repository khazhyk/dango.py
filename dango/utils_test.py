import unittest

from dango import utils
import discord


class TestTypeInheritanceMap(unittest.TestCase):

    def test_lookup(self):
        m = utils.TypeMap()

        m.put(discord.abc.User, "something")
        m.put(discord.TextChannel, "something else")
        m.put(discord.Guild, "another thing")

        self.assertEquals("something", m.lookup(discord.abc.User))
        self.assertEquals("something", m.lookup(discord.User))
        self.assertEquals("something", m.lookup(discord.Member))
        self.assertEquals("something else", m.lookup(discord.TextChannel))
        self.assertEquals(None, m.lookup(discord.DMChannel))

    def test_constructed(self):
        m = utils.TypeMap({
            discord.abc.User: "something",
            discord.TextChannel: "something else",
            discord.Guild: "another thing"
            })

        self.assertEquals("something", m.lookup(discord.abc.User))
        self.assertEquals("something", m.lookup(discord.User))
        self.assertEquals("something", m.lookup(discord.Member))
        self.assertEquals("something else", m.lookup(discord.TextChannel))
        self.assertEquals(None, m.lookup(discord.DMChannel))


if __name__ == "__main__":
    unittest.main()
