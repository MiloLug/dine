"""Server commands in-process with the fake target: log scoping and the stale-code warning."""

import importlib.machinery
import importlib.util
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from dine.dbg import session
from dine.dbg.server import Server
from dine.dbg.targets.base import CmdError
from dine.paths import DineError


class ServerLogTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.server = Server("fake", "Dine", Path(tmp.name))
        self.addCleanup(self.server.store.close)

    def call(self, cmd, code=None, **args):
        return self.server.handle({"cmd": cmd, "args": args, "code": code})["text"]

    def launch_with_lines(self):
        store = self.server.store
        store.append("syslog", "line", "NOTICE dev.dine.Dine/library: loaded 1 apps")
        self.call("note", kind="launching", text="launching Dine", mark=True)
        store.append("syslog", "line", "NOTICE dev.dine.Dine/library: loaded 2 apps")
        store.append("syslog", "line", "NOTICE com.apple.UIKit/cache: loaded 7 items")

    def test_listings_start_at_the_last_launch(self):
        self.launch_with_lines()
        out = self.call("log", op="grep", pattern="loaded")
        self.assertIn("since launch #2", out)
        self.assertIn("2 matches", out)
        self.assertNotIn("loaded 1 apps", out)
        self.assertIn("3 matches", self.call("log", op="grep", pattern="loaded", since=0))
        self.assertIn("loaded 1 apps", self.call("log", op="since", since=0))

    def test_app_and_text(self):
        self.launch_with_lines()
        self.assertIn("1 matches", self.call("log", op="grep", pattern="loaded", app=True))
        lines = self.call("log", op="tail", n=1, app=True, text=True).splitlines()
        self.assertEqual(lines[1], "loaded 2 apps")

    def test_wait_exit_follows_a_target_that_watches_exits(self):
        self.server.target.watching_exit = lambda: True
        exits = threading.Timer(0.2, self.server.store.append, ("event", "exited", "pid 9 exited with status 0"))
        exits.start()
        self.addCleanup(exits.cancel)
        resp = self.server.handle({"cmd": "wait", "args": {"exit": True}, "timeout": 5})
        self.assertEqual(resp["code"], 0, resp["text"])
        self.assertIn("matched --exit", resp["text"])

    def test_wait_without_a_process_names_the_targets_way_to_start_one(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        server = Server("gtk", "app.apk", Path(tmp.name))
        self.addCleanup(server.store.close)
        resp = server.handle({"cmd": "wait", "args": {"exit": True}, "timeout": 1})
        self.assertEqual((resp["code"], resp["text"].splitlines()[0]), (1, "ATL isn't running: tools/dine dbg fresh"))

    def test_stale_code_warning(self):
        self.assertTrue(self.call("status", code="older").startswith("warning: the server runs older dbg code"))
        self.assertFalse(self.call("status", code=self.server.code).startswith("warning"))
        self.assertFalse(self.call("status").startswith("warning"))


class RequestTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.server = Server("fake", "Dine", Path(tmp.name))
        self.addCleanup(self.server.store.close)
        self.interrupts = []
        self.server.target.interrupt_command = self.interrupts.append

    def handle(self, cmd, timeout, max_lines=60, **args):
        return self.server.handle({"cmd": cmd, "args": args, "timeout": timeout, "max_lines": max_lines})

    def test_a_commands_own_wait_ends_inside_the_requests(self):
        def step(timeout=30):
            time.sleep(timeout + 0.1)
            return "still running"
        self.server.target.do_step = step
        resp = self.handle("step", 1)
        self.assertEqual((resp["code"], resp["text"], self.interrupts), (0, "still running", []))

    def test_a_reply_within_the_grace_join_reaches_the_client(self):
        def late():
            time.sleep(1.2)
            return "late reply"
        self.server.target.do_late = late
        resp = self.handle("late", 1)
        self.assertEqual((resp["code"], resp["text"]),
                         (0, "late reply\n(`late` timed out after 1s; interrupted: that may be cut short)"))

    def test_any_error_within_the_grace_join_names_the_timeout(self):
        for error, says in ((DineError("no device tunnel"), "no device tunnel"), (RuntimeError("lost"), "RuntimeError: lost")):
            with self.subTest(says):
                def late():
                    time.sleep(1.2)
                    raise error
                self.server.target.do_late = late
                resp = self.handle("late", 1)
                self.assertEqual(resp["code"], 1)
                self.assertRegex(resp["text"], f"timed out after 1s; interrupted: {says}")

    def test_an_error_within_the_grace_join_reaches_the_client(self):
        def late():
            time.sleep(1.2)
            raise CmdError("lldb is stuck in it")
        self.server.target.do_late = late
        resp = self.handle("late", 1)
        self.assertEqual(resp["code"], 1)
        self.assertRegex(resp["text"], "timed out after 1s; interrupted: lldb is stuck in it")

    def test_zero_timeout_is_no_default(self):
        self.handle("syslog_start", 5)
        start = time.monotonic()
        # the thread bounds the test: with the default it waits 30 s
        out = {}
        t = threading.Thread(target=lambda: out.update(self.handle("wait", 0, log=["never"], since="now")), daemon=True)
        t.start()
        t.join(3)
        self.assertEqual(out.get("code"), 2)
        self.assertLess(time.monotonic() - start, 1)

    def test_zero_max_lines_is_no_default(self):
        self.assertTrue(self.handle("status", 5, max_lines=0)["text"].startswith("\u2026 5 more lines"))

    def test_a_failed_shutdown_still_stops_the_server(self):
        def shutdown(kill_app):
            raise DineError("no device tunnel")
        self.server.target.shutdown = shutdown
        resp = self.handle("shutdown", 5, kill_app=True)
        self.assertEqual((resp["code"], self.server.shut_down), (1, True))
        self.assertIn("no device tunnel", resp["text"])


class FingerprintTest(unittest.TestCase):
    def test_tracks_code_not_tests(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(session, "PACKAGE", Path(d)):
            (Path(d) / "server.py").write_text("a")
            (Path(d) / "test_server.py").write_text("a")
            first = session.code_fingerprint()
            (Path(d) / "test_server.py").write_text("ab")
            self.assertEqual(session.code_fingerprint(), first)
            (Path(d) / "cli.py").write_text("client only")
            self.assertEqual(session.code_fingerprint(), first)
            (Path(d) / "server.py").write_text("ab")
            self.assertNotEqual(session.code_fingerprint(), first)

    def test_code_fingerprint_covers_uidrive(self):
        with tempfile.TemporaryDirectory() as d:
            pkg = Path(d) / "uidrive"
            pkg.mkdir()
            for name in ("__init__.py", "client.py", "test_client.py"):
                (pkg / name).write_text("a")
            spec = importlib.machinery.ModuleSpec("uidrive", None, origin=str(pkg / "__init__.py"))
            find_spec = importlib.util.find_spec
            with mock.patch.object(session.importlib.util, "find_spec",
                                   side_effect=lambda name, *a: spec if name == "uidrive" else find_spec(name, *a)):
                first = session.code_fingerprint()
                os.utime(pkg / "test_client.py", ns=(1, 1))
                self.assertEqual(session.code_fingerprint(), first)
                os.utime(pkg / "client.py", ns=(1, 1))
                self.assertNotEqual(session.code_fingerprint(), first)


if __name__ == "__main__":
    unittest.main()
