"""Command line: tools/dine test runtime [fetch|build|run|all] [options]."""

import argparse
import collections
import datetime
import json
import os
import platform
import time

import expect
from build import build_all
from common import BUILD, ROOT, RUNS, RUNTIME, discover, load_corpus, new_run_dir, stop_on_signals
from fetch import fetch
from run import RunOptions, run_all

def _positive(value: str) -> int:
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return n


def _args(argv):
    p = argparse.ArgumentParser(prog="tools/dine test runtime", allow_abbrev=False,
                                description="ART run-tests on the local dalvikvm (-Xint).")
    p.add_argument("stage", nargs="?", default="all", choices=["fetch", "build", "run", "all"],
                   help="fetch: upstream tests + tool check; build: fetch + build (incremental); "
                        "run: run existing builds; all (default): fetch + build + run")
    p.add_argument("-f", "--filter", metavar="REGEX", help="only tests whose name matches")
    p.add_argument("-j", "--jobs", type=_positive, default=os.cpu_count())
    p.add_argument("--timeout", type=_positive, metavar="S", help="default per-test timeout (seconds)")
    p.add_argument("--vm-arg", action="append", default=[], metavar="ARG",
                   help="extra dalvikvm argument (repeatable)")
    p.add_argument("--network", action="store_true",
                   help="also run tests that need the internet (skipped otherwise)")
    p.add_argument("--expectations", default=str(RUNTIME / f"expectations/linux-{platform.machine()}.json"))
    p.add_argument("--update-expectations", action="store_true",
                   help="drop the entries of tests that pass now and list the tests that ran; "
                        "refused while a regression stands")
    args = p.parse_args(argv)
    if args.update_expectations and (args.vm_arg or args.timeout):
        p.error("--update-expectations records the suite's own run: not with --vm-arg or --timeout")
    return args


def _rel(path) -> str:
    return os.path.relpath(path, ROOT)


def _load_bundles(names) -> dict[str, dict]:
    bundles, missing = {}, []
    for name in names:
        p = BUILD / name / "bundle.json"
        if p.exists():
            bundles[name] = json.loads(p.read_text())
        else:
            missing.append(name)
    if missing:
        raise SystemExit(f"not built: {', '.join(missing[:5])}{' …' if len(missing) > 5 else ''}"
                         " (run the build stage)")
    return bundles


def _new_run_dir():
    run_dir = new_run_dir(RUNS)
    run_dir.mkdir(parents=True)
    latest = RUNS / "latest"
    latest.unlink(missing_ok=True)
    latest.symlink_to(run_dir.name)
    return run_dir.name, run_dir


def _report(results: dict, seconds: float) -> None:
    counts = collections.Counter(r["status"] for r in results.values())
    skips = collections.Counter(r["reason"] for r in results.values() if r["status"] == "skip")
    print(f"runtime: {len(results)} tests in {seconds:.1f}s")
    print("  " + " | ".join(f"{s} {counts[s]}" for s in ("pass", "fail", "crash", "timeout", "build-fail", "skip")))
    if skips:
        print("  skipped: " + " · ".join(f"{r} {n}" for r, n in skips.most_common()))


def main(argv=None) -> int:
    args = _args(argv)
    stop_on_signals()
    corpus = load_corpus()
    if args.stage != "run":
        fetch(corpus)
    if args.stage == "fetch":
        return 0

    start = time.monotonic()
    tests = discover(args.filter)
    if not tests:
        raise SystemExit(f"no tests match {args.filter!r}")
    expectations_path = ROOT / args.expectations
    if args.stage == "run":
        bundles = _load_bundles(tests)
    else:
        expected_build_fail = {n for n, e in expect.load(expectations_path).items() if e["expect"] == "build-fail"}
        bundles = build_all(tests, args.jobs, expected_build_fail)
        built = sum(1 for b in bundles.values() if not b.get("cached"))
        failed = sum(1 for b in bundles.values() if b["status"] == "build-fail")
        print(f"build: {len(bundles)} tests, {built} (re)built, {failed} failed "
              f"({time.monotonic() - start:.1f}s) → {_rel(BUILD)}")
    if args.stage == "build":
        return 0

    run_id, run_dir = _new_run_dir()
    opts = RunOptions(jobs=args.jobs, timeout=args.timeout, vm_args=args.vm_arg, network=args.network)
    results = run_all(bundles, corpus, run_dir, opts)
    (run_dir / "results.json").write_text(json.dumps({
        "id": run_id,
        "upstream": corpus["upstream"]["commit"],
        "vm_args": corpus["run"]["vm_args"] + args.vm_arg,
        "results": dict(sorted(results.items())),
    }, indent=2) + "\n")
    _report(results, time.monotonic() - start)

    def where(name: str) -> str:
        r = results[name]
        path = (BUILD / name / "build-output.txt" if r["status"] == "build-fail"
                else run_dir / name / ("diff" if (run_dir / name / "diff").exists() else "output.txt"))
        return f"{name}  {r['status']}  {_rel(path)}"

    statuses = {n: r["status"] for n, r in results.items()}
    needs_network = frozenset(n for n, r in results.items() if r.get("reason") == "needs network")
    cmp, rc = expect.settle(statuses, expectations_path, whole=not args.filter, record=args.update_expectations,
                            new_reason=f"baseline {datetime.date.today()}", optional=needs_network, describe=where)
    print(f"  expected failures: {len(cmp.expected_failures)}")
    print(f"results: {_rel(run_dir / 'results.json')}")
    return rc
