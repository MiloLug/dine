"""Command line: scripts/test-runtime.sh [fetch|build|run|all] [options]."""

import argparse
import collections
import datetime
import json
import os
import platform
import shutil
import time

import expect
from build import build_all
from common import BUILD, ROOT, RUNS, RUNTIME, discover, load_corpus
from fetch import fetch
from run import RunOptions, run_all

KEEP_RUNS = 10


def _positive(value: str) -> int:
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return n


def _args(argv):
    p = argparse.ArgumentParser(prog="scripts/test-runtime.sh",
                                description="ART run-tests on the local dalvikvm (-Xint).")
    p.add_argument("stage", nargs="?", default="all", choices=["fetch", "build", "run", "all"],
                   help="fetch: upstream tests + tool check; build: fetch + build (incremental); "
                        "run: run existing builds; all (default): fetch + build + run")
    p.add_argument("-f", "--filter", metavar="REGEX", help="only tests whose name matches")
    p.add_argument("-j", "--jobs", type=_positive, default=os.cpu_count())
    p.add_argument("--timeout", type=_positive, metavar="S", help="default per-test timeout (seconds)")
    p.add_argument("--strict", action="store_true",
                   help="fail tests that abort in the runtime's shutdown thread")
    p.add_argument("--vm-arg", action="append", default=[], metavar="ARG",
                   help="extra dalvikvm argument (repeatable)")
    p.add_argument("--expectations", default=str(RUNTIME / f"expectations/linux-{platform.machine()}.json"))
    p.add_argument("--update-expectations", action="store_true",
                   help="rewrite the expectations file from this run's results")
    return p.parse_args(argv)


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
    run_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True)
    latest = RUNS / "latest"
    latest.unlink(missing_ok=True)
    latest.symlink_to(run_id)
    for old in sorted(d for d in RUNS.iterdir() if d.is_dir() and not d.is_symlink())[:-KEEP_RUNS]:
        shutil.rmtree(old)
    return run_id, run_dir


def _report(results: dict, cmp: expect.Comparison, run_dir, seconds: float, strict: bool) -> None:
    counts = collections.Counter(r["status"] for r in results.values())
    skips = collections.Counter(r["reason"] for r in results.values() if r["status"] == "skip")
    aborts = sum(1 for r in results.values() if r.get("shutdown_abort"))
    print(f"runtime: {len(results)} tests in {seconds:.1f}s")
    print("  " + " | ".join(f"{s} {counts[s]}" for s in ("pass", "fail", "timeout", "build-fail", "skip")))
    if skips:
        print("  skipped: " + " · ".join(f"{r} {n}" for r, n in skips.most_common()))
    if aborts:
        print(f"  shutdown-thread aborts: {aborts}, " +
              ("failed (--strict)" if strict else "tolerated (--strict fails them)"))
    print(f"  expected failures: {len(cmp.expected_failures)}")
    if cmp.regressions:
        print(f"  REGRESSIONS ({len(cmp.regressions)}):")
        for name in cmp.regressions:
            r = results[name]
            where = (BUILD / name / "build-output.txt" if r["status"] == "build-fail"
                     else run_dir / name / ("diff" if (run_dir / name / "diff").exists() else "vm-output.txt"))
            print(f"    {name}  {r['status']}  {_rel(where)}")
    if cmp.fixed:
        print(f"  fixed ({len(cmp.fixed)}): {' '.join(cmp.fixed)}")
        print("    → record with --update-expectations")
    print(f"results: {_rel(run_dir / 'results.json')}")


def main(argv=None) -> int:
    args = _args(argv)
    corpus = load_corpus()
    if args.stage != "run":
        fetch(corpus)
    if args.stage == "fetch":
        return 0

    start = time.monotonic()
    tests = discover(args.filter)
    if not tests:
        raise SystemExit(f"no tests match {args.filter!r}")
    if args.stage == "run":
        bundles = _load_bundles(tests)
    else:
        bundles = build_all(tests, args.jobs)
        built = sum(1 for b in bundles.values() if not b.get("cached"))
        failed = sum(1 for b in bundles.values() if b["status"] == "build-fail")
        print(f"build: {len(bundles)} tests, {built} (re)built, {failed} failed "
              f"({time.monotonic() - start:.1f}s) → {_rel(BUILD)}")
    if args.stage == "build":
        return 0

    run_id, run_dir = _new_run_dir()
    opts = RunOptions(jobs=args.jobs, timeout=args.timeout, strict=args.strict, vm_args=args.vm_arg)
    results = run_all(bundles, corpus, run_dir, opts)
    (run_dir / "results.json").write_text(json.dumps({
        "id": run_id,
        "upstream": corpus["upstream"]["commit"],
        "vm_args": corpus["run"]["vm_args"] + args.vm_arg,
        "strict": args.strict,
        "results": dict(sorted(results.items())),
    }, indent=2) + "\n")

    expectations_path = ROOT / args.expectations
    expectations = expect.load(expectations_path)
    statuses = {n: r["status"] for n, r in results.items()}
    cmp = expect.compare(statuses, expectations)
    _report(results, cmp, run_dir, time.monotonic() - start, args.strict)

    if args.update_expectations:
        new = expect.update(statuses, expectations, f"baseline {datetime.date.today()}")
        expect.save(expectations_path, new)
        print(f"expectations: {len(new)} entries ({len(new) - len(expectations):+d}) → "
              f"{_rel(expectations_path)}")
        return 0
    return 1 if cmp.regressions else 0
