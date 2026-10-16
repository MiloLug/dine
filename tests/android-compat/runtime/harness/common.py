"""Paths, config and helpers shared by the harness stages."""

import concurrent.futures
import os
import re
import sys
import tomllib
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
RUNTIME = HARNESS.parent                    # tests/android-compat/runtime
SHIMS = RUNTIME / "shims"
AUTHORED = RUNTIME / "authored"
ROOT = Path(os.environ.get("DINE_ROOT") or RUNTIME.parents[2])
OUT = ROOT / "out/tests/runtime"
UPSTREAM = OUT / "upstream/art"             # sparse clone of AOSP art (test/ only)
TOP = OUT / "top"                           # fake ANDROID_BUILD_TOP for upstream build scripts
BUILD = OUT / "build"                       # build/<test>/: dex jars + bundle.json
RUNS = OUT / "runs"                         # runs/<id>/<test>/: work dir + output per run
PREFIX = Path(os.environ.get("DINE_LINUX_PREFIX") or ROOT / "out/linux/prefix")
CORE_JAR = PREFIX / "lib/java/core-all_classes.jar"   # art_standalone libcore, for javac/d8

UPSTREAM_TEST = re.compile(r"^\d{3,4}-")


def load_corpus() -> dict:
    return tomllib.loads((RUNTIME / "corpus.toml").read_text())


def discover(pattern: str | None = None) -> dict[str, Path]:
    """Test name -> source dir, upstream first, then authored/."""
    dirs = [d for d in (UPSTREAM / "test").iterdir() if d.is_dir() and UPSTREAM_TEST.match(d.name)]
    dirs += [d for d in AUTHORED.iterdir() if d.is_dir()]
    tests = {d.name: d for d in sorted(dirs)}
    if pattern:
        rx = re.compile(pattern)
        tests = {n: d for n, d in tests.items() if rx.search(n)}
    return tests


def parallel(fn, items: list, jobs: int, label: str) -> list:
    """Map fn over items on a thread pool (the work is in subprocesses), with a progress line."""
    tty = sys.stderr.isatty()
    results = []
    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
        futures = [pool.submit(fn, item) for item in items]
        for i, f in enumerate(concurrent.futures.as_completed(futures), 1):
            results.append(f.result())
            if tty:
                print(f"\r{label} {i}/{len(items)}", end="", file=sys.stderr, flush=True)
    if tty:
        print(file=sys.stderr)
    return results
