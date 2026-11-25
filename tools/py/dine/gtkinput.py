"""The gtk smoke check `input-gtk`: pointer and key events fed through the gtk agent's `touch` and
`key` commands, which reach the functions GTK's own events do, into APK activities that log what
Java gets."""

import re
import time

from . import paths
from .gtkdrive import Problem, Session

DIALOG_APK = paths.OUT / "tests/apks/dialog.apk"
NAV_APK = paths.OUT / "tests/apks/nav.apk"
WIDGETS_APK = paths.OUT / "tests/apks/widgets.apk"
WINDOWS_APK = paths.OUT / "tests/apks/windows.apk"

# GDK keyval and hardware keycode
TAB = (0xFF09, 23)
RETURN = (0xFF0D, 36)
T = (0x74, 28)
# the US keymap's key 1, with Shift and without; Shift_L; the keypad's 1 without NumLock
EXCLAM = (0x21, 10)
ONE = (0x31, 10)
SHIFT_L = (0xFFE1, 50)
KP_END = (0xFF9C, 87)
SHIFT_MASK = 1

# a point in the app window outside a dialog around its centre
OUTSIDE = 300


def _expect(session: Session, since: int, *lines: str) -> None:
    """The app's lines (tag `dialog`) from `since` on are exactly these."""
    got = [l.split(": ", 1)[-1] for l in session.lines_since(since) if l.startswith("I/dialog")]
    if got != list(lines):
        raise session.fail(f"the dialog lines after the step are {got}, want {list(lines)}")


def outside_touch(env: dict[str, str]) -> None:
    """A dialog dismissed from its own ACTION_UP leaves the next gesture working."""
    with Session(DIALOG_APK, "dev/dine/dialog/OutsideActivity", env) as s:
        s.wait_line("outside shown")
        x, y = s.centre("outside text")
        mark = s.mark()
        s.touch("down", 0, x - OUTSIDE, y)
        s.touch("up", 0, x - OUTSIDE, y)
        mark = s.wait_line("outside dismissed", mark)
        s.touch("down", 0, x - OUTSIDE, y)
        s.touch("up", 0, x - OUTSIDE, y)
        s.wait_line("outside behind ACTION_UP ids", mark)
        _expect(s, mark, "outside behind ACTION_DOWN ids 0", "outside behind ACTION_UP ids 0")
        mark = s.mark()
        # two fingers, the mouse's NULL handle and a made-up sequence: the ids are 0 and 1
        s.touch("down", 0, x - OUTSIDE, y)
        s.touch("down", 7, x - OUTSIDE + 20, y)
        s.touch("move", 7, x - OUTSIDE + 30, y)
        s.touch("up", 0, x - OUTSIDE, y)
        s.touch("up", 7, x - OUTSIDE + 30, y)
        s.wait_line("outside behind ACTION_UP ids", mark)
        _expect(s, mark, "outside behind ACTION_DOWN ids 0", "outside behind ACTION_POINTER_DOWN(1) ids 0,1",
                "outside behind ACTION_MOVE ids 0,1", "outside behind ACTION_POINTER_UP(0) ids 0,1",
                "outside behind ACTION_UP ids 1")
        if s.died():
            raise s.fail(s.died())


def popup_outside(env: dict[str, str]) -> None:
    """A touch outside a PopupWindow that watches outside touches reaches it as ACTION_OUTSIDE, which
    closes it, and the activity under it still gets the touch."""
    with Session(WINDOWS_APK, "dev/dine/windows/PopupActivity", env) as s:
        s.wait_line("popup activity created")
        s.activate("anchor")
        s.wait_line("popup shown")
        x, y = s.centre("elsewhere")
        mark = s.mark()
        s.touch("down", 0, x, y)
        s.touch("up", 0, x, y)
        s.wait_line("popup dismissed", mark, timeout=10)
        s.wait_line("popup elsewhere", mark, timeout=10)


def gesture_of_a_hidden_activity(env: dict[str, str]) -> None:
    """An activity that starts another from its DOWN is hidden: its gesture is canceled and the rest of
    it reaches neither activity."""
    with Session(NAV_APK, "dev/dine/nav/TouchStartActivity", env) as s:
        s.wait_line("nav: P onResume")
        x, y = 100.0, 100.0
        mark = s.mark()
        s.touch("down", 0, x, y)  # P starts Q
        s.wait_line("nav: Q onResume", mark, timeout=10)
        s.wait_line("nav: P touch ACTION_CANCEL", mark, timeout=10)
        s.touch("move", 0, x, y + 20)
        s.touch("up", 0, x, y + 20)
        time.sleep(0.5)
        touches = [re.sub(r" \d+,\d+ \d+$", "", l.split(": ", 1)[-1]) for l in s.lines_since(mark) if l.startswith("I/nav ") and " touch " in l]
        if touches != ["nav: P touch ACTION_DOWN", "nav: P touch ACTION_CANCEL"]:
            raise s.fail(f"the touch lines after the DOWN are {touches}, want P's DOWN and its CANCEL only")


