"""Linux smoke: the gtk build runs Gravity Defied to onResume, the dialog and views APKs and the
widgets APK's drawing, on a hidden display (display.py); the headless build runs demo_app and the
looper, dialog, nav, views, widgets and windows APKs. Needs a prior `tools/dine linux build`."""

import fcntl
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import display, gtkinput, gtktext, paths
from .paths import DineError

GTK_BUILD = paths.ATL_GTK_BUILD
HEADLESS_BUILD = paths.ATL_HEADLESS_BUILD
HEADLESS_TESTS = paths.ROOT / "dine-atl/tests/headless"
APKS = paths.ROOT / "third_party/apks"
LOOPER_APK = paths.OUT / "tests/apks/looper.apk"
DIALOG_APK = paths.OUT / "tests/apks/dialog.apk"
NAV_APK = paths.OUT / "tests/apks/nav.apk"
VIEWS_APK = paths.OUT / "tests/apks/views.apk"
WIDGETS_APK = paths.OUT / "tests/apks/widgets.apk"
WINDOWS_APK = paths.OUT / "tests/apks/windows.apk"
# not in tests/apks: the iOS dev payload bundles every APK there
CRASH_APK = paths.OUT / "tests/linux-apks/crash.apk"


@dataclass(frozen=True)
class Check:
    name: str
    what: str
    # None when it passed, else the problem: its first line goes in the FAILED line, the rest below
    run: Callable[[], str | None]


_display: display.Display | None = None


@contextmanager
def builds(exclusive: bool):
    """The lock on the Linux builds: `linux build` holds it alone, runs that read them share it.
    The two ATL builds write the same generated headers, and a run must not see a build change
    under it."""
    paths.OUT.mkdir(exist_ok=True)
    with open(paths.OUT / ".linux-builds.lock", "a") as lock:
        try:
            fcntl.flock(lock, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError:
            busy = "in use by a build or by a test or smoke run" if exclusive else "being built"
            raise DineError(f"the Linux builds are {busy}: wait for that tools/dine to end") from None
        yield


def require_fresh(build_dir: Path, rebuild: str, *targets: str, default: bool = True) -> None:
    """Raises when a meson build dir has pending work: what runs from it would be an older build
    than the sources. Checks the default targets (unless `default` is off) and `targets`."""
    if not (build_dir / "build.ninja").exists():
        raise DineError(f"no build in {build_dir}: run {rebuild}")
    for target in (*([[]] if default else []), *([t] for t in targets)):
        r = subprocess.run(["ninja", "-C", str(build_dir), "-n", *target], capture_output=True, text=True)
        if r.returncode != 0 or "no work to do" not in r.stdout:
            raise DineError(f"{build_dir} is behind its sources: run {rebuild}")


def _gtk_env() -> dict[str, str]:
    """The env for a gtk run: the smoke run's hidden display, started by its first gtk check."""
    global _display
    if _display is None:
        _display = display.Display()
    return _display.env()


def _gd(*args: str) -> str | None:
    _need_gtk()
    proc = subprocess.run([sys.executable, str(paths.ROOT / "tests/harness/apps.py"), "--gtk", "-f", "^gd$", *args],
                          env=_gtk_env(), capture_output=True, text=True)
    # its pass, not an expected failure
    if proc.returncode == 0 and "apps (gtk): 1/1 pass" in proc.stdout:
        return None
    return (proc.stdout + proc.stderr).strip() or f"apps.py: exit status {proc.returncode}, no output"


def _script(label: str, *args, env: dict[str, str] | None = None) -> str | None:
    r = subprocess.run([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    return None if r.returncode == 0 else f"{label}: exit status {r.returncode}\n{r.stdout.rstrip()}"


_fresh: set[Path] = set()   # builds this smoke run has checked


def _need(build: Path, stage: str) -> None:
    if build not in _fresh:
        require_fresh(build, f"tools/dine linux build {stage}")
        _fresh.add(build)


def _need_headless() -> None:
    _need(HEADLESS_BUILD, "atl-headless")


def _need_gtk() -> None:
    _need(GTK_BUILD, "atl")


def _demo() -> str | None:
    _need_headless()
    return _script("run-demo.sh", HEADLESS_TESTS / "run-demo.sh", HEADLESS_BUILD, APKS / "demo_app.apk")


def _demo_480() -> str | None:
    _need_headless()
    return _script("run-demo.sh", HEADLESS_TESTS / "run-demo.sh", HEADLESS_BUILD, APKS / "demo_app.apk",
                   "--density", "480")


def _looper() -> str | None:
    _need_headless()
    return (_script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "looper", LOOPER_APK)
            or _script("run-looper.sh", HEADLESS_TESTS / "run-looper.sh", HEADLESS_BUILD, LOOPER_APK))


def _loop() -> str | None:
    _need_headless()
    _need_gtk()
    for build in (HEADLESS_BUILD, GTK_BUILD):
        problem = _script(f"meson test loop pointers ({build.name})", "meson", "test", "-C", build, "--no-rebuild",
                          "--print-errorlogs", "loop", "pointers")
        if problem:
            return problem
    return None


def _dialog_apk(build: Path = HEADLESS_BUILD) -> str | None:
    return _script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "dialog", DIALOG_APK,
                   "--atl", build)


def _dialog() -> str | None:
    _need_headless()
    return _dialog_apk() or _script("run-dialog.sh", HEADLESS_TESTS / "run-dialog.sh", "--headless", HEADLESS_BUILD,
                                    DIALOG_APK)


def _dialog_gtk() -> str | None:
    _need_gtk()
    return _dialog_apk(GTK_BUILD) or _script("run-dialog.sh", HEADLESS_TESTS / "run-dialog.sh", GTK_BUILD, DIALOG_APK,
                                    env=_gtk_env())


def _nav() -> str | None:
    _need_headless()
    return (_script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "nav", NAV_APK)
            or _script("run-nav.sh", HEADLESS_TESTS / "run-nav.sh", HEADLESS_BUILD, NAV_APK))


