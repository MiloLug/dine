import unittest
from unittest import mock

from dine import linux
from dine.paths import DineError


class LinuxSmokeTest(unittest.TestCase):
    def test_select(self):
        self.assertEqual([c.name for c in linux.select([])], ["gd", "gd-package", "demo", "demo-480", "looper", "dialog", "dialog-gtk", "nav", "crash", "views", "views-gtk", "widgets", "controls", "text", "draw", "draw-gtk"])
        self.assertEqual([c.name for c in linux.select(["looper", "gd"])], ["looper", "gd"])
        with self.assertRaisesRegex(DineError, "no smoke check gtk, x; there are: gd, gd-package, demo, demo-480, looper, dialog, dialog-gtk, nav, crash, views, views-gtk, widgets, controls, text, draw, draw-gtk"):
            linux.select(["gtk", "demo", "x"])

    def test_listing_names_every_check(self):
        self.assertEqual([line.split(":")[0] for line in linux.listing().splitlines()],
                         ["gd", "gd-package", "demo", "demo-480", "looper", "dialog", "dialog-gtk", "nav", "crash", "views", "views-gtk", "widgets", "controls", "text", "draw", "draw-gtk"])

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
