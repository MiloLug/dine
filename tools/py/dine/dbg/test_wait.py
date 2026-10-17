import tempfile
import threading
import time
import unittest
from pathlib import Path

from dine.dbg import wait
from dine.dbg.logstore import LogStore


class WaitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LogStore(Path(self.tmp.name))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def later(self, delay, *event, **data):
        threading.Timer(delay, lambda: self.store.append(*event, **data)).start()

    def test_log_match_after_since(self):
        self.store.append("syslog", "line", "loaded 3 apps")
        since = self.store.cursor
        self.later(0.1, "syslog", "line", "loaded 4 apps")
        out = wait.run(self.store, [wait.log_cond("loaded apps")], since, 2)
        self.assertEqual(out.code, wait.OK)
        self.assertIn("loaded 4 apps", out.text)

    def test_event_before_wait_but_after_since_is_seen(self):
        since = self.store.cursor
        self.store.append("event", "stopped", "stopped", location={"file": "a/HelloView.swift", "line": 8})
        out = wait.run(self.store, [wait.stop_cond("HelloView.swift:8")], since, 1)
        self.assertEqual(out.code, wait.OK)

    def test_replayed_stop_and_exit_are_history(self):
        self.store.append("event", "stopped", "stopped after attach", crash=False, location={})
        self.store.append("event", "exited", "exited with status 0", status=0)
        self.store.set_mark()
        self.store.append("syslog", "line", "loaded 3 apps")
        out = wait.run(self.store, [wait.log_cond("loaded apps")], 0, 1)
        self.assertEqual(out.code, wait.OK)
        out = wait.run(self.store, [wait.log_cond("never")], 0, 0.3)
        self.assertEqual(out.code, wait.TIMEOUT)

    def test_exit_between_action_and_wait_ends_it(self):
        self.store.set_mark()
        self.store.append("event", "exited", "exited with status 3", status=3)
        out = wait.run(self.store, [wait.log_cond("never")], self.store.mark, 5, grace=0.1)
        self.assertEqual(out.code, wait.EXITED)

    def test_log_line_right_after_stop_still_matches(self):
        self.later(0.05, "event", "stopped", "stopped", crash=False, location={})
        self.later(0.3, "syslog", "line", "about to stop")
        out = wait.run(self.store, [wait.log_cond("about to")], self.store.cursor, 5)
        self.assertEqual(out.code, wait.OK)

    def test_events_during_ui_poll_are_not_skipped(self):
        def slow_poll(left):
            self.store.append("event", "exited", "exited with status 1", status=1)
            return None
        start = time.monotonic()
        out = wait.run(self.store, [wait.ui_cond("x", slow_poll)], 0, 5, poll_every=0.05)
        self.assertEqual(out.code, wait.EXITED)
        self.assertLess(time.monotonic() - start, 3)

    def test_syslog_end_stops_log_waits(self):
        self.later(0.1, "event", "syslog-ended", "syslog capture ended (exit 1)")
        start = time.monotonic()
        out = wait.run(self.store, [wait.log_cond("never")], 0, 10, grace=0.1)
        self.assertEqual(out.code, wait.BLOCKED)
        self.assertLess(time.monotonic() - start, 3)

    def test_timeout_reports_recent_events(self):
        self.store.append("syslog", "line", "something else")
        start = time.monotonic()
        out = wait.run(self.store, [wait.log_cond("never")], 0, 0.3)
        self.assertEqual(out.code, wait.TIMEOUT)
        self.assertLess(time.monotonic() - start, 1.5)
        self.assertIn("something else", out.text)

    def test_timeout_points_at_match_before_since(self):
        self.store.append("syslog", "line", "loaded 3 apps")
        since = self.store.cursor
        out = wait.run(self.store, [wait.log_cond("loaded apps")], since, 0.2)
        self.assertEqual(out.code, wait.TIMEOUT)
        self.assertIn("log show 1", out.text)

    def test_exit_fails_fast(self):
        self.later(0.1, "event", "exited", "exited with status 1", status=1)
        start = time.monotonic()
        out = wait.run(self.store, [wait.log_cond("never")], 0, 10)
        self.assertEqual(out.code, wait.EXITED)
        self.assertLess(time.monotonic() - start, 2)

    def test_crash_matches_exit_condition(self):
        self.later(0.1, "event", "stopped", "crashed", crash=True, location={})
        out = wait.run(self.store, [wait.exit_cond()], 0, 2)
        self.assertEqual(out.code, wait.OK)

    def test_unmatched_stop_blocks(self):
        self.later(0.1, "event", "stopped", "stopped", crash=False, location={"function": "other"})
        out = wait.run(self.store, [wait.stop_cond("HelloView.swift")], 0, 5)
        self.assertEqual(out.code, wait.BLOCKED)

    def test_parked_process_blocks_at_once(self):
        start = time.monotonic()
        out = wait.run(self.store, [wait.log_cond("x")], 0, 5, parked=lambda: "main at a.c:1", grace=0.1)
        self.assertEqual(out.code, wait.BLOCKED)
        self.assertLess(time.monotonic() - start, 1)

    def test_all_needs_every_condition(self):
        self.later(0.1, "syslog", "line", "first")
        self.later(0.3, "syslog", "line", "second")
        out = wait.run(self.store, [wait.log_cond("first"), wait.log_cond("second")], 0, 2, need_all=True)
        self.assertEqual(out.code, wait.OK)
        self.assertIn("second", out.text)

    def test_ui_poll(self):
        found = []
        threading.Timer(0.2, lambda: found.append("hello++, Button")).start()
        out = wait.run(self.store, [wait.ui_cond("hello", lambda left: found[0] if found else None)], 0, 3,
                       poll_every=0.05)
        self.assertEqual(out.code, wait.OK)
        self.assertIn("hello++", out.text)


if __name__ == "__main__":
    unittest.main()
