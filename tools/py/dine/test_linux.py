import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dine import linux
from dine.paths import DineError


class LinuxSmokeTest(unittest.TestCase):
    def test_select(self):
        self.assertEqual([c.name for c in linux.select([])], ["gd", "gd-package", "demo", "demo-480", "loop", "looper", "dialog", "dialog-gtk", "nav", "crash", "views", "views-gtk", "widgets", "lists", "controls", "text", "draw", "draw-gtk", "windows", "windows-gtk", "keyboard", "config"])
        self.assertEqual([c.name for c in linux.select(["looper", "gd"])], ["looper", "gd"])
        with self.assertRaisesRegex(DineError, "no smoke check gtk, x; there are: gd, gd-package, demo, demo-480, loop, looper, dialog, dialog-gtk, nav, crash, views, views-gtk, widgets, lists, controls, text, draw, draw-gtk, windows, windows-gtk, keyboard, config$"):
            linux.select(["gtk", "demo", "x"])

    def test_listing_names_every_check(self):
        self.assertEqual([line.split(":")[0] for line in linux.listing().splitlines()],
                         ["gd", "gd-package", "demo", "demo-480", "loop", "looper", "dialog", "dialog-gtk", "nav", "crash", "views", "views-gtk", "widgets", "lists", "controls", "text", "draw", "draw-gtk", "windows", "windows-gtk", "keyboard", "config"])

    def test_smoke_stops_at_the_first_failure(self):
        ran, lines = [], []
        checks = [linux.Check(n, n, lambda n=n, p=p: ran.append(n) or p)
                  for n, p in (("a", None), ("b", "run.sh: exit status 1\nFAIL: x\nlog: y"), ("c", None))]
        with mock.patch.object(linux, "CHECKS", checks):
            self.assertEqual(linux.smoke([], out=lines.append), 1)
        self.assertEqual(ran, ["a", "b"])
        self.assertTrue(lines[0].startswith("a: ok ("))
        self.assertEqual(lines[1], "b: FAILED (run.sh: exit status 1)\nFAIL: x\nlog: y")

    def test_smoke_closes_the_display_a_check_started(self):
        closed = []
        started = mock.Mock(close=lambda: closed.append(True))

        def check():
            linux._display = started
            return "x: exit status 1"
        with mock.patch.object(linux, "CHECKS", [linux.Check("a", "a", check)]):
            self.assertEqual(linux.smoke([], out=lambda _: None), 1)
        self.assertEqual(closed, [True])
        self.assertIsNone(linux._display)

    def test_smoke_passed_line(self):
        lines = []
        with mock.patch.object(linux, "CHECKS", [linux.Check("a", "a", lambda: None)]):
            self.assertEqual(linux.smoke([], out=lines.append), 0)
        self.assertTrue(lines[-1].startswith("smoke passed: a ("))


class BuildsLockTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.object(linux.paths, "OUT", Path(tmp.name))
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_build_excludes_runs_and_other_builds(self):
        with linux.builds(exclusive=True):
            for exclusive in (False, True):
                with self.assertRaisesRegex(DineError, "Linux builds are"):
                    with linux.builds(exclusive=exclusive):
                        pass

    def test_runs_share_and_keep_a_build_out(self):
        with linux.builds(exclusive=False), linux.builds(exclusive=False):
            with self.assertRaisesRegex(DineError, "in use"):
                with linux.builds(exclusive=True):
                    pass
        with linux.builds(exclusive=True):
            pass


class FreshTest(unittest.TestCase):
    def test_no_build_names_the_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(DineError, "run tools/dine linux build atl"):
                linux.require_fresh(Path(tmp), "tools/dine linux build atl")

    def test_pending_work_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "build.ninja").write_text("rule cp\n  command = cp $in $out\nbuild out: cp in\ndefault out\n")
            Path(tmp, "in").write_text("1")
            with self.assertRaisesRegex(DineError, "behind its sources"):
                linux.require_fresh(Path(tmp), "the build")
            subprocess.run(["ninja", "-C", tmp], check=True, capture_output=True)
            linux.require_fresh(Path(tmp), "the build")
