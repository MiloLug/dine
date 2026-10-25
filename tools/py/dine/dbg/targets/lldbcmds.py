"""lldb commands of the targets that debug through lldbhost.LldbHost."""

import json
import os
import re
import sys
import time
from pathlib import Path

from ... import paths
from ...paths import DineError
from .base import CmdError

NUMBER = re.compile(r"[-+]?(0[xX][0-9a-fA-F]+|\d+(\.\d+)?)")


def _lldb_libs() -> list[str]:
    # liblldb's RUNPATH is relative to the real file, but Python loads it through the
    # site-packages symlink; libpython3.12 comes from the .venv's base interpreter.
    prefix = paths.OUT / "lldb"
    return [str(d) for d in (Path(sys.base_prefix) / "lib", prefix / "lib", prefix / "lib/swift/linux",
                             prefix / "lib/swift/host/compiler")]


def lldb_env() -> dict[str, str]:
    """The server's env for importing out/lldb's Python package."""
    prefix = paths.OUT / "lldb"
    pkg = next(prefix.glob("local/lib*/python3.12/site-packages/lldb/__init__.py"), None) \
        or next(prefix.glob("lib*/python3.12/site-packages/lldb/__init__.py"), None)
    if pkg is None:
        raise DineError(f"no lldb Python package under {prefix}")
    return {"PYTHONPATH": str(pkg.parent.parent),
            "LD_LIBRARY_PATH": ":".join([*_lldb_libs(), *filter(None, [os.environ.get("LD_LIBRARY_PATH")])])}


def without_lldb_env(env: dict[str, str]) -> dict[str, str]:
    """`env` without lldb_env's library dirs, for a process the server starts: out/lldb's Swift
    runtime libraries would come first on its library path."""
    lldb = set(_lldb_libs())
    dirs = [d for d in env.get("LD_LIBRARY_PATH", "").split(":") if d and d not in lldb]
    return {**{k: v for k, v in env.items() if k not in ("PYTHONPATH", "LD_LIBRARY_PATH")},
            **({"LD_LIBRARY_PATH": ":".join(dirs)} if dirs else {})}


def c_literal(arg: str) -> str:
    """A `dbg call` argument as C: numbers as written, anything else a string literal."""
    return arg if NUMBER.fullmatch(arg) else json.dumps(arg, ensure_ascii=False)


class LldbCommands:
    """Mixin for a Target with `host` (an LldbHost, or None before the first attach). Per platform:
    `call_lang`, `_main_thread(process)`, `_exec_refusal(thread)`."""

    call_lang = "c"

    def _lldb(self):
        if self.host is None:
            raise CmdError("nothing attached: tools/dine dbg attach")
        return self.host

    def _lldb_state(self) -> dict:
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
        if self.host is None:
            return
        if on:
            self.host.dbg.RequestInterrupt()
        else:
            self.host.dbg.CancelInterruptRequest()

    def _stopped_at(self) -> str | None:
        """Where lldb has the app stopped (the agent can't answer then), or None."""
        if self.host is not None and self.host.state == "stopped":
            from ..lldbhost import where
            return where(self.host.location)
        return None

    def _main_thread(self, process):
        return process.GetThreadAtIndex(0)

    def _exec_refusal(self, thread) -> str | None:
        """Why an expression on this thread is unsafe, or None."""
        return None

    def do_detach(self):
        return self._lldb().detach()

    def do_continue(self, thread=None, timeout=30):
        return self._lldb().resume()

    def do_interrupt(self):
        return self._lldb().interrupt()

    def do_step(self, thread=None, timeout=30):
        return self._lldb().step("step", thread, timeout)

    def do_next(self, thread=None, timeout=30):
        return self._lldb().step("next", thread, timeout)

    def do_finish(self, thread=None, timeout=30):
        return self._lldb().step("finish", thread, timeout)

    def do_stepi(self, thread=None, timeout=30):
        return self._lldb().step("stepi", thread, timeout)

    def do_threads(self):
        return self._lldb().threads()

    def do_bt(self, n=20, thread=None):
        return self._lldb().backtrace(n, thread)

    def do_frame(self, index=None):
        return self._lldb().select_frame(index)

    def do_up(self):
        return self._lldb().select_frame(None, +1)

    def do_down(self):
        return self._lldb().select_frame(None, -1)

    def do_source(self, context=8):
        return self._lldb().source(context)

    def do_vars(self, names=()):
        return self._lldb().variables(list(names))

    def do_exec(self, expr, lang=None, po=False, allow_exceptions=False, force=False, timeout=60):
        th = self._lldb().thread()
        if not force and (why := self._exec_refusal(th)):
            raise CmdError(why)
        return self.host.evaluate(expr, lang, po, timeout, trap_exceptions=not allow_exceptions)

    def do_cmd(self, command, timeout=60):
        return self._lldb().run(command).strip() or "(no output)"

    def do_bp(self, op, spec=None, cond=None, once=False):
        return self._lldb().breakpoint(op, spec, cond, once)

    def _in_app(self, fn, timeout: float):
        """`fn(left)` runs paused on the main thread; `left()` is the time remaining."""
        h = self.host
        if h is None or h.state not in ("running", "stopped"):
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
        h.process.SetSelectedThread(self._main_thread(h.process))
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
        return self._in_app(lambda left: self.host.evaluate(expr, self.call_lang, po, left()), timeout)
