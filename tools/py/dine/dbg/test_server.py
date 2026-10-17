"""End to end over the socket with the fake target: tools/dine dbg … as subprocesses."""

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

DINE = Path(__file__).resolve().parents[4] / "tools/dine"


class FakeServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # AF_UNIX paths are capped at ~108 bytes: keep the dir short.
        cls.dir = tempfile.mkdtemp(prefix="dinet-", dir="/tmp")
        cls.env = {**os.environ, "DINE_DBG_DIR": cls.dir}
        cls.dbg("start-server", "--target", "fake", "--timeout", "20", check=0)

    @classmethod
    def tearDownClass(cls):
        cls.dbg("stop-server")
        shutil.rmtree(cls.dir, ignore_errors=True)

    @classmethod
    def dbg(cls, *args, check=None):
        r = subprocess.run([str(DINE), "dbg", *args], env=cls.env, capture_output=True, text=True, timeout=60)
        if check is not None and r.returncode != check:
            raise AssertionError(f"dbg {' '.join(args)} → {r.returncode}\n{r.stdout}{r.stderr}")
        return r

    def test_second_server_refused(self):
        self.assertEqual(self.dbg("start-server", "--target", "fake").returncode, 1)

    def test_wait_requires_syslog(self):
        self.dbg("syslog", "stop", check=0)
        r = self.dbg("wait", "--log", "x", "--timeout", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("syslog start", r.stdout)

    def test_log_wait_and_timeout(self):
        self.dbg("syslog", "start", check=0)
        self.dbg("fake", "log", "loaded 3 apps", "--delay", "0.3", check=0)
        r = self.dbg("wait", "--log", "loaded apps", "--timeout", "5", check=0)
        self.assertIn("loaded 3 apps", r.stdout)
        start = time.monotonic()
        self.dbg("wait", "--log", "never", "--timeout", "0.5", "--since", "now", check=2)
        self.assertLess(time.monotonic() - start, 5)

    def test_stop_continue_race_and_exit(self):
        self.dbg("syslog", "start", check=0)
        self.dbg("attach", check=0)
        self.dbg("continue", check=0)
        self.dbg("fake", "stop", "HelloView.swift:8", check=0)
        self.dbg("wait", "--at", "HelloView.swift:8", "--timeout", "5", check=0)
        self.dbg("continue", check=0)
        self.dbg("fake", "exit", "3", "--delay", "0.3", check=0)
        self.dbg("wait", "--log", "never", "--timeout", "20", check=3)
        self.dbg("detach", check=1)

    def test_locked_command_timeout_is_interrupted(self):
        start = time.monotonic()
        r = self.dbg("fake", "slow", "30", "--timeout", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("timed out after 1s", r.stdout)
        self.assertLess(time.monotonic() - start, 10)
        self.dbg("fake", "slow", "0", check=0)

    def test_interrupt_frees_a_busy_server(self):
        slow = subprocess.Popen([str(DINE), "dbg", "fake", "slow", "30", "--timeout", "40"], env=self.env,
                                stdout=subprocess.PIPE, text=True)
        time.sleep(0.5)
        self.assertIn("busy: `slow`", self.dbg("status", check=0).stdout)
        self.dbg("interrupt", check=0)
        self.assertEqual(slow.wait(10), 1)
        self.dbg("fake", "slow", "0", check=0)

    def test_status_and_log(self):
        self.assertIn("target fake", self.dbg("status", check=0).stdout)
        self.assertIn("events.jsonl", self.dbg("log", "path", check=0).stdout)


class ShutdownTest(unittest.TestCase):
    def test_stop_server_while_busy(self):
        d = tempfile.mkdtemp(prefix="dinet-", dir="/tmp")
        env = {**os.environ, "DINE_DBG_DIR": d}
        run = lambda *a: subprocess.run([str(DINE), "dbg", *a], env=env, capture_output=True, text=True, timeout=60)
        try:
            self.assertEqual(run("start-server", "--target", "fake").returncode, 0)
            slow = subprocess.Popen([str(DINE), "dbg", "fake", "slow", "30", "--timeout", "40"], env=env,
                                    stdout=subprocess.DEVNULL)
            time.sleep(0.5)
            start = time.monotonic()
            r = run("stop-server")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertLess(time.monotonic() - start, 15)
            self.assertEqual(run("status").returncode, 4)
            slow.wait(10)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class NoServerTest(unittest.TestCase):
    def test_exit_4(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as d:
            r = subprocess.run([str(DINE), "dbg", "status"], env={**os.environ, "DINE_DBG_DIR": d},
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 4)


if __name__ == "__main__":
    unittest.main()
