"""iOS device target: lldb (remote-ios through the tunnel), the app's syslog, UI through the app's debug agent."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

from ... import ios, paths
from ...paths import DineError
from .. import agent
from .agentui import AgentUi
from .base import CmdError, Target
from .lldbcmds import LldbCommands, lldb_env


class IosTarget(AgentUi, LldbCommands, Target):
    name = "ios"
    relaunch = "tools/dine ios kill, then relaunch"
    call_lang = "objc"

    @classmethod
    def preflight(cls, app: str) -> None:
        ios.require_tunnel()
        if warning := ios.quickack_warning():
            print(f"warning: {warning}", file=sys.stderr)
        symbols = ios.symbols_dir()
        if not (symbols / "Symbols").is_dir():
            print(f"warning: no local system symbols for this iOS ({symbols}); Swift po will fall back "
                  "to p: tools/dine ios symbols", file=sys.stderr)
        if not paths.app_binary(app).is_file():
            raise DineError(f"{paths.app_binary(app)} missing: tools/dine ios run {app}")
        # Rebuilds out/lldb when swift-bin or the Darwin SDK changed.
        lldb = paths.env("DINE_LLDB")
        r = subprocess.run([lldb, "--version"], capture_output=True, text=True, timeout=600)
        if r.returncode:
            raise DineError(f"{lldb} --version failed:\n{r.stderr.strip()[-1500:]}")

    @classmethod
    def server_env(cls) -> dict[str, str]:
        return lldb_env()

    def __init__(self, store, app):
        super().__init__(store, app)
        self.host = None
        self._syslog: subprocess.Popen | None = None
        self._ui: agent.Labels = []

    def setup(self) -> None:
        from ..lldbhost import LldbHost
        self.host = LldbHost(self.store, launch_hint=f"tools/dine ios launch {self.app}")
        h = self.host
        out = h.run(ios.lldb_platform_cmd())
        for c in ios.lldb_memory_cmds():
            h.run(c)
        h.create_target(paths.app_binary(self.app))
        for c in ios.lldb_setup_cmds():
            h.run(c)
        self.store.append("lldb", "setup", out.strip())

    def state(self) -> dict:
        return self._lldb_state()

    def _main_thread(self, process):
        return next((t for t in process if t.GetQueueName() == "com.apple.main-thread"), process.GetThreadAtIndex(0))

    def _exec_refusal(self, thread) -> str | None:
        top = thread.GetFrameAtIndex(0)
        if not parked_in_kernel(thread.GetQueueName(), top.GetModule().GetFileSpec().GetFilename()):
            return None
        return (f"thread #{thread.GetIndexID()} waits in the kernel ({top.GetFunctionName()}); an expression "
                "there can crash the app once it resumes. Use the main thread (bt --thread 1) or a "
                "breakpoint in this thread's code; --force runs it anyway")

    def shutdown(self, kill_app: bool) -> str:
        out = []
        if self.syslog_running():
            out.append(self.do_syslog_stop())
        if self.host.wedged:
            out.append(f"lldb is stuck ({self.host.wedged}); not detaching. If the app stays stopped: "
                       f"tools/dine ios kill {self.app}")
        elif self.host.state in ("running", "stopped"):
            out.append(self.host.kill() if kill_app else self.host.detach())
        self.host.close()
        return "\n".join(out)

    def do_attach(self, pid=None, timeout=120):
        self.host.need("none", "detached", "exited")
        if pid is None:
            procs = ios.processes(self.app)
            if not procs:
                raise CmdError(f"{self.app} isn't running: tools/dine ios launch {self.app}")
            if len(procs) > 1:
                raise CmdError(f"several {self.app} processes ({', '.join(str(p['pid']) for p in procs)}): --pid")
            pid = procs[0]["pid"]
        return self.host.attach(pid, timeout, url=ios.debugserver_url())

    def syslog_running(self) -> bool:
        return self._syslog is not None and self._syslog.poll() is None

    def do_syslog_start(self, debug=False, subsystem=None):
        if self.syslog_running():
            return "syslog capture already running"
        self._syslog = subprocess.Popen(
            [str(paths.PMD), "syslog", "live", "-pn", self.app, "--format", "json",
             *([] if debug else ["--no-debug"]), *(["-s", subsystem] if subsystem else [])],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
        threading.Thread(target=self._read_syslog, args=(self._syslog,), daemon=True).start()
        return f"capturing {self.app}'s syslog (tools/dine dbg wait --log …, log tail --src syslog)"

    def _read_syslog(self, proc: subprocess.Popen) -> None:
        for line in proc.stdout:
            text = syslog_text(line)
            if text:
                self.store.append("syslog", "line", text)
        err = proc.stderr.read().strip()
        self.store.append("event", "syslog-ended", f"syslog capture ended (exit {proc.wait()})"
                          + (f": {err[-500:]}" if err else ""))

    def do_syslog_stop(self):
        if not self.syslog_running():
            return "syslog capture is off"
        self._syslog.terminate()
        try:
            self._syslog.wait(5)
        except subprocess.TimeoutExpired:
            self._syslog.kill()
        return "syslog capture stopped"

    def is_app_line(self, text: str) -> bool:
        return f" {ios.bundle_base(self.app)}/" in text.split(":", 1)[0] + "/"

    def _request(self, line: str, timeout: float) -> dict:
        return agent.request(line, timeout, self._stopped_at)

    def _no_agent(self) -> str:
        return (f"no debug agent in {self.app}: it isn't running, or wasn't started by tools/dine ios launch "
                "(relaunch with it)")

    def _went_away(self) -> str:
        return f"{self.app} went away after the action (crashed?): tools/dine dbg status"

    def do_ui_back(self, timeout=60):
        self._agent("back")
        tail, r = self._settle()
        if r.get("ran") and not r.get("result"):
            raise CmdError("nothing on screen handled the escape (no back navigation here?)")
        return "went back" + (f" (escape handled by {r['result']})" if r.get("result") else "") + tail

    def do_ui_action(self, arg=None, timeout=60):
        if not arg:
            raise CmdError("usage: tools/dine dbg ui action <name>")
        self._agent(f"action {json.dumps(arg)}")
        tail, r = self._settle()
        if r.get("ran") and r.get("result") is None:
            raise CmdError(f"no accessibility action {arg!r} on this screen")
        if r.get("ran") and r.get("result") is False:
            raise CmdError(f"{arg!r} declined")
        return f"ran {arg!r}" + tail

    def do_ui_screenshot(self, arg=None):
        d = self.store.dir / "screenshots"
        d.mkdir(exist_ok=True)
        path = Path(arg) if arg else d / f"{self.store.cursor:06d}.png"
        path.write_bytes(ios.screenshot())
        return f"screenshot: {path}"


def parked_in_kernel(queue: str | None, module: str | None) -> bool:
    """A worker thread sitting in a syscall (semaphore, mach_msg, psynch wait)."""
    return queue != "com.apple.main-thread" and module == "libsystem_kernel.dylib"


def syslog_text(line: str) -> str | None:
    """One `syslog live --format json` entry as `LEVEL subsystem/category: message`."""
    line = line.strip()
    if not line:
        return None
    try:
        e = json.loads(line)
    except json.JSONDecodeError:
        return line
    if not isinstance(e, dict) or "message" not in e:
        return line
    label = e.get("label") or {}
    where = "/".join(filter(None, [label.get("subsystem"), label.get("category")]))
    return f"{e.get('level', '')} {where}: {e['message']}" if where else f"{e.get('level', '')}: {e['message']}"
