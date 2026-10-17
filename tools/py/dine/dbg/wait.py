"""`dbg wait`: block on conditions over the session log; bounded, and fails fast when stuck."""

import time
from dataclasses import dataclass
from typing import Callable

from . import match
from .logstore import LogStore, render

OK, BLOCKED, TIMEOUT, EXITED = 0, 1, 2, 3


@dataclass
class Cond:
    label: str
    kind: str                                         # stop | log | exit | ui
    test: Callable[[dict], bool] | None = None        # event predicate
    poll: Callable[[float], str | None] | None = None  # ui: (seconds left) -> the match, or None
    hit: dict | None = None


@dataclass
class Outcome:
    code: int
    text: str


def is_stop(ev: dict) -> bool:
    return ev["src"] == "event" and ev["kind"] == "stopped"


def is_exit(ev: dict) -> bool:
    return ev["src"] == "event" and ev["kind"] == "exited"


def is_crash(ev: dict) -> bool:
    return is_stop(ev) and ev.get("data", {}).get("crash", False)


def stop_cond(at: str | None) -> Cond:
    where = match.location(at) if at else None
    return Cond(f"--stop{f' --at {at}' if at else ''}", "stop",
                lambda ev: is_stop(ev) and (where is None or where(ev["data"].get("location", {}))))


def log_cond(text: str, is_regex: bool = False) -> Cond:
    m = match.regex(text) if is_regex else match.loose(text)
    return Cond(f"--log{'-re' if is_regex else ''} {text!r}", "log",
                lambda ev: ev["src"] == "syslog" and m(ev["text"]))


def exit_cond() -> Cond:
    return Cond("--exit", "exit", lambda ev: is_exit(ev) or is_crash(ev))


def ui_cond(label: str, poll: Callable[[float], str | None]) -> Cond:
    return Cond(f"--ui {label!r}", "ui", poll=poll)


def run(store: LogStore, conds: list[Cond], since: int, timeout: float, need_all: bool = False,
        parked: Callable[[], str | None] = lambda: None, poll_every: float = 1.0, grace: float = 1.0) -> Outcome:
    """`parked` says where the process is stopped right now, or None. Stops and exits before the
    mark (the last action) are history and only matched; after it they end the wait."""
    deadline = time.monotonic() + timeout
    seen = min(since, store.cursor)
    live = max(seen, store.mark)
    next_poll = 0.0
    waiting = lambda: " ".join(c.label for c in conds if c.hit is None)

    def scan() -> dict | None:
        nonlocal seen
        for ev in store.select(seen):
            seen = ev["seq"]
            for c in conds:
                if c.hit is None and c.test and c.test(ev):
                    c.hit = ev
            if _done(conds, need_all):
                return None
            if ev["seq"] > live and (is_exit(ev) or is_stop(ev) or _syslog_ended(ev, conds)):
                return ev
        return None

    def end_early(text: str, code: int, ev: dict | None) -> Outcome:
        # lldb reports a stop before the syslog relay delivers the lines logged just ahead of it.
        if any(c.hit is None and c.kind == "log" for c in conds):
            until = time.monotonic() + grace
            while time.monotonic() < until and not _done(conds, need_all):
                store.wait(seen, until)
                scan()
        if _done(conds, need_all):
            return _matched(store, conds)
        return Outcome(code, text + (("\n" + "\n".join(render(ev))) if ev else "") + f"\ncursor {store.cursor}")

    while True:
        ev = scan()
        if _done(conds, need_all):
            return _matched(store, conds)
        if ev is not None:
            if _syslog_ended(ev, conds):
                return end_early(f"syslog capture ended while waiting for {waiting()}:", BLOCKED, ev)
            if is_exit(ev) or is_crash(ev):
                what = "crashed" if is_crash(ev) else "exited"
                return end_early(f"process {what} while waiting for {waiting()}:", EXITED, ev)
            return end_early(f"process stopped while waiting for {waiting()} (continue first):", BLOCKED, ev)

        # Stop events are logged before the state flips: parked with nothing unread is current.
        why = parked()
        if why:
            if store.cursor > seen:
                continue
            return end_early(f"process is stopped at {why}; nothing can arrive for {waiting()} "
                             "(continue first)", BLOCKED, None)

        now = time.monotonic()
        if now >= next_poll:
            for c in conds:
                if c.hit is None and c.poll:
                    found = c.poll(max(deadline - now, 1.0))
                    if found:
                        c.hit = store.get(store.append("event", "ui", found))
            if _done(conds, need_all):
                return _matched(store, conds)
            now = time.monotonic()
            next_poll = now + poll_every

        if now >= deadline:
            recent = store.select(since, ("syslog", "event", "lldb"))[-20:]
            tail = [line for ev in recent for line in render(ev, 3)]
            return Outcome(TIMEOUT, f"timeout after {timeout:g}s waiting for {waiting()}\n"
                           f"events since #{since}:" + ("\n" + "\n".join(tail) if tail else " none")
                           + _earlier(store, conds, since) + f"\ncursor {store.cursor}")
        wake = min(deadline, next_poll) if any(c.poll for c in conds) else deadline
        store.wait(seen, wake)


def _syslog_ended(ev: dict, conds: list[Cond]) -> bool:
    return ev["src"] == "event" and ev["kind"] == "syslog-ended" and \
        any(c.hit is None and c.kind == "log" for c in conds)


def _earlier(store: LogStore, conds: list[Cond], since: int) -> str:
    hits = [ev for ev in store.select(0)[:since] if any(c.test and c.test(ev) for c in conds)]
    if not hits:
        return ""
    ev = hits[-1]
    return (f"\nnote: matched before #{since} (the mark is set by each action command), "
            f"latest at #{ev['seq']}: {ev['text'][:200]}\n  see it: tools/dine dbg log show {ev['seq']}; "
            "or wait with --since 0")


def _done(conds: list[Cond], need_all: bool) -> bool:
    hits = [c.hit is not None for c in conds]
    return all(hits) if need_all else any(hits)


def _matched(store: LogStore, conds: list[Cond]) -> Outcome:
    lines = []
    for c in conds:
        if c.hit is None:
            continue
        lines.append(f"matched {c.label}:")
        lines += ["  " + line for line in render(c.hit, 10)]
    return Outcome(OK, "\n".join(lines) + f"\ncursor {store.cursor}")
