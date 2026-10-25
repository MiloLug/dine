"""`ui` commands through an app's debug agent (agent.py's wire format), for the targets that have one."""

from __future__ import annotations

import json

from .. import agent, match
from .base import CmdError


class AgentUi:
    """Mixin for a Target. It provides `_request(line, timeout)` (raises agent.AgentDown when nothing
    listens), `_stopped_at()` (where lldb holds the app, or None), `_no_agent()` and `_went_away()`
    (what to say when the agent is missing before or after an action), and sets `_ui = []`."""

    def _agent(self, line: str, timeout: float = 10) -> dict:
        if where := self._stopped_at():
            raise CmdError(f"the app is stopped at {where} and can't answer UI requests: tools/dine dbg continue")
        try:
            return self._request(line, timeout)
        except agent.AgentDown:
            raise CmdError(self._no_agent()) from None

    def _ls(self) -> agent.Labels:
        self._ui = agent.labels_of(self._agent("ls"))
        return self._ui

    def _settle(self) -> tuple[str, dict]:
        """Waits for the screen the last tap/back led to; text to append, and the reply. No stop check
        first: a tap into a breakpoint stops the app right after the tap's reply."""
        try:
            r = self._request("settle 3000", 8)
        except agent.AgentDown:
            raise CmdError(self._went_away()) from None
        if "stopped" in r:
            return f"; stopped at {r['stopped']}", r
        self._ui = agent.labels_of(r)
        if not r["ran"]:
            return "; the app's main thread hasn't run it yet after 3 s (busy?)", r
        return "\nscreen: " + agent.screen(self._ui) + ("" if r["settled"] else " (still changing after 3 s)"), r

    def _pick(self, arg: str) -> int:
        if arg.startswith("#") and arg[1:].isdigit():
            i = int(arg[1:])
            if i >= len(self._ui):
                raise CmdError(f"no {arg} in the last `ui ls` ({len(self._ui)} elements)")
            return i
        return agent.pick(self._ls(), arg)

    def do_ui_ls(self):
        return agent.listing(self._ls())

    def ui_find(self, label: str, timeout: float) -> str | None:
        """None also while the agent can't answer: the wait's own stop and exit checks report those."""
        if self._stopped_at():
            return None
        m = match.loose(label)
        try:
            r = self._request("ls", min(timeout, 2))
        except (agent.AgentDown, CmdError, OSError):
            return None
        return next((l for _, l in agent.labels_of(r) if m(l)), None)

    def do_ui_tap(self, arg=None, timeout=60):
        if not arg:
            raise CmdError("usage: tools/dine dbg ui tap <label|#N>")
        i = self._pick(arg)
        label = self._ui[i][1]
        self._agent(f"tap {i} {json.dumps(label)}")
        tail, r = self._settle()
        if r.get("ran") and r.get("result") is False:
            raise CmdError(f"{label!r} declined the activation (back navigation: tools/dine dbg ui back)")
        return f"tapped {label!r}" + tail

    def do_ui_type(self, arg=None, text=None, timeout=60):
        if not arg or text is None:
            raise CmdError("usage: tools/dine dbg ui type <label|#N> <text>")
        i = self._pick(arg)
        label = self._ui[i][1]
        self._agent(f"type {i} {json.dumps([label, text])}")
        tail, r = self._settle()
        if r.get("ran") and r.get("result") is False:
            raise CmdError(f"{label!r} takes no text (not a text field, or it can't take the focus)")
        return f"typed {text!r} into {label!r}" + tail
