import unittest

from framework import parse

BLOCK = """INSTRUMENTATION_STATUS: class=a.B
INSTRUMENTATION_STATUS: current={n}
INSTRUMENTATION_STATUS: numtests={total}
INSTRUMENTATION_STATUS: stream=
a.B:
INSTRUMENTATION_STATUS: test={test}
INSTRUMENTATION_STATUS_CODE: {code}
"""


def block(test, code, n=1, total=2):
    return BLOCK.format(test=test, code=code, n=n, total=total)


END = "INSTRUMENTATION_RESULT: stream=\nOK (2 tests)\n\nINSTRUMENTATION_CODE: -1\n"


class ParseTest(unittest.TestCase):
    def test_pass_and_failure(self):
        run = parse(block("t1", 1) + block("t1", 0) + block("t2", 1, 2) + block("t2", -2, 2) + END)
        self.assertEqual({"a.B#t1": "pass", "a.B#t2": "fail"}, run.tests)
        self.assertEqual([], run.problems)

    def test_crash_mid_test(self):
        run = parse(block("t1", 1) + block("t1", 0) + block("t2", 1, 2))
        self.assertEqual("fail", run.tests["a.B#t2"])
        self.assertIn("no INSTRUMENTATION_CODE: -1", run.problems)

    def test_no_tests(self):
        run = parse("INSTRUMENTATION_RESULT: stream=\nOK (0 tests)\nINSTRUMENTATION_CODE: -1\n")
        self.assertEqual(["no tests found"], run.problems)

    def test_missing_reports(self):
        run = parse(block("t1", 1) + block("t1", 0) + END)
        self.assertEqual(["1 of 2 tests reported"], run.problems)

    def test_uncaught_exception(self):
        # Instrumentation.ExceptionHandler: the stack goes to stderr, then exit 1
        run = parse(block("t1", 1) + "INSTRUMENTATION_RESULT: shortMsg=INSTRUMENTATION_STATUS_CODE: -1\n")
        self.assertIn("aborted by an uncaught exception (stack in stderr)", run.problems)
        self.assertIn("no INSTRUMENTATION_CODE: -1", run.problems)

    def test_runner_abort(self):
        run = parse(block("t1", 1) + "INSTRUMENTATION_STATUS: shortMsg=ugly hack: Test run aborted\n"
                    "INSTRUMENTATION_STATUS_CODE: -1\n" + END)
        self.assertIn("aborted: ugly hack: Test run aborted", run.problems)

    def test_failure_stack(self):
        failed = block("t1", -2).replace("INSTRUMENTATION_STATUS: stream=\n",
                                         "INSTRUMENTATION_STATUS: stack=junit.framework.AssertionFailedError\n"
                                         "\tat a.B.t1(B.java:3)\nINSTRUMENTATION_STATUS: stream=\n")
        run = parse(block("t1", 1) + failed + block("t2", 1, 2) + block("t2", 0, 2) + END)
        self.assertEqual({"a.B#t1": "fail", "a.B#t2": "pass"}, run.tests)

    def test_stray_stdout_line(self):
        # ATL prints lines like this from the main thread while a block is open
        stray = block("t1", 0).replace("INSTRUMENTATION_STATUS_CODE", "window: frame #ff1a1b20\nINSTRUMENTATION_STATUS_CODE")
        run = parse(block("t1", 1) + stray + block("t2", 1, 2) + block("t2", 0, 2) + END)
        self.assertEqual({"a.B#t1": "pass", "a.B#t2": "pass"}, run.tests)
        self.assertEqual([], run.problems)


if __name__ == "__main__":
    unittest.main()
