"""`dine dbg smoke`: an app's smoke checks as one deterministic run through the debug server. These
tables are what "smoke" means; docs point here instead of listing the steps."""

import time
from dataclasses import dataclass
from typing import Callable

from .. import ios, paths
from ..paths import DineError
from . import client


@dataclass
class Step:
    title: str
    tap: str | None = None
    back: bool = False
    action: str | None = None  # an accessibility custom action's name
    ok: tuple[str, ...] = ()    # regexes that must all show up in the app's syslog
    fail: tuple[str, ...] = ()  # any of these ends the step as failed
    network: bool = False
    timeout: float = 60


@dataclass
class Scenario:
    name: str
    steps: list[Step]
    uses_vm: bool = False   # creates the process's one Java VM
    needs_clean: bool = False  # ATL: needs a process without a VM, and runs once per process
    check: Callable[[int], str | None] | None = None  # after the steps: (seq at start) -> problem or None
    alive: bool = False     # the app must still run afterwards


def viewtree_problem(log: str, golden: str) -> str | None:
    """`viewtree:` lines of a `log grep --text` listing against the Linux golden file's."""
    got = [line.rstrip() for line in log.splitlines() if line.startswith("viewtree:")]
    want = [line.rstrip() for line in golden.splitlines()]
    if got == want:
        return None
    return "viewtree differs from the Linux golden:\n  got:  " + "\n        ".join(got) + \
        "\n  want: " + "\n        ".join(want)


def _demo_viewtree(since: int) -> str | None:
    resp = client.call("log", {"op": "grep", "pattern": "viewtree:", "since": since, "src": ["syslog"],
                               "text": True, "n": 500})
    return viewtree_problem(resp["text"], (paths.ROOT / "dine-atl/tests/headless/demo_app.viewtree").read_text())


# The app's own log line that says it started; checked after every relaunch.
STARTUP = {"Dine": r"loaded \d+ apps"}
ART_FAIL = ("art main threw", "a run is still active")
ATL_FAIL = ("atl already ran", "atl needs a process without a VM", r"atl main returned (?!0\b)")
NAV_LIST_FAIL = (r"nav: list \d", "nav: list canceled")  # an answer nobody gave

