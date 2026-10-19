"""lldb in the server process (SB API, async mode). Only `_events` reads process events; it logs
each state change before flipping `state`, which `wait` relies on."""

import threading
import time
from pathlib import Path

import lldb

from .logstore import LogStore
from .targets.base import CmdError

LANGS = {"swift": lldb.eLanguageTypeSwift, "c++": lldb.eLanguageTypeC_plus_plus,
         "c": lldb.eLanguageTypeC, "objc": lldb.eLanguageTypeObjC_plus_plus}
REASONS = {lldb.eStopReasonBreakpoint: "breakpoint", lldb.eStopReasonWatchpoint: "watchpoint",
           lldb.eStopReasonSignal: "signal", lldb.eStopReasonException: "exception",
           lldb.eStopReasonPlanComplete: "step", lldb.eStopReasonTrace: "trace",
           lldb.eStopReasonInterrupt: "interrupt", lldb.eStopReasonInstrumentation: "instrumentation"}
QUIET_SIGNALS = {"SIGSTOP", "SIGINT", "SIGTRAP"}
NO_RESULT = 0x1001  # lldb's UserExpression::kNoResult: the expression is void, not failed
STATES = {lldb.eStateConnected: "connected", lldb.eStateRunning: "running", lldb.eStateStepping: "running",
          lldb.eStateStopped: "stopped", lldb.eStateSuspended: "stopped", lldb.eStateCrashed: "stopped",
          lldb.eStateExited: "exited", lldb.eStateDetached: "detached"}


def where(loc: dict | None) -> str:
    if not loc:
        return "?"
    s = loc.get("function") or loc.get("pc", "?")
    if loc.get("file"):
        s += f" at {Path(loc['file']).name}:{loc.get('line')}"
    elif loc.get("module"):
        s = f"{loc['module']}`{s}"
    return s


def frame_loc(fr: lldb.SBFrame) -> dict:
    loc = {"function": fr.GetDisplayFunctionName() or fr.GetFunctionName() or fr.GetSymbol().GetName(),
           "pc": f"0x{fr.GetPC():x}", "module": fr.GetModule().GetFileSpec().GetFilename()}
    le = fr.GetLineEntry()
    if le.IsValid() and le.GetFileSpec().GetFilename():
        loc["file"] = str(le.GetFileSpec())
        loc["line"] = le.GetLine()
    return loc


