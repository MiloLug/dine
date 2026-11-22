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
    dbg: tuple[str, dict] | None = None  # a debug server command and its arguments
    says: str | None = None     # a regex that command's reply must hold
    type: tuple[str, str] | None = None  # (label, text): the text typed into that field
    appearance: str | None = None  # light, dark or system: the key window's interface style
    declined: bool = False      # the tap must be declined (a disabled control or alert action)
    ok: tuple[str, ...] = ()    # regexes that must all show up in the app's syslog
    ui: tuple[str, ...] = ()    # accessibility labels that must all show up, after ok
    gone: tuple[str, ...] = ()  # accessibility labels that must all be off the screen, after ui
    text: tuple[str, str] | None = None  # (label, text): that field shows this text, after ui and gone
    fail: tuple[str, ...] = ()  # any of these ends the step as failed
    network: bool = False
    timeout: float = 60


@dataclass
class Scenario:
    name: str
    steps: list[Step]
    uses_vm: bool = False   # creates the process's one Java VM
    needs_clean: bool = False  # starts in a process that has no VM yet
    check: Callable[[int], str | None] | None = None  # after the steps: (seq at start) -> problem or None
    alive: bool = False     # the app must still run afterwards


# a view's state (checked, scroll 0,20, ...) follows its text, and is no part of the shape
_VIEWTREE_LINE = re.compile(r'viewtree: ( *)(\S+) (-?\d+),(-?\d+) (\d+)x(\d+)( ".*")?(?: (?:checked|pressed|invisible|gone|disabled|scroll -?\d+,-?\d+|ellipsize (?:start|middle|end)))*$')


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


_LONG_CONTENT = re.compile(r"text long content (\d+) of (\d+)")


# TextActivity's long alert: its view gets the height it asks for beside the message
def _text_layout(since: int) -> str | None:
    resp = client.call("log", {"op": "grep", "pattern": "text long content", "since": since, "src": ["syslog"], "text": True, "n": 20})
    heights = [(int(m[1]), int(m[2])) for m in _LONG_CONTENT.finditer(resp["text"])]
    return None if any(got == asks for got, asks in heights) else f"the long alert's view got heights (of what it asks) {heights}"


_SPIN = re.compile(r"widgets spin (\d+) in (\d+) ms")


# DrawStayActivity's self-invalidating bar: at most one draw pass per frame of the 60 Hz display
def _spin_paced(since: int) -> str | None:
    resp = client.call("log", {"op": "grep", "pattern": "widgets spin", "since": since, "src": ["syslog"],
                               "text": True, "n": 5})
    m = _SPIN.search(resp["text"])
    if not m:
        return "no \"widgets spin\" line"
    draws, ms = int(m[1]), int(m[2])
    if draws * 1000 > 65 * ms:
        return f"{draws} draws in {ms} ms: more than one per frame"
    return None


_WINDOW_SIZE = re.compile(r"nav: window size (\d+x\d+)")
_SURFACE_SIZE = re.compile(r"nav: surface (\d+x\d+)")


# the last size Dine told ATL is the one UIKit laid the app's surface out at
def _surface_size(since: int) -> str | None:
    last = []
    for line in (_WINDOW_SIZE, _SURFACE_SIZE):
        resp = client.call("log", {"op": "grep", "pattern": line.pattern, "since": since, "src": ["syslog"],
                                   "text": True, "n": 1})
        sizes = line.findall(resp["text"])
        if not sizes:
            return f"no {line.pattern!r} line"
        last.append(sizes[-1])
    return None if last[0] == last[1] else f"the app's window is {last[0]}, its surface {last[1]}"


_LOOPER_WAIT = re.compile(r"looper (timed|untimed) wait (\d+) ms cpu (\d+) ms")


# The looper APK's two 50 ms waits, as run-looper.sh grades them: one that returns at once spins.
def _looper_waits(since: int) -> str | None:
    resp = client.call("log", {"op": "grep", "pattern": "looper .* wait", "since": since, "src": ["syslog"],
                               "text": True, "n": 5})
    waits = {m[1]: (int(m[2]), int(m[3])) for m in _LOOPER_WAIT.finditer(resp["text"])}
    for kind in ("timed", "untimed"):
        if kind not in waits:
            return f"no \"looper {kind} wait\" line"
        ms, cpu = waits[kind]
        if ms < 50 or cpu >= 10:
            return f"the {kind} wait spun or was cut short: {ms} ms, cpu {cpu} ms"
    return None


# The app's own log line that says it started; checked after every relaunch.
STARTUP = {"Dine": r"loaded \d+ apps"}
ART_FAIL = ("art main threw", "a run is still active")
ATL_FAIL = ("atl is still starting", "atl needs a process without a VM", "atl: can't attach the app's thread",
            "or a library dir missing", r"atl (app )?main returned (?!0\b)")
# never part of a passing scenario, whatever its steps wait for
FATAL = ("UnsatisfiedLinkError", "JNI DETECTED ERROR", "Runtime aborting", "FATAL EXCEPTION",
         "hacky_uncaught_exception_handler", "atl: app exception cleared",
         r"nav: surface \d+x\d+ size constraints (?!2\b)",
         "the navigation stack will not be updated")
