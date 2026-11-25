import json
import os
import socket
import subprocess
import sys
import threading
import unittest
from unittest import mock

import uidrive.client
import uidrive.ios

from dine import paths
from dine.dbg import agent
from dine.dbg.targets import agentui
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


class PointTest(unittest.TestCase):
    def test_point_parse(self):
        self.assertEqual(agent.parse_point("@10,20.5"), (10.0, 20.5))
        self.assertIsNone(agent.parse_point("hello"))
        self.assertIsNone(agent.parse_point("#3"))

    def test_point_parse_rejects_junk(self):
        for junk in ("@", "@1", "@a,b", "@nan,1", "@1,inf", "@1,2,3"):
            with self.subTest(junk=junk), self.assertRaisesRegex(CmdError, "@X,Y"):
                agent.parse_point(junk)

    def test_frames_of(self):
        self.assertEqual(agent.frames_of({"frames": [[0, 1.5, 390, 44]]}), [(0.0, 1.5, 390.0, 44.0)])
        # gtk's agent sends no frames
        self.assertEqual(agent.frames_of({"labels": [[True, "a"]]}), [])


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

    # a field's text is its value, apart from its label (the hint)
    def test_values_follow_the_labels(self):
        reply = {"labels": [[True, "fill"], [True, "name"]], "values": [None, "hi"]}
        self.assertEqual(agent.values_of(reply), [None, "hi"])
        self.assertEqual(agent.listing(agent.labels_of(reply), agent.values_of(reply)), "#0 fill\n#1 name = hi")
        self.assertEqual(agent.listing(agent.labels_of(reply)), "#0 fill\n#1 name")
        self.assertEqual(agent.values_of({"labels": []}), [])

    def test_error_reply(self):
        with self.assertRaisesRegex(CmdError, "screen changed"):
            agent.request('activate 1 "x"', 5, connect=self.serve(b'{"error": "the screen changed"}\n'))

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


class AgentDownTest(unittest.TestCase):
    def test_uidrive_agent_down_maps_to_dine_agent_down(self):
        def connect(timeout):
            raise uidrive.client.AgentDown("nothing listens on port 47802")
        with self.assertRaises(agent.AgentDown):
            agent.request("ls", 5, connect=connect)

        class Target(agentui.AgentUi):
            _stopped_at = staticmethod(lambda: None)

            def _request(self, line, timeout):
                return agent.request(line, timeout, connect=connect)

            def _no_agent(self):
                return "no debug agent in Dine: it isn't running"
        with self.assertRaisesRegex(CmdError, "^no debug agent in Dine: it isn't running$"):
            Target().do_ui_ls()


class ConnectTest(unittest.TestCase):
    def connect_raising(self, error: Exception, timeout: float = 3) -> str:
        with mock.patch("uidrive.ios.connect", side_effect=error):
            with self.assertRaises(CmdError) as caught:
                agent._connect(timeout)
        return str(caught.exception)

    def test_connect_errors_keep_their_wording(self):
        self.assertEqual(self.connect_raising(uidrive.ios.NoDevice("no device on usbmux")),
                         "no phone on usbmux: tools/dine ios tunnel status")
        self.assertEqual(self.connect_raising(uidrive.ios.UsbmuxUnreachable("usbmuxd isn't reachable")),
                         "usbmuxd isn't reachable: tools/dine ios tunnel status")
        self.assertEqual(self.connect_raising(uidrive.client.AgentTimeout("no usbmux connection to port 47802 within 3s")),
                         "no usbmux connection to the app within 3s")

    def test_connect_agent_down_is_dine_agent_down(self):
        with mock.patch("uidrive.ios.connect", side_effect=uidrive.client.AgentDown("nothing listens on port 47802")):
            with self.assertRaises(agent.AgentDown):
                agent._connect(3)

    def test_connect_goes_to_uidrives_port(self):
        with mock.patch("uidrive.ios.connect", return_value="sock") as connect:
            self.assertEqual(agent._connect(3), "sock")
        connect.assert_called_once_with(uidrive.ios.DEFAULT_PORT, 3)


if __name__ == "__main__":
    unittest.main()