def _crash() -> str | None:
    _need_headless()
    return (_script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "crash", CRASH_APK)
            or _script("run-crash.sh", HEADLESS_TESTS / "run-crash.sh", HEADLESS_BUILD, CRASH_APK))


def _views_apk(build: Path = HEADLESS_BUILD) -> str | None:
    return _script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "views", VIEWS_APK,
                   "--atl", build)


def _views() -> str | None:
    _need_headless()
    return _views_apk() or _script("run-views.sh", HEADLESS_TESTS / "run-views.sh", "--headless", HEADLESS_BUILD,
                                   VIEWS_APK)


def _views_gtk() -> str | None:
    _need_gtk()
    return _views_apk(GTK_BUILD) or _script("run-views.sh", HEADLESS_TESTS / "run-views.sh", GTK_BUILD, VIEWS_APK,
                                   env=_gtk_env())


def _widgets_apk(build: Path = HEADLESS_BUILD) -> str | None:
    return _script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "widgets", WIDGETS_APK,
                   "--atl", build)


def _widgets() -> str | None:
    _need_headless()
    return _widgets_apk() or _script("run-widgets.sh", HEADLESS_TESTS / "run-widgets.sh", HEADLESS_BUILD, WIDGETS_APK)


def _lists() -> str | None:
    _need_headless()
    return _widgets_apk() or _script("run-lists.sh", HEADLESS_TESTS / "run-lists.sh", HEADLESS_BUILD, WIDGETS_APK)


def _controls() -> str | None:
    _need_headless()
    return _widgets_apk() or _script("run-controls.sh", HEADLESS_TESTS / "run-controls.sh", HEADLESS_BUILD, WIDGETS_APK)


def _text() -> str | None:
    _need_headless()
    return _widgets_apk() or _script("run-text.sh", HEADLESS_TESTS / "run-text.sh", HEADLESS_BUILD, WIDGETS_APK)


def _pan() -> str | None:
    _need_headless()
    return _widgets_apk() or _script("run-pan.sh", HEADLESS_TESTS / "run-pan.sh", HEADLESS_BUILD, WIDGETS_APK)


def _frames() -> str | None:
    _need_headless()
    return _widgets_apk() or _script("run-frames.sh", HEADLESS_TESTS / "run-frames.sh", HEADLESS_BUILD, WIDGETS_APK)


def _windows() -> str | None:
    _need_headless()
    return (_script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "windows", WINDOWS_APK)
            or _script("run-windows.sh", HEADLESS_TESTS / "run-windows.sh", HEADLESS_BUILD, WINDOWS_APK))


def _keyboard() -> str | None:
    _need_headless()
    return (_script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "windows", WINDOWS_APK)
            or _script("run-keyboard.sh", HEADLESS_TESTS / "run-keyboard.sh", HEADLESS_BUILD, WINDOWS_APK))


def _config() -> str | None:
    _need_headless()
    return (_script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "windows", WINDOWS_APK)
            or _script("run-config.sh", HEADLESS_TESTS / "run-config.sh", HEADLESS_BUILD, WINDOWS_APK))


def _windows_gtk() -> str | None:
    _need_gtk()
    return (_script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "windows", WINDOWS_APK,
                    "--atl", GTK_BUILD)
            or _script("run-windows.sh", HEADLESS_TESTS / "run-windows.sh", "--gtk", GTK_BUILD, WINDOWS_APK, env=_gtk_env()))


