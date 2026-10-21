"""`dine dbg smoke`: an app's smoke checks as one deterministic run through the debug server. These
tables are what "smoke" means; docs point here instead of listing the steps."""

import re
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
    ui: tuple[str, ...] = ()    # accessibility labels that must all show up, after ok
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


_VIEWTREE_LINE = re.compile(r'viewtree: ( *)(\S+) (-?\d+),(-?\d+) (\d+)x(\d+)( ".*")?$')


@dataclass
class _Node:
    depth: int
    name: str
    x: int
    y: int
    w: int
    h: int
    text: str | None
    prev: "_Node | None" = None  # the previous sibling


def _viewtree(lines: list[str]) -> list[_Node] | None:
    nodes: list[_Node] = []
    for line in lines[:-1]:
        m = _VIEWTREE_LINE.match(line)
        if not m:
            return None
        node = _Node(len(m[1]) // 2, m[2], int(m[3]), int(m[4]), int(m[5]), int(m[6]), m[7])
        node.prev = next((n for n in reversed(nodes) if n.depth <= node.depth), None)
        if node.prev and node.prev.depth != node.depth:
            node.prev = None
        nodes.append(node)
    return nodes


def _shape_problem(got: _Node, want: _Node, root: tuple[_Node, _Node]) -> str | None:
    if (got.depth, got.name, got.text) != (want.depth, want.name, want.text):
        return "another view"
    if got.x != want.x:
        return "another x"
    if want.y == 0 and got.y != 0:
        return "y not 0"
    if want.prev and want.y == want.prev.y + want.prev.h and got.y != got.prev.y + got.prev.h:
        return "not below its previous sibling"
    if want.text is not None and (got.w <= 0 or got.h <= 0):
        return "empty text"
    if want.text is None and (want.w, want.h) == (root[1].w, root[1].h) and (got.w, got.h) != (root[0].w, root[0].h):
        return "doesn't fill the window"
    return None


def viewtree_problem(log: str, golden: str) -> str | None:
    """`viewtree:` lines of a `log grep --text` listing against the Linux golden file's: their shape
    (`_shape_problem`), since window and text sizes differ on the phone."""
    got_lines = [line.rstrip() for line in log.splitlines() if line.startswith("viewtree:")]
    want_lines = [line.rstrip() for line in golden.splitlines()]
    got, want = _viewtree(got_lines), _viewtree(want_lines)
    problem = None
    if got is None or want is None or got_lines[-1:] != ["viewtree: end"] or len(got) != len(want) or not want:
        problem = "another tree"
    else:
        problem = next((f"line {i + 1}: {p}" for i, (g, w) in enumerate(zip(got, want))
                        if (p := _shape_problem(g, w, (got[0], want[0])))), None)
    if not problem:
        return None
    return f"viewtree differs from the Linux golden ({problem}):\n  got:  " + "\n        ".join(got_lines) + \
        "\n  want: " + "\n        ".join(want_lines)


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
            Step("run demo", tap="demo_app", ok=("onResume", "viewtree: end", "nav: container shown demo_app"),
                 ui=("hello PoC world!", "second one (static)"), fail=ATL_FAIL, timeout=120),
            Step("Home", action="Home", ok=("nav: launcher root",)),
        ], uses_vm=True, needs_clean=True, check=_demo_viewtree),
        Scenario("atl-looper", [
            Step("atl", tap="atl"),
            Step("run looper", tap="looper", ok=("looper done", "atl main returned 0", "nav: container dismissed exit"),
                 fail=ATL_FAIL, timeout=120),
            Step("back", back=True),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-views", [
            Step("atl", tap="atl"),
            # c was laid out before its free; a layout pass after it walks the records without it
            Step("run views", tap="views", ok=("dialogfreed:", "drawablefreed:", 'viewfreed: android.widget.TextView "c"',
                                               "views row attached true", "views matrix 0,1 paint 2.0", "nav: frame fullscreen true",
                                               "views widgets", "views done", "atl main returned 0", "nav: container dismissed exit"),
                 fail=ATL_FAIL + ("native_1destructor", "native_1removeView", "nativeDestroy", "native_1unref"),
                 timeout=120),
            Step("back", back=True),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-widgets", [
            Step("atl", tap="atl"),
            Step("run widgets", tap="widgets", ok=("widgets shown", "nav: frame fullscreen true"), ui=("widgets fullscreen",),
                 fail=ATL_FAIL, timeout=120),
            Step("windowed after 5 s", ok=("widgets fullscreen off", "nav: frame fullscreen false"), ui=("widgets windowed",),
                 fail=ATL_FAIL),
            Step("Home", action="Home", ok=("nav: launcher root",)),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-dialog", [
            Step("atl", tap="atl"),
            Step("run dialog", tap="dialog", ok=("dialog: presented",), fail=ATL_FAIL, timeout=120),
            Step("Yes", tap="Yes", ok=("dialog onClick -1", "dialog: presented"), fail=ATL_FAIL),
            Step("Green", tap="Green", ok=("dialog onClick 1", "dialog done", "nav: container dismissed exit"),
                 fail=ATL_FAIL),
            Step("back", back=True),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-nav", [
            Step("atl", tap="atl"),
            # px at 3x: 20 pt side strips, the home indicator at the bottom; B excludes 200-300 px of its right edge
            Step("run nav", tap="nav", ok=("nav: B onResume", "nav: container shown nav",
                                          r"nav: B insets 60 0 60 [1-9]\d* 0 0 0 [1-9]\d* 0 0 0 [1-9]\d*",
                                          "nav: exclusion left 0 right 1"), fail=ATL_FAIL, timeout=120),
            Step("Back", action="Back", ok=("nav: B onDestroy", "nav: A onResume", "nav: exclusion left 0 right 0"),
                 fail=ATL_FAIL),
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
                         + (f"; shows {', '.join(map(repr, st.ui))}" if st.ui else "")
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
            else:
                # it waits for what earlier steps set off: lines from before it would match too early
                client.call("note", {"kind": "smoke", "text": st.title, "mark": True})
            for ok in st.ok:
                resp = client.call("wait", {"log_re": [ok, *st.fail], "since": "mark"}, timeout=st.timeout)
                hit = fail_hit(resp["text"], st.fail)
                if resp["code"] or hit:
                    out(f"{sc.name}: {st.title}: FAILED" + (f" ({hit})" if hit else f" waiting for {ok!r}")
                        + f"\n{resp['text']}")
                    return 1
            for label in st.ui:
                resp = client.call("wait", {"ui": [label]}, timeout=st.timeout)
                if resp["code"]:
                    out(f"{sc.name}: {st.title}: FAILED waiting for {label!r} on screen\n{resp['text']}")
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