def gesture_outlives_activity(env: dict[str, str]) -> None:
    """The activity whose DOWN began a gesture finishes under it: it gets no CANCEL after its onDestroy,
    and the activity below gets nothing of the gesture (no UP without a DOWN)."""
    with Session(NAV_APK, "dev/dine/nav/TouchTapActivity", env) as s:
        s.wait_line("nav: U onResume")
        x, y = s.centre("go")
        s.activate("go")  # U starts Q, which finishes on its DOWN
        s.wait_line("nav: Q onResume")
        mark = s.mark()
        s.touch("down", 0, x, y)
        s.wait_line("nav: Q onDestroy", mark, timeout=10)
        s.touch("up", 0, x, y)
        time.sleep(0.5)
        touches = [l.split(": ", 1)[-1] for l in s.lines_since(mark) if l.startswith("I/nav ") and " touch " in l]
        if touches != ["nav: Q touch ACTION_DOWN"]:
            raise s.fail(f"the touch lines after the DOWN are {touches}, want Q's DOWN only")


def keys(env: dict[str, str]) -> None:
    """Tab moves Java's focus through widgets.apk's rows and Return clicks the focused one. A key
    release goes to Java only after its press: T's lone release is dropped, its press and release
    (MainActivity logs both) are not."""
    with Session(WIDGETS_APK, "dev/dine/widgets/MainActivity", env) as s:
        s.wait_line("widgets shown")
        mark = s.mark()
        for _ in range(3):
            s.key("down", *TAB)
            s.key("up", *TAB)
        s.wait_line("widgets focus one true", mark)
        s.key("down", *RETURN)
        s.key("up", *RETURN)
        s.wait_line("widgets click one", mark)
        s.key("up", *T)
        if not s.key("down", *T):
            raise s.fail("Java didn't take T's press")
        s.key("up", *T)
        s.wait_line("widgets keyup 48", mark)
        time.sleep(0.5)
        got = [l.split(": ", 1)[-1] for l in s.lines_since(mark) if l.startswith("I/widgets") and " keycode " not in l]
        want = ["widgets focus tap true", "widgets focus tap false", "widgets focus hold true", "widgets focus hold false",
                "widgets focus one true", "widgets keychar 66 10", "widgets click one", "widgets key 48", "widgets keyup 48"]
        if got != want:
            raise s.fail(f"the widgets lines after the keys are {got}, want {want}")


def key_codes(env: dict[str, str]) -> None:
    """A key's code is the key's, whatever the modifiers: Shift+1 goes down as '!' and up as '1', both
    KEYCODE_1; Shift is SHIFT_LEFT; the keypad's 1 without NumLock is NUMPAD_1."""
    with Session(WIDGETS_APK, "dev/dine/widgets/MainActivity", env) as s:
        s.wait_line("widgets shown")
        mark = s.mark()
        s.key("down", *SHIFT_L)
        s.key("down", *EXCLAM, SHIFT_MASK)
        s.key("up", *SHIFT_L, SHIFT_MASK)
        s.key("up", *ONE)
        s.key("down", *KP_END)
        s.key("up", *KP_END)
        deadline = time.monotonic() + 5
        while True:
            got = [l.split(": ", 1)[-1] for l in s.lines_since(mark) if l.startswith("I/widgets") and " keycode " in l]
            if len(got) >= 6 or time.monotonic() > deadline:
                break
            time.sleep(0.1)
        want = ["widgets keycode down 59 0", "widgets keycode down 8 33", "widgets keycode up 59 0", "widgets keycode up 8 49",
                "widgets keycode down 145 0", "widgets keycode up 145 0"]
        if got != want:
            raise s.fail(f"the key lines are {got}, want {want}")


CHECKS = [outside_touch, popup_outside, gesture_of_a_hidden_activity, gesture_outlives_activity, keys, key_codes]


def run(env: dict[str, str]) -> str | None:
    try:
        for check in CHECKS:
            check(env)
    except Problem as e:
        return str(e)
    return None
