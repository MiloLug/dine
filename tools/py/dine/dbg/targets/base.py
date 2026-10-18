"""Backend seam: what a debug target provides to the server. A target is fixed per server."""

from pathlib import Path

from ..logstore import LogStore


class Unsupported(Exception):
    pass


class CmdError(Exception):
    """A command can't run in the current state; the message names the explicit fix."""


class Target:
    name = "?"

    # Client side, before the server is spawned.
    @classmethod
    def preflight(cls, app: str) -> None:
        pass

    @classmethod
    def server_env(cls) -> dict[str, str]:
        return {}

    # Server side. Every method returns text for the client or raises CmdError.
    def __init__(self, store: LogStore, app: str, actions: Path | None = None):
        self.store = store
        self.app = app
        self.actions = actions

    def setup(self) -> None:
        pass

    def shutdown(self, kill_app: bool) -> str:
        return ""

    def state(self) -> dict:
        """`attached`, `state` (none|running|stopped|exited|detached), `pid`, `location` if stopped."""
        return {"attached": False, "state": "none"}

    def interrupt_command(self, on: bool) -> None:
        """Ask (on) or stop asking (off) a running lldb command to give up."""

    def syslog_running(self) -> bool:
        return False

    def watching_exit(self) -> bool:
        return False

    def ui_find(self, label: str, timeout: float) -> str | None:
        raise Unsupported(f"UI isn't supported by target {self.name}")

    def __getattr__(self, name):
        if name.startswith("do_"):
            def unsupported(**_):
                raise Unsupported(f"`{name[3:]}` isn't supported by target {self.name}")
            return unsupported
        raise AttributeError(name)
