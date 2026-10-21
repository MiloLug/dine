#!/usr/bin/env python3
"""tools/dine test framework: android.* JUnit3 suites run in-VM on the headless ATL build.

Each dine-atl/tests/framework/<suite>/ is a test APK; the runner finds its TestCases in the dex.
Results are `<Class>#<test>` plus `suite:<name>` for the run itself.
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
EXPECTATIONS = SUITES / "expectations/linux-x86_64-headless.json"
HEADLESS = ROOT / "out/linux/build/dine-atl-headless"
OUT = ROOT / "out/tests/framework"
CLASSPATH = (HEADLESS / "src/test-runner/test_runner.jar",   # not dexed: the device copy is ./test_runner.jar
             PREFIX / "lib/java/core-junit_classes.jar",
             PREFIX / "lib/java/junit-runner_classes.jar")
RUNNER = "android.test.InstrumentationTestRunner"
TIMEOUT = 120

STATUS_CODES = {0: "pass", -1: "fail", -2: "fail"}   # -1 error, -2 assertion failure
MULTILINE = {"stream", "stack"}   # other lines between status lines are ATL's own stdout


@dataclass
class Run:
    tests: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def parse(stdout: str) -> Run:
    """`am instrument -r` output: INSTRUMENTATION_STATUS key=value lines, each block ended by
    INSTRUMENTATION_STATUS_CODE; INSTRUMENTATION_CODE ends the run."""
    run = Run()
    block: dict[str, str] = {}
    key = None
    numtests = None
    started: set[str] = set()
    finished = False
    for line in stdout.splitlines():
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
                run.problems.append("aborted by an uncaught exception (stack in stderr)")
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


def run_suite(suite: Path, work: Path) -> tuple[str, Run, str]:
    work.mkdir(parents=True)
    package = OUT / "apks" / f"{suite.name}.apk"
    try:
        apk.build(suite, package, CLASSPATH)
    except (subprocess.CalledProcessError, SystemExit) as e:
        return suite.name, Run(problems=[f"APK build failed: {e}"]), "fail"
    (work / "data").mkdir()
    env = dict(os.environ, RUN_FROM_BUILDDIR="1", ANDROID_APP_DATA_DIR=str(work / "data"))
    cmd = ["./android-translation-layer", "--instrument", RUNNER, str(package), "-X", "-Xint"]
    with open(work / "stdout", "w") as out, open(work / "stderr", "w") as err:
        try:
            proc = subprocess.run(cmd, cwd=HEADLESS, env=env, stdout=out, stderr=err, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            run = parse((work / "stdout").read_text(errors="replace"))
            return suite.name, run, "timeout"
    run = parse((work / "stdout").read_text(errors="replace"))
    if proc.returncode != 0:
        run.problems.append(f"exit {proc.returncode}")
    return suite.name, run, "fail" if run.problems else "pass"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("-f", "--filter", help="regex on suite names")
    p.add_argument("--update-expectations", action="store_true",
                   help="record this run's failures as expected (passes clear their entries)")
    a = p.parse_args()

    for f in (HEADLESS / "android-translation-layer", HEADLESS / "test_runner.jar"):
        if not f.exists():
            sys.exit(f"missing {f}: run tools/dine linux build")
    suites = sorted(d for d in SUITES.iterdir() if (d / "AndroidManifest.xml").exists())
    if a.filter:
        suites = [d for d in suites if re.search(a.filter, d.name)]
    if not suites:
        sys.exit(f"no suite in {SUITES} matches")
    runs = OUT / "runs" / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    done = parallel(lambda s: run_suite(s, runs / s.name), suites, os.cpu_count() or 4, "framework")

    results: dict[str, str] = {}
    for name, run, status in sorted(done):
        results[f"suite:{name}"] = status
        results.update(run.tests)
        for problem in run.problems:
            print(f"{name}: {problem} (log: {runs / name})")
    expectations = expect.load(EXPECTATIONS)
    if a.update_expectations:
        expect.save(EXPECTATIONS, expect.update(results, expectations, "new failure"))
        print(f"updated {EXPECTATIONS}")
        return 0
    c = expect.compare(results, expectations)
    passed = sum(s == "pass" for n, s in results.items() if not n.startswith("suite:"))
    print(f"framework: {len(suites)} suites, {passed}/{len(results) - len(suites)} tests pass, "
          f"{len(c.expected_failures)} expected failures → {runs}")
    for name in c.fixed:
        print(f"fixed: {name} (run with --update-expectations)")
    for name in c.regressions:
        print(f"REGRESSION: {name} {results[name]}")
    return 1 if c.regressions else 0


if __name__ == "__main__":
    sys.exit(main())
