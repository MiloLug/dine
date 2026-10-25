"""Client of an app's debug agent (iOS: native/dev/dbgagent/agent.mm; gtk: dine-atl
src/backends/ui/gtk/agent.c): one request line, one JSON reply line, over the connection the target's
`connect` makes (default: usbmux to the agent's port on the phone)."""

import asyncio
import json
import socket
import time
from typing import Callable

from .. import ios
from . import match
from .targets.base import CmdError

Labels = list[tuple[bool, str]]


class AgentDown(Exception):
    """Nothing listens on the agent port: the app isn't running or wasn't started by `ios launch`."""


class AgentClosed(CmdError):
    """The agent closed the connection unanswered, as when the app exits under it."""


def _connect(timeout: float) -> socket.socket:
    from pymobiledevice3 import usbmux
    from pymobiledevice3.exceptions import ConnectionFailedError, ConnectionFailedToUsbmuxdError

    async def connect():
        device = await usbmux.select_device()
        if device is None:
            raise CmdError("no phone on usbmux: tools/dine ios tunnel status")
        return await device.connect(ios.AGENT_PORT)
    try:
        sock = asyncio.run(asyncio.wait_for(connect(), timeout))
    except ConnectionFailedToUsbmuxdError:
        raise CmdError("usbmuxd isn't reachable: tools/dine ios tunnel status") from None
    except ConnectionFailedError:
        raise AgentDown from None
    except TimeoutError:
        raise CmdError(f"no usbmux connection to the app within {timeout:g}s") from None
    sock.setblocking(True)
    return sock


def request(line: str, timeout: float = 10, stopped: Callable[[], str | None] = lambda: None,
            connect: Callable[[float], socket.socket] = _connect) -> dict:
    """The agent's reply, or `{"stopped": where}` once `stopped()` names a stop: lldb stopping the app
    stops the agent too, so the reply would never come."""
    deadline = time.monotonic() + timeout
    verb = line.split(" ", 1)[0]
    with connect(timeout) as sock:
        sock.sendall(line.encode() + b"\n")
        buf = b""
        while not buf.endswith(b"\n"):
            where = stopped()
            if where:
                return {"stopped": where}
            left = deadline - time.monotonic()
            if left <= 0:
                raise CmdError(f"the app's debug agent didn't answer `{verb}` within {timeout:g}s")
            sock.settimeout(min(0.2, left))
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                break
            buf += chunk
    if not buf:
        raise AgentClosed(f"the app's debug agent closed the connection on `{verb}` (did the app exit?)")
    reply = json.loads(buf)
    if "error" in reply:
        raise CmdError(reply["error"])
    return reply


def labels_of(reply: dict) -> Labels:
    return [(bool(flag), label) for flag, label in reply.get("labels", [])]


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


def listing(labels: Labels) -> str:
    """`#N label` per distinct label; N is what `ui tap #N` sends."""
    seen = set()
    lines = []
    for i, (_, label) in enumerate(labels):
        if label not in seen:
            seen.add(label)
            lines.append(f"#{i} {label}")
    return "\n".join(lines) or "(no accessibility elements)"


def screen(labels: Labels) -> str:
    return " | ".join(dict.fromkeys(label for _, label in labels)) or "(no accessibility elements)"