DIALOG_UNDER_KEYBOARD = r"keyboard: dialogbottom ime [1-9]\d* .* above false"  # atl-keyboard-dialog: ATL-160
NAV_LIST_FAIL = (r"nav: list \d", "nav: list canceled")  # an answer nobody gave
# the launcher's own button: a container left on the screen takes the escape and hides it
BACK = Step("back", back=True, ui=("Add App",))

SCENARIOS = {
    "Dine": [
        Scenario("hello", [
            Step("hello++", tap="hello++", ok=(r"Dine native: Hello from C\+\+",)),
            BACK,
        ]),
        Scenario("probe", [
            Step("probe", tap="probe", ok=(r"probe done \d+ ok 0 fail",), fail=(r"probe done \d+ ok [1-9]",)),
            BACK,
        ]),
        Scenario("atl-demo", [
            Step("atl", tap="atl"),
            Step("run demo", tap="demo_app", ok=("onResume", "viewtree: end", "nav: container shown demo_app"),
                 ui=("hello PoC world!", "second one (static)"), fail=ATL_FAIL, timeout=120),
            Step("Home", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, check=_demo_viewtree),
        Scenario("atl-looper", [
            Step("atl", tap="atl"),
            Step("run looper", tap="looper", ok=("looper laid out", "looper done", "atl main returned 0",
                                                "nav: container dismissed exit"),
                 fail=ATL_FAIL, timeout=120),
            BACK,
        ], uses_vm=True, needs_clean=True, alive=True, check=_looper_waits),
        Scenario("atl-views", [
            Step("atl", tap="atl"),
            # c was laid out before its free; a layout pass after it walks the records without it
            Step("run views", tap="views", ok=("dialogfreed:", "drawablefreed:", 'viewfreed: android.widget.TextView "c"',
                                               "views row attached true", "views matrix 0,1 paint 2.0", "nav: frame fullscreen true",
                                               "views widgets", "views done", "atl main returned 0", "nav: container dismissed exit"),
                 fail=ATL_FAIL + ("native_1destructor", "native_1removeView", "nativeDestroy", "native_1unref"),
                 timeout=120),
            BACK,
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-widgets", [
            Step("atl", tap="atl"),
            Step("run widgets", tap="widgets", ok=("widgets shown", "nav: frame fullscreen true"), ui=("widgets fullscreen",),
                 fail=ATL_FAIL, timeout=120),
            Step("windowed after 5 s", ok=("widgets fullscreen off", "nav: frame fullscreen false"), ui=("widgets windowed",),
                 fail=ATL_FAIL),
            Step("Home", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-draw", [
            Step("atl", tap="atl"),
            # the bitmap redraws start when the draws are done, before the spin
            # view pixels: the replay of the view's list (cg_list_draw) read back; metrics: Paint against the labels
            Step("run draw", tap="draw", ok=("widgets bitmap pixel ffff0000 0", "widgets pixels ok", "widgets blend ok", "widgets layers ok",
                                               "widgets view pixels ok scales 1 3", "widgets draw 3", "widgets draw done", "widgets metrics ok",
                                               "widgets bitmap redraw done"),
                 fail=ATL_FAIL + ("widgets metrics failed", r"widgets view pixels (?!ok\b)"), timeout=120),
            Step("spin", ok=(r"widgets spin \d+ in \d+ ms",), fail=ATL_FAIL),
            Step("Home", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, alive=True, check=_spin_paced),
        Scenario("atl-lists", [
            Step("atl", tap="atl"),
            Step("run lists", tap="lists", ok=(r"lists first [1-9]\d* of \d+ shown",), fail=ATL_FAIL, timeout=120),
            Step("Home", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-frames", [
            Step("atl", tap="atl"),
            Step("run frames", tap="frames", ok=("frames shown",), ui=("target text", "move"), fail=ATL_FAIL, timeout=120),
            # FramesActivity moves a text that draws nothing a screen to the right: UIKit has the new frame
            # once the accessibility walk, which lists only what is on screen, no longer finds it
            Step("move", tap="move", ok=("frames moved",), gone=("target text",), fail=ATL_FAIL),
            Step("Home", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-passes", [
            Step("atl", tap="atl"),
            # an OnPreDrawListener cancels three frames, so the view draws after its fourth call, and an
            # invalidate's after its second; a layout asked for from a global layout call is done in the same
            # pass; one asked for from every call comes at the frame rate (20 to 399 calls in the 500 ms of a
            # message that must still run)
            Step("run passes", tap="passes", ok=("passes drawn after 4 calls", "passes invalidate drawn after 2 calls", "passes round 2",
                                                 "passes frame", r"passes layouts ([2-9]\d|[1-3]\d\d) in [56]\d\d ms",
                                                 "atl main returned 0", "nav: container dismissed exit"),
                 fail=ATL_FAIL + (r"passes drawn after [0-3] calls", r"passes invalidate drawn after [01] calls"), timeout=120),
            BACK,
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-windows", [
            Step("atl", tap="atl"),
            # a dialog's window state: keep-screen-on, its exclusion rect at the left edge and its
            # share of the insets; its brightness reaches the host, which ignores it (DINE-11)
            Step("run windows state", tap="windows state",
                 ok=("state dialog shown", "state dialog laid out", "nav: keep screen on true",
                     "nav: exclusion left 1 right 0", r"state insets [1-9]\d* 0 0 0"),
                 fail=ATL_FAIL, timeout=120),
            Step("Home", action="Home", ok=("nav: launcher root", "nav: keep screen on false"), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-keyboard", [
            Step("atl", tap="atl"),
            # adjustResize: with the keyboard up the window lays out above it, so its bottom insets go
            # a window below the status bar keeps the size Dine started it with: no resize on the show
            Step("run keyboard resize", tap="keyboard resize", ok=(r"keyboard: resize ime 0 nav [1-9]\d* size",),
                 ui=("resize field",), fail=ATL_FAIL + ("nav: window size",), timeout=120),
            Step("type into the field", type=("resize field", "a"), ok=(r"keyboard: resize ime 0 nav 0 size",), fail=ATL_FAIL),
            # the keyboard's inset stays behind with the front: back in front, the bottom inset is the bar's again
            Step("Home with the keyboard", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
            Step("Recent apps", action="Recent apps", ok=("nav: apps list shown",)),
            Step("back to app", tap="back to app", ok=(r"keyboard: resize ime 0 nav [1-9]\d* size",), fail=ATL_FAIL),
            Step("Home", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-keyboard-dialog", [
            Step("atl", tap="atl"),
            # stateVisible: the keyboard comes with the dialog, which is placed above it. `ok` alone would match the first
            # layout's line, so a field under the keyboard fails; the placed window's lines carry ime 0 (ATL-165)
            Step("run keyboard dialog", tap="keyboard dialog",
                 ok=(r"keyboard: dialogbottom ime [1-9]\d* ", r"keyboard: dialogbottom ime 0 .* above true"),
                 ui=("dialogbottom field",), fail=ATL_FAIL + ("nav: window size", DIALOG_UNDER_KEYBOARD), timeout=120),
            Step("type into the field", type=("dialogbottom field", "a"), fail=ATL_FAIL + (DIALOG_UNDER_KEYBOARD,)),
            Step("Home", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-config", [
            Step("atl", tap="atl"),
            Step("run config", tap="config", ok=("config: activity created color",), fail=ATL_FAIL, timeout=120),
            # from light, whatever the phone's own: a dark switch is then a change
            Step("light first", appearance="light"),
            Step("dark", appearance="dark", ok=("config: application night 32", "config: activity night 32 color #ffaabbcc",
                                                "config: view night 32"), fail=ATL_FAIL),
            Step("light", appearance="light", ok=("config: application night 16", "config: activity night 16 color #ff112233"),
                 fail=ATL_FAIL),
            Step("system", appearance="system"),
            Step("Home", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-popup", [
            Step("atl", tap="atl"),
            Step("run windows popup", tap="windows popup", ok=("popup activity created",), fail=ATL_FAIL, timeout=120),
            Step("anchor", tap="anchor", ok=("popup shown",), ui=("one", "two"), fail=ATL_FAIL),
            Step("one", tap="one", ok=("popup row one",), fail=ATL_FAIL),
            # outside the popup: it closes (ACTION_OUTSIDE) and the tap still reaches the activity
            Step("elsewhere", tap="elsewhere", ok=("popup dismissed", "popup elsewhere"), fail=ATL_FAIL),
            # PopupMenu as iOS's own menu; the agent can't pick its items (a hand check), Back closes it
            Step("menu", tap="menu", ok=("menu: presented",), ui=("Copy", "Paste", "Bold", "More"), fail=ATL_FAIL),
            Step("Back closes the menu", back=True, ok=("menu dismissed",), fail=ATL_FAIL + ("nav: container dismissed",)),
            Step("toast", tap="toast", ok=('toast: shown "toasted"',), fail=ATL_FAIL),
            # the drop-down doesn't take the keys: the field keeps the keyboard while it shows
            Step("type into fruit", type=("fruit", "ap"), ok=("actv dropdown shown",), ui=("apple", "apricot"), fail=ATL_FAIL),
            Step("apple", tap="apple", ok=("actv text apple",), fail=ATL_FAIL),
            # the app ends (its last activity finishes) while its toast shows: the toast goes with its window
            Step("bye", tap="bye", ok=("toast: gone with its window",), fail=ATL_FAIL),
            BACK,
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-gd", [
            Step("atl", tap="atl"),
            Step("run gravity", tap="gravity", ok=("- onResume - yay!", "nav: container shown gravity"),
                 fail=ATL_FAIL + ("UnsatisfiedLinkError", "JNI DETECTED ERROR"), timeout=120),
            # the GameView redraws itself: the records draw pass's stats (test_hooks)
            Step("frames", ok=("atl frames ",), fail=ATL_FAIL + ("UnsatisfiedLinkError",), timeout=30),
            Step("Home", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-dialog", [
            Step("atl", tap="atl"),
            Step("run dialog", tap="dialog", ok=("dialog: presented",), fail=ATL_FAIL, timeout=120),
            Step("Yes", tap="Yes", ok=("dialog onClick -1", "dialog: presented"), fail=ATL_FAIL),
            Step("Green", tap="Green", ok=("dialog onClick 1", "dialog done", "nav: container dismissed exit"),
                 fail=ATL_FAIL),
            BACK,
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-controls", [
            Step("atl", tap="atl"),
            Step("run controls", tap="controls", ok=("controls shown",), ui=("PUSH", "lamp off", "BOLD & CAPS"), fail=ATL_FAIL, timeout=120),
            Step("PUSH", tap="PUSH", ok=("controls click push",), fail=ATL_FAIL),
            Step("locked", tap="locked", declined=True),
            Step("check", tap="check", ok=("controls checked check true",), fail=ATL_FAIL),
            Step("red", tap="red", ok=("controls checked red true", "controls radio red"), fail=ATL_FAIL),
            Step("green", tap="green", ok=("controls checked green true", "controls checked red false", "controls radio green"),
                 fail=ATL_FAIL),
            Step("switch", tap="switch", ok=("controls checked switch true",), fail=ATL_FAIL),
            Step("lamp off", tap="lamp off", ok=("controls click toggle lamp on",), ui=("lamp on",), fail=ATL_FAIL),
            Step("Home", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-text", [
            Step("atl", tap="atl"),
            Step("run text", tap="text", ok=("text shown",), ui=("name", "fill"), fail=ATL_FAIL, timeout=120),
            # the field's filter drops the digit: Java's watcher sees the filtered text, and the field shows it
            Step("type into name", type=("name", "hi1"), ok=('text after "hi"',), text=("name", "hi"), fail=ATL_FAIL),
            Step("show", tap="show", ok=('text show "hi" 2,2',), fail=ATL_FAIL),
            Step("fill", tap="fill", ok=('text after "filled"',), text=("name", "filled"), fail=ATL_FAIL),
            Step("type after fill", type=("name", "!"), ok=('text after "filled!"',), text=("name", "filled!"), fail=ATL_FAIL),
            # a selection that ends before it starts stays Java's: UIKit's ordered range is no change
            Step("reverse", tap="reverse", ok=("text reversed 5,2",), fail=ATL_FAIL),
            Step("show reversed", tap="show", ok=('text show "filled!" 5,2',), fail=ATL_FAIL + ('text show "filled!" 2,5',)),
            # a tap into the field, its text and range unchanged: the range stays Java's
            Step("tap name", tap="name"),
            Step("show after tap", tap="show", ok=(r'text show "filled!" \d+,\d+',), fail=ATL_FAIL + ('text show "filled!" 2,5',)),
            # Java moves the focus to notes and back to name at once, the keyboard stays on name: it is still
            # Java's request that hide answers
            Step("swap", tap="swap"),
            # and the inset the keyboard left goes with it
            Step("hide", tap="hide", ok=("text hide true", "text ime 0"), fail=ATL_FAIL + ("text hide false",)),
            # a field Android's tap rule gives no keyboard (showSoftInputOnFocus false, no input type) takes
            # the focus and no keyboard: nothing to hide. Its edits are refused only by the text field's
            # delegate, which the agent's insertText: bypasses: no step types into a field with no input type
            Step("type into calc", type=("calc", "7"), ok=("text focus calc true", 'text calc "7"'), text=("calc", "7"),
                 fail=ATL_FAIL),
            Step("calc has no keyboard", tap="hide", ok=("text hide false",), fail=ATL_FAIL + ("text hide true",)),
            # the native view of a text with a colored first word is swapped for a selectable one
            Step("select", tap="select", ok=("text selectable",), ui=("Error: disk full",), fail=ATL_FAIL),
            # a message taller than the screen scrolls in the alert's panel; the view under it keeps room (_text_layout)
            # the header's cap binds here: records' chrome must match the panel's laid-out header
            Step("long alert", tap="long alert", ok=(r"dialog: chrome measured .* ok",), ui=("Long", "Close"),
                 fail=ATL_FAIL + ("dialog: chrome measured .* differs",)),
            # its label is over 4 KB: the agent takes a request of any length, and a text declines the tap
            Step("tap the long message", tap="A line of a long message", declined=True),
            Step("Close", tap="Close", ok=("text long closed",), fail=ATL_FAIL),
            Step("Home", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, alive=True, check=_text_layout),
        Scenario("atl-dialog-keep", [
            Step("atl", tap="atl"),
            # onShow disabled "Yes", hid "Later" and took over "No"
            Step("run dialog keep", tap="dialog keep", ok=("dialog: presented",), fail=ATL_FAIL, timeout=120),
            Step("Yes", tap="Yes", declined=True),
            Step("No", tap="No", ok=("keep no kept", "dialog: presented"), ui=("Sure",), fail=ATL_FAIL),
            Step("Sure", tap="Sure", ok=("keep onClick -1", "keep done", "nav: container dismissed exit"), fail=ATL_FAIL),
            BACK,
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-dialog-content", [
            Step("atl", tap="atl"),
            # a Dialog with a content view: drawn over the activity, its dim over the status bar too
            Step("run dialog content", tap="dialog content", ok=("content shown", r"nav: status dim 0\.[1-9]"),
                 ui=("content text", "Close", "Dismiss"), fail=ATL_FAIL, timeout=120),
            Step("Close", tap="Close", ok=("content click", "content dismissed", "content shown"), fail=ATL_FAIL),
            # the dim's activate is a tap outside the dialog: the second one cancels and the activity ends
            Step("Dismiss", tap="Dismiss", ok=("content canceled", "content dismissed", "nav: container dismissed exit"),
                 fail=ATL_FAIL),
            BACK,
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-dialog-view", [
            Step("atl", tap="atl"),
            # setView content in the alert's panel: the field takes the keyboard, the panel's OK answers
            Step("run dialog view", tap="dialog view", ok=("view shown", r"dialog: chrome measured .* ok"),
                 ui=("View test", "Inner", "OK", "Cancel"), fail=ATL_FAIL + ("dialog: chrome measured .* differs",), timeout=120),
            Step("Inner", tap="Inner", ok=("view inner click",), fail=ATL_FAIL),
            Step("type into name", type=("name", "hey"), fail=ATL_FAIL),
            Step("OK", tap="OK", ok=('view ok "hey"', "view dismissed", "nav: container dismissed exit"), fail=ATL_FAIL),
            BACK,
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-dialog-choice", [
            Step("atl", tap="atl"),
            # the panel's own rows; Blue opens a plain alert over the panel, which waits under it
            Step("run dialog choice", tap="dialog choice", ok=(r"dialog: chrome measured .* ok",), ui=("Pick one", "Red", "Blue", "OK"),
                 fail=ATL_FAIL + ("dialog: chrome measured .* differs",), timeout=120),
            Step("Blue", tap="Blue", ok=("choice single 2", "dialog: presented"), ui=("Blue is taken", "Okay"), fail=ATL_FAIL),
            Step("Okay", tap="Okay", ok=("dialog: closed",), ui=("Pick one", "OK"), fail=ATL_FAIL),
            Step("OK", tap="OK", ok=("choice single ok 2",), ui=("Pick some", "Salt"), fail=ATL_FAIL),
            Step("Salt", tap="Salt", ok=("choice multi 0 true",), fail=ATL_FAIL),
            Step("OK multi", tap="OK", ok=("choice multi ok 0,1", "choice adapter shown"), ui=("Apple", "Pear", "Skip"), fail=ATL_FAIL),
            Step("Pear", tap="Pear", ok=("choice adapter 1", "choice done", "nav: container dismissed exit"), fail=ATL_FAIL),
            BACK,
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-dialog-alerts", [
            Step("atl", tap="atl"),
            Step("run dialog alerts", tap="dialog alerts", ok=("alerts first shown", 'dialog: presented "First"'),
                 ui=("Show second", "Cover"), fail=ATL_FAIL, timeout=120),
            # a window with a view over the plain alert: it goes while the window shows (covered), and comes back
            Step("Cover", tap="Cover", ok=("alerts cover shown",), ui=("Uncover",), gone=("Show second",), fail=ATL_FAIL),
            Step("Uncover", tap="Uncover", ok=("alerts cover closed", 'dialog: presented "First"'), ui=("Show second", "Cover"),
                 gone=("Uncover",), fail=ATL_FAIL),
            # the button kept the first alert open, the second shows over it, as in the registry: UIKit stacks the
            # controllers in the order they present, and the first is presented again after a tap (the lines name
            # the alert a presented one is over; the first one's labels stay in the tree under the second's)
            Step("Show second", tap="Show second", ok=("alerts second shown", 'dialog: presented "Second" above "First"'),
                 ui=("Close first", "Done"), fail=ATL_FAIL),
            # a button of the second dismisses the second before its listener runs, so the first changes and goes from a
            # timer, with the second up (presented again): UIKit's dismiss of a controller that presents another takes
            # that one down too; the second must be put back over the rebuilt first, and stay when the first goes
            Step("Later", tap="Later", ok=("alerts first rebuilt",), ui=("the first alert, rebuilt", "Close first", "Done"),
                 fail=ATL_FAIL),
            # (the second timer is 6 s after the tap: this step starts about 2.5 s after it, and waits from its own mark)
            Step("first goes", ok=("alerts first dismissed later",), ui=("Close first", "Done"),
                 gone=("Show second", "the first alert, rebuilt"), fail=ATL_FAIL, timeout=30),
            Step("Done", tap="Done", ok=("alerts done", "nav: container dismissed exit"), fail=ATL_FAIL),
            BACK,
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-dialog-late", [
            Step("atl", tap="atl"),
            Step("run dialog late", tap="dialog late", ok=('dialog: presented "Late test"',), ui=("Yes", "No", "Later"), fail=ATL_FAIL, timeout=120),
            # "No" disables "Yes" and hides "Later" while the alert is presented: UIKit's alert can't change its
            # actions, a new one replaces it with the new labels
            Step("No", tap="No", ok=("late no kept", 'dialog: presented "Late test"'), ui=("Yes", "No"), gone=("Later",), fail=ATL_FAIL),
            Step("Yes", tap="Yes", declined=True),
            Step("Home", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-dialog-modal", [
            Step("atl", tap="atl"),
            # not cancelable: only its buttons close it
            Step("run dialog modal", tap="dialog modal", ok=('dialog: presented "Modal test"',), ui=("Done", "More"),
                 fail=ATL_FAIL, timeout=120),
            Step("Done", tap="Done", ok=("modal done", "nav: container dismissed exit"), fail=ATL_FAIL),
            BACK,
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-dialog-progress", [
            Step("atl", tap="atl"),
            Step("run dialog progress", tap="dialog progress", ok=("progress spinner shown true", "progress bar shown", "progress 5/10",
                                                                   "progress done", "nav: container dismissed exit"),
                 fail=ATL_FAIL, timeout=120),
            BACK,
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-dialog-stack", [
            Step("atl", tap="atl"),
            # a non-touch-modal dialog: an activity started over it hides it, Back brings both back
            Step("run dialog stack", tap="dialog stack", ok=("stack resumed",), ui=("next", "line 0", "under"),
                 fail=ATL_FAIL, timeout=120),
            Step("next", tap="next", ok=("stack cover resumed",), fail=ATL_FAIL),
            Step("Back", action="Back", ok=("stack resumed",), ui=("next", "line 0"), fail=ATL_FAIL),
            Step("Home", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-nav", [
            Step("atl", tap="atl"),
            # px at 3x: 20 pt side strips, the home indicator at the bottom; B's two rects at its right edge make one span
            Step("run nav", tap="nav", ok=("nav: B onResume", "nav: container shown nav",
                                          r"nav: B insets 60 0 60 [1-9]\d* 0 0 0 [1-9]\d* 0 0 0 [1-9]\d*",
                                          "nav: exclusion left 0 right 1"), fail=ATL_FAIL + ("nav: window size",), timeout=120),
            Step("Back", action="Back", ok=("nav: B onDestroy", "nav: A onResume", "nav: exclusion left 0 right 0"),
                 fail=ATL_FAIL),
            Step("back on the task root", back=True,
                 ok=("nav: A onStop", "nav: container dismissed back", "nav: launcher root"), fail=ATL_FAIL),
            Step("Recent apps", action="Recent apps", ok=("nav: apps list shown",)),
            Step("back to app", tap="back to app", ok=("nav: A onRestart", "nav: A onResume", "nav: container shown nav"),
                 fail=ATL_FAIL),
            Step("Home", action="Home", ok=("nav: A onStop", "nav: launcher root"), ui=("Add App",), fail=ATL_FAIL),
            # A showed its list in that onStop, while in the back: it waits for the front
            Step("Recent apps, list held", action="Recent apps", ok=("nav: apps list shown",)),
            Step("back to app, list shown", tap="back to app", ok=("nav: container shown nav", "dialog: presented"),
                 fail=ATL_FAIL + NAV_LIST_FAIL),
            Step("Home with the list", action="Home", ok=("nav: container dismissed home", "nav: A onStop"), ui=("Add App",),
                 fail=ATL_FAIL + NAV_LIST_FAIL),
            Step("Recent apps, list held again", action="Recent apps", ok=("nav: apps list shown",)),
            Step("back to app, list again", tap="back to app", ok=("nav: container shown nav", "dialog: presented"),
                 fail=ATL_FAIL + NAV_LIST_FAIL),
            Step("Odd item", tap="Odd ��\U0001f600��", ok=("dialog: closed", "nav: list 1"),
                 fail=ATL_FAIL + ("nav: list canceled",)),
            # from the app: it goes to the back, the list shows in its place
            Step("Recent apps from the app", action="Recent apps",
                 ok=("nav: A onStop", "nav: container dismissed list", "nav: apps list shown"), fail=ATL_FAIL),
            Step("back to app from the list", tap="back to app",
                 ok=("nav: A onRestart", "nav: container shown nav"), fail=ATL_FAIL),
            Step("Home at the end", action="Home", ok=("nav: A onStop", "nav: launcher root"), ui=("Add App",), fail=ATL_FAIL),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-immersive", [
            Step("atl", tap="atl"),
            # nav.apk's ImmersiveActivity: the window grows under the status bar, the home indicator hides
            Step("run nav immersive", tap="nav immersive",
                 ok=("nav: I onResume", "nav: frame fullscreen false cover true hide navigation true immersive true",
                     r"nav: window size \d+x\d+", r"nav: I edges status 0 [1-9]\d* 0 0 ime 0 0 0 0 hidden", r"nav: I size \d+x\d+"),
                 fail=ATL_FAIL, timeout=120),
            Step("Home", action="Home", ok=("nav: I onStop", "nav: launcher root"), ui=("Add App",), fail=ATL_FAIL),
            # in its second container the window moves back below the status bar: a new size
            Step("Recent apps", action="Recent apps", ok=("nav: apps list shown",)),
            Step("back to app", tap="back to app", ok=("nav: I onResume", "nav: container shown nav immersive"), fail=ATL_FAIL),
            Step("windowed", tap="windowed", ok=("nav: frame fullscreen false cover false", r"nav: window size \d+x\d+"),
                 fail=ATL_FAIL),
            Step("Home at the end", action="Home", ok=("nav: I onStop", "nav: launcher root"), ui=("Add App",), fail=ATL_FAIL),
        ], uses_vm=True, needs_clean=True, alive=True, check=_surface_size),
        Scenario("atl-installer", [
            Step("atl", tap="atl"),
            # the package suite's installer app: a session confirmed from its Application context
            Step("run installer", tap="installer", ok=("scenario: status -1 dev.dine.pkg.ext", "dialog: presented"),
                 ui=("Install", "Cancel"), fail=ATL_FAIL + ("scenario: failed",), timeout=120),
            Step("Install", tap="Install", ok=("scenario: status 0 dev.dine.pkg.ext", "scenario: installer dev.dine.pkg.driver",
                                               "nav: container dismissed exit"),
                 fail=ATL_FAIL + ("scenario: failed", r"scenario: status [1-9]")),
            BACK,
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("atl-two-apps", [
            Step("atl", tap="atl"),
            # two apps of one VM: each gets its own answers, a night change reaches both, and one's end leaves the other
            Step("run dialog late", tap="dialog late", ok=("nav: container shown dialog late", 'dialog: presented "Late test"'),
                 ui=("Yes", "No", "Later"), fail=ATL_FAIL, timeout=120),
            Step("No in the first", tap="No", ok=("late no kept", 'dialog: presented "Late test"'), gone=("Later",),
                 fail=ATL_FAIL),
            Step("Home from the first", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
            Step("atl again", tap="atl"),
            Step("run text beside it", tap="text", ok=("atl app start", "nav: container shown text", "text shown"),
                 ui=("name", "fill"), fail=ATL_FAIL + ("runs already",), timeout=120),
            Step("long alert", tap="long alert", ui=("Long", "Close"), fail=ATL_FAIL),
            Step("Close in the second", tap="Close", ok=("text long closed",), fail=ATL_FAIL + ("late onClick", "late done")),
            Step("Home from the second", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
            Step("atl for the first", tap="atl"),
            Step("the first's tile", tap="dialog late",
                 ok=("nav: dialog late runs already: front", "nav: container shown dialog late", 'dialog: presented "Late test"'),
                 ui=("Yes", "No"), gone=("fill",), fail=ATL_FAIL + ("atl app start",)),
            Step("Yes is still disabled", tap="Yes", declined=True, fail=("text long closed",)),
            Step("light first", appearance="light"),
            Step("dark for both", appearance="dark", ok=("late night 32", "text night 32"), fail=ATL_FAIL),
            Step("light for both", appearance="light", ok=("late night 16", "text night 16"), fail=ATL_FAIL),
            Step("system", appearance="system"),
            Step("Back ends the first", action="Back", ok=("late done", "nav: container dismissed exit", "atl main returned 0"),
                 fail=ATL_FAIL),
            Step("the second's tile", tap="text", ok=("nav: text runs already: front", "nav: container shown text"),
                 ui=("name", "fill"), fail=ATL_FAIL + ("atl app start",)),
            Step("show in the second", tap="show", ok=('text show ""',), fail=ATL_FAIL),
            Step("Home", action="Home", ok=("nav: launcher root",), ui=("Add App",)),
        ], uses_vm=True, needs_clean=True, alive=True),
        Scenario("art", [
            Step("art", tap="art", ok=("art probe done",)),
            Step("run hello", tap="run hello", ok=("Hello from dine runtime tests", "art main returned"),
                 fail=ART_FAIL),
            Step("run jni args", tap="run jni args", ok=("jni args ok", "art main returned"),
                 fail=("jni args failed", *ART_FAIL)),
            Step("run https", tap="run https", ok=("https ok", "art main returned"),
                 fail=("https failed", *ART_FAIL), network=True, timeout=120),
            Step("run park", tap="run park", ok=("park ok", "art main returned"),
                 fail=("park failed", *ART_FAIL)),
            Step("run cleanup", tap="run cleanup", ok=("cleanup ok", "art main returned"),
                 fail=("cleanup failed", *ART_FAIL), timeout=90),
            Step("run cpu time", tap="run cpu time", ok=("thread cpu time ok", "art main returned"),
                 fail=("thread cpu time failed", *ART_FAIL)),
            Step("run netif", tap="run netif", ok=("netif ok", "art main returned"),
                 fail=("netif failed", *ART_FAIL)),
            BACK,
        ], uses_vm=True, needs_clean=True),   # as a run of it alone: it creates the VM itself
        # last, in a process of its own: the server's lldb on the running app
        Scenario("lldb", [
            Step("attach", dbg=("attach", {}), says="attached to pid", timeout=120),
            Step("breakpoint", dbg=("bp", {"op": "add", "spec": "HelloView.swift:23", "once": True}),
                 says=r"breakpoint \d+: .*HelloView\.swift:23"),
            Step("continue", dbg=("continue", {}), says="running"),
            Step("hello++", tap="hello++"),
            Step("stop", dbg=("wait", {"at": "HelloView.swift:23"}), says="matched --stop"),
            # C: a Swift expression needs the system symbols of the phone's iOS (`ios symbols`)
            Step("expression", dbg=("exec", {"expr": "(const char *)dine_hello()", "lang": "c"}), says=r"Hello from C\+\+",
                 timeout=90),
            Step("continue from it", dbg=("continue", {}), says="running"),
            Step("detach", dbg=("detach", {}), says="detached"),
            BACK,
        ], needs_clean=True, alive=True),
    ],
}


def listing(app: str) -> str:
    lines = []
    for sc in table(app):
        flags = [f for f, on in (("fresh process", sc.needs_clean), ("app stays up", sc.alive)) if on]
        lines.append(f"{sc.name}" + (f" ({', '.join(flags)})" if flags else ""))
        for st in sc.steps:
            what = " ".join((st.dbg[0], *map(str, st.dbg[1].values()))) if st.dbg else f"tap {st.tap!r}" if st.tap else f"type {st.type[1]!r} into {st.type[0]!r}" if st.type else \
                f"action {st.action!r}" if st.action else f"appearance {st.appearance}" if st.appearance else \
                "back" if st.back else st.title
            lines.append(f"  {what}" + (f"; wait for {', '.join(st.ok)}" if st.ok else "")
                         + (f"; shows {', '.join(map(repr, st.ui))}" if st.ui else "")
                         + (f"; no longer shows {', '.join(map(repr, st.gone))}" if st.gone else "")
                         + (f"; {st.text[0]!r} shows the text {st.text[1]!r}" if st.text else "")
                         + (" [--network]" if st.network else ""))
    return "\n".join(lines)


def table(app: str) -> list[Scenario]:
    if app not in SCENARIOS or app not in STARTUP:
        raise DineError(f"no smoke checks for {app} in {__file__}")
    return SCENARIOS[app]


def field_text_problem(label: str, want: str) -> str | None:
    """What is wrong with the text the field `label` shows: the agent's listing words it `#N label = text`
    (nothing after the label while the field is empty). It retries for 5 s: a report may be on its way."""
    deadline = time.monotonic() + 5
    pattern = re.compile(rf"#\d+ {re.escape(label)}(?: = (.*))?")
    while True:
        found = [m for line in client.call("ui_ls", {})["text"].splitlines() if (m := pattern.fullmatch(line))]
        shown = found[0][1] or "" if found else None
        if shown == want:
            return None
        if time.monotonic() > deadline:
            return f"no field {label!r} on screen" if shown is None else f"{label!r} shows {shown!r}, want {want!r}"
        time.sleep(0.3)


def fail_hit(text: str, fail: tuple[str, ...]) -> str | None:
    lines = text.splitlines()
    return next((f for f in fail if any(line.startswith(f"matched --log-re {f!r}") for line in lines)), None)


def logged(patterns: tuple[str, ...], since: int) -> str | None:
    """The first of the patterns the app's syslog shows after `since`, with its line."""
    for pattern in patterns:
        resp = client.call("log", {"op": "grep", "pattern": pattern, "since": since, "src": ["syslog"],
                                   "text": True, "n": 1})
        head, _, rest = resp["text"].partition("\n")
        if not head.startswith("0 matches"):
            return f"{pattern!r}: {rest.partition(chr(10))[0]}"
    return None


def run(app: str, names: list[str], network: bool, relaunch: Callable[[], int], out=print) -> int:
    """Relaunches before the first scenario and before ATL ones that need a clean process; exit 1 at
    the first failure."""
    debugged: list[tuple[str, dict]] = []
    try:
        return _run(app, names, network, relaunch, out, debugged)
    finally:
        # a failure in between would leave the app stopped, the next relaunch refused and the breakpoint set
        for cmd, args in debugged:
            client.call(cmd, args)


def _run(app: str, names: list[str], network: bool, relaunch: Callable[[], int], out,
         debugged: list[tuple[str, dict]]) -> int:
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
            step_start = client.call("status")["cursor"]
            if st.dbg:
                if st.dbg[0] == "attach":
                    debugged.append(("detach", {}))
                resp = client.call(*st.dbg, timeout=st.timeout)
                if resp["code"] or (st.says and not re.search(st.says, resp["text"])):
                    out(f"{sc.name}: {st.title}: FAILED\n{resp['text']}")
                    return 1
                if set_at := re.match(r"breakpoint (\d+):", resp["text"]):
                    debugged.append(("bp", {"op": "rm", "spec": set_at[1]}))
                if st.dbg[0] == "detach":
                    debugged.clear()   # a one-shot breakpoint went at its stop
            elif st.tap or st.type or st.back or st.action or st.appearance:
                resp = client.call("ui_tap", {"arg": st.tap}, timeout=30) if st.tap else \
                    client.call("ui_type", {"arg": st.type[0], "text": st.type[1]}, timeout=30) if st.type else \
                    client.call("ui_action", {"arg": st.action}, timeout=30) if st.action else \
                    client.call("ui_appearance", {"arg": st.appearance}, timeout=30) if st.appearance else \
                    client.call("ui_back", {}, timeout=30)
                declined = bool(resp["code"]) and "declined the activation" in resp["text"]
                if st.declined != declined or (resp["code"] and not declined):
                    out(f"{sc.name}: {st.title}: FAILED" + (" (not declined)" if st.declined and not declined else "")
                        + f"\n{resp['text']}")
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
            for label in st.gone:
                deadline = time.monotonic() + 5
                while label in client.call("ui_ls", {})["text"]:
                    if time.monotonic() > deadline:
                        out(f"{sc.name}: {st.title}: FAILED: {label!r} is still on screen")
                        return 1
                    time.sleep(0.5)
            if st.text and (problem := field_text_problem(*st.text)):
                out(f"{sc.name}: {st.title}: FAILED: {problem}")
                return 1
            # the waits end at their first match: a forbidden line after it, or in a step with no
            # `ok`, shows only here
            if hit := logged(st.fail, step_start):
                out(f"{sc.name}: {st.title}: FAILED ({hit})")
                return 1
            out(f"{sc.name}: {st.title}: ok ({time.monotonic() - t:.1f} s)")
        problem = sc.check(start) if sc.check else None
        if hit := logged(FATAL, start):
            problem = hit
        if sc.alive and not any(p["pid"] == pid for p in ios.processes(app)):
            problem = f"{app} pid {pid} is gone"
        if problem:
            out(f"{sc.name}: FAILED: {problem}")
            return 1
        dirty = dirty or sc.uses_vm
    out(f"smoke passed: {', '.join(sc.name for sc in chosen)} ({time.monotonic() - begin:.0f} s)")
    return 0

