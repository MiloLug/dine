"""Backend seam: what a debug target provides to the server. A target is fixed per server."""

from ..logstore import LogStore


class Unsupported(Exception):
    pass


class CmdError(Exception):
    """A command can't run in the current state; the message names the explicit fix."""


class Target:
    name = "?"
    # what to run when the app is left stopped
    relaunch = "relaunch the app"
    # what starts capturing the app's log
    capture = "tools/dine dbg syslog start"
    # `wait --stop`/`--exit` with no process to watch
    no_process = "nothing attached: tools/dine dbg attach"

    # Client side, before the server is spawned.
    @classmethod
    def preflight(cls, app: str) -> None:
        pass

    @classmethod
    def server_env(cls) -> dict[str, str]:
        return {}

    # Server side. Every method returns text for the client or raises CmdError.
    def __init__(self, store: LogStore, app: str):
        self.store = store
        self.app = app

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
        """The app's exit gets logged although nothing is attached."""
        return False

    def is_app_line(self, text: str) -> bool:
        """`log --app`: a captured line of the app's own, not a system framework's."""
        return True

    def ui_find(self, label: str, timeout: float) -> str | None:
        raise Unsupported(f"UI isn't supported by target {self.name}")

    def __getattr__(self, name):
        if name.startswith("do_"):
            def unsupported(**_):
                raise Unsupported(f"`{name[3:]}` isn't supported by target {self.name}")
            return unsupported
        raise AttributeError(name)
