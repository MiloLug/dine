"""The ios target's shutdown, LldbHost's kill and AgentUi's verdicts, without a phone or lldb."""

import importlib
import sys
import unittest
from unittest import mock

from dine.dbg.targets import agentui, ios
from dine.dbg.targets.base import CmdError
from dine.paths import DineError


class StubHost:
    def __init__(self, state="none", wedged=None):
        self.state, self.wedged, self.closed = state, wedged, False

    def kill(self):
        raise CmdError("kill: lost connection")

    def detach(self):
        return "detached"

    def close(self):
        self.closed = True


class IosShutdownTest(unittest.TestCase):
    def shutdown(self, host, kill_app, kill_error=None):
        target = ios.IosTarget(mock.Mock(), "Dine")
        target.host = host
        with mock.patch.object(ios.ios, "processes", return_value=[{"pid": 7}]), \
                mock.patch.object(ios.ios, "kill", side_effect=kill_error) as kill:
            try:
                return target.shutdown(kill_app), kill
            finally:
                self.assertTrue(host.closed)

    def test_kill_app_unattached(self):
        for state in ("none", "detached", "exited"):
            text, kill = self.shutdown(StubHost(state), True)
            kill.assert_called_once_with(7)
            self.assertIn("killed pid 7", text)

    def test_kill_app_with_lldb_stuck(self):
        text, kill = self.shutdown(StubHost("running", "attach hung"), True)
        kill.assert_called_once_with(7)
        self.assertIn("lldb is stuck", text)

    def test_unattached_without_the_flag_kills_nothing(self):
        kill = self.shutdown(StubHost(), False)[1]
        kill.assert_not_called()

    def test_a_failed_kill_is_an_error(self):
        with self.assertRaisesRegex(DineError, "no device tunnel"):
            self.shutdown(StubHost(), True, DineError("no device tunnel"))
        with self.assertRaisesRegex(CmdError, "lost connection"):
            self.shutdown(StubHost("running"), True)


class LldbKillTest(unittest.TestCase):
    def host(self, ok: bool, exits: bool):
        with mock.patch.dict(sys.modules, {"lldb": mock.MagicMock()}):
            sys.modules.pop("dine.dbg.lldbhost", None)
            lldbhost = importlib.import_module("dine.dbg.lldbhost")
        host = lldbhost.LldbHost.__new__(lldbhost.LldbHost)
        host.process = mock.Mock()
        host.process.Kill.return_value.Success.return_value = ok
        host.process.Kill.return_value.GetCString.return_value = "lost connection"
        host.wait_state = lambda cond, timeout: exits
        return host

    def test_kill(self):
        self.assertEqual(self.host(True, True).kill(), "killed the app")
        with self.assertRaisesRegex(CmdError, "lost connection"):
            self.host(False, True).kill()
        with self.assertRaisesRegex(CmdError, "didn't exit"):
            self.host(True, False).kill()


class AgentUiTest(unittest.TestCase):
    def ui(self, result, label="Button"):
        ui = agentui.AgentUi()
        ui._ui, ui._values = [], []
        ui._stopped_at = lambda: None
        self.sent = []

        def request(line, timeout):
            self.sent.append(line)
            labels = [[True, label]]
            if line == "ls":
                return {"labels": labels}
            if line.startswith("settle"):
                return {"labels": labels, "ran": True, "settled": True, "result": result}
            return {"ok": True}
        ui._request = request
        return ui

    def test_activate(self):
        self.assertEqual(self.ui(True).do_ui_activate("Button").splitlines()[0], "activated 'Button'")
        with self.assertRaisesRegex(CmdError, "declined the activation"):
            self.ui(False).do_ui_activate("Button")

    def test_activate_line_quotes_the_label(self):
        self.ui(True, 'say "hi" é').do_ui_activate('say "hi" é')
        self.assertEqual(self.sent[1], 'activate 0 "say \\"hi\\" \\u00e9"')

    def test_insert(self):
        self.assertEqual(self.ui(True).do_ui_insert("Button", "x").splitlines()[0], "inserted 'x' into 'Button'")
        self.assertEqual(self.sent[1], 'insert 0 ["Button", "x"]')
        with self.assertRaisesRegex(CmdError, "takes no text"):
            self.ui(False).do_ui_insert("Button", "x")


