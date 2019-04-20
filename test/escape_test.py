import unittest

from dango.plugins.common.utils import escape_invis_chars

class TestWeirdEscapes(unittest.TestCase):

    def test_idk(self):
        self.assertEqual("hello world", escape_invis_chars("hello world"))

    def test_the_big_deal(self):
        self.assertEqual(r"hello\u200bworld", escape_invis_chars("hello\u200bworld"))

    def test_the_biggest_deal(self):
        self.assertEqual("hello\\u200b\U0001f361world", escape_invis_chars("hello\u200b\U0001f361world"))

if __name__ == "__main__":
    unittest.main()
