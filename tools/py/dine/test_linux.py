import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from dine import linux
from dine.paths import DineError


class LinuxSmokeTest(unittest.TestCase):
    def test_select(self):
        self.assertEqual([c.name for c in linux.select([])], ["gd", "demo", "demo-480", "looper", "dialog", "dialog-gtk", "nav", "views", "views-gtk", "widgets", "controls", "text"])
        self.assertEqual([c.name for c in linux.select(["looper", "gd"])], ["looper", "gd"])
        with self.assertRaisesRegex(DineError, "no smoke check gtk, x; there are: gd, demo, demo-480, looper, dialog, dialog-gtk, nav, views, views-gtk, widgets, controls, text"):
            linux.select(["gtk", "demo", "x"])

    def test_listing_names_every_check(self):
        self.assertEqual([line.split(":")[0] for line in linux.listing().splitlines()],
                         ["gd", "demo", "demo-480", "looper", "dialog", "dialog-gtk", "nav", "views", "views-gtk", "widgets", "controls", "text"])

    def test_smoke_stops_at_the_first_failure(self):
        ran, lines = [], []
        checks = [linux.Check(n, n, lambda n=n, p=p: ran.append(n) or p)
                  for n, p in (("a", None), ("b", "run.sh: exit status 1\nFAIL: x\nlog: y"), ("c", None))]
        with mock.patch.object(linux, "CHECKS", checks):
            self.assertEqual(linux.smoke([], out=lines.append), 1)
        self.assertEqual(ran, ["a", "b"])
        self.assertTrue(lines[0].startswith("a: ok ("))
        self.assertEqual(lines[1], "b: FAILED (run.sh: exit status 1)\nFAIL: x\nlog: y")

    def test_smoke_passed_line(self):
        lines = []
        with mock.patch.object(linux, "CHECKS", [linux.Check("a", "a", lambda: None)]):
            self.assertEqual(linux.smoke([], out=lines.append), 0)
        self.assertTrue(lines[-1].startswith("smoke passed: a ("))


class GdTest(unittest.TestCase):
    """_gd against a stub ATL that records its pid, which is also its process group."""

    def gd(self, body: str) -> tuple[str | None, int]:
        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp, "atl")
            stub.write_text(f"#!/bin/sh\necho $$ > {tmp}/pid\n{body}\n")
            stub.chmod(0o755)
            with mock.patch.dict(os.environ, {"DISPLAY": ":0"}), \
                    mock.patch.object(linux.shutil, "which", lambda _: str(stub)), \
                    mock.patch.object(linux, "LOG_DIR", Path(tmp)), mock.patch.object(linux, "GD_TIMEOUT", 1):
                problem = linux._gd()
            return problem, int(Path(tmp, "pid").read_text())

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

    def test_on_resume_passes_and_kills_the_group(self):
        problem, pgid = self.gd("echo '- onResume - yay!' >&2\nsleep 30 & sleep 30")
        self.assertIsNone(problem)
        self.assertGroupGone(pgid)

    def test_timeout_kills_the_group(self):
        problem, pgid = self.gd("sleep 30 & sleep 30")
        self.assertRegex(problem, r"^no onResume in 1 s; log: ")
        self.assertGroupGone(pgid)

    def test_exit_before_on_resume(self):
        problem, _ = self.gd("exit 3")
        self.assertRegex(problem, r"^exit status 3 before onResume")
