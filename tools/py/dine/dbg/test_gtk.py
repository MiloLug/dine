"""The gtk target's process handling against a stub ATL; the display is the caller's environment."""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from dine.dbg import agent
from dine.dbg.logstore import LogStore
from dine.dbg.targets import gtk, lldbcmds
from dine.dbg.targets.base import CmdError
from dine.paths import DineError


class LldbEnvTest(unittest.TestCase):
    def test_atl_gets_no_lldb_library_dirs_or_python_path(self):
        lldb = lldbcmds._lldb_libs()
        env = {"LD_LIBRARY_PATH": ":".join([*lldb, "/prefix/lib"]), "PYTHONPATH": "/x", "A": "b"}
        self.assertEqual(lldbcmds.without_lldb_env(env), {"LD_LIBRARY_PATH": "/prefix/lib", "A": "b"})
        self.assertEqual(lldbcmds.without_lldb_env({"LD_LIBRARY_PATH": lldb[0]}), {})


class StubDisplay:
    def env(self):
        return dict(os.environ)


class GtkTargetTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.build = self.tmp / "build"
        self.build.mkdir()
        (self.tmp / "session").mkdir()
        self.store = LogStore(self.tmp / "session")
        self.addCleanup(self.store.close)
        patcher = mock.patch.object(gtk.paths, "ATL_GTK_BUILD", self.build)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.target = gtk.GtkTarget(self.store, str(self.tmp / "app.apk"))
        self.target.display = StubDisplay()
        self.addCleanup(self.target.do_kill)

    def stub(self, body: str):
        atl = self.build / "android-translation-layer"
        atl.write_text(f"#!/bin/sh\n{body}\n")
        atl.chmod(0o755)

    def events(self, kind: str) -> list[dict]:
        return [e for e in self.store.select(0) if e["kind"] == kind]

    def wait_for(self, kind: str) -> dict:
        deadline = time.monotonic() + 5
        while not self.events(kind):
            self.assertLess(time.monotonic(), deadline, f"no {kind} event")
            time.sleep(0.02)
        return self.events(kind)[0]

    def test_output_is_the_log_and_the_exit_an_event(self):
        self.stub('echo "I/x (1): hello $1"; echo "$ATL_DBG_AGENT" >&2; exit 3')
        self.assertRegex(self.target.do_launch(), r"^launched app.apk pid \d+$")
        exited = self.wait_for("exited")
        self.assertEqual(exited["data"]["status"], 3)
        self.assertRegex(exited["text"], r"^pid \d+ exited with status 3$")
        lines = [e["text"] for e in self.store.select(0) if e["src"] == "syslog"]
        self.assertEqual(lines, [f"I/x (1): hello {self.tmp / 'app.apk'}", str(self.target.socket)])
        self.assertEqual(self.target.state()["state"], "exited")
        self.assertFalse(self.target.watching_exit())

    def test_activity_goes_to_atl(self):
        self.stub('echo "$2 $3"; sleep 30')
        self.assertIn(" -l a/B pid ", self.target.do_launch(activity="a/B"))
        deadline = time.monotonic() + 5
        while not [e for e in self.store.select(0) if e["src"] == "syslog"]:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.02)
        self.assertEqual([e["text"] for e in self.store.select(0) if e["src"] == "syslog"], ["-l a/B"])

    def test_kill_logs_the_exit_before_returning(self):
        # a child of its writes the last line after it exited
        self.stub("trap '(sleep 0.3; echo bye) & exit 1' TERM; echo up; sleep 30 & wait")
        self.target.do_launch()
        self.wait_for("line")
        self.assertEqual(self.target.state()["state"], "running")
        self.assertTrue(self.target.watching_exit())
        self.assertRegex(self.target.do_kill(), r"^killed pid \d+$")
        self.assertEqual([e["text"] for e in self.store.select(0) if e["src"] == "syslog"], ["up", "bye"])
        self.assertRegex(self.events("exited")[0]["text"], r"exited with status 1$")
        self.assertEqual(self.target.do_kill(), "ATL isn't running")

    def test_launch_refuses_a_second_run(self):
        self.stub("sleep 30")
        self.target.do_launch()
        with self.assertRaisesRegex(CmdError, "ATL runs already"):
            self.target.do_launch()

    def test_a_closed_connection_after_the_exit_means_the_agent_went_away(self):
        self.stub("exit 0")
        self.target.do_launch()
        with mock.patch.object(gtk.agent, "request", side_effect=agent.AgentClosed("closed")):
            with self.assertRaises(agent.AgentDown):
                self.target._request("settle 3000", 1)

    def test_a_closed_connection_while_running_stays_an_error(self):
        self.stub("sleep 30")
        self.target.do_launch()
        with mock.patch.object(gtk.agent, "request", side_effect=agent.AgentClosed("closed")):
            with self.assertRaises(agent.AgentClosed):
                self.target._request("ls", 1)

    def test_preflight(self):
        with self.assertRaisesRegex(DineError, "no APK"):
            gtk.GtkTarget.preflight(str(self.tmp / "app.apk"))
        (self.tmp / "app.apk").write_bytes(b"")
        with self.assertRaisesRegex(DineError, "no gtk ATL build"):
            gtk.GtkTarget.preflight(str(self.tmp / "app.apk"))
        (self.build / "meson-info").mkdir()
        (self.build / "meson-info/intro-buildoptions.json").write_text(
            json.dumps([{"name": "test_hooks", "value": False}]))
        with self.assertRaisesRegex(DineError, "test_hooks off"):
            gtk.GtkTarget.preflight(str(self.tmp / "app.apk"))
