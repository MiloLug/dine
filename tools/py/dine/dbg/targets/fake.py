"""Scripted stand-in process for testing the server, client and waits without a device.

`dbg fake <log|stop|crash|exit|ui> …` makes the fake process emit that event after `--delay`.
"""

import threading

from .. import agent
from .base import CmdError, Target


class FakeTarget(Target):
    name = "fake"

    def __init__(self, store, app):
        super().__init__(store, app)
        self._state = "none"
        self._location: dict | None = None
        self._syslog = False
        self._ui: list[str] = []
        self._lock = threading.Lock()
        self._interrupt = threading.Event()

    def state(self) -> dict:
        with self._lock:
            s = {"attached": self._state in ("running", "stopped"), "state": self._state}
            if s["attached"]:
                s["pid"] = 1
            if self._state == "stopped":
                s["location"] = _where(self._location)
            return s

    def _set(self, state: str, kind: str, text: str, **data) -> None:
        # Log first, then flip the state: `wait` relies on that order.
        self.store.append("event", kind, text, **data)
        with self._lock:
            self._state = state
            self._location = data.get("location")

    def _need(self, *states: str) -> None:
        if self._state not in states:
            raise CmdError(f"process is {self._state}; needs {'/'.join(states)}")

    def do_attach(self, pid=None, timeout=30):
        if self._state in ("running", "stopped"):
            raise CmdError("already attached: tools/dine dbg detach first")
        self.store.append("event", "attached", f"attached to fake pid {pid or 1}")
        self._set("stopped", "stopped", "stopped after attach", reason="signal", crash=False,
                  location={"function": "mach_msg2_trap"})
        return f"attached to pid {pid or 1}, stopped"

    def do_detach(self):
        self._need("running", "stopped")
        self._set("detached", "detached", "detached")
        return "detached"

    def do_continue(self, thread=None, timeout=10):
        self._need("stopped")
        self._set("running", "running", "running")
        return "running"

    def do_interrupt(self):
        self._need("running")
        self._set("stopped", "stopped", "stopped: interrupted", reason="signal", crash=False,
                  location={"function": "mach_msg2_trap"})
        return "stopped"

    def do_slow(self, seconds: float):
        """A locked command that takes `seconds` unless interrupted, like a stuck lldb call."""
        self._interrupt.clear()
        if self._interrupt.wait(seconds):
            raise CmdError("interrupted")
        return f"slept {seconds:g}s"

    def interrupt_command(self, on: bool) -> None:
        if on:
            self._interrupt.set()

    def do_syslog_start(self, debug=False, subsystem=None):
        self._syslog = True
        return "syslog capture started (fake)"

    def do_syslog_stop(self):
        self._syslog = False
        return "syslog capture stopped"

    def syslog_running(self) -> bool:
        return self._syslog

    def ui_find(self, label: str, timeout: float = 30):
        from .. import match
        m = match.loose(label)
        hits = [e for e in self._ui if m(e)]
        return hits[0] if hits else None

    def _labels(self) -> agent.Labels:
        return [(True, label) for label in self._ui]

    def do_ui_ls(self):
        return agent.listing(self._labels())

    def do_ui_tap(self, arg=None, timeout=10):
        labels = self._labels()
        i = int(arg[1:]) if arg and arg[:1] == "#" and arg[1:].isdigit() else agent.pick(labels, arg or "")
        return f"tapped {labels[i][1]!r}\nscreen: {agent.screen(labels)}"

    def do_ui_back(self, timeout=10):
        return f"went back\nscreen: {agent.screen(self._labels())}"

    def do_ui_action(self, arg=None, timeout=10):
        return f"ran {arg!r}\nscreen: {agent.screen(self._labels())}"

    def do_fake(self, action: str, text: str = "", delay: float = 0.0):
        def fire():
            if action == "log":
                self.store.append("syslog", "line", text)
            elif action == "stop":
                file, _, line = text.rpartition(":")
                loc = {"function": "fake", "file": file, "line": int(line)} if line.isdigit() \
                    else {"function": text}
                self._set("stopped", "stopped", f"stopped at {_where(loc)}", reason="breakpoint",
                          crash=False, location=loc)
            elif action == "crash":
                self._set("stopped", "stopped", f"crashed: {text or 'EXC_BAD_ACCESS'}",
                          reason="exception", crash=True, location={"function": "fake_crash"})
            elif action == "exit":
                self._set("exited", "exited", f"exited with status {text or 0}", status=int(text or 0))
            elif action == "ui":
                self._ui = [t for t in text.split("|") if t]
        if action not in ("log", "stop", "crash", "exit", "ui"):
            raise CmdError(f"unknown fake action {action!r}")
        if delay > 0:
            threading.Timer(delay, fire).start()
            return f"fake {action} in {delay:g}s"
        fire()
        return f"fake {action}"


def _where(loc: dict | None) -> str:
    if not loc:
        return "?"
    if loc.get("file"):
        return f"{loc.get('function', '?')} at {loc['file']}:{loc.get('line', '?')}"
    return loc.get("function", "?")
