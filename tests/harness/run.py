"""Run stage: each built test under dalvikvm, graded against its expected output.

Per test, runs/<id>/<test>/ is both DEX_LOCATION and ANDROID_DATA (as on upstream host runs):
symlinks to the build dir's files plus a fresh dalvik-cache, so runs never write into build/.
Files: vm-output.txt (raw, stdout+stderr merged), output.txt (graded), diff (on mismatch).
"""

import os
import platform
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from classify import expand_vars
from common import BUILD, parallel
from grade import diff, expected_file, outputs_match, strip_shutdown_abort, verdict


@dataclass
class RunOptions:
    jobs: int
    timeout: int | None = None      # overrides the corpus default (not per-test overrides)
    strict: bool = False            # don't tolerate the shutdown abort
    vm_args: list[str] = field(default_factory=list)


def _timeout(name: str, bundle: dict, corpus: dict, opts: RunOptions) -> int:
    return (corpus.get("timeouts", {}).get(name) or bundle.get("timeout") or opts.timeout
            or corpus["run"]["timeout"])


def _workdir(wd: Path, build_dir: Path) -> None:
    wd.mkdir(parents=True)
    for entry in build_dir.iterdir():
        if entry.name not in ("dalvik-cache", "oat"):
            (wd / entry.name).symlink_to(entry)
    (wd / "dalvik-cache" / platform.machine()).mkdir(parents=True)


def _build_fail(name: str, bundle: dict) -> dict:
    """Upstream grades a failed build too: its `check` script gets the build output, so a test
    that expects the build to fail (e.g. 089-many-methods) passes."""
    bdir = BUILD / name
    expected = expected_file(bdir)
    if (bdir / "check").exists() and expected:
        rc = subprocess.run(["bash", "./check", expected.name, "build-output.txt"], cwd=bdir,
                            capture_output=True).returncode
        if rc == 0:
            return {"name": name, "status": "pass", "reason": "build failed as expected"}
    return {"name": name, "status": "build-fail", "reason": bundle["reason"]}


def run_one(name: str, bundle: dict, corpus: dict, run_dir: Path, opts: RunOptions) -> dict:
    if bundle["status"] == "build-fail":
        return _build_fail(name, bundle)
    if bundle["status"] != "ok":
        return {"name": name, "status": bundle["status"], "reason": bundle["reason"]}

    wd = run_dir / name
    _workdir(wd, BUILD / name)
    env = os.environ | {"ANDROID_LOG_TAGS": corpus["run"]["log_tags"], "ANDROID_PRINTF_LOG": "brief",
                        "ANDROID_DATA": str(wd), "DEX_LOCATION": str(wd)}
    cp = str(wd / bundle["jar"])
    if bundle["secondary"] and bundle["ex_jar"]:
        cp += ":" + str(wd / bundle["ex_jar"])
    cmd = ["dalvikvm", *corpus["run"]["vm_args"], *expand_vars(bundle["vm_args"], env), *opts.vm_args,
           "-cp", cp, bundle["main"], *expand_vars(bundle["main_args"], env)]

    start = time.monotonic()
    p = subprocess.Popen(cmd, cwd=wd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         start_new_session=True)
    try:
        out, _ = p.communicate(timeout=_timeout(name, bundle, corpus, opts))
        timed_out = False
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, _ = p.communicate()
        timed_out = True
    seconds = round(time.monotonic() - start, 2)
    output = out.decode("utf-8", "replace")
    (wd / "vm-output.txt").write_text(output)

    result = {"name": name, "exit": p.returncode, "seconds": seconds}
    if timed_out:
        return result | {"status": "timeout", "shutdown_abort": False}

    stripped, abort = strip_shutdown_abort(output)
    graded = output if opts.strict else stripped
    (wd / "output.txt").write_text(graded)
    expected = (wd / bundle["expected"]).read_text(errors="replace")
    if bundle["check"]:
        matched = subprocess.run(["bash", "./check", bundle["expected"], "output.txt"], cwd=wd,
                                 env=env, capture_output=True).returncode == 0
    else:
        matched = outputs_match(expected, graded)
    if not matched:
        (wd / "diff").write_text(diff(expected, graded))
    return result | {"status": verdict(p.returncode, abort, matched, strict=opts.strict),
                     "shutdown_abort": abort}


def run_all(bundles: dict[str, dict], corpus: dict, run_dir: Path, opts: RunOptions) -> dict[str, dict]:
    results = parallel(lambda name: run_one(name, bundles[name], corpus, run_dir, opts),
                       sorted(bundles), opts.jobs, "run")
    return {r["name"]: r for r in results}
