import unittest

from dine.dbg.targets.ios import c_literal


class CLiteralTest(unittest.TestCase):
    def test_numbers_pass_through(self):
        for arg in ("0", "42", "-7", "3.5", "-0.25", "0x1f"):
            self.assertEqual(c_literal(arg), arg)

    def test_other_args_are_strings(self):
        self.assertEqual(c_literal("hello"), '"hello"')
        self.assertEqual(c_literal(""), '""')
        self.assertEqual(c_literal("1 2"), '"1 2"')

    def test_escapes(self):
        self.assertEqual(c_literal('say "hi"\\now'), r'"say \"hi\"\\now"')
        self.assertEqual(c_literal("a\nb"), r'"a\nb"')

    def test_non_ascii_is_utf8_in_the_literal(self):
        self.assertEqual(c_literal("Привіт"), '"Привіт"')


if __name__ == "__main__":
    unittest.main()
