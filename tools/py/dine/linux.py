"""Linux smoke: the gtk build runs Gravity Defied to onResume, the dialog and views APKs and the
widgets APK's drawing, on a hidden display (display.py); the headless build runs demo_app and the
looper, dialog, nav, views and widgets APKs. Needs a prior `tools/dine linux build`."""

import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable

from . import display, paths
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
# not in tests/apks: the iOS dev payload bundles every APK there
CRASH_APK = paths.OUT / "tests/linux-apks/crash.apk"


@dataclass(frozen=True)
class Check:
    name: str
    what: str
    # None when it passed, else the problem: its first line goes in the FAILED line, the rest below
    run: Callable[[], str | None]


_display: display.Display | None = None


def _gtk_env() -> dict[str, str]:
    """The env for a gtk run: the smoke run's hidden display, started by its first gtk check."""
    global _display
    if _display is None:
        _display = display.Display()
    return _display.env()


def _gd(*args: str) -> str | None:
    if not GTK_BUILD.is_dir():
        raise DineError(f"no {GTK_BUILD}: run tools/dine linux build atl")
    proc = subprocess.run([sys.executable, str(paths.ROOT / "tests/harness/apps.py"), "--gtk", "-f", "^gd$", *args],
                          env=_gtk_env(), capture_output=True, text=True)
    # its pass, not an expected failure
    return None if proc.returncode == 0 and "apps (gtk): 1/1 pass" in proc.stdout else (proc.stdout + proc.stderr).strip()


def _script(label: str, *args, env: dict[str, str] | None = None) -> str | None:
    r = subprocess.run([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    return None if r.returncode == 0 else f"{label}: exit status {r.returncode}\n{r.stdout.rstrip()}"


def _need_headless() -> None:
    if not HEADLESS_BUILD.is_dir():
        raise DineError(f"no {HEADLESS_BUILD}: run tools/dine linux build atl-headless")


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


def _dialog_apk() -> str | None:
    return _script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "dialog", DIALOG_APK)


def _dialog() -> str | None:
    _need_headless()
    return _dialog_apk() or _script("run-dialog.sh", HEADLESS_TESTS / "run-dialog.sh", "--headless", HEADLESS_BUILD,
                                    DIALOG_APK)


def _dialog_gtk() -> str | None:
    if not GTK_BUILD.is_dir():
        raise DineError(f"no {GTK_BUILD}: run tools/dine linux build atl")
    return _dialog_apk() or _script("run-dialog.sh", HEADLESS_TESTS / "run-dialog.sh", GTK_BUILD, DIALOG_APK,
                                    env=_gtk_env())


def _nav() -> str | None:
    _need_headless()
    return (_script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "nav", NAV_APK)
            or _script("run-nav.sh", HEADLESS_TESTS / "run-nav.sh", HEADLESS_BUILD, NAV_APK))


def _crash() -> str | None:
    _need_headless()
    return (_script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "crash", CRASH_APK)
            or _script("run-crash.sh", HEADLESS_TESTS / "run-crash.sh", HEADLESS_BUILD, CRASH_APK))


def _views_apk() -> str | None:
    return _script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "views", VIEWS_APK)


def _views() -> str | None:
    _need_headless()
    return _views_apk() or _script("run-views.sh", HEADLESS_TESTS / "run-views.sh", "--headless", HEADLESS_BUILD,
                                   VIEWS_APK)


def _views_gtk() -> str | None:
    if not GTK_BUILD.is_dir():
        raise DineError(f"no {GTK_BUILD}: run tools/dine linux build atl")
    return _views_apk() or _script("run-views.sh", HEADLESS_TESTS / "run-views.sh", GTK_BUILD, VIEWS_APK,
                                   env=_gtk_env())


def _widgets_apk() -> str | None:
    return _script("apk.py", sys.executable, paths.ROOT / "tests/harness/apk.py", HEADLESS_TESTS / "widgets", WIDGETS_APK)


def _widgets() -> str | None:
    _need_headless()
    return _widgets_apk() or _script("run-widgets.sh", HEADLESS_TESTS / "run-widgets.sh", HEADLESS_BUILD, WIDGETS_APK)


def _controls() -> str | None:
    _need_headless()
    return _widgets_apk() or _script("run-controls.sh", HEADLESS_TESTS / "run-controls.sh", HEADLESS_BUILD, WIDGETS_APK)


def _text() -> str | None:
    _need_headless()
    return _widgets_apk() or _script("run-text.sh", HEADLESS_TESTS / "run-text.sh", HEADLESS_BUILD, WIDGETS_APK)


def _draw() -> str | None:
    _need_headless()
    return _widgets_apk() or _script("run-draw.sh", HEADLESS_TESTS / "run-draw.sh", "--headless", HEADLESS_BUILD,
                                     WIDGETS_APK)


def _draw_gtk() -> str | None:
    if not GTK_BUILD.is_dir():
        raise DineError(f"no {GTK_BUILD}: run tools/dine linux build atl")
    return _widgets_apk() or _script("run-draw.sh", HEADLESS_TESTS / "run-draw.sh", GTK_BUILD, WIDGETS_APK,
                                     env=_gtk_env())


CHECKS = [
    Check("gd", "gtk: Gravity Defied reaches onResume under -Xint", _gd),
    Check("gd-package", "gtk: the same, installed with --install-internal and run with --package", lambda: _gd("--by-package")),
    Check("demo", "headless: demo_app reaches onResume, view tree matches the golden", _demo),
    Check("demo-480", "headless: the same at density 480, where sp, dp and px differ", _demo_480),
    Check("looper", "headless: looper.apk goes through the loop paths and exits 0", _looper),
    Check("dialog", "headless: dialog.apk's alerts and list take scripted answers, an alert changes its buttons in onShow, it exits 0", _dialog),
    Check("dialog-gtk", "gtk: the same through the GTK dialog's widgets", _dialog_gtk),
    Check("nav", "headless: nav.apk's lifecycle under Back, Home and front from cli -c", _nav),
    Check("crash", "headless: crash.apk throws in onCreate, onResume, a posted Runnable and a started activity's onCreate; each ends ATL through the uncaught handler with exit 10, no CheckJNI abort", _crash),
    Check("views", "headless: views.apk removes, re-adds and frees views, view tree matches the golden", _views),
    Check("views-gtk", "gtk: the same through GTK's widgets, and gsk frees a nine-patch and a StateListDrawable", _views_gtk),
    Check("widgets", "headless: widgets.apk takes taps, a hold, Tab, Enter, a drag and keys from cli -c; a press shows only in its own copy of a shared selector resource", _widgets),
    Check("controls", "headless: widgets.apk's buttons, checkboxes, radios, switch, toggle and image button take taps and keys from cli -c", _controls),
    Check("text", "headless: widgets.apk's text fields take cli -c text lines through filters, watchers, a composition, a held report, focus moves and Back", _text),
    Check("draw", "headless: widgets.apk's Canvas view redraws on invalidate, not on a same-size layout; display lists (clips, a PNG bitmap, a scrolled background, text, paths, arcs, gradients, a layer, nine-patches) match the golden", _draw),
    Check("draw-gtk", "gtk: the same view draws through gsk", _draw_gtk),
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
