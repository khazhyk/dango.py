import unittest

from dango.plugins.common import utils

class TestWeirdEscapes(unittest.TestCase):

    def test_idk(self):
        self.assertEqual(b"hello world", "hello world".encode("ascii", "escape-invis"))

    def test_the_big_deal(self):
        self.assertEqual(rb"hello\u200bworld", "hello\u200bworld".encode("ascii", "escape-invis"))

    def test_the_biggest_deal(self):
        self.assertEqual("hello\\u200b\U0001f361world".encode("utf8"), "hello\u200b\U0001f361world".encode("ascii", "escape-invis"))

if __name__ == "__main__":
    unittest.main()
