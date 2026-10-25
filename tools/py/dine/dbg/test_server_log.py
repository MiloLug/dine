"""Server commands in-process with the fake target: log scoping and the stale-code warning."""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from dine.dbg import session
from dine.dbg.server import Server


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


if __name__ == "__main__":
    unittest.main()