def _input_gtk() -> str | None:
    _need_gtk()
    return (_dialog_apk(GTK_BUILD)
            or _script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "nav", NAV_APK)
            or _widgets_apk(GTK_BUILD)
            or _script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "windows", WINDOWS_APK,
                       "--atl", GTK_BUILD)
            or gtkinput.run(_gtk_env()))


def _text_gtk() -> str | None:
    _need_gtk()
    return _widgets_apk(GTK_BUILD) or gtktext.run(_gtk_env())


def _draw() -> str | None:
    _need_headless()
    return _widgets_apk() or _script("run-draw.sh", HEADLESS_TESTS / "run-draw.sh", "--headless", HEADLESS_BUILD,
                                     WIDGETS_APK)


def _draw_gtk() -> str | None:
    _need_gtk()
    return _widgets_apk(GTK_BUILD) or _script("run-draw.sh", HEADLESS_TESTS / "run-draw.sh", GTK_BUILD, WIDGETS_APK,
                                     env=_gtk_env())


CHECKS = [
    Check("gd", "gtk: Gravity Defied reaches onResume under -Xint", _gd),
    Check("gd-package", "gtk: the same, installed with --install-internal and run with --package", lambda: _gd("--by-package")),
    Check("demo", "headless: demo_app reaches onResume, view tree matches the golden", _demo),
    Check("demo-480", "headless: the same at density 480, where sp, dp and px differ", _demo_480),
    Check("loop", "headless and gtk: the loop slot's rules on the poll and glib backends alone (a scheduled dispatch, a wake before a schedule, posts across threads and after a quit, a dispatch that yields to a post), and the pointer tracker gtk and uikit share (ids, action codes, a table that stays right when a gesture ends during a delivery)", _loop),
    Check("looper", "headless: looper.apk goes through the loop paths, its timed and untimed waits last their 50 ms without spinning, a layout pass runs between messages that are all due, and it exits 0", _looper),
    Check("dialog", "headless: dialog.apk's scripted runs log exactly the expected lines (alerts, a list, choice rows, progress, a setView panel, buttons changed in onShow and while drawn, an alert that isn't cancelable); from cli -c, content dialogs and panels match dialog-content.viewtree and dialog-view.viewtree under taps, text, Back and touches outside, and a finishing activity's dialog goes with it", _dialog),
    Check("dialog-gtk", "gtk: dialog.apk's scripted runs through the GTK dialog's widgets, graded on the app's lines and exit status; none of the cli -c steps", _dialog_gtk),
    Check("nav", "headless: nav.apk's lifecycle, insets, exclusion span and window size under Back, Home, front, insets and size from cli -c; the insets, span and size again at 480 dpi; an immersive activity's bar flags; an activity started for a result from a tap and from onCreate, its result or Back's RESULT_CANCELED before the caller restarts; a finish inside onCreate, onStart and onResume; the only activity finishing and starting the next; an activity started and one finished in the back", _nav),
    Check("crash", "headless: crash.apk throws in onCreate, onResume, a posted Runnable, a started activity's onCreate, onLayout, and onPause and onDestroy inside a finish; each ends ATL through the uncaught handler with exit 10 and, with CheckJNI on, no CheckJNI abort; a throw in onMeasure or onDraw is printed and cleared, and the app goes on", _crash),
    Check("views", "headless: views.apk removes, re-adds and frees views, a dialog and three drawables; the first layout's tree and the one after a laid-out view's removal match views.viewtree and views-removed.viewtree", _views),
    Check("views-gtk", "gtk: views.apk's steps through GTK's widgets; its dialog is freed and gsk frees a nine-patch and a StateListDrawable; no tree and no view frees are checked", _views_gtk),
    Check("widgets", "headless: widgets.apk takes taps, a hold, Tab, Enter, a drag and keys from cli -c; a press shows only in its own copy of a shared selector resource", _widgets),
    Check("lists", "headless: widgets.apk's ListView scrolled by 600 px has row 11 first and 12 rows shown, and ATL stays up until the timeout", _lists),
    Check("controls", "headless: widgets.apk's buttons, checkboxes, radios, switch, toggle and image button take taps and keys from cli -c", _controls),
    Check("text", "headless: widgets.apk's text fields take cli -c text lines through filters, watchers, a composition, a held report, focus moves and Back", _text),
    Check("pan", "headless: widgets.apk's PanActivity: a gesture on a scroll node is taken as the toolkit's pan is, as Android's ScrollView and HorizontalScrollView take it: not when a child asked its parent not to intercept, not by a ScrollView whose content fits, by a HorizontalScrollView whose content fits, and by a node with content to scroll", _pan),
    Check("draw", "headless: widgets.apk's Canvas view redraws on invalidate, not on a same-size layout; display lists (clips, a PNG bitmap, a scrolled background, text, paths, arcs, gradients, a layer, nine-patches) match the golden; the view readback says it draws no views", _draw),
    Check("draw-gtk", "gtk: the same view draws its three times through gsk and the bitmap readbacks and the view's own replay's (clips, a PNG, a filtered drawable, a gradient, text) hold, with no missing native and no GTK critical; the draws' order and the display lists aren't compared", _draw_gtk),
    Check("frames", "headless: widgets.apk's PassesActivity: an OnPreDrawListener that cancels three frames holds a view's draw back to the fourth, one that cancels an invalidate's draw-only pass does the same; a layout asked for from a global layout call is done before the next frame's callbacks; a listener that asks for a layout in every call gets passes at the frame rate, with the main loop still running its posted message", _frames),
    Check("windows", "headless: windows.apk's window state from an activity and a dialog in order with the task's moves, none from a stopped activity; a dialog's insets at 160 and 480 dpi; the order and frames of WindowManager windows (an overlay and a toast above the dialogs, a dialog's place kept by a hide and a show), where dialogs and a popup are placed in the bars and the display, a popup, an AutoCompleteTextView's drop-down, a menu, and toasts with their durations; a dialog's views are drawn", _windows),
    Check("windows-gtk", "gtk: a popup below its anchor, a native menu and a toast", _windows_gtk),
    Check("input-gtk", "gtk: pointer events fed through the debug agent: in the dialog APK's OutsideActivity a touch outside its dialog closes it from its own UP, the next gesture reaches the activity behind, and two pointers get ids 0 and 1; in the nav APK an activity that finishes on its DOWN gets a CANCEL and the activity below gets nothing of that gesture; in widgets.apk keys fed through the key controllers move focus and click, a release with no press goes nowhere, and a key's code is its hardware key's whatever the modifiers; in windows.apk a touch outside a popup that watches outside touches closes it and reaches the activity", _input_gtk),
    Check("text-gtk", "gtk: widgets.apk's TextActivity: text typed through the debug agent into a GtkText goes through Java's filter and the field shows Java's text, also after Java's setText and typing on; a Return typed with a character in one main-loop call reaches Java's key listener after the character; InputStateActivity's fields keep GTK's input in a disabled ScrollView and at alpha 0, and a field under blocksDescendants gives GTK's focus back; an alert's long message leaves its view room", _text_gtk),
    Check("keyboard", "headless: windows.apk's fields under an IME inset: adjustPan moves the window up only as far as the field needs, adjustResize lays it out above the keyboard (keyboard-pan.viewtree, keyboard-resize.viewtree), both also against what their layout alone would give and at 480 dpi; no mode follows the scroll container; a dialog is placed above the keyboard and a popup follows its field (keyboard-dialog-*, keyboard-popup*); stateVisible and an adjustResize window going forward open the keyboard", _keyboard),
    Check("config", "headless: windows.apk under night changes from cli -c: an activity whose manifest covers uiMode, its view, its dialogs' views (a hidden one too) and the Application hear them and resolve night resources; one that doesn't keeps its configuration, its dialog's view too", _config),
]


