import unittest

from grade import outputs_match, verdict


class OutputsMatch(unittest.TestCase):
    def test_trailing_cr_ignored(self):
        self.assertTrue(outputs_match("a\nb\n", "a\r\nb\r\n"))

    def test_other_whitespace_matters(self):
        self.assertFalse(outputs_match("a\n", "a \n"))
        self.assertFalse(outputs_match("a\n", "a"))


class Verdict(unittest.TestCase):
    def test_pass_needs_exit_zero_and_match(self):
        self.assertEqual(verdict(0, True), "pass")
        self.assertEqual(verdict(1, True), "fail")
        self.assertEqual(verdict(0, False), "fail")

    def test_signal_is_a_crash_whatever_the_output(self):
        self.assertEqual(verdict(-6, True), "crash")
        self.assertEqual(verdict(-11, False), "crash")


if __name__ == "__main__":
    unittest.main()
