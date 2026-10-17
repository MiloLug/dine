import unittest

from dine.dbg import match


class LooseTest(unittest.TestCase):
    def test_words_in_order_ignoring_case_and_punctuation(self):
        m = match.loose("hello from c++")
        self.assertTrue(m("Hello from C++ (libc++ ok, 3 parts)"))
        self.assertFalse(m("from C++ hello"))

    def test_prefix_and_gaps(self):
        self.assertTrue(match.loose("loaded apps")("library: loaded 3 apps"))
        self.assertTrue(match.loose("hello")("hello++, Button"))
        self.assertFalse(match.loose("apps loaded")("loaded 3 apps"))

    def test_empty_pattern_rejected(self):
        with self.assertRaises(ValueError):
            match.loose("  ,, ")


class LocationTest(unittest.TestCase):
    loc = {"function": "HelloView.init()", "file": "/src/apps/Dine/HelloView.swift", "line": 8}

    def test_file_line(self):
        self.assertTrue(match.location("HelloView.swift:8")(self.loc))
        self.assertFalse(match.location("HelloView.swift:9")(self.loc))

    def test_file_only_and_function(self):
        self.assertTrue(match.location("HelloView.swift")(self.loc))
        self.assertTrue(match.location("HelloView.init")(self.loc))
        self.assertFalse(match.location("dine_hello")(self.loc))


if __name__ == "__main__":
    unittest.main()
