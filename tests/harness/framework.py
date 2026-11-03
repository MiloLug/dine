#!/usr/bin/env python3
"""tools/dine test framework: android.* JUnit3 suites run in-VM on the headless ATL build, or with
--gtk on the gtk build (needs a display); --one-vm runs them side by side in one headless VM.

Each dine-atl/tests/framework/<suite>/ is a test APK; the runner finds its TestCases in the dex.
Results are `<Class>#<test>` plus `suite:<name>` for the run itself (and `suite:one-vm` for the
shared VM); each build has its own expectations file.
"""

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import apk
import expect
from common import PREFIX, ROOT, parallel

SUITES = ROOT / "dine-atl/tests/framework"
OUT = ROOT / "out/tests/framework"
JUNIT = (PREFIX / "lib/java/core-junit_classes.jar", PREFIX / "lib/java/junit-runner_classes.jar")
RUNNER = "android.test.InstrumentationTestRunner"
TIMEOUT = 120

STATUS_CODES = {0: "pass", -1: "fail", -2: "fail"}   # -1 error, -2 assertion failure
MULTILINE = {"stream", "stack"}
# Instrumentation's lines carry their app's package; unprefixed ones are ATL's own stdout
PREFIXED = re.compile(r"\[([\w.]+)\] (.*)")


@dataclass(frozen=True)
class Build:
    dir: Path
    expectations: Path
    jobs: int

    def classpath(self) -> tuple[Path, ...]:
        # not dexed: the device copy is ./test_runner.jar
        return (self.dir / "src/test-runner/test_runner.jar", *JUNIT)


HEADLESS = Build(ROOT / "out/linux/build/dine-atl-headless", SUITES / "expectations/linux-x86_64-headless.json",
                 os.cpu_count() or 4)
# one suite at a time: their windows share the display
GTK = Build(ROOT / "out/linux/build/dine-atl", SUITES / "expectations/linux-x86_64-gtk.json", 1)


@dataclass
class Run:
    tests: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def lines_by_package(stdout: str) -> dict[str, list[str]]:
    """Instrumentation's lines by the package that printed them, prefix stripped."""
    lines: dict[str, list[str]] = {}
    for line in stdout.splitlines():
        if m := PREFIXED.fullmatch(line):
            lines.setdefault(m[1], []).append(m[2])
    return lines


def parse(stdout: str, package: str | None = None) -> Run:
    """`am instrument -r` output of one app (package; None: a run of one app): INSTRUMENTATION_STATUS
    key=value lines, each block ended by INSTRUMENTATION_STATUS_CODE; INSTRUMENTATION_CODE ends the
    run."""
    by_package = lines_by_package(stdout)
    if package is None:
        lines = [line for app in by_package.values() for line in app]
    else:
        lines = by_package.get(package, [])
    run = Run()
    block: dict[str, str] = {}
    key = None
    numtests = None
    started: set[str] = set()
    finished = False
    for line in lines:
        if line.startswith("INSTRUMENTATION_STATUS: "):
            key, _, value = line[len("INSTRUMENTATION_STATUS: "):].partition("=")
            block[key] = value
        elif line.startswith("INSTRUMENTATION_STATUS_CODE: "):
            code = int(line.split(": ", 1)[1])
            if "shortMsg" in block:
                run.problems.append(f"aborted: {block['shortMsg']}")
            if "class" in block and "test" in block:
                name = f"{block['class']}#{block['test']}"
                if code == 1:
                    started.add(name)
                else:
                    run.tests[name] = STATUS_CODES.get(code, "fail")
            if "numtests" in block:
                numtests = int(block["numtests"])
            block, key = {}, None
        elif line.startswith("INSTRUMENTATION_RESULT: "):
            key = None
            if line.startswith("INSTRUMENTATION_RESULT: shortMsg="):
                run.problems.append(f"aborted by an uncaught exception: {line.partition('=')[2]} (stack in stderr)")
        elif line.startswith("INSTRUMENTATION_CODE: "):
            finished = line == "INSTRUMENTATION_CODE: -1"
            if not finished:
                run.problems.append(line)
        elif key in MULTILINE:
            block[key] += "\n" + line
    for name in started - run.tests.keys():
        run.tests[name] = "fail"
        run.problems.append(f"{name} never finished")
    if not finished:
        run.problems.append("no INSTRUMENTATION_CODE: -1")
    if not numtests:
        run.problems.append("no tests found")
    elif len(run.tests) != numtests:
        run.problems.append(f"{len(run.tests)} of {numtests} tests reported")
    return run


