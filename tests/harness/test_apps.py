import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import apps
from apps import verdict

RESUMED = b"I/Activity( 1): - onResume - yay!\n"
WANTED = [b"- onResume - yay!", b"atl frames "]


class VerdictTest(unittest.TestCase):
    def test_waits_for_every_marker(self):
        self.assertIsNone(verdict(RESUMED, WANTED, running=True))
        self.assertEqual("pass", verdict(RESUMED + b"atl frames 9 in 5000 ms\n", WANTED, running=True))

    def test_fatal_line_fails_even_after_the_markers(self):
        log = RESUMED + b"atl frames 9\njava.lang.UnsatisfiedLinkError: No implementation found for x\n"
        self.assertEqual("fatal: java.lang.UnsatisfiedLinkError: No implementation found for x",
                         verdict(log, WANTED, running=True))

    def test_uncaught_handler_line_fails(self):
        log = RESUMED + b"hacky_uncaught_exception_handler: Thread: main, Exception: \njava.lang.IllegalStateException: x\n"
        self.assertEqual("fatal: java.lang.IllegalStateException: x", verdict(log, WANTED, running=False))

    def test_exit_fails(self):
        self.assertEqual("exited before 'atl frames '", verdict(RESUMED, WANTED, running=False))
        self.assertEqual("exited", verdict(RESUMED + b"atl frames 1\n", WANTED, running=False))


class RunAppTest(unittest.TestCase):
    """run_app against a stub ATL that records its pid, which is also its process group."""

    def run_stub(self, body: str) -> tuple[str, str | None, int]:
        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp, "android-translation-layer")
            stub.write_text(f"#!/bin/sh\necho $$ > {tmp}/pid\n{body}\n")
            stub.chmod(0o755)
            build = apps.Build("headless", Path(tmp), Path(tmp, "expect.json"), 1)
            app = {"apk": "x.apk", "activity": "a/B", "markers": ["- onResume - yay!"]}
            with mock.patch.object(apps, "TIMEOUT", 1), mock.patch.object(apps, "SETTLE", 0.3):
                _, status, problem = apps.run_app("x", app, Path(tmp, "work"), build)
            return status, problem, int(Path(tmp, "pid").read_text())

    def assertGroupGone(self, pgid: int):
        # the killed background child lingers as a zombie until init reaps it
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.killpg(pgid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        self.fail(f"process group {pgid} still alive")

    def test_markers_pass_and_kill_the_group(self):
        status, problem, pgid = self.run_stub("echo '- onResume - yay!' >&2\nsleep 30 & sleep 30")
        self.assertEqual(("pass", None), (status, problem))
        self.assertGroupGone(pgid)

    def test_a_crash_after_the_markers_fails(self):
        status, problem, _ = self.run_stub("echo '- onResume - yay!'\nsleep 0.1\nexit 3")
        self.assertEqual("fail", status)
        self.assertRegex(problem, r"^exited \(log: ")

    def test_timeout_kills_the_group(self):
        status, problem, pgid = self.run_stub("sleep 30 & sleep 30")
        self.assertEqual("timeout", status)
        self.assertRegex(problem, r"^no '- onResume - yay!' in 1 s")
        self.assertGroupGone(pgid)


if __name__ == "__main__":
    unittest.main()
