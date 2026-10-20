"""Linux smoke: the gtk build runs Gravity Defied to onResume and the dialog APK; the headless build
runs demo_app and the looper and dialog APKs. Needs a prior `tools/dine linux build`."""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Callable

from . import paths
from .paths import DineError

ON_RESUME = b"- onResume - yay!"
GTK_BUILD = paths.OUT / "linux/build/dine-atl"
HEADLESS_BUILD = paths.OUT / "linux/build/dine-atl-headless"
HEADLESS_TESTS = paths.ROOT / "dine-atl/tests/headless"
APKS = paths.ROOT / "third_party/atl_test_apks"
LOOPER_APK = paths.OUT / "tests/apks/looper.apk"
DIALOG_APK = paths.OUT / "tests/apks/dialog.apk"
LOG_DIR = paths.OUT / "linux/smoke"
GD_TIMEOUT = 120


@dataclass(frozen=True)
class Check:
    name: str
    what: str
    # None when it passed, else the problem: its first line goes in the FAILED line, the rest below
    run: Callable[[], str | None]


def _need_display(check: str) -> None:
    if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        raise DineError(f"{check} needs a display (WSLg sets WAYLAND_DISPLAY); headless only: "
                        "tools/dine linux smoke demo looper dialog")


def _gd() -> str | None:
    _need_display("gd")
    atl = shutil.which("android-translation-layer")
    if not atl:
        raise DineError("no android-translation-layer on PATH: run tools/dine linux build atl")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_DIR / "gd.log"
    # ATL runs in its own session, out of reach of signals sent to us: turn them into an exit so the
    # finally below closes its window
    handlers = {sig: signal.signal(sig, lambda signum, _: sys.exit(128 + signum))
                for sig in (signal.SIGTERM, signal.SIGHUP)}
    with tempfile.TemporaryDirectory(prefix="dine-gd-") as data, open(log, "wb") as out:
        proc = subprocess.Popen([atl, str(APKS / "org.happysanta.gd_29.apk"), "-l", "org/happysanta/gd/GDActivity",
                                 "-X", "-Xint"], env={**os.environ, "ANDROID_APP_DATA_DIR": data},
                                stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + GD_TIMEOUT
            while time.monotonic() < deadline:
                exited = proc.poll() is not None
                # bytes: ATL's output needn't be UTF-8
                if ON_RESUME in log.read_bytes():
                    return None
                if exited:
                    return f"exit status {proc.returncode} before onResume; log: {log}"
                time.sleep(0.2)
            return f"no onResume in {GD_TIMEOUT} s; log: {log}"
        finally:
            _kill_group(proc)
            for sig, handler in handlers.items():
                signal.signal(sig, handler)


def _kill_group(proc: subprocess.Popen) -> None:
    # the whole group even when its leader is gone: ATL's children may still run
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def _script(label: str, *args) -> str | None:
    r = subprocess.run([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return None if r.returncode == 0 else f"{label}: exit status {r.returncode}\n{r.stdout.rstrip()}"


def _need_headless() -> None:
    if not HEADLESS_BUILD.is_dir():
        raise DineError(f"no {HEADLESS_BUILD}: run tools/dine linux build atl-headless")


def _demo() -> str | None:
    _need_headless()
    return _script("run-demo.sh", HEADLESS_TESTS / "run-demo.sh", HEADLESS_BUILD, APKS / "demo_app.apk")


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
    _need_display("dialog-gtk")
    if not GTK_BUILD.is_dir():
        raise DineError(f"no {GTK_BUILD}: run tools/dine linux build atl")
    return _dialog_apk() or _script("run-dialog.sh", HEADLESS_TESTS / "run-dialog.sh", GTK_BUILD, DIALOG_APK)


CHECKS = [
    Check("gd", "gtk: Gravity Defied reaches onResume under -Xint (opens a window)", _gd),
    Check("demo", "headless: demo_app reaches onResume, view tree matches the golden", _demo),
    Check("looper", "headless: looper.apk goes through the loop paths and exits 0", _looper),
    Check("dialog", "headless: dialog.apk's alert and list take scripted answers, it exits 0", _dialog),
    Check("dialog-gtk", "gtk: the same through the GTK dialog's widgets (opens a window)", _dialog_gtk),
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
    begin = time.monotonic()
    checks = select(names)
    for c in checks:
        t = time.monotonic()
        problem = c.run()
        if problem:
            head, _, rest = problem.partition("\n")
            out(f"{c.name}: FAILED ({head})" + (f"\n{rest}" if rest else ""))
            return 1
        out(f"{c.name}: ok ({time.monotonic() - t:.1f} s)")
    out(f"smoke passed: {', '.join(c.name for c in checks)} ({time.monotonic() - begin:.0f} s)")
    return 0
