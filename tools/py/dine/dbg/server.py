"""The debug server: one process per session, driven over a Unix socket by `dine dbg …`.

Run by `tools/dine dbg start-server` only: `python -m dine.dbg.server --target T --app A --session DIR`.
"""

import argparse
import inspect
import json
import os
import re
import signal
import socket
import threading
import time
import traceback
from pathlib import Path

from . import session, wait
from .. import ios
from ..paths import DineError
from .logstore import LogStore, bare, path_for, render
from .targets import TARGETS
from .targets.base import CmdError, Unsupported

# Never touch lldb, so they can't queue behind a stuck lldb command.
UNLOCKED = {"interrupt", "syslog_start", "syslog_stop", "fake", "ui_ls", "ui_tap", "ui_back", "ui_screenshot"}
# Start something that later shows up as events; `wait --since mark` starts before them.
ACTIONS = {"attach", "continue", "interrupt", "step", "next", "finish", "stepi", "cmd", "ui_tap", "ui_back",
           "call", "syslog_start", "fake"}
# Output of these isn't worth a copy in the cmd log.
QUIET = {"status", "log", "wait", "note"}
DEFAULT_SRCS = ("syslog", "event", "lldb")


class Server:
    def __init__(self, target_name: str, app: str, directory: Path):
        self.dir = directory
        self.store = LogStore(directory)
        self.target = TARGETS[target_name](self.store, app)
        self.target_name, self.app = target_name, app
        self.started = time.time()
        self.code = session.code_fingerprint()
        # Seq before the latest `ios launch`: where `log` listings start by default.
        self.run_start = 0
        self.lock = threading.Lock()
        self.busy: tuple[str, float] | None = None
        self.stopping = threading.Event()
        self.shut_down = False

    def handle(self, req: dict) -> dict:
        cmd = req.get("cmd", "")
        args = req.get("args") or {}
        timeout = float(req.get("timeout") or 30)
        max_lines = int(req.get("max_lines") or 60)
        code = 0
        try:
            server_fn = getattr(self, f"cmd_{cmd}", None)
            if server_fn:
                text, code = server_fn(timeout=timeout, **args)
            else:
                fn = getattr(self.target, f"do_{cmd}")
                if cmd in ACTIONS:
                    self.store.set_mark()
                kw = dict(args)
                if _accepts(fn, "timeout"):
                    kw["timeout"] = timeout
                if cmd == "interrupt" and self.busy:
                    text = self._interrupt_busy()
                    if self.target.state().get("state") == "running":
                        text += "\n" + fn(**kw)
                else:
                    text = fn(**kw) if cmd in UNLOCKED else self._locked(cmd, lambda: fn(**kw), timeout)
        except (CmdError, Unsupported, DineError) as e:
            text, code = str(e), 1
        except TypeError as e:
            text, code = f"bad arguments for {cmd}: {e}", 1
        except Exception as e:
            traceback.print_exc()
            text, code = f"internal error in {cmd}: {type(e).__name__}: {e} (see {self.dir}/server.log)", 1
        line = req.get("argv") or cmd
        seq = self.store.append("cmd", cmd, f"$ {line}  → exit {code}" if cmd in QUIET
                                else f"$ {line}  → exit {code}\n{text}")
        hint = "narrow it: -n, --src, log grep" if cmd in QUIET else f"tools/dine dbg log show {seq}"
        if req.get("code") and req["code"] != self.code:
            text = ("warning: the server runs older dbg code: tools/dine dbg stop-server; "
                    "tools/dine dbg start-server\n" + text)
        resp = {"code": code, "text": clip(text, max_lines, hint), "cursor": self.store.cursor, "seq": seq}
        if cmd == "status":
            resp["state"] = self.target.state()
            resp["app"] = self.app
        return resp

    def _interrupt_busy(self) -> str:
        busy = self.busy
        name = busy[0] if busy else "?"
        self.target.interrupt_command(True)
        deadline = time.monotonic() + 5
        while self.busy and time.monotonic() < deadline:
            time.sleep(0.1)
        self.target.interrupt_command(False)
        text = f"interrupted `{name}`" + (" (still busy: tools/dine dbg status)" if self.busy else "")
        self.store.append("event", "interrupted", text)
        return text

    def _locked(self, cmd: str, fn, timeout: float):
        if not self.lock.acquire(timeout=min(timeout, 5)):
            name, since = self.busy or ("?", time.monotonic())
            raise CmdError(f"busy: `{name}` running for {time.monotonic() - since:.0f}s; "
                           "tools/dine dbg interrupt, or wait for it")
        self.busy = (cmd, time.monotonic())
        result: dict = {}

        def work():
            try:
                result["value"] = fn()
            except BaseException as e:
                result["error"] = e
            finally:
                self.busy = None
                self.lock.release()

        t = threading.Thread(target=work, name=f"cmd-{cmd}", daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            self.target.interrupt_command(True)
            t.join(5)
            self.target.interrupt_command(False)
            raise CmdError(f"`{cmd}` timed out after {timeout:g}s"
                           + ("; lldb is still busy with it (tools/dine dbg status)" if t.is_alive()
                              else "; interrupted"))
        if "error" in result:
            raise result["error"]
        return result["value"]

    def cmd_status(self, timeout):
        st = self.target.state()
        lines = [
            f"server pid {os.getpid()}, target {self.target_name}, app {self.app}, "
            f"up {time.time() - self.started:.0f}s",
            f"session {self.dir}",
            f"process: {st.get('state')}" + (f" pid {st['pid']}" if st.get("pid") else "")
            + (f", stopped at {st['location']}" if st.get("location") else ""),
            f"syslog: {'capturing' if self.target.syslog_running() else 'off'}",
            f"cursor {self.store.cursor}, mark {self.store.mark}",
        ]
        busy = self.busy
        if busy:
            lines.append(f"busy: `{busy[0]}` for {time.monotonic() - busy[1]:.0f}s")
        return "\n".join(lines), 0

    def cmd_note(self, timeout, kind, text, mark=False):
        """Something outside the server happened (`ios launch`/`kill`): log it; `mark` before the
        action, so `wait --since mark` sees everything the action causes."""
        if mark:
            self.store.set_mark()
        if kind == "launching":
            self.run_start = self.store.cursor
        self.store.append("event", kind, text)
        return text, 0

    def cmd_shutdown(self, timeout, kill_app=False):
        code = 0
        if self.busy:
            self._interrupt_busy()
        try:
            text = self._locked("shutdown", lambda: self.target.shutdown(kill_app), timeout)
        except CmdError as e:
            code = 1
            text = f"{e}\ncouldn't detach cleanly: the app may be left stopped (tools/dine ios kill, then relaunch)"
        # `serve` exits once this answer is sent.
        self.shut_down = True
        return (text + "\n" if text else "") + f"server stopped; logs kept in {self.dir}", code

    def cmd_wait(self, timeout, stop=False, at=None, log=(), log_re=(), exit=False, ui=(),
                 all=False, since="mark"):
        conds = []
        if at and not stop:
            stop = True
        st = self.target.state()
        if (stop or exit) and st.get("state") == "none" and not self.target.watching_exit():
            raise CmdError("nothing attached: tools/dine dbg attach")
        if (log or log_re) and not self.target.syslog_running():
            raise CmdError("syslog capture is off: tools/dine dbg syslog start")
        if stop:
            conds.append(wait.stop_cond(at))
        conds += [wait.log_cond(t) for t in log] + [wait.log_cond(t, True) for t in log_re]
        if exit:
            conds.append(wait.exit_cond())
        conds += [wait.ui_cond(label, lambda left, label=label: self.target.ui_find(label, left)) for label in ui]
        if not conds:
            raise CmdError("nothing to wait for: give --stop, --log, --log-re, --exit or --ui")
        start = {"mark": self.store.mark, "now": self.store.cursor}.get(str(since))
        if start is None:
            try:
                start = int(since)
            except ValueError:
                raise CmdError(f"--since takes mark, now or a seq number, not {since!r}") from None

        def parked():
            st = self.target.state()
            return st.get("location") or "?" if st.get("state") == "stopped" else None
        if not any(c.kind not in ("stop", "exit") for c in conds) and not st.get("attached"):
            # Detached or exited: only what's already logged can match.
            out = wait.run(self.store, conds, start, 0, all, parked)
            if out.code == wait.TIMEOUT:
                raise CmdError(f"process {st.get('state')}; nothing new can arrive for "
                               + " ".join(c.label for c in conds))
            return out.text, out.code
        out = wait.run(self.store, conds, start, timeout, all, parked, poll_every=0.25)
        return out.text, out.code

    def cmd_log(self, timeout, op="tail", n=40, src=(), since=None, pattern=None, context=0, seq=None,
                app=False, text=False):
        srcs = tuple(src) or (None if op == "show" else DEFAULT_SRCS)
        if op == "path":
            return "\n".join([str(self.dir)] + [f"  {path_for(self.dir, s)}" for s in
                                                (None, "syslog", "event", "lldb", "cmd")]), 0
        if op == "show":
            ev = self.store.get(int(seq or 0))
            if not ev:
                raise CmdError(f"no event #{seq}; cursor is {self.store.cursor}")
            return "\n".join(bare(ev) if text else render(ev)), 0
        scoped = since is None and self.run_start > 0
        evs = self.store.select(self.run_start if since is None else int(since), srcs)
        if app:
            own = f" {ios.bundle_base(self.app)}/"
            evs = [e for e in evs if e["src"] != "syslog" or own in e["text"].split(":", 1)[0] + "/"]
        heads = [f"since launch #{self.run_start + 1} (--from 0: whole session)"] if scoped else []
        if op == "grep":
            rx = re.compile(pattern or "", re.I)
            hits = [i for i, e in enumerate(evs) if rx.search(e["text"])]
            keep = sorted({j for i in hits for j in range(max(0, i - context), min(len(evs), i + context + 1))})
            picked = [evs[j] for j in keep][-n:]
            heads.append(f"{len(hits)} matches" + (f", last {n} shown" if len(keep) > n else ""))
        elif op in ("head", "since"):
            picked = evs[:n]
        else:
            picked = evs[-n:]
        lines = [line for e in picked for line in (bare(e) if text else render(e, 5))]
        more = len(evs) - len(picked) if op != "grep" else 0
        if more > 0:
            nxt = f"tools/dine dbg log since {picked[-1]['seq']}" if op in ("head", "since") else "raise -n"
            lines.append(f"… {more} more events: {nxt}")
        lines.append(f"cursor {self.store.cursor}")
        return "\n".join(heads + lines), 0

    def serve(self) -> None:
        session.SOCKET.unlink(missing_ok=True)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(session.SOCKET))
        srv.listen(16)
        srv.settimeout(0.5)
        session.PIDFILE.write_text(str(os.getpid()))
        print(f"ready: {session.SOCKET}", flush=True)
        try:
            while not self.stopping.is_set():
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                threading.Thread(target=self._conn, args=(conn,), daemon=True).start()
        finally:
            srv.close()
            session.SOCKET.unlink(missing_ok=True)

    def _conn(self, conn: socket.socket) -> None:
        with conn:
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    return
                buf += chunk
            try:
                resp = self.handle(json.loads(buf))
            except json.JSONDecodeError as e:
                resp = {"code": 1, "text": f"bad request: {e}"}
            try:
                conn.sendall((json.dumps(resp) + "\n").encode())
            except OSError:
                pass
        if self.shut_down:
            self.stopping.set()


def _accepts(fn, name: str) -> bool:
    try:
        return name in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def clip(text: str, max_lines: int, hint: str) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines] + [f"… {len(lines) - max_lines} more lines: {hint}"])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True, choices=sorted(TARGETS))
    p.add_argument("--app", required=True)
    p.add_argument("--session", required=True, type=Path)
    a = p.parse_args()
    server = Server(a.target, a.app, a.session)
    signal.signal(signal.SIGTERM, lambda *_: server.stopping.set())
    try:
        server.target.setup()
        server.serve()
        if not server.shut_down:
            server.target.shutdown(kill_app=False)
    finally:
        server.store.close()
        session.SOCKET.unlink(missing_ok=True)
        session.PIDFILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