class IosRealInputTest(unittest.TestCase):
    SCREEN = {"windows": [{"class": "UIWindow", "level": 0, "key": True, "ctx": 5, "hidden": False,
                           "frame": [0, 0, 390, 844]},
                          {"class": "UITextEffectsWindow", "level": 10, "key": False, "ctx": 0, "hidden": True,
                           "frame": [0, 0, 100, 100]}]}

    def target(self, labels, frames):
        """An ios target whose agent answers `ls` with these labels and frames; `self.sent` records lines."""
        target = ios.IosTarget(mock.Mock(), "Dine")
        target._stopped_at = lambda: None
        self.sent = []

        def request(line, timeout):
            self.sent.append(line)
            if line == "ls":
                return {"labels": [[True, l] for l in labels], "frames": frames}
            if line == "windows":
                return self.SCREEN
            if line.startswith("settle"):
                return {"labels": [[True, l] for l in labels], "frames": frames, "ran": True, "settled": True,
                        "result": True}
            return {"ok": True, "window": "UIWindow", "ctx": 5}
        target._request = request
        return target

    def test_point_after_a_tap_reads_fresh_frames(self):
        target = self.target(["a", "b"], [[0, 0, 10, 10], [100, 200, 50, 20]])
        target._ui = [(True, "a"), (True, "b")]
        target._frames = []
        self.assertEqual(target._point("#1"), ("'b'", (125, 210)))
        self.assertIn("ls", self.sent)

    def test_point_of_offscreen_element_is_refused(self):
        target = self.target(["a"], [[0, -500, 100, 40]])
        with self.assertRaisesRegex(CmdError, "^'a' has no on-screen frame$"):
            target._point("a")
        target = self.target(["a"], [[10, 10, 0, 40]])
        with self.assertRaisesRegex(CmdError, "^'a' has no on-screen frame$"):
            target._point("a")

    def test_point_as_given(self):
        self.assertEqual(self.target([], [])._point("@1,420.5"), ("@1,420.5", (1.0, 420.5)))
        self.assertEqual(self.sent, [])

    def test_tap_sends_a_60ms_gesture_at_the_centre(self):
        target = self.target(["a"], [[10, 20, 100, 40]])
        self.assertEqual(target.do_ui_tap("a").splitlines()[0], "tapped 'a'")
        self.assertIn('gesture {"fingers":[[[60,40,0],[60,40,60]]]}', self.sent)
        self.assertTrue(self.sent[-1].startswith("settle"))
        target.do_ui_tap("@5,6", window=2)
        self.assertIn('gesture {"fingers":[[[5.0,6.0,0],[5.0,6.0,60]]],"window":2}', self.sent)

    def test_drag_between_points_in_its_window(self):
        target = self.target([], [])
        self.assertEqual(target.do_ui_drag("@1,420", "@300,420", ms=250, window=0).splitlines()[0],
                         "dragged @1,420 to @300,420 in 250 ms")
        self.assertIn('gesture {"fingers":[[[1.0,420.0,0],[300.0,420.0,250]]],"window":0}', self.sent)

    def test_drag_duration_is_bounded(self):
        for ms in (0, -1, 10001):
            with self.subTest(ms=ms), self.assertRaisesRegex(CmdError, r"--ms 1\.\.10000"):
                self.target([], []).do_ui_drag("@1,1", "@2,2", ms=ms)

    def test_windows_listing(self):
        self.assertEqual(self.target([], []).do_ui_windows().splitlines(),
                         ["#0 UIWindow level 0 ctx 5 key 0,0 390x844",
                          "#1 UITextEffectsWindow level 10 ctx 0 hidden 0,0 100x100"])


if __name__ == "__main__":
    unittest.main()
