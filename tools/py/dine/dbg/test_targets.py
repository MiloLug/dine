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


if __name__ == "__main__":
    unittest.main()
