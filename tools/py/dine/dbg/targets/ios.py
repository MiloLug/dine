"""iOS device target: lldb (remote-ios through the tunnel), the app's syslog, UI through the app's debug agent."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from ... import ios, paths
from ...paths import DineError
from .. import agent, match
from .base import CmdError, Target

NUMBER = re.compile(r"[-+]?(0[xX][0-9a-fA-F]+|\d+(\.\d+)?)")


class IosTarget(Target):
    name = "ios"

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
        prefix = paths.OUT / "lldb"
        pkg = next(prefix.glob("local/lib*/python3.12/site-packages/lldb/__init__.py"), None) \
            or next(prefix.glob("lib*/python3.12/site-packages/lldb/__init__.py"), None)
        if pkg is None:
            raise DineError(f"no lldb Python package under {prefix}")
        # liblldb's RUNPATH is relative to the real file, but Python loads it through the
        # site-packages symlink; libpython3.12 comes from the .venv's base interpreter.
        libs = [Path(sys.base_prefix) / "lib", prefix / "lib", prefix / "lib/swift/linux",
                prefix / "lib/swift/host/compiler"]
        return {"PYTHONPATH": str(pkg.parent.parent),
                "LD_LIBRARY_PATH": ":".join([*map(str, libs), *filter(None, [os.environ.get("LD_LIBRARY_PATH")])])}

    def __init__(self, store, app):
        super().__init__(store, app)
        self.host = None
        self._syslog: subprocess.Popen | None = None
        self._ui: agent.Labels = []

    def setup(self) -> None:
        from ..lldbhost import LldbHost
        self.host = LldbHost(self.store)
        h = self.host
        out = h.run(ios.lldb_platform_cmd())
        for c in ios.lldb_memory_cmds():
            h.run(c)
        h.create_target(paths.app_binary(self.app))
        for c in ios.lldb_setup_cmds():
            h.run(c)
        self.store.append("lldb", "setup", out.strip())

    def state(self) -> dict:
        h = self.host
        s = {"attached": h.state in ("running", "stopped"),
             "state": "paused" if h.state == "stopped" and h.last_quiet else h.state}
        if h.process and h.process.IsValid() and s["attached"]:
            s["pid"] = h.process.GetProcessID()
        if s["state"] == "stopped":
            from ..lldbhost import where
            s["location"] = where(h.location)
        return s

    def interrupt_command(self, on: bool) -> None:
        if on:
            self.host.dbg.RequestInterrupt()
        else:
            self.host.dbg.CancelInterruptRequest()

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
        return self.host.connect_attach(ios.debugserver_url(), pid, timeout)

    def do_detach(self):
        return self.host.detach()

    def do_continue(self, thread=None, timeout=30):
        return self.host.resume()

    def do_interrupt(self):
        return self.host.interrupt()

    def do_step(self, thread=None, timeout=30):
        return self.host.step("step", thread, timeout)

    def do_next(self, thread=None, timeout=30):
        return self.host.step("next", thread, timeout)

    def do_finish(self, thread=None, timeout=30):
        return self.host.step("finish", thread, timeout)

    def do_stepi(self, thread=None, timeout=30):
        return self.host.step("stepi", thread, timeout)

    def do_threads(self):
        return self.host.threads()

    def do_bt(self, n=20, thread=None):
        return self.host.backtrace(n, thread)

    def do_frame(self, index=None):
        return self.host.select_frame(index)

    def do_up(self):
        return self.host.select_frame(None, +1)

    def do_down(self):
        return self.host.select_frame(None, -1)

    def do_source(self, context=8):
        return self.host.source(context)

    def do_vars(self, names=()):
        return self.host.variables(list(names))

    def do_exec(self, expr, lang=None, po=False, allow_exceptions=False, force=False, timeout=60):
        th = self.host.thread()
        top = th.GetFrameAtIndex(0)
        if not force and parked_in_kernel(th.GetQueueName(), top.GetModule().GetFileSpec().GetFilename()):
            raise CmdError(f"thread #{th.GetIndexID()} waits in the kernel ({top.GetFunctionName()}); an expression "
                           "there can crash the app once it resumes. Use the main thread (bt --thread 1) or a "
                           "breakpoint in this thread's code; --force runs it anyway")
        return self.host.evaluate(expr, lang, po, timeout, trap_exceptions=not allow_exceptions)

    def do_cmd(self, command, timeout=60):
        return self.host.run(command).strip() or "(no output)"

    def do_bp(self, op, spec=None, cond=None, once=False):
        return self.host.breakpoint(op, spec, cond, once)

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

    def _stopped_at(self) -> str | None:
        """Where lldb has the app stopped (the agent can't answer then), or None."""
        if self.host.state == "stopped":
            from ..lldbhost import where
            return where(self.host.location)
        return None

    def _agent(self, line: str, timeout: float = 10) -> dict:
        if where := self._stopped_at():
            raise CmdError(f"the app is stopped at {where} and can't answer UI requests: tools/dine dbg continue")
        try:
            return agent.request(line, timeout, self._stopped_at)
        except agent.AgentDown:
            raise CmdError(f"no debug agent in {self.app}: it isn't running, or wasn't started by "
                           f"tools/dine ios launch (relaunch with it)") from None

    def _ls(self) -> agent.Labels:
        self._ui = agent.labels_of(self._agent("ls"))
        return self._ui

    def _settle(self) -> tuple[str, dict]:
        """Waits for the screen the last tap/back led to; text to append, and the reply. No stop check
        first: a tap into a breakpoint stops the app right after the tap's reply."""
        try:
            r = agent.request("settle 3000", 8, self._stopped_at)
        except agent.AgentDown:
            raise CmdError(f"{self.app} went away after the action (crashed?): tools/dine dbg status") from None
        if "stopped" in r:
            return f"; stopped at {r['stopped']}", r
        self._ui = agent.labels_of(r)
        if not r["ran"]:
            return "; the app's main thread hasn't run it yet after 3 s (busy?)", r
        return "\nscreen: " + agent.screen(self._ui) + ("" if r["settled"] else " (still changing after 3 s)"), r

    def do_ui_ls(self):
        return agent.listing(self._ls())

    def ui_find(self, label: str, timeout: float) -> str | None:
        """None also while the agent can't answer: the wait's own stop and exit checks report those."""
        if self._stopped_at():
            return None
        m = match.loose(label)
        try:
            r = agent.request("ls", min(timeout, 2), self._stopped_at)
        except (agent.AgentDown, CmdError, OSError):
            return None
        return next((l for _, l in agent.labels_of(r) if m(l)), None)

    def do_ui_tap(self, arg=None, timeout=60):
        if not arg:
            raise CmdError("usage: tools/dine dbg ui tap <label|#N>")
        if arg.startswith("#") and arg[1:].isdigit():
            i = int(arg[1:])
            if i >= len(self._ui):
                raise CmdError(f"no {arg} in the last `ui ls` ({len(self._ui)} elements)")
        else:
            i = agent.pick(self._ls(), arg)
        label = self._ui[i][1]
        self._agent(f"tap {i} {json.dumps(label)}")
        tail, r = self._settle()
        if r.get("ran") and r.get("result") is False:
            raise CmdError(f"{label!r} declined the activation (back navigation: tools/dine dbg ui back)")
        return f"tapped {label!r}" + tail

    def do_ui_type(self, arg=None, text=None, timeout=60):
        if not arg or text is None:
            raise CmdError("usage: tools/dine dbg ui type <label|#N> <text>")
        if arg.startswith("#") and arg[1:].isdigit():
            i = int(arg[1:])
            if i >= len(self._ui):
                raise CmdError(f"no {arg} in the last `ui ls` ({len(self._ui)} elements)")
        else:
            i = agent.pick(self._ls(), arg)
        label = self._ui[i][1]
        self._agent(f"type {i} {json.dumps([label, text])}")
        tail, r = self._settle()
        if r.get("ran") and r.get("result") is False:
            raise CmdError(f"{label!r} takes no text (not a text field, or it can't become the first responder)")
        return f"typed {text!r} into {label!r}" + tail

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

    def _in_app(self, fn, timeout: float):
        """`fn(left)` runs paused on the main thread; `left()` is the time remaining."""
        h = self.host
        if h.state not in ("running", "stopped"):
            raise CmdError("`call` runs through the debugger: tools/dine dbg attach")
        deadline = time.monotonic() + timeout

        def left() -> float:
            s = deadline - time.monotonic()
            if s < 1:
                raise CmdError(f"ran out of its {timeout:g}s")
            return s
        resume = h.state == "running"
        if resume:
            h.interrupt(quiet=True)
            h.need("stopped")
        th = h.process.GetSelectedThread()
        main = next((t for t in h.process if t.GetQueueName() == "com.apple.main-thread"),
                    h.process.GetThreadAtIndex(0))
        h.process.SetSelectedThread(main)
        try:
            text = fn(left)
        finally:
            h.process.SetSelectedThread(th)
            if resume and h.state == "stopped":
                h.resume()
        return text + ("; resumed" if resume else "; still stopped (tools/dine dbg continue to let it act)")

    def do_call(self, fn, args=(), po=False, timeout=60):
        if not re.fullmatch(r"[A-Za-z_]\w*", fn):
            raise CmdError(f"{fn!r} isn't a function name")
        expr = f"{fn}({', '.join(map(c_literal, args))})"
        return self._in_app(lambda left: self.host.evaluate(expr, "objc", po, left()), timeout)

    def do_ui_screenshot(self, arg=None):
        d = self.store.dir / "screenshots"
        d.mkdir(exist_ok=True)
        path = Path(arg) if arg else d / f"{self.store.cursor:06d}.png"
        path.write_bytes(ios.screenshot())
        return f"screenshot: {path}"


def parked_in_kernel(queue: str | None, module: str | None) -> bool:
    """A worker thread sitting in a syscall (semaphore, mach_msg, psynch wait)."""
    return queue != "com.apple.main-thread" and module == "libsystem_kernel.dylib"


def c_literal(arg: str) -> str:
    """A `dbg call` argument as C: numbers as written, anything else a string literal."""
    return arg if NUMBER.fullmatch(arg) else json.dumps(arg, ensure_ascii=False)


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