def listing() -> str:
    return "\n".join(f"{c.name}: {c.what}" for c in CHECKS)


def select(names: list[str]) -> list[Check]:
    known = {c.name: c for c in CHECKS}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise DineError(f"no smoke check {', '.join(unknown)}; there are: {', '.join(known)}")
    return [known[n] for n in names] if names else CHECKS


def smoke(names: list[str], out=print) -> int:
    """Exit 1 at the first failure."""
    global _display
    begin = time.monotonic()
    checks = select(names)
    # gtk runs sit in their own sessions, out of reach of signals sent to us: turn them into an exit
    # so the finally blocks kill the runs and the display
    handlers = {sig: signal.signal(sig, lambda signum, _: sys.exit(128 + signum))
                for sig in (signal.SIGTERM, signal.SIGHUP)}
    try:
        _fresh.clear()
        for c in checks:
            t = time.monotonic()
            problem = c.run()
            if problem:
                head, _, rest = problem.partition("\n")
                out(f"{c.name}: FAILED ({head})" + (f"\n{rest}" if rest else ""))
                return 1
            out(f"{c.name}: ok ({time.monotonic() - t:.1f} s)")
    finally:
        if _display:
            _display.close()
            _display = None
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    out(f"smoke passed: {', '.join(c.name for c in checks)} ({time.monotonic() - begin:.0f} s)")
    return 0