class LldbHost:
    def __init__(self, store: LogStore):
        self.store = store
        self.dbg = lldb.SBDebugger.Create(False)
        self.dbg.SetAsync(True)
        self.ci = self.dbg.GetCommandInterpreter()
        self.listener = lldb.SBListener("dine-events")
        self.target: lldb.SBTarget | None = None
        self.process: lldb.SBProcess | None = None
        self.state = "none"
        self.location: dict | None = None
        self.stops = 0
        # Set around stops the tool makes for itself (`dbg call`): logged as `paused`, which waits ignore.
        self.quiet_stop = False
        self.last_quiet = False
        self.wedged: str | None = None
        self._changed = threading.Condition()
        self._closing = False
        threading.Thread(target=self._events, name="lldb-events", daemon=True).start()

    def run(self, command: str, check: bool = True) -> str:
        r = lldb.SBCommandReturnObject()
        self.ci.HandleCommand(command, r)
        out = (r.GetOutput() or "") + (r.GetError() or "")
        if check and not r.Succeeded():
            raise CmdError(f"lldb: {command}\n{out.strip()}")
        return out

    def create_target(self, binary: Path) -> None:
        """Once per server: later processes attach to the same target, which keeps breakpoints and the
        parsed shared-cache modules (a later attach takes ~3.5 s instead of ~15 s)."""
        self.run(f'target create "{binary}"')
        self.target = self.dbg.GetSelectedTarget()

    def _set(self, state: str, kind: str | None, text: str = "", **data) -> None:
        if kind:
            self.store.append("event", kind, text, **data)
        with self._changed:
            self.state = state
            if state == "stopped":
                self.stops += 1
                self.location = data.get("location")
            self._changed.notify_all()

    def wait_state(self, ok, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._changed:
            while not ok():
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self._changed.wait(left)
            return True

    def _events(self) -> None:
        ev = lldb.SBEvent()
        while not self._closing:
            if not self.listener.WaitForEvent(1, ev):
                continue
            if not lldb.SBProcess.EventIsProcessEvent(ev):
                continue
            if ev.GetType() & lldb.SBProcess.eBroadcastBitStateChanged == 0:
                continue
            st = lldb.SBProcess.GetStateFromEvent(ev)
            if lldb.SBProcess.GetRestartedFromEvent(ev):
                continue
            name = STATES.get(st)
            if name == "stopped":
                self.report_stop()
            elif name == "exited":
                p = lldb.SBProcess.GetProcessFromEvent(ev)
                status = p.GetExitStatus()
                desc = p.GetExitDescription() or ""
                self._set("exited", "exited", f"process exited with status {status}" + (f" ({desc})" if desc else ""),
                          status=status)
            elif name == "running" and self.state != "running":
                self._set("running", "running", "running")
            elif name == "detached":
                self._set("detached", "detached", "detached")

    def report_stop(self) -> None:
        p = self.process
        th = p.GetSelectedThread()
        if th.GetStopReason() in (lldb.eStopReasonNone, lldb.eStopReasonInvalid):
            for t in p:
                if t.GetStopReason() not in (lldb.eStopReasonNone, lldb.eStopReasonInvalid):
                    th = t
                    p.SetSelectedThread(t)
                    break
        code = th.GetStopReason()
        reason = REASONS.get(code, "other")
        # Signal numbers are the target's (Darwin SIGSTOP is 17), not Python's.
        sig = p.GetUnixSignals().GetSignalAsCString(th.GetStopReasonDataAtIndex(0)) \
            if code == lldb.eStopReasonSignal else None
        crash = code == lldb.eStopReasonException or (sig is not None and sig not in QUIET_SIGNALS)
        loc = frame_loc(th.GetFrameAtIndex(0))
        desc = th.GetStopDescription(256)
        quiet, self.quiet_stop = self.quiet_stop, False
        self.last_quiet = quiet and not crash
        kind = "paused" if self.last_quiet else "stopped"
        label = "CRASHED" if crash else kind
        self._set("stopped", kind, f"{label}: thread #{th.GetIndexID()} {where(loc)} ({desc})",
                  reason=reason, crash=crash, thread=th.GetIndexID(), location=loc)
        if sig == "SIGKILL":
            # Killed from outside (`ios kill`, a relaunch): it only exits once resumed, and until then
            # it blocks launching a new instance.
            p.Continue()

    def close(self) -> None:
        self._closing = True

    def need(self, *states: str) -> None:
        if self.wedged:
            raise CmdError(f"lldb is stuck ({self.wedged}): tools/dine dbg stop-server, then start-server")
        if self.state not in states:
            hint = {"none": "nothing attached: tools/dine dbg attach",
                    "detached": "detached: tools/dine dbg attach",
                    "exited": "process exited: relaunch (tools/dine ios launch) and attach",
                    "running": "process is running: tools/dine dbg interrupt, or wait --stop",
                    "stopped": f"process is stopped at {where(self.location)}: tools/dine dbg continue"}
            raise CmdError(hint.get(self.state, f"process is {self.state}"))

    def connect_attach(self, url: str, pid: int, timeout: float) -> str:
        if self.state in ("running", "stopped"):
            raise CmdError("already attached: tools/dine dbg detach first")
        err = lldb.SBError()
        self.process = self.target.ConnectRemote(self.listener, url, "gdb-remote", err)
        if not err.Success():
            raise CmdError(f"connect {url}: {err.GetCString()}")
        self.store.append("event", "attaching", f"attaching to pid {pid}")
        # Wants an empty listener (the process has ours), blocks with no deadline of its own, and its
        # stop goes to a hijack listener; `process attach` never returns in async mode. Run it aside.
        result: dict = {}

        def attach():
            e = lldb.SBError()
            result["process"] = self.target.AttachToProcessWithID(lldb.SBListener(), pid, e)
            result["error"] = e
        t = threading.Thread(target=attach, name="lldb-attach", daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            self.wedged = f"attach to pid {pid} hung"
            raise CmdError(f"attach to pid {pid} didn't finish within {timeout:g}s (phone locked? app gone?). "
                           "lldb is stuck in it: tools/dine dbg stop-server, then start-server")
        e = result["error"]
        if not e.Success():
            raise CmdError(f"attach to pid {pid}: {e.GetCString()}")
        self.process = result["process"]
        if self.process.GetState() == lldb.eStateStopped:
            self.report_stop()
        return f"attached to pid {pid}; stopped at {where(self.location)} (attach stops the app: " \
               "tools/dine dbg continue)"

    def detach(self) -> str:
        self.need("running", "stopped")
        err = self.process.Detach()
        if not err.Success():
            raise CmdError(f"detach: {err.GetCString()}")
        self.wait_state(lambda: self.state == "detached", 5)
        if self.state != "detached":
            self._set("detached", "detached", "detached")
        return "detached; the app keeps running"

    def kill(self) -> str:
        self.process.Kill()
        self.wait_state(lambda: self.state == "exited", 10)
        return "killed the app"

    def resume(self) -> str:
        self.need("stopped")
        before = self.stops
        err = self.process.Continue()
        if not err.Success():
            raise CmdError(f"continue: {err.GetCString()}")
        self.wait_state(lambda: self.state != "stopped" or self.stops != before, 5)
        return "running (tools/dine dbg wait --stop … to catch the next stop)"

    def interrupt(self, quiet: bool = False) -> str:
        if self.state != "running":
            return f"no running process to stop ({self.state})"
        self.quiet_stop = quiet
        err = self.process.Stop()
        if not err.Success():
            self.quiet_stop = False
            raise CmdError(f"interrupt: {err.GetCString()}")
        self.wait_state(lambda: self.state != "running", 10)
        if self.state == "running":
            self.quiet_stop = False
        return f"stopped at {where(self.location)}" if self.state == "stopped" else f"state: {self.state}"

    def step(self, kind: str, thread: int | None, timeout: float) -> str:
        self.need("stopped")
        th = self.thread(thread)
        before = self.stops
        getattr(th, {"step": "StepInto", "next": "StepOver", "finish": "StepOut"}.get(kind, "StepInstruction"))(
            *([False] if kind == "stepi" else []))
        if not self.wait_state(lambda: self.stops != before or self.state not in ("stopped", "running"), timeout):
            return f"still running after {timeout:g}s (a breakpoint-free step can run long): " \
                   "tools/dine dbg wait --stop, or interrupt"
        if self.state != "stopped":
            return f"process {self.state}"
        return self.source(2)

    def thread(self, index: int | None = None) -> lldb.SBThread:
        self.need("stopped")
        if index is None:
            return self.process.GetSelectedThread()
        th = self.process.GetThreadByIndexID(index)
        if not th.IsValid():
            raise CmdError(f"no thread #{index}: tools/dine dbg threads")
        self.process.SetSelectedThread(th)
        return th

    def frame(self) -> lldb.SBFrame:
        return self.thread().GetSelectedFrame()

    def threads(self) -> str:
        sel = self.thread().GetIndexID()
        lines = []
        for th in self.process:
            reason = REASONS.get(th.GetStopReason(), "")
            q = th.GetQueueName()
            lines.append(f"{'*' if th.GetIndexID() == sel else ' '} #{th.GetIndexID()} "
                         f"{where(frame_loc(th.GetFrameAtIndex(0)))}"
                         + (f"  queue {q}" if q else "") + (f"  [{reason}]" if reason else ""))
        return "\n".join(lines)

    def backtrace(self, n: int, thread: int | None) -> str:
        th = self.thread(thread)
        sel = th.GetSelectedFrame().GetFrameID()
        lines = [f"thread #{th.GetIndexID()}, {th.GetNumFrames()} frames"]
        for i, fr in enumerate(th):
            if i >= n:
                lines.append(f"  … {th.GetNumFrames() - n} more: -n {th.GetNumFrames()}")
                break
            lines.append(f"{'*' if i == sel else ' '} #{i} {where(frame_loc(fr))}")
        return "\n".join(lines)

    def select_frame(self, index: int | None, delta: int = 0) -> str:
        th = self.thread()
        if index is None:
            index = th.GetSelectedFrame().GetFrameID() + delta
        if not 0 <= index < th.GetNumFrames():
            raise CmdError(f"no frame #{index} (0..{th.GetNumFrames() - 1})")
        th.SetSelectedFrame(index)
        return f"frame #{index}: " + self.source(3)

    def source(self, context: int) -> str:
        fr = self.frame()
        loc = frame_loc(fr)
        lang = fr.GuessLanguage()
        head = where(loc) + (f" [{lldb.SBLanguageRuntime.GetNameForLanguageType(lang)}]" if lang else "")
        path = Path(loc.get("file", ""))
        if not loc.get("file") or not path.is_file():
            return head + "\n(no local source)"
        lines = path.read_text(errors="replace").splitlines()
        line = loc["line"]
        lo, hi = max(1, line - context), min(len(lines), line + context)
        return head + "\n" + "\n".join(f"{'->' if i == line else '  '} {i:4} {lines[i - 1]}" for i in range(lo, hi + 1))

    def variables(self, names: list[str]) -> str:
        fr = self.frame()
        if names:
            vals = [fr.GetValueForVariablePath(n) for n in names]
        else:
            vals = list(fr.GetVariables(True, True, False, True))
        out = []
        for name, v in zip(names or [v.GetName() for v in vals], vals):
            if not v.IsValid() or v.GetError().Fail():
                out.append(f"{name}: {v.GetError().GetCString() or 'not found'}")
            else:
                out.append(str(v).strip())
        return "\n".join(out) or "(no variables)"

    def _expression(self, code: str, lang: str | None, timeout: float, trap_exceptions: bool = True) -> lldb.SBValue:
        # Trapping unwinds an expression at its first throw, even one it would catch itself; that
        # can leave state half-done (a static's init guard taken, so the app aborts later).
        fr = self.frame()
        opts = lldb.SBExpressionOptions()
        opts.SetTrapExceptions(trap_exceptions)
        if lang:
            opts.SetLanguage(LANGS[lang])
        opts.SetTimeoutInMicroSeconds(int(max(timeout - 2, 1) * 1e6))
        opts.SetTryAllThreads(True)
        opts.SetUnwindOnError(True)
        opts.SetIgnoreBreakpoints(True)
        opts.SetFetchDynamicValue(lldb.eDynamicDontRunTarget)
        v = fr.EvaluateExpression(code, opts)
        err = v.GetError()
        if err.Fail() and err.GetError() != NO_RESULT:
            raise CmdError(err.GetCString().strip())
        return v

    def evaluate(self, expr: str, lang: str | None, po: bool, timeout: float, trap_exceptions: bool = True) -> str:
        v = self._expression(expr, lang, timeout, trap_exceptions)
        if v.GetError().GetError() == NO_RESULT:
            return "(no result)"
        if po:
            return (v.GetObjectDescription() or str(v)).strip()
        return str(v).strip() or "(no result)"

    def breakpoint(self, op: str, spec: str | None, cond: str | None, once: bool) -> str:
        t = self.target
        if op == "ls":
            lines = []
            for bp in t.breakpoint_iter():
                locs = [where(frame_loc_addr(l.GetAddress())) for l in bp]
                lines.append(f"{bp.GetID()}: {'enabled' if bp.IsEnabled() else 'disabled'}, hits {bp.GetHitCount()}"
                             + (f", if {bp.GetCondition()}" if bp.GetCondition() else "")
                             + (", once" if bp.IsOneShot() else "")
                             + (f" → {'; '.join(locs)}" if locs else " (unresolved)"))
            return "\n".join(lines) or "no breakpoints"
        if not spec:
            raise CmdError(f"bp {op} needs {'a location' if op == 'add' else 'an id'}")
        if op == "add":
            file, _, line = spec.rpartition(":")
            bp = t.BreakpointCreateByLocation(file, int(line)) if file and line.isdigit() \
                else t.BreakpointCreateByName(spec)
            if not bp.IsValid():
                raise CmdError(f"can't set a breakpoint at {spec}")
            if cond:
                bp.SetCondition(cond)
            bp.SetOneShot(once)
            locs = [where(frame_loc_addr(l.GetAddress())) for l in bp]
            return f"breakpoint {bp.GetID()}: " + ("; ".join(locs) if locs else
                                                  "no locations yet (pending; resolves when the code loads)")
        bp = t.FindBreakpointByID(int(spec))
        if not bp.IsValid():
            raise CmdError(f"no breakpoint {spec}: tools/dine dbg bp ls")
        if op == "rm":
            t.BreakpointDelete(bp.GetID())
            return f"deleted breakpoint {spec}"
        bp.SetEnabled(op == "enable")
        return f"breakpoint {spec} {op}d"


def frame_loc_addr(addr: lldb.SBAddress) -> dict:
    loc = {"function": addr.GetFunction().GetDisplayName() or addr.GetSymbol().GetName(),
           "module": addr.GetModule().GetFileSpec().GetFilename()}
    le = addr.GetLineEntry()
    if le.IsValid() and le.GetFileSpec().GetFilename():
        loc["file"] = str(le.GetFileSpec())
        loc["line"] = le.GetLine()
    return loc
