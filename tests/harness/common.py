import concurrent.futures
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import tomllib
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
SHIMS = HARNESS / "shims"
ROOT = Path(os.environ.get("DINE_ROOT") or HARNESS.parents[1])
RUNTIME = ROOT / "dine-art/tests/runtime"   # the suite: corpus.toml, expectations/, authored/
AUTHORED = RUNTIME / "authored"
D8 = ROOT / "tools/bin/d8"                  # build-tools d8 on its own JDK
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
    """Test name -> source dir, for upstream and authored/ tests."""
    dirs = [d for d in (UPSTREAM / "test").iterdir() if d.is_dir() and UPSTREAM_TEST.match(d.name)]
    dirs += [d for d in AUTHORED.iterdir() if d.is_dir()]
    tests = {d.name: d for d in sorted(dirs)}
    if pattern:
        rx = re.compile(pattern)
        tests = {n: d for n, d in tests.items() if rx.search(n)}
    return tests


def parallel(fn, items: list, jobs: int, label: str) -> list:
    """Map fn over items on a thread pool (the work is in subprocesses), with a progress line.
    Results come in completion order, not item order."""
    tty = sys.stderr.isatty()
    results = []
    pool = concurrent.futures.ThreadPoolExecutor(jobs)
    try:
        futures = [pool.submit(fn, item) for item in items]
        for i, f in enumerate(concurrent.futures.as_completed(futures), 1):
            results.append(f.result())
            if tty:
                print(f"\r{label} {i}/{len(items)}", end="", file=sys.stderr, flush=True)
    finally:
        pool.shutdown(cancel_futures=True)
    if tty:
        print(file=sys.stderr)
    return results


_sessions: set[int] = set()   # process groups of the children that run
_stopping = False


def spawn(cmd, **kwargs) -> subprocess.Popen:
    """Popen in a session of its own, which `end` and a stop signal kill as a whole."""
    proc = subprocess.Popen(cmd, start_new_session=True, **kwargs)
    _sessions.add(proc.pid)
    if _stopping:
        end(proc)
        raise KeyboardInterrupt
    return proc


def end(proc: subprocess.Popen) -> None:
    """Kills the child's session: its own children may outlive the leader."""
    if proc.pid not in _sessions:
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()
    _sessions.discard(proc.pid)


def run(cmd, timeout: float, **kwargs) -> int | None:
    """The child's exit status, or None when it was killed at the timeout."""
    proc = spawn(cmd, **kwargs)
    try:
        status = proc.wait(timeout)
    except subprocess.TimeoutExpired:
        status = None
    finally:
        end(proc)
    if _stopping:   # the stop signal killed it: its status says nothing about the child
        raise KeyboardInterrupt
    return status


def stop_on_signals() -> None:
    """SIGINT, SIGTERM and SIGHUP end every child `spawn` started, then the harness: the children
    sit in their own sessions, out of reach of a signal sent to us."""
    def stop(signum, _):
        global _stopping
        _stopping = True
        for pgid in list(_sessions):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        sys.exit(128 + signum)
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, stop)


def new_run_dir(runs: Path, keep: int = 10) -> Path:
    """A new runs/<time>-<pid>, after dropping all but the newest `keep` older ones."""
    if runs.is_dir():
        for old in sorted(d for d in runs.iterdir() if d.is_dir() and not d.is_symlink())[:-keep]:
            shutil.rmtree(old, ignore_errors=True)
    return runs / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
