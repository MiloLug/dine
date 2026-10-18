"""iOS device target: lldb (remote-ios through the tunnel), the app's syslog, UI via accessibility."""

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
from .. import match
from .base import CmdError, Target

ACTIONS = paths.ROOT / "tools/dbg-actions.mm"
PROTOTYPE = re.compile(r'^(extern "C" [^;{]+?)\s*\{', re.M)
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

    def __init__(self, store, app, actions=None):
        super().__init__(store, app, actions or ACTIONS)
        self.host = None
        self._syslog: subprocess.Popen | None = None
        self._ui: list[str] = []
        self._ui_skip: list[str] = []
        self._actions_target = 0
        self._prototypes = ""

    def setup(self) -> None:
        from ..lldbhost import LldbHost
        self.host = LldbHost(self.store)
        h = self.host
        out = h.run(ios.lldb_platform_cmd())
        for c in ios.lldb_memory_cmds():
            h.run(c)
        self._new_target()
        self.store.append("lldb", "setup", out.strip())

    def _new_target(self) -> None:
        self.host.create_target(paths.app_binary(self.app))
        for c in ios.lldb_setup_cmds():
            self.host.run(c)

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
        if self.host.process is not None and self.host.process.GetProcessID() != pid:
            self._new_target()
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

    def do_exec(self, expr, lang=None, po=False, allow_exceptions=False, timeout=60):
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

    def _need_running(self) -> None:
        if self.host.state == "stopped":
            from ..lldbhost import where
            raise CmdError(f"the app is stopped at {where(self.host.location)} and can't answer UI "
                           "queries: tools/dine dbg continue")

    def _elements(self, timeout: float = 30) -> list[str]:
        out = ios.pmd("developer", "accessibility", "list-items", "--tunnel", "", timeout=min(timeout, 30))
        self._ui = [e.get("CaptionTextValue_v1") or e.get("caption") or str(e) for e in json.loads(out)]
        return self._ui

    def do_ui_ls(self):
        self._need_running()
        items = self._elements()
        return "\n".join(f"#{i} {c}" for i, c in enumerate(items)) or "(no accessibility elements)"

    def ui_find(self, label: str, timeout: float) -> str | None:
        if self.host.state == "stopped":
            return None
        m = match.loose(label)
        try:
            return next((c for c in self._elements(timeout) if m(c)), None)
        except DineError:
            return None

    def _in_app(self, fn, timeout: float):
        """`fn(left)` runs paused on the main thread, actions defined; `left()` is the time remaining."""
        h = self.host
        if h.state not in ("running", "stopped"):
            raise CmdError("UI actions and calls run through the debugger: tools/dine dbg attach")
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
            self._define_actions(left())
            text = fn(left)
        finally:
            h.process.SetSelectedThread(th)
            if resume and h.state == "stopped":
                h.resume()
        return text + ("; resumed" if resume else "; still stopped (tools/dine dbg continue to let it act)")

    def _define_actions(self, timeout: float) -> None:
        if self._actions_target == self.host.targets:
            return
        try:
            code = self.actions.read_text()
        except OSError as e:
            raise CmdError(f"actions file: {e}") from None
        try:
            self.host.define(code, timeout)
        except CmdError as e:
            raise CmdError(f"{self.actions}:\n{e}") from None
        self._prototypes = "\n".join(p + ";" for p in PROTOTYPE.findall(code))
        self._actions_target = self.host.targets
        self.store.append("lldb", "actions", f"defined {self.actions}")

    def _call(self, expr: str, po: bool, left) -> str:
        return self.host.evaluate(expr, "objc", po, left(), prefix=self._prototypes)

    def _collect(self, left) -> list[tuple[bool, str]]:
        skip = self._ui_skip
        for _ in range(5):
            try:
                out = self._call(f"dine_ui_collect({c_literal(','.join(skip))})", True, left)
                return [(x[0] == "1", x[1:]) for x in out.split("\x1e") if x]
            except CmdError as e:
                # An AX getter threw, aborting the walk (no @try in lldb's ObjC): skip its class.
                if "exception" not in str(e):
                    raise
                m = re.search(r'"(.*)"\s*$', self._call("dine_ui_last_class()", False, left))
                if not m or m.group(1) in skip:
                    raise
                skip.append(m.group(1))
                self.store.append("lldb", "ui", f"{m.group(1)} throws from its accessibility getters; skipped")
        raise CmdError(f"accessibility walk keeps throwing (skipped {', '.join(skip)})")

    def do_ui_tap(self, arg=None, timeout=60):
        """Host-side AX `perform_press` is ignored by our apps, so the app calls `accessibilityActivate`
        on the matching element itself."""
        if not arg:
            raise CmdError("usage: tools/dine dbg ui tap <label|#N>")
        if arg.startswith("#") and arg[1:].isdigit():
            if int(arg[1:]) >= len(self._ui):
                raise CmdError(f"no {arg} in the last `ui ls` ({len(self._ui)} elements)")
            arg = self._ui[int(arg[1:])].split(", ")[0]

        def tap(left):
            items = self._collect(left)
            m = match.loose(arg)
            hits = [i for i, (_, label) in enumerate(items) if m(label)]
            if not hits:
                raise CmdError(f"no element matches {arg!r}; labels: " + ", ".join(sorted({l for _, l in items})))
            exact = [i for i in hits if items[i][1].lower() == arg.lower()]
            labels = sorted({items[i][1] for i in hits})
            if len(labels) > 1 and not exact:
                raise CmdError(f"{arg!r} is ambiguous: " + ", ".join(labels))
            pick = next((i for i in exact or hits if items[i][0]), (exact or hits)[0])
            ok = self._call(f"dine_ui_activate({pick})", False, left)
            label = items[pick][1]
            if not re.search(r"\b(YES|true)\b", ok):
                raise CmdError(f"{label!r} declined the activation (back navigation: tools/dine dbg ui back)")
            return f"tapped {label!r}"
        return self._in_app(tap, timeout)

    def do_ui_back(self, timeout=60):
        def back(left):
            if not self._collect(left):
                raise CmdError("no accessibility elements on screen")
            m = re.search(r'"(.*)"\s*$', self._call("dine_ui_escape()", False, left))
            if not m:
                raise CmdError("nothing on screen handled the escape (no back navigation here?)")
            return f"went back (escape handled by {m.group(1)})"
        return self._in_app(back, timeout)

    def do_call(self, fn, args=(), po=False, timeout=60):
        if not re.fullmatch(r"[A-Za-z_]\w*", fn):
            raise CmdError(f"{fn!r} isn't a function name")
        expr = f"{fn}({', '.join(map(c_literal, args))})"
        return self._in_app(lambda left: self._call(expr, po, left), timeout)

    def do_ui_screenshot(self, arg=None):
        d = self.store.dir / "screenshots"
        d.mkdir(exist_ok=True)
        path = Path(arg) if arg else d / f"{self.store.cursor:06d}.png"
        ios.pmd("developer", "dvt", "screenshot", "--tunnel", "", str(path), timeout=30)
        return f"screenshot: {path}"


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
