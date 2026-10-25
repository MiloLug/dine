"""A hidden display for ATL's gtk build: headless sway on a socket of its own, so gtk runs open
nothing on WSLg."""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from .paths import DineError

# No includes: Arch's /etc/sway/config.d pushes WAYLAND_DISPLAY into the systemd user manager and
# D-Bus activation. Floating windows keep ATL's own size, as on WSLg.
CONFIG = """\
output HEADLESS-1 mode 1920x1080 scale 1
xwayland disable
swaybg_command -
for_window [all] floating enable
default_border none
default_floating_border none
"""
STARTUP = 5


class Display:
    """A running compositor. Start it from a thread that outlives it: its pdeathsig fires when the
    starting thread exits."""

    def __init__(self):
        if not shutil.which("sway"):
            raise DineError("no sway: paru -S sway grim (docs/first-run.md)")
        # Its own runtime dir under /tmp: no other compositor's wayland-N lands there, and a socket
        # path over 108 bytes can't bind
        self.dir = Path(tempfile.mkdtemp(prefix="dine-wl-", dir="/tmp"))
        config = self.dir / "sway.conf"
        config.write_text(CONFIG)
        env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY")}
        env.update(XDG_RUNTIME_DIR=str(self.dir), WLR_BACKENDS="headless", WLR_RENDERER="pixman")
        self.log = self.dir / "sway.log"
        # sway has file capabilities, and exec clears the parent-death signal for those: a shell holds
        # it and passes it on
        with open(self.log, "wb") as out:
            self.proc = subprocess.Popen(["setpriv", "--pdeathsig", "TERM", "sh", "-c",
                                          'sway -c "$1" & trap "kill $!" TERM; wait', "sh", str(config)],
                                         env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                         start_new_session=True)
        try:
            self.socket = self._wait_socket()
        except BaseException:
            self.close()
            raise

    def _wait_socket(self) -> Path:
        deadline = time.monotonic() + STARTUP
        while time.monotonic() < deadline:
            sockets = [p for p in self.dir.glob("wayland-*") if p.suffix != ".lock"]
            if sockets:
                return sockets[0]
            if self.proc.poll() is not None:
                raise DineError(f"sway exited with {self.proc.returncode}:\n{self.log.read_text(errors='replace')}")
            time.sleep(0.05)
        raise DineError(f"sway made no socket in {STARTUP} s:\n{self.log.read_text(errors='replace')}")

    def env(self, base: dict[str, str] | None = None) -> dict[str, str]:
        """`base` (default: ours) set up for this display. The real XDG_RUNTIME_DIR stays: D-Bus and
        pulse live there."""
        # GDK falls back to X11, WSLg's :0, when it can't reach the Wayland socket
        env = {k: v for k, v in (os.environ if base is None else base).items() if k != "DISPLAY"}
        env.update(WAYLAND_DISPLAY=str(self.socket), GDK_BACKEND="wayland")
        return env

    def windows(self, pid: int) -> list[dict]:
        """`rect`s ({x, y, width, height} on the output) of the process's windows, dialogs included."""
        ipc = next(self.dir.glob("sway-ipc.*.sock"), None)
        if ipc is None:
            raise DineError(f"no sway IPC socket in {self.dir}")
        r = subprocess.run(["swaymsg", "-s", str(ipc), "-r", "-t", "get_tree"], capture_output=True, text=True,
                           timeout=10)
        if r.returncode:
            raise DineError(f"swaymsg get_tree: {r.stderr.strip()}")
        found = []

        def walk(node):
            if node.get("pid") == pid:
                found.append(node["rect"])
            for child in node.get("nodes", []) + node.get("floating_nodes", []):
                walk(child)
        walk(json.loads(r.stdout))
        return found

    def screenshot(self, path: Path, pid: int | None = None) -> None:
        """A PNG of the output, cropped to the process's windows when it has some."""
        rects = self.windows(pid) if pid else []
        crop = []
        if rects:
            x0, y0 = min(r["x"] for r in rects), min(r["y"] for r in rects)
            x1 = max(r["x"] + r["width"] for r in rects)
            y1 = max(r["y"] + r["height"] for r in rects)
            crop = ["-g", f"{x0},{y0} {x1 - x0}x{y1 - y0}"]
        r = subprocess.run(["grim", *crop, str(path)], env=self.env(), capture_output=True, text=True, timeout=30)
        if r.returncode:
            raise DineError(f"grim: {r.stderr.strip() or f'exit status {r.returncode}'}")

    def close(self) -> None:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(self.proc.pid, sig)
            except ProcessLookupError:
                break
            try:
                self.proc.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                pass
        shutil.rmtree(self.dir, ignore_errors=True)


@contextmanager
def headless():
    """A Display for the main thread's `with`: SIGTERM and SIGHUP become an exit, so it closes."""
    handlers = {sig: signal.signal(sig, lambda signum, _: sys.exit(128 + signum))
                for sig in (signal.SIGTERM, signal.SIGHUP)}
    try:
        d = Display()
        try:
            yield d
        finally:
            d.close()
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
