import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from dine import display, paths


class EnvTest(unittest.TestCase):
    def test_env_points_gdk_at_the_socket_only(self):
        d = object.__new__(display.Display)
        d.socket = Path("/tmp/dine-wl-x/wayland-1")
        env = d.env({"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0", "XDG_RUNTIME_DIR": "/run/user/1000", "A": "b"})
        self.assertEqual(env, {"WAYLAND_DISPLAY": "/tmp/dine-wl-x/wayland-1", "GDK_BACKEND": "wayland",
                               "XDG_RUNTIME_DIR": "/run/user/1000", "A": "b"})

    def test_config_has_no_includes_or_execs(self):
        self.assertNotRegex(display.CONFIG, r"(?m)^\s*(include|exec)\b")


class CheckTest(unittest.TestCase):
    def display(self, status: int) -> "display.Display":
        d = object.__new__(display.Display)
        d.dir = Path(tempfile.mkdtemp(prefix="dinet-"))
        self.addCleanup(shutil.rmtree, d.dir, True)
        d.log = d.dir / "sway.log"
        d.log.write_text("start\n" + "".join(f"line {i}\n" for i in range(30)) + "failed to open the output\n")
        d.proc = subprocess.Popen(["sh", "-c", f"exit {status}"])
        d.proc.wait()
        return d

    def test_an_ended_compositor_raises_with_the_tail_of_its_log(self):
        with self.assertRaises(display.DineError) as caught:
            self.display(3).check()
        text = str(caught.exception)
        self.assertIn("sway exited with 3", text)
        self.assertIn("failed to open the output", text)
        self.assertNotIn("start", text)

    def test_a_running_compositor_passes(self):
        d = self.display(0)
        d.proc = subprocess.Popen(["sleep", "30"])
        self.addCleanup(lambda: (d.proc.kill(), d.proc.wait()))
        d.check()


# the pid of sway, the only child of display's shell
SWAY = "/proc/{pid}/task/{pid}/children"


@unittest.skipUnless(shutil.which("sway"), "no sway")
class HeadlessTest(unittest.TestCase):
    def assertGone(self, pid: int):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            if Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].startswith("Z"):
                return
            time.sleep(0.05)
        self.fail(f"pid {pid} still alive")

    def test_clients_connect_and_close_cleans_up(self):
        with display.headless() as d:
            self.assertEqual(d.socket.parent, d.dir)
            with socket.socket(socket.AF_UNIX) as s:
                s.connect(str(d.socket))
            sway, directory = int(Path(SWAY.format(pid=d.proc.pid)).read_text()), d.dir
        self.assertGone(sway)
        self.assertFalse(directory.exists())

    def test_sway_dies_with_a_killed_owner(self):
        owner = subprocess.Popen([sys.executable, "-c", "import time; from dine import display\n"
                                  "d = display.Display(); print(open(%r.format(pid=d.proc.pid)).read(), d.dir, flush=True)\n"
                                  "time.sleep(30)" % SWAY],
                                 stdout=subprocess.PIPE, text=True,
                                 env={**os.environ, "PYTHONPATH": str(paths.PY)})
        sway, directory = owner.stdout.readline().split()
        owner.send_signal(signal.SIGKILL)
        owner.wait()
        self.assertGone(int(sway))
        shutil.rmtree(directory)
