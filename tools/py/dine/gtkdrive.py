"""ATL's gtk build run on the smoke display and driven through its debug agent (dine-atl
src/backends/ui/gtk/agent.c): the checks that feed pointer events, which headless takes from the
cli host's -c."""

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from . import paths
from .dbg import agent
from .dbg.targets.base import CmdError


class Problem(Exception):
    """What the run did wrong, for the check's FAILED line."""


class Session:
    """ATL's gtk build running `activity` of `apk`: its output in `lines`, its agent behind `ask`."""

    def __init__(self, apk: Path, activity: str, env: dict[str, str], build: Path = paths.ATL_GTK_BUILD):
        self.dir = Path(tempfile.mkdtemp(prefix="dine-gtk-"))
        self.socket = self.dir / "agent.sock"
        run_env = dict(env)
        run_env.update(RUN_FROM_BUILDDIR="1", DINE_PREFIX=str(self.dir / "data"), ATL_DBG_AGENT=str(self.socket))
        for name in ("ANDROID_LOG_TAGS", "ATL_DIALOG_ANSWERS"):
            run_env.pop(name, None)
        run_env["ANDROID_PRINTF_LOG"] = "brief"
        self.lines: list[str] = []
        self._lock = threading.Lock()
        self.proc = subprocess.Popen(["./android-translation-layer", str(apk), "-l", activity, "-X", "-Xint"], cwd=build,
                                     env=run_env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, start_new_session=True)
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        with self.proc.stdout:
            for raw in self.proc.stdout:
                with self._lock:
                    self.lines.append(raw.decode(errors="replace").rstrip("\n"))

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(self.proc.pid, sig)
                self.proc.wait(timeout=5)
                break
            except ProcessLookupError:
                break
            except subprocess.TimeoutExpired:
                pass
        self._reader.join(5)
        shutil.rmtree(self.dir, ignore_errors=True)

    def log(self) -> str:
        with self._lock:
            return "\n".join(self.lines)

    def died(self) -> str | None:
        status = self.proc.poll()
        if status is None:
            return None
        how = f"killed by {signal.Signals(-status).name}" if status < 0 else f"exited with status {status}"
        return f"ATL {how}"

    def fail(self, what: str) -> Problem:
        lines = self.log().splitlines()
        # a crash's report is long: its first lines name the signal and the function
        fatal = next((i for i, line in enumerate(lines) if line.startswith("Fatal signal")), None)
        shown = lines[fatal:fatal + 14] if fatal is not None else lines[-25:]
        return Problem(f"{what}\n--- the log's {'crash' if fatal is not None else 'last lines'}:\n" + "\n".join(shown))

    def wait_line(self, pattern: str, since: int = 0, timeout: float = 30) -> int:
        """The index after the first line from `since` on that matches `pattern`."""
        found = re.compile(pattern)
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                for i in range(since, len(self.lines)):
                    if found.search(self.lines[i]):
                        return i + 1
                n = len(self.lines)
            if self.died():
                time.sleep(0.2)  # the reader's last lines
                with self._lock:
                    for i in range(since, len(self.lines)):
                        if found.search(self.lines[i]):
                            return i + 1
                raise self.fail(f"{self.died()} before {pattern!r}")
            if time.monotonic() > deadline:
                raise self.fail(f"no {pattern!r} within {timeout:g} s (after {n} lines)")
            time.sleep(0.05)

    def lines_since(self, since: int) -> list[str]:
        with self._lock:
            return self.lines[since:]

    def mark(self) -> int:
        with self._lock:
            return len(self.lines)

    def ask(self, line: str, timeout: float = 10) -> dict:
        deadline = time.monotonic() + 30
        while not self.socket.exists():
            if self.died() or time.monotonic() > deadline:
                raise self.fail(self.died() or "the agent made no socket")
            time.sleep(0.05)

        def connect(wait: float) -> socket.socket:
            # the agent binds its socket a moment before it listens
            until = time.monotonic() + wait
            while True:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(wait)
                try:
                    sock.connect(str(self.socket))
                except ConnectionRefusedError:
                    sock.close()
                    if time.monotonic() > until:
                        raise
                    time.sleep(0.05)
                    continue
                sock.setblocking(True)
                return sock
        try:
            return agent.request(line, timeout, stopped=lambda: None, connect=connect)
        except (CmdError, OSError) as e:
            raise self.fail(f"the agent: {e} ({self.died() or 'ATL runs'})") from None

    def labels(self) -> agent.Labels:
        return agent.labels_of(self.ask("ls"))

    def wait_label(self, label: str, timeout: float = 30) -> agent.Labels:
        deadline = time.monotonic() + timeout
        while True:
            labels = self.labels()
            if any(l == label for _, l in labels):
                return labels
            if time.monotonic() > deadline:
                raise self.fail(f"no {label!r} on screen; there is: {[l for _, l in labels]}")
            time.sleep(0.2)

    def tap(self, label: str) -> None:
        """The agent's tap on the element `label` of a fresh walk."""
        labels = self.wait_label(label)
        n = agent.pick(labels, label)
        self.ask(f'tap {n} {_json(labels[n][1])}')

    def centre(self, label: str) -> tuple[float, float]:
        labels = self.wait_label(label)
        n = agent.pick(labels, label)
        at = self.ask(f'at {n} {_json(labels[n][1])}')
        return at["x"], at["y"]

    def touch(self, what: str, sequence: int, x: float, y: float) -> bool:
        """One pointer's event; whether the gesture is Java's."""
        return self.ask(f"touch {what} {sequence} {x:.2f} {y:.2f}")["claimed"]


    def key(self, what: str, keyval: int, keycode: int, state: int = 0) -> bool:
        """One key event through the window's key controllers; whether Java took it."""
        return self.ask(f"key {what} {keyval} {keycode} {state}")["handled"]


def _json(text: str) -> str:
    return json.dumps(text)
