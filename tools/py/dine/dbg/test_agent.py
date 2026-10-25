import json
import os
import socket
import subprocess
import sys
import threading
import unittest

from dine import paths
from dine.dbg import agent
from dine.dbg.targets.base import CmdError

LAUNCHER = [(False, "Toolbar"), (True, "Add App"), (True, "art"), (False, "art"), (True, "hello++"),
            (True, "Apps")]


class ImportTest(unittest.TestCase):
    def test_agent_imports_first(self):
        # a fresh interpreter: in the test run, other modules have loaded the targets already
        r = subprocess.run([sys.executable, "-c", "import dine.dbg.agent"], capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": str(paths.PY)})
        self.assertEqual(r.returncode, 0, r.stderr)


class PickTest(unittest.TestCase):
    def test_loose_and_exact(self):
        self.assertEqual(agent.pick(LAUNCHER, "hello"), 4)
        self.assertEqual(agent.pick(LAUNCHER, "add"), 1)

    def test_element_beats_container_with_the_same_label(self):
        self.assertEqual(agent.pick([(False, "art"), (True, "art")], "art"), 1)

    def test_exact_label_beats_looser_matches(self):
        self.assertEqual(agent.pick([(True, "run hello"), (True, "hello++"), (True, "hello")], "hello"), 2)

    def test_ambiguous_and_missing(self):
        with self.assertRaisesRegex(CmdError, "ambiguous"):
            agent.pick([(True, "run hello"), (True, "run https")], "run")
        with self.assertRaisesRegex(CmdError, "no element matches 'nope'"):
            agent.pick(LAUNCHER, "nope")

    def test_listing_keeps_indexes_and_drops_repeats(self):
        self.assertEqual(agent.listing(LAUNCHER).splitlines(),
                         ["#0 Toolbar", "#1 Add App", "#2 art", "#4 hello++", "#5 Apps"])
        self.assertEqual(agent.screen(LAUNCHER), "Toolbar | Add App | art | hello++ | Apps")


class RequestTest(unittest.TestCase):
    def serve(self, reply: bytes | None):
        """A connect() whose peer reads one line and sends `reply` (None: never answers)."""
        ours, theirs = socket.socketpair()
        self.addCleanup(theirs.close)

        def peer():
            buf = b""
            while not buf.endswith(b"\n"):
                buf += theirs.recv(100)
            self.got = buf
            if reply is not None:
                theirs.sendall(reply)
                theirs.close()
        threading.Thread(target=peer, daemon=True).start()
        return lambda timeout: ours

    def test_reply(self):
        r = agent.request("ls", 5, connect=self.serve(json.dumps({"labels": [[True, "art"]]}).encode() + b"\n"))
        self.assertEqual(self.got, b"ls\n")
        self.assertEqual(agent.labels_of(r), [(True, "art")])

    def test_error_reply(self):
        with self.assertRaisesRegex(CmdError, "screen changed"):
            agent.request('tap 1 "x"', 5, connect=self.serve(b'{"error": "the screen changed"}\n'))

    def test_closed_without_reply(self):
        with self.assertRaisesRegex(CmdError, "closed the connection"):
            agent.request("ls", 5, connect=self.serve(b""))

    def test_stop_ends_the_wait(self):
        stops = iter([None, None, "HelloView.body.getter at HelloView.swift:23"])
        r = agent.request("settle 3000", 5, stopped=lambda: next(stops), connect=self.serve(None))
        self.assertEqual(r, {"stopped": "HelloView.body.getter at HelloView.swift:23"})

    def test_timeout(self):
        with self.assertRaisesRegex(CmdError, "didn't answer `settle`"):
            agent.request("settle 3000", 0.3, connect=self.serve(None))


if __name__ == "__main__":
    unittest.main()
