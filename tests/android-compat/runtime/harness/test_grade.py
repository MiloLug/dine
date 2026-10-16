import unittest

from grade import outputs_match, strip_shutdown_abort, verdict

DUMP = (
    "*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***\n"
    "Fatal signal 6 (SIGABRT), code -6 (SI_TKILL)\n"
    "OS: Linux 6.18.40.1-microsoft-standard-WSL2 (x86_64)\n"
    "Cmdline: <unset>\n"
    'Thread: 591219 "Shutdown thread"\n'
    "Registers:\n"
    "    rax: 0x0000000000000000\n"
)


class StripShutdownAbort(unittest.TestCase):
    def test_strips_trailing_shutdown_dump(self):
        self.assertEqual(strip_shutdown_abort("hi 0\n" + DUMP), ("hi 0\n", True))

    def test_no_peer_variant(self):
        dump = DUMP.replace('"Shutdown thread"', '"Shutdown thread (no java peer)"')
        self.assertEqual(strip_shutdown_abort("x\n" + dump), ("x\n", True))

    def test_keeps_crash_in_main(self):
        out = "hi\n" + DUMP.replace('"Shutdown thread"', '"main"')
        self.assertEqual(strip_shutdown_abort(out), (out, False))

    def test_clean_output_untouched(self):
        self.assertEqual(strip_shutdown_abort("a\nb\n"), ("a\nb\n", False))


class OutputsMatch(unittest.TestCase):
    def test_trailing_cr_ignored(self):
        self.assertTrue(outputs_match("a\nb\n", "a\r\nb\r\n"))

    def test_other_whitespace_matters(self):
        self.assertFalse(outputs_match("a\n", "a \n"))
        self.assertFalse(outputs_match("a\n", "a"))


class Verdict(unittest.TestCase):
    def test_pass_needs_exit_zero_and_match(self):
        self.assertEqual(verdict(0, False, True, strict=False), "pass")
        self.assertEqual(verdict(1, False, True, strict=False), "fail")
        self.assertEqual(verdict(0, False, False, strict=False), "fail")

    def test_shutdown_abort_tolerated_unless_strict(self):
        self.assertEqual(verdict(134, True, True, strict=False), "pass")
        self.assertEqual(verdict(134, True, True, strict=True), "fail")


if __name__ == "__main__":
    unittest.main()