SCENARIOS = {
    "Dine": [
        Scenario("hello", [
            Step("hello++", tap="hello++", ok=(r"Dine native: Hello from C\+\+",)),
            Step("back", back=True),
        ]),
        Scenario("probe", [
            Step("probe", tap="probe", ok=(r"probe done \d+ ok 0 fail",), fail=(r"probe done \d+ ok [1-9]",)),
            Step("back", back=True),
        ]),
        Scenario("atl-demo", [
            Step("atl", tap="atl"),
            Step("run demo", tap="run demo", ok=("onResume", "viewtree: end", "nav: container shown demo_app"),
                 fail=ATL_FAIL, timeout=120),
            Step("Home", action="Home", ok=("nav: launcher root",)),
        ], uses_vm=True, needs_clean=True, check=_demo_viewtree),
        Scenario("atl-looper", [
            Step("atl", tap="atl"),
            Step("run looper", tap="run looper", ok=("looper done", "atl main returned 0", "nav: container dismissed exit"),
                 fail=ATL_FAIL, timeout=120),
            Step("back", back=True),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-dialog", [
            Step("atl", tap="atl"),
            Step("run dialog", tap="run dialog", ok=("dialog: presented",), fail=ATL_FAIL, timeout=120),
            Step("Yes", tap="Yes", ok=("dialog onClick -1", "dialog: presented"), fail=ATL_FAIL),
            Step("Green", tap="Green", ok=("dialog onClick 1", "dialog done", "nav: container dismissed exit"),
                 fail=ATL_FAIL),
            Step("back", back=True),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-nav", [
            Step("atl", tap="atl"),
            Step("run nav", tap="run nav", ok=("nav: B onResume", "nav: container shown nav"), fail=ATL_FAIL,
                 timeout=120),
            Step("Back", action="Back", ok=("nav: B onDestroy", "nav: A onResume"), fail=ATL_FAIL),
            Step("back on the task root", back=True,
                 ok=("nav: A onStop", "nav: container dismissed back", "nav: launcher root"), fail=ATL_FAIL),
            Step("Recent apps", action="Recent apps", ok=("nav: apps list shown",)),
            Step("back to app", tap="back to app", ok=("nav: A onRestart", "nav: A onResume", "nav: container shown nav"),
                 fail=ATL_FAIL),
            Step("Home", action="Home", ok=("nav: A onStop", "nav: launcher root"), fail=ATL_FAIL),
            # A showed its list in that onStop, while in the back: it waits for the front
            Step("Recent apps, list held", action="Recent apps", ok=("nav: apps list shown",)),
            Step("back to app, list shown", tap="back to app", ok=("nav: container shown nav", "dialog: presented"),
                 fail=ATL_FAIL + NAV_LIST_FAIL),
            Step("Home with the list", action="Home", ok=("nav: container dismissed home", "nav: A onStop"),
                 fail=ATL_FAIL + NAV_LIST_FAIL),
            Step("Recent apps, list held again", action="Recent apps", ok=("nav: apps list shown",)),
            Step("back to app, list again", tap="back to app", ok=("nav: container shown nav", "dialog: presented"),
                 fail=ATL_FAIL + NAV_LIST_FAIL),
            Step("Odd item", tap="Odd ��\U0001f600��", ok=("dialog: closed", "nav: list 1"),
                 fail=ATL_FAIL + ("nav: list canceled",)),
            Step("Home at the end", action="Home", ok=("nav: A onStop", "nav: launcher root"), fail=ATL_FAIL),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("art", [
            Step("art", tap="art", ok=("art probe done",)),
            Step("run hello", tap="run hello", ok=("Hello from dine runtime tests", "art main returned"),
                 fail=ART_FAIL),
            Step("run jni args", tap="run jni args", ok=("jni args ok", "art main returned"),
                 fail=("jni args failed", *ART_FAIL)),
            Step("run https", tap="run https", ok=("https ok", "art main returned"), fail=ART_FAIL,
                 network=True, timeout=120),
            Step("run park", tap="run park", ok=("park ok", "art main returned"),
                 fail=("park failed", *ART_FAIL)),
            Step("back", back=True),
        ], uses_vm=True),
    ],
}


def listing(app: str) -> str:
    lines = []
    for sc in table(app):
        flags = [f for f, on in (("fresh process", sc.needs_clean), ("app stays up", sc.alive)) if on]
        lines.append(f"{sc.name}" + (f" ({', '.join(flags)})" if flags else ""))
        for st in sc.steps:
            what = f"tap {st.tap!r}" if st.tap else f"action {st.action!r}" if st.action else \
                "back" if st.back else st.title
            lines.append(f"  {what}" + (f"; wait for {', '.join(st.ok)}" if st.ok else "")
                         + (" [--network]" if st.network else ""))
    return "\n".join(lines)


def table(app: str) -> list[Scenario]:
    if app not in SCENARIOS or app not in STARTUP:
        raise DineError(f"no smoke checks for {app} in {__file__}")
    return SCENARIOS[app]


def fail_hit(text: str, fail: tuple[str, ...]) -> str | None:
    lines = text.splitlines()
    return next((f for f in fail if any(line.startswith(f"matched --log-re {f!r}") for line in lines)), None)


def run(app: str, names: list[str], network: bool, relaunch: Callable[[], int], out=print) -> int:
    """Relaunches before the first scenario and before ATL ones that need a clean process; exit 1 at
    the first failure."""
    scenarios = table(app)
    known = {sc.name: sc for sc in scenarios}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise DineError(f"no smoke scenario {', '.join(unknown)}; there are: {', '.join(known)}")
    chosen = [known[n] for n in names] if names else scenarios
    begin = time.monotonic()
    pid, dirty = None, False
    for sc in chosen:
        if pid is None or (sc.needs_clean and dirty):
            t = time.monotonic()
            pid, dirty = relaunch(), False
            resp = client.call("wait", {"log_re": [STARTUP[app]], "since": "mark"}, timeout=30)
            if resp["code"]:
                out(f"relaunch: FAILED waiting for {STARTUP[app]!r}\n{resp['text']}")
                return 1
            out(f"relaunched {app} pid {pid} ({time.monotonic() - t:.1f} s)")
        start = client.call("status")["cursor"]
        for st in sc.steps:
            if st.network and not network:
                out(f"{sc.name}: {st.title}: skipped (needs --network)")
                continue
            t = time.monotonic()
            if st.tap or st.back or st.action:
                resp = client.call("ui_tap", {"arg": st.tap}, timeout=30) if st.tap else \
                    client.call("ui_action", {"arg": st.action}, timeout=30) if st.action else \
                    client.call("ui_back", {}, timeout=30)
                if resp["code"]:
                    out(f"{sc.name}: {st.title}: FAILED\n{resp['text']}")
                    return 1
            for ok in st.ok:
                resp = client.call("wait", {"log_re": [ok, *st.fail], "since": "mark"}, timeout=st.timeout)
                hit = fail_hit(resp["text"], st.fail)
                if resp["code"] or hit:
                    out(f"{sc.name}: {st.title}: FAILED" + (f" ({hit})" if hit else f" waiting for {ok!r}")
                        + f"\n{resp['text']}")
                    return 1
            out(f"{sc.name}: {st.title}: ok ({time.monotonic() - t:.1f} s)")
        problem = sc.check(start) if sc.check else None
        if sc.alive and not any(p["pid"] == pid for p in ios.processes(app)):
            problem = f"{app} pid {pid} is gone"
        if problem:
            out(f"{sc.name}: FAILED: {problem}")
            return 1
        dirty = dirty or sc.uses_vm
    out(f"smoke passed: {', '.join(sc.name for sc in chosen)} ({time.monotonic() - begin:.0f} s)")
    return 0

