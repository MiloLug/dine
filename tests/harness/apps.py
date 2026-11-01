#!/usr/bin/env python3
"""tools/dine test apps: real APKs run on the headless ATL build, or with --gtk on the gtk build
(needs a display), to their log markers.

The table is tests/android-compat/apps/apps.toml, each build's expectations sit beside it in
expectations/. Results are one per app: pass, fail or timeout.
"""

import argparse
import os
import re
import signal
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

import expect
from common import ROOT, parallel

SUITE = ROOT / "tests/android-compat/apps"
APKS = ROOT / "third_party/apks"
OUT = ROOT / "out/tests/apps"
TIMEOUT = 60
SETTLE = 3   # s the app must stay up after its last marker
FATAL = re.compile(rb"UnsatisfiedLinkError|JNI DETECTED ERROR|Runtime aborting|FATAL EXCEPTION")


@dataclass(frozen=True)
class Build:
    name: str
    dir: Path
    expectations: Path
    jobs: int


HEADLESS = Build("headless", ROOT / "out/linux/build/dine-atl-headless", SUITE / "expectations/linux-x86_64-headless.json",
                 os.cpu_count() or 4)
# one app at a time: their windows share the display
GTK = Build("gtk", ROOT / "out/linux/build/dine-atl", SUITE / "expectations/linux-x86_64-gtk.json", 1)


def markers(app: dict, build: Build) -> list[bytes]:
    return [m.encode() for m in app["markers"] + app.get(f"{build.name}_markers", [])]


def verdict(log: bytes, wanted: list[bytes], running: bool) -> str | None:
    """None while the run should go on, else pass or a problem. Bytes: ATL's output needn't be UTF-8."""
    fatal = FATAL.search(log)
    if fatal:
        line = log[log.rfind(b"\n", 0, fatal.start()) + 1:].split(b"\n", 1)[0]
        return "fatal: " + line.decode(errors="replace").strip()
    missing = [m for m in wanted if m not in log]
    if not running:
        return f"exited before {missing[0].decode()!r}" if missing else "exited"
    return None if missing else "pass"


def run_app(name: str, app: dict, work: Path, build: Build) -> tuple[str, str, str | None]:
    """(name, status, problem)"""
    work.mkdir(parents=True)
    (work / "data").mkdir()
    log = work / "log"
    env = dict(os.environ, RUN_FROM_BUILDDIR="1", ANDROID_APP_DATA_DIR=str(work / "data"))
    cmd = ["./android-translation-layer", str(APKS / app["apk"]), "-l", app["activity"], "-X", "-Xint"]
    wanted = markers(app, build)
    with open(log, "wb") as out:
        proc = subprocess.Popen(cmd, cwd=build.dir, env=env, stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT, start_new_session=True)
    try:
        deadline, settled = time.monotonic() + TIMEOUT, None
        while time.monotonic() < deadline:
            running = proc.poll() is None
            result = verdict(log.read_bytes(), wanted, running)
            if result == "pass":
                settled = settled or time.monotonic() + SETTLE
                if time.monotonic() >= settled:
                    return name, "pass", None
            elif result:
                return name, "fail", f"{result} (log: {log})"
            time.sleep(0.2)
        return name, "timeout", f"no {', '.join(repr(m.decode()) for m in wanted if m not in log.read_bytes())} in {TIMEOUT} s (log: {log})"
    finally:
        try: # the whole group, even when its leader is gone: ATL's children may still run
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("-f", "--filter", help="regex on app names")
    p.add_argument("--gtk", action="store_true", help="run on the gtk build (needs a display; tools/dine test "
                                                        "apps --gtk gives it a hidden one)")
    p.add_argument("--update-expectations", action="store_true",
                   help="record this run's failures as expected (passes clear their entries)")
    a = p.parse_args()

    build = GTK if a.gtk else HEADLESS
    if a.gtk and not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        sys.exit("--gtk needs a display: run it as tools/dine test apps --gtk")
    if not (build.dir / "android-translation-layer").exists():
        sys.exit(f"missing {build.dir / 'android-translation-layer'}: run tools/dine linux build")
    apps = tomllib.loads((SUITE / "apps.toml").read_text())
    if a.filter:
        apps = {n: app for n, app in apps.items() if re.search(a.filter, n)}
    if not apps:
        sys.exit(f"no app in {SUITE / 'apps.toml'} matches")
    for app in apps.values():
        if not (APKS / app["apk"]).exists():
            sys.exit(f"missing {APKS / app['apk']}: docs/first-run.md lists the APKs")
    runs = OUT / "runs" / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    done = parallel(lambda n: run_app(n, apps[n], runs / n, build), sorted(apps), build.jobs, "apps")

    results = {}
    for name, status, problem in sorted(done):
        results[name] = status
        if problem:
            print(f"{name}: {problem}")
    expectations = expect.load(build.expectations)
    if a.update_expectations:
        expect.save(build.expectations, expect.update(results, expectations, "new failure"))
        print(f"updated {build.expectations}")
        return 0
    c = expect.compare(results, expectations)
    passed = sum(s == "pass" for s in results.values())
    print(f"apps ({build.name}): {passed}/{len(results)} pass, {len(c.expected_failures)} expected failures → {runs}")
    for name in c.fixed:
        print(f"fixed: {name} (run with --update-expectations)")
    for name in c.regressions:
        print(f"REGRESSION: {name} {results[name]}")
    return 1 if c.regressions else 0


if __name__ == "__main__":
    sys.exit(main())
