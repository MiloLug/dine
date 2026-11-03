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


def prefixed(text, package="a"):
    """Instrumentation's lines: each with its app's package."""
    return "".join(f"[{package}] {line}\n" for line in text.splitlines())


def block(test, code, n=1, total=2, package="a"):
    return prefixed(BLOCK.format(test=test, code=code, n=n, total=total), package)


END = prefixed("INSTRUMENTATION_RESULT: stream=\nOK (2 tests)\n\nINSTRUMENTATION_CODE: -1\n")


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
        run = parse(prefixed("INSTRUMENTATION_RESULT: stream=\nOK (0 tests)\nINSTRUMENTATION_CODE: -1\n"))
        self.assertEqual(["no tests found"], run.problems)

    def test_missing_reports(self):
        run = parse(block("t1", 1) + block("t1", 0) + END)
        self.assertEqual(["1 of 2 tests reported"], run.problems)

    def test_uncaught_exception(self):
        # Instrumentation.ExceptionHandler: the stack goes to stderr, then exit 1
        run = parse(block("t1", 1) + prefixed("INSTRUMENTATION_RESULT: shortMsg=java.lang.Error: x\n"
                                                "INSTRUMENTATION_STATUS_CODE: -1\n"))
        self.assertIn("aborted by an uncaught exception: java.lang.Error: x (stack in stderr)", run.problems)
        self.assertIn("no INSTRUMENTATION_CODE: -1", run.problems)

    def test_runner_abort(self):
        run = parse(block("t1", 1) + prefixed("INSTRUMENTATION_STATUS: shortMsg=ugly hack: Test run aborted\n"
                                              "INSTRUMENTATION_STATUS_CODE: -1\n") + END)
        self.assertIn("aborted: ugly hack: Test run aborted", run.problems)

    def test_failure_stack(self):
        failed = block("t1", -2).replace("[a] INSTRUMENTATION_STATUS: stream=\n",
                                         "[a] INSTRUMENTATION_STATUS: stack=junit.framework.AssertionFailedError\n"
                                         "[a] \tat a.B.t1(B.java:3)\n[a] INSTRUMENTATION_STATUS: stream=\n")
        run = parse(block("t1", 1) + failed + block("t2", 1, 2) + block("t2", 0, 2) + END)
        self.assertEqual({"a.B#t1": "fail", "a.B#t2": "pass"}, run.tests)

    def test_stray_stdout_line(self):
        # ATL prints lines like this from the main thread while a block is open
        stray = block("t1", 0).replace("[a] INSTRUMENTATION_STATUS_CODE", "window: frame #ff1a1b20\n[a] INSTRUMENTATION_STATUS_CODE")
        run = parse(block("t1", 1) + stray + block("t2", 1, 2) + block("t2", 0, 2) + END)
        self.assertEqual({"a.B#t1": "pass", "a.B#t2": "pass"}, run.tests)
        self.assertEqual([], run.problems)


class OneVmTest(unittest.TestCase):
    def test_interleaved_apps(self):
        # two apps' blocks, each printed whole, in any order; a stack of b's lands between a's blocks
        a = [block("t1", 1), block("t1", 0), block("t2", 1, 2), block("t2", -2, 2), END]
        b_end = prefixed("INSTRUMENTATION_RESULT: stream=\nOK (2 tests)\n\nINSTRUMENTATION_CODE: -1\n", "b")
        b = [block("t1", 1, package="b"), block("t1", -1, package="b").replace("[b] INSTRUMENTATION_STATUS: stream=\n",
             "[b] INSTRUMENTATION_STATUS: stack=java.lang.Error\n[b] \tat x\n[b] INSTRUMENTATION_STATUS: stream=\n"),
             block("t2", 1, 2, package="b"), block("t2", 0, 2, package="b"), b_end]
        stdout = "".join(x + y for x, y in zip(a, b))
        run_a, run_b = parse(stdout, "a"), parse(stdout, "b")
        self.assertEqual({"a.B#t1": "pass", "a.B#t2": "fail"}, run_a.tests)
        self.assertEqual({"a.B#t1": "fail", "a.B#t2": "pass"}, run_b.tests)
        self.assertEqual([], run_a.problems)
        self.assertEqual([], run_b.problems)

    def test_missing_app(self):
        run = parse(block("t1", 1) + END, "b")
        self.assertIn("no INSTRUMENTATION_CODE: -1", run.problems)


if __name__ == "__main__":
    unittest.main()
