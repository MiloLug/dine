"""Session log: every stream and client command in one append-only list, mirrored to the session dir.
Seq numbers are the cursors clients pass back (`wait --since`, `log since`)."""

import json
import threading
import time
from pathlib import Path

SOURCES = ("syslog", "lldb", "event", "cmd")


def stamp(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts)) + f".{int(ts * 1000) % 1000:03d}"


def render(ev: dict, max_lines: int | None = None) -> list[str]:
    lines = ev["text"].splitlines() or [""]
    head = f"#{ev['seq']} {stamp(ev['ts'])} {ev['src']}/{ev['kind']}"
    if len(lines) == 1:
        return [f"{head}: {lines[0]}"]
    shown = lines if max_lines is None else lines[:max_lines]
    out = [f"{head}:"] + [f"    {line}" for line in shown]
    if len(shown) < len(lines):
        out.append(f"    … {len(lines) - len(shown)} more lines: tools/dine dbg log show {ev['seq']}")
    return out


class LogStore:
    def __init__(self, directory: Path):
        self.dir = directory
        self._events: list[dict] = []
        self._cond = threading.Condition()
        self._jsonl = open(directory / "events.jsonl", "a", buffering=1)
        self._mirrors = {s: open(directory / f"{s}.log", "a", buffering=1) for s in SOURCES}
        # Seq before the latest action command (continue, step, tap, …): `wait --since mark` starts
        # there, so an event that fires between the action and the `wait` call isn't missed.
        self.mark = 0

    @property
    def cursor(self) -> int:
        return len(self._events)

    def append(self, src: str, kind: str, text: str, **data) -> int:
        with self._cond:
            ev = {"seq": len(self._events) + 1, "ts": time.time(), "src": src, "kind": kind, "text": text}
            if data:
                ev["data"] = data
            self._events.append(ev)
            self._jsonl.write(json.dumps(ev) + "\n")
            self._mirrors[src].write("\n".join(render(ev)) + "\n")
            self._cond.notify_all()
            return ev["seq"]

    def set_mark(self) -> int:
        with self._cond:
            self.mark = self.cursor
            return self.mark

    def get(self, seq: int) -> dict | None:
        return self._events[seq - 1] if 0 < seq <= len(self._events) else None

    def select(self, since: int = 0, srcs=None) -> list[dict]:
        with self._cond:
            evs = self._events[max(since, 0):]
        return [e for e in evs if not srcs or e["src"] in srcs]

    def wait(self, seen: int, deadline: float) -> int:
        """Block until the cursor moves past `seen` or `deadline` (monotonic); return the cursor."""
        with self._cond:
            while self.cursor <= seen:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self._cond.wait(left)
            return self.cursor

    def wake(self) -> None:
        with self._cond:
            self._cond.notify_all()

    def close(self) -> None:
        self._jsonl.close()
        for f in self._mirrors.values():
            f.close()


def path_for(directory: Path, src: str | None) -> Path:
    return directory / (f"{src}.log" if src else "events.jsonl")
