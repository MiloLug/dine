"""Client side of `dine dbg`: talk to the server, and start/stop it."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from .. import paths
from . import session
from .targets import TARGETS

NOT_RUNNING = 4
# Slack on top of the command's own deadline: the server's lock wait (5 s) and interrupt (5 s).
MARGIN = 15


class NotRunning(Exception):
    pass


def call(cmd: str, args: dict | None = None, timeout: float = 30, max_lines: int = 60,
         argv: str | None = None) -> dict:
    if session.server_pid() is None:
        raise NotRunning
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout + MARGIN)
    try:
        s.connect(str(session.SOCKET))
        s.sendall((json.dumps({"cmd": cmd, "args": args or {}, "timeout": timeout, "max_lines": max_lines,
                               "argv": argv, "code": session.code_fingerprint()}) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    except (FileNotFoundError, ConnectionRefusedError):
        raise NotRunning from None
    except socket.timeout:
        return {"code": 1, "text": f"no answer from the server within {timeout + MARGIN:g}s "
                                   "(tools/dine dbg status; its log: tools/dine dbg log path)"}
    finally:
        s.close()
    if not buf:
        return {"code": 1, "text": "server closed the connection without answering"}
    return json.loads(buf)


def start_server(target: str, app: str, timeout: float) -> tuple[int, str]:
    pid = session.server_pid()
    if pid:
        return 1, f"already running (pid {pid}, session {session.CURRENT.resolve()}); " \
                  "one server at a time: tools/dine dbg stop-server first"
    session.clear_stale()
    cls = TARGETS[target]
    cls.preflight(app)
    directory = session.new_session_dir()
    env = {**os.environ, **cls.server_env()}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(paths.PY), env.get("PYTHONPATH")]))
    log = open(directory / "server.log", "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "dine.dbg.server", "--target", target, "--app", app,
         "--session", str(directory)],
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env,
        cwd=paths.ROOT, start_new_session=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return 1, f"server exited with {proc.returncode} during setup:\n{_tail(directory / 'server.log')}"
        if session.server_pid() == proc.pid and session.SOCKET.exists():
            st = call("status", timeout=10)
            return st["code"], st["text"]
        time.sleep(0.2)
    proc.terminate()
    return 1, f"server not ready after {timeout:g}s, terminated:\n{_tail(directory / 'server.log')}"


def _tail(path: Path, n: int = 20) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-n:])
    except OSError:
        return "(no log)"
