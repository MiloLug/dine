"""Dine's side of an app's UI agent: uidrive's client (PROTOCOL.md in github.com/MiloLug/dine-uidrive)
with Dine's label matching and wording. iOS: the injected uidrive agent, reached over usbmux; gtk:
dine-atl src/backends/ui/gtk/agent.c, which speaks the same protocol over the Unix socket the
target's `connect` opens."""

import math
import socket
from typing import Callable

import uidrive.client

from . import match
from .targets.base import CmdError

Labels = list[tuple[bool, str]]


class AgentDown(Exception):
    """Nothing listens on the agent port: the app isn't running or wasn't started by `ios launch`."""


class AgentClosed(CmdError):
    """The agent closed the connection unanswered, as when the app exits under it."""


def _connect(timeout: float) -> socket.socket:
    import uidrive.ios   # pymobiledevice3's modules are slow to import; only a request to the phone needs them
    try:
        return uidrive.ios.connect(uidrive.ios.DEFAULT_PORT, timeout)
    except uidrive.ios.NoDevice:
        raise CmdError("no phone on usbmux: tools/dine ios tunnel status") from None
    except uidrive.ios.UsbmuxUnreachable:
        raise CmdError("usbmuxd isn't reachable: tools/dine ios tunnel status") from None
    except uidrive.client.AgentTimeout:
        raise CmdError(f"no usbmux connection to the app within {timeout:g}s") from None
    except uidrive.client.AgentDown:
        raise AgentDown from None


def request(line: str, timeout: float = 10, stopped: Callable[[], str | None] = lambda: None,
            connect: Callable[[float], socket.socket] = _connect) -> dict:
    """The agent's reply, or `{"stopped": where}` once `stopped()` names a stop: lldb stopping the app
    stops the agent too, so the reply would never come."""
    verb = line.split(" ", 1)[0]
    try:
        return uidrive.client.request(line, connect, timeout, interrupt=stopped)
    except uidrive.client.Interrupted as e:
        return {"stopped": e.value}
    except uidrive.client.AgentTimeout:
        raise CmdError(f"the app's debug agent didn't answer `{verb}` within {timeout:g}s") from None
    except uidrive.client.AgentClosed:
        raise AgentClosed(f"the app's debug agent closed the connection on `{verb}` (did the app exit?)") from None
    except uidrive.client.AgentError as e:
        raise CmdError(str(e)) from None
    except uidrive.client.AgentDown:
        raise AgentDown from None


def labels_of(reply: dict) -> Labels:
    return [(bool(flag), label) for flag, label in reply.get("labels", [])]


def frames_of(reply: dict) -> list[tuple[float, float, float, float]]:
    """Each label's frame `(x, y, w, h)` in screen points, parallel to labels_of; gtk's agent sends none."""
    return [tuple(map(float, f)) for f in reply.get("frames", [])]


def parse_point(arg: str) -> tuple[float, float] | None:
    """`@X,Y` as a screen point; None for anything else (a label or `#N`)."""
    if not arg.startswith("@"):
        return None
    try:
        x, y = map(float, arg[1:].split(","))
    except ValueError:
        x = y = math.nan
    if not (math.isfinite(x) and math.isfinite(y)):
        raise CmdError(f"bad point {arg!r}: @X,Y with finite numbers in screen points")
    return x, y


def values_of(reply: dict) -> list[str | None]:
    """What each label's element holds (a text field's text), parallel to labels_of."""
    return list(reply.get("values", []))


def pick(labels: Labels, query: str) -> int:
    """Index of the element `query` names: loose match; an exact label beats looser ones, and an
    accessibility element beats a container with the same label."""
    m = match.loose(query)
    hits = [i for i, (_, label) in enumerate(labels) if m(label)]
    if not hits:
        raise CmdError(f"no element matches {query!r}; labels: " + ", ".join(sorted({l for _, l in labels})))
    exact = [i for i in hits if labels[i][1].lower() == query.lower()]
    names = sorted({labels[i][1] for i in hits})
    if len(names) > 1 and not exact:
        raise CmdError(f"{query!r} is ambiguous: " + ", ".join(names))
    pool = exact or hits
    return next((i for i in pool if labels[i][0]), pool[0])


def listing(labels: Labels, values: list[str | None] | None = None) -> str:
    """`#N label` per distinct label, `#N label = value` for an element with a value; `#N` names that
    element in `ui activate` and `ui insert`."""
    seen = set()
    lines = []
    for i, (_, label) in enumerate(labels):
        if label not in seen:
            seen.add(label)
            value = values[i] if values and i < len(values) else None
            lines.append(f"#{i} {label}" + (f" = {value}" if value else ""))
    return "\n".join(lines) or "(no accessibility elements)"


def screen(labels: Labels) -> str:
    return " | ".join(dict.fromkeys(label for _, label in labels)) or "(no accessibility elements)"
