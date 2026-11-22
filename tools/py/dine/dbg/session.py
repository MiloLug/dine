"""Where the one debug server lives: socket, pid file, and per-session log dirs."""

import datetime
import fcntl
import hashlib
import os
import shutil
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
# Never imported by the server.
CLIENT_ONLY = {"__main__.py", "cli.py", "linux.py", "dbg/client.py", "dbg/smoke.py"}
STALE = "warning: the server runs older dbg code"   # starts a reply of a server the edits passed by

# Fixed, not $TMPDIR: a sandboxed shell may set its own TMPDIR and then miss the running server.
BASE = Path(os.environ.get("DINE_DBG_DIR", "/tmp/dine-dbg"))
SOCKET = BASE / "server.sock"
PIDFILE = BASE / "server.pid"
LOCK = BASE / "server.lock"
SESSIONS = BASE / "sessions"
CURRENT = BASE / "current"
KEEP = 10


def lock() -> int | None:
    """The lock of the one server, as an fd, or None while another holds it. start-server takes it
    before it touches the session and hands it to the server, which keeps it until it exits."""
    BASE.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def locked() -> bool:
    fd = lock()
    if fd is None:
        return True
    os.close(fd)
    return False


def server_pid() -> int | None:
    """The live server's pid; a pidfile left by a killed server whose pid got reused doesn't count."""
    try:
        pid = int(PIDFILE.read_text())
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (OSError, ValueError):
        return None
    return pid if b"dine.dbg.server" in cmdline else None


def new_session_dir() -> Path:
    SESSIONS.mkdir(parents=True, exist_ok=True)
    name = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = SESSIONS / name
    n = 1
    while d.exists():
        n += 1
        d = SESSIONS / f"{name}-{n}"
    d.mkdir()
    CURRENT.unlink(missing_ok=True)
    CURRENT.symlink_to(d)
    for old in sorted(p for p in SESSIONS.iterdir() if p.is_dir())[:-KEEP]:
        shutil.rmtree(old, ignore_errors=True)
    return d


def code_fingerprint() -> str:
    """Changes when the server's Python changes: a server older than that runs stale code."""
    h = hashlib.sha1()
    for p in sorted(PACKAGE.rglob("*.py")):
        if not p.name.startswith("test_") and p.relative_to(PACKAGE).as_posix() not in CLIENT_ONLY:
            st = p.stat()
            h.update(f"{p}:{st.st_size}:{st.st_mtime_ns}".encode())
    return h.hexdigest()[:12]


def clear() -> None:
    """Only under the lock: the socket and pid file are then one's own or a dead server's."""
    SOCKET.unlink(missing_ok=True)
    PIDFILE.unlink(missing_ok=True)
