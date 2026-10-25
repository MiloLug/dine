"""Linux gtk target: ATL's gtk build run by the server on its hidden display (display.py), the run's
output as the log, UI through ATL's debug agent (dine-atl src/backends/ui/gtk/agent.c), lldb attached
to it locally."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import threading
from pathlib import Path

from ... import display, paths
from ...paths import DineError
from .. import agent
from .agentui import AgentUi
from .base import CmdError, Target
from .lldbcmds import LldbCommands, lldb_env, without_lldb_env


class GtkTarget(AgentUi, LldbCommands, Target):
    name = "gtk"
    relaunch = "tools/dine dbg fresh"
    capture = "tools/dine dbg fresh"
    no_process = "ATL isn't running: tools/dine dbg fresh"

    @classmethod
    def preflight(cls, app: str) -> None:
        if not Path(app).is_file():
            raise DineError(f"no APK {app}: --app takes the APK's path")
        info = paths.ATL_GTK_BUILD / "meson-info/intro-buildoptions.json"
        if not info.exists():
            raise DineError(f"no gtk ATL build in {paths.ATL_GTK_BUILD}: tools/dine linux build atl")
        if not next((o["value"] for o in json.loads(info.read_text()) if o["name"] == "test_hooks"), False):
            raise DineError(f"{paths.ATL_GTK_BUILD} has test_hooks off, so ATL has no debug agent: "
                            "reconfigure it with -Dtest_hooks=true")

    @classmethod
    def server_env(cls) -> dict[str, str]:
        # lldb only for attach: a server without it still runs the UI
        try:
            return lldb_env()
        except DineError:
            return {}

    def __init__(self, store, app):
        super().__init__(store, app)
        self.apk = Path(app).resolve()
        self.display: display.Display | None = None
        self.proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self.host = None
        self._ui: agent.Labels = []
        self.socket = store.dir / "agent.sock"
        # kept across launches, as an installed app keeps its data
        self.data = store.dir / "data"

    def setup(self) -> None:
        # on the server's main thread, which outlives it (display.py)
        self.display = display.Display()
        self.data.mkdir(exist_ok=True)
        self.store.append("event", "display", f"hidden display {self.display.socket}")

    def shutdown(self, kill_app: bool) -> str:
        out = []
        if self.host is not None:
            if self.host.wedged:
                out.append(f"lldb is stuck ({self.host.wedged})")
            elif self.host.state in ("running", "stopped"):
                out.append(self.host.kill())
            self.host.close()
        out.append(self.do_kill())
        if self.display:
            self.display.close()
        return "\n".join(out)

    def _running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def state(self) -> dict:
        if self.host is not None and self.host.state in ("running", "stopped"):
            return self._lldb_state()
        if self.proc is None:
            return {"attached": False, "state": "none"}
        return {"attached": False, "state": "running" if self._running() else "exited", "pid": self.proc.pid}

    def syslog_running(self) -> bool:
        return self.proc is not None

    def watching_exit(self) -> bool:
        return self._running()

    def do_launch(self, activity=None, timeout=30):
        if self._running():
            raise CmdError(f"ATL runs already (pid {self.proc.pid}): tools/dine dbg fresh relaunches it")
        env = without_lldb_env(self.display.env())
        env.update(RUN_FROM_BUILDDIR="1", ANDROID_APP_DATA_DIR=str(self.data), ATL_DBG_AGENT=str(self.socket))
        cmd = ["./android-translation-layer", str(self.apk), *(["-l", activity] if activity else []), "-X", "-Xint"]
        self.socket.unlink(missing_ok=True)
        self.proc = subprocess.Popen(cmd, cwd=paths.ATL_GTK_BUILD, env=env, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        self._reader = threading.Thread(target=self._read, args=(self.proc,), daemon=True)
        self._reader.start()
        return f"launched {self.apk.name}" + (f" -l {activity}" if activity else "") + f" pid {self.proc.pid}"

    def _read(self, proc: subprocess.Popen) -> None:
        with proc.stdout:
            for raw in proc.stdout:
                self.store.append("syslog", "line", raw.decode(errors="replace").rstrip("\n"))
        status = proc.wait()
        how = f"killed by {signal.Signals(-status).name}" if status < 0 else f"exited with status {status}"
        self.store.append("event", "exited", f"pid {proc.pid} {how}", status=status)

    def do_kill(self, timeout=30):
        if not self._running():
            return "ATL isn't running"
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(self.proc.pid, sig)
                self.proc.wait(timeout=5)
                break
            except ProcessLookupError:
                break
            except subprocess.TimeoutExpired:
                pass
        # its exit is logged before the next launch's mark
        self._reader.join(5)
        return f"killed pid {self.proc.pid}"

    def _main_thread(self, process):
        pid = process.GetProcessID()
        return next((t for t in process if t.GetThreadID() == pid), process.GetThreadAtIndex(0))

    def do_attach(self, pid=None, timeout=60):
        if not self._running():
            raise CmdError(self.no_process)
        if pid not in (None, self.proc.pid):
            raise CmdError(f"the gtk target debugs the ATL it runs, pid {self.proc.pid}")
        if self.host is None:
            try:
                from ..lldbhost import LldbHost
            except ImportError as e:
                raise CmdError(f"no lldb in the server ({e}): build it with $DINE_LLDB --version, then "
                               "tools/dine dbg stop-server; start-server") from None
            self.host = LldbHost(self.store, launch_hint="tools/dine dbg fresh")
            self.host.create_target(paths.ATL_GTK_BUILD / "android-translation-layer")
        self.host.need("none", "detached", "exited")
        return self.host.attach(self.proc.pid, timeout)

    def _connect(self, timeout: float) -> socket.socket:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect(str(self.socket))
        except (FileNotFoundError, ConnectionRefusedError):
            s.close()
            raise agent.AgentDown from None
        return s

    def _request(self, line: str, timeout: float) -> dict:
        try:
            return agent.request(line, timeout, self._stopped_at, connect=self._connect)
        except agent.AgentClosed as closed:
            try:
                self.proc.wait(2)
            except subprocess.TimeoutExpired:
                raise closed from None
            raise agent.AgentDown from None

    def _no_agent(self) -> str:
        if self.proc is None:
            return self.no_process
        if not self._running():
            return f"ATL exited ({self._exit_text()}): tools/dine dbg fresh"
        return "ATL's debug agent isn't up yet (its window isn't shown): retry, or tools/dine dbg log tail"

    def _went_away(self) -> str:
        return f"ATL exited after the action ({self._exit_text()}): tools/dine dbg log tail"

    def _exit_text(self) -> str:
        status = self.proc.wait(5)
        return f"killed by {signal.Signals(-status).name}" if status < 0 else f"status {status}"

    def do_ui_back(self, timeout=60):
        self._agent("back")
        try:
            tail, r = self._settle()
        except CmdError:
            if self._running():
                raise
            # Back closed the last activity
            return f"went back; ATL exited ({self._exit_text()})"
        if r.get("ran") and not r.get("result"):
            raise CmdError("ATL took no Back: its main loop isn't up yet")
        return "went back" + tail

    def do_ui_screenshot(self, arg=None):
        d = self.store.dir / "screenshots"
        d.mkdir(exist_ok=True)
        path = Path(arg) if arg else d / f"{self.store.cursor:06d}.png"
        try:
            self.display.screenshot(path, self.proc.pid if self._running() else None)
        except DineError as e:
            raise CmdError(str(e)) from None
        return f"screenshot: {path}"