def run_suite(suite: Path, work: Path, build: Build) -> tuple[str, Run, str]:
    work.mkdir(parents=True)
    package = OUT / "apks" / f"{suite.name}.apk"
    try:
        apk.build(suite, package, build.classpath())
    except (subprocess.CalledProcessError, SystemExit) as e:
        return suite.name, Run(problems=[f"APK build failed: {e}"]), "fail"
    (work / "data").mkdir()
    # MALLOC_PERTURB_ fills freed memory, so a use-after-free fails instead of reading intact data
    env = dict(os.environ, RUN_FROM_BUILDDIR="1", DINE_PREFIX=str(work / "data"), MALLOC_PERTURB_="85")
    cmd = ["./android-translation-layer", "--instrument", RUNNER, str(package), "-X", "-Xint"]
    with open(work / "stdout", "w") as out, open(work / "stderr", "w") as err:
        try:
            proc = subprocess.run(cmd, cwd=build.dir, env=env, stdout=out, stderr=err, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            run = parse((work / "stdout").read_text(errors="replace"))
            return suite.name, run, "timeout"
    run = parse((work / "stdout").read_text(errors="replace"))
    if proc.returncode != 0:
        run.problems.append(f"exit {proc.returncode}")
    return suite.name, run, "fail" if run.problems else "pass"


def manifest_package(suite: Path) -> str:
    return re.search(r'package="([^"]+)"', (suite / "AndroidManifest.xml").read_text())[1]


def run_one_vm(suites: list[Path], work: Path, build: Build) -> tuple[dict[str, tuple[Run, str]], Run, str]:
    """All suites as apps of one VM: each suite's run and status, and the shared run's."""
    work.mkdir(parents=True)
    shared = Run()
    cmd = ["./android-translation-layer", "-X", "-Xint"]
    for suite in suites:
        package = OUT / "apks" / f"{suite.name}.apk"
        try:
            apk.build(suite, package, build.classpath())
        except (subprocess.CalledProcessError, SystemExit) as e:
            shared.problems.append(f"{suite.name}: APK build failed: {e}")
            return {}, shared, "fail"
        cmd += ["--instrument", RUNNER, str(package)]
    (work / "data").mkdir()
    env = dict(os.environ, RUN_FROM_BUILDDIR="1", DINE_PREFIX=str(work / "data"), MALLOC_PERTURB_="85")
    status = None
    with open(work / "stdout", "w") as out, open(work / "stderr", "w") as err:
        try:
            proc = subprocess.run(cmd, cwd=build.dir, env=env, stdout=out, stderr=err, timeout=TIMEOUT * len(suites))
            if proc.returncode != 0:
                shared.problems.append(f"exit {proc.returncode}")
        except subprocess.TimeoutExpired:
            status = "timeout"
    stdout = (work / "stdout").read_text(errors="replace")
    runs = {}
    for suite in suites:
        run = parse(stdout, manifest_package(suite))
        runs[suite.name] = run, status or ("fail" if run.problems else "pass")
    return runs, shared, status or ("fail" if shared.problems else "pass")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("-f", "--filter", help="regex on suite names")
    p.add_argument("--gtk", action="store_true", help="run on the gtk build (needs a display; tools/dine test "
                                                        "framework --gtk gives it a hidden one)")
    p.add_argument("--one-vm", action="store_true", help="run the suites side by side in one headless VM")
    p.add_argument("--update-expectations", action="store_true",
                   help="record this run's failures as expected (passes clear their entries)")
    a = p.parse_args()

    if a.one_vm and a.gtk:
        sys.exit("--one-vm runs on the headless build: gtk runs one app per process")
    build = GTK if a.gtk else HEADLESS
    if a.gtk and not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        sys.exit("--gtk needs a display: run it as tools/dine test framework --gtk")
    for f in (build.dir / "android-translation-layer", build.dir / "test_runner.jar"):
        if not f.exists():
            sys.exit(f"missing {f}: run tools/dine linux build")
    suites = sorted(d for d in SUITES.iterdir() if (d / "AndroidManifest.xml").exists())
    if a.filter:
        suites = [d for d in suites if re.search(a.filter, d.name)]
    if not suites:
        sys.exit(f"no suite in {SUITES} matches")
    runs = OUT / "runs" / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    results: dict[str, str] = {}
    if a.one_vm:
        by_suite, shared, status = run_one_vm(suites, runs / "one-vm", build)
        done = [(name, run, suite_status) for name, (run, suite_status) in by_suite.items()]
        results["suite:one-vm"] = status
        for problem in shared.problems:
            print(f"one-vm: {problem} (log: {runs / 'one-vm'})")
    else:
        done = parallel(lambda s: run_suite(s, runs / s.name, build), suites, build.jobs, "framework")

    for name, run, status in sorted(done):
        results[f"suite:{name}"] = status
        results.update(run.tests)
        for problem in run.problems:
            print(f"{name}: {problem} (log: {runs / ('one-vm' if a.one_vm else name)})")
    expectations = expect.load(build.expectations)
    if a.update_expectations:
        expect.save(build.expectations, expect.update(results, expectations, "new failure"))
        print(f"updated {build.expectations}")
        return 0
    c = expect.compare(results, expectations)
    passed = sum(s == "pass" for n, s in results.items() if not n.startswith("suite:"))
    n_suite_rows = sum(n.startswith("suite:") for n in results)
    print(f"framework{' (one VM)' if a.one_vm else ''}: {len(suites)} suites, {passed}/{len(results) - n_suite_rows} tests pass, "
          f"{len(c.expected_failures)} expected failures → {runs}")
    for name in c.fixed:
        print(f"fixed: {name} (run with --update-expectations)")
    for name in c.regressions:
        print(f"REGRESSION: {name} {results[name]}")
    return 1 if c.regressions else 0


if __name__ == "__main__":
    sys.exit(main())
