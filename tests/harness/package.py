#!/usr/bin/env python3
"""tools/dine test package: package install, query and removal on the headless ATL build.

Rows: `cli:<check>` (installs and removals through the CLI, graded on exit codes, registry rows and
files), `<Class>#<test>` (the JUnit suite in dine-atl/tests/package/suite, run in-VM after the
fixtures are installed) and `scenario:<name>` (the driver app, one process per scenario, each with
its own scripted dialog answers). Every check gets a fresh prefix.
"""

import argparse
import concurrent.futures
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Callable
from pathlib import Path

import apk
import expect
import framework
from common import ROOT, parallel

SUITE = ROOT / "dine-atl/tests/package"
OUT = ROOT / "out/tests/package"
APKS = OUT / "apks"
BUILD = framework.HEADLESS
EXPECTATIONS = SUITE / "expectations/linux-x86_64-headless.json"
TIMEOUT = 120


@dataclass(frozen=True)
class Fixture:
    name: str
    src: str
    key: str | None
    link_args: tuple[str, ...] = ()
    manifest_replace: tuple[tuple[str, str], ...] = ()   # (old, new) in src's manifest: what aapt2 can't rename


def _version(code: int) -> tuple[str, ...]:
    return ("--version-code", str(code), "--version-name", f"{code}.0")


FIXTURES = (
    Fixture("ext", "ext", "a"),
    Fixture("app", "app", "a", _version(2)),
    Fixture("app-v3", "app", "a", _version(3)),
    Fixture("app-v1", "app", "a", _version(1)),
    Fixture("app-keyb", "app", "b", _version(4)),
    Fixture("plain", "app", None, (*_version(1), "--rename-manifest-package", "dev.dine.pkg.plain"),
            (("dev.dine.pkg.app.prov", "dev.dine.pkg.plain.prov"),)),
    Fixture("provdup", "app", None, (*_version(1), "--rename-manifest-package", "dev.dine.pkg.provdup")),
    Fixture("spoof", "spoof", "a"),
    Fixture("spoofdeny", "spoof", "a", ("--rename-manifest-package", "dev.dine.pkg.spoofdeny")),
    Fixture("gms", "ext", "b", ("--rename-manifest-package", "com.google.android.gms")),
    Fixture("extb", "ext", "b", ("--rename-manifest-package", "dev.dine.pkg.extb")),
    Fixture("gone", "ext", "a", ("--rename-manifest-package", "dev.dine.pkg.gone")),
    Fixture("gone-v2", "ext", "a", ("--rename-manifest-package", "dev.dine.pkg.gone", "--version-code", "2",
                                    "--replace-version")),
    Fixture("driver", "driver", "a", _version(1)),
    Fixture("driver-v2", "driver", "a", _version(2)),
)


def build_fixture(f: Fixture) -> str | None:
    key = SUITE / "keys" / f"{f.key}.p12" if f.key else None
    src = SUITE / "fixtures" / f.src
    with tempfile.TemporaryDirectory() as tmp:
        manifest = None
        if f.manifest_replace:
            text = (src / "AndroidManifest.xml").read_text()
            for old, new in f.manifest_replace:
                if old not in text:
                    return f"{f.name}: {old!r} is not in {src / 'AndroidManifest.xml'}"
                text = text.replace(old, new)
            manifest = Path(tmp) / "AndroidManifest.xml"
            manifest.write_text(text)
        try:
            apk.build(src, APKS / f"{f.name}.apk", link_args=f.link_args, key=key, manifest=manifest)
        except (subprocess.CalledProcessError, SystemExit) as e:
            return f"{f.name}: {e}"
    return None


def env(prefix: Path, **extra: str) -> dict[str, str]:
    prefix.mkdir(parents=True, exist_ok=True)
    return dict(os.environ, RUN_FROM_BUILDDIR="1", DINE_PREFIX=str(prefix),
                DINE_TEST_FIXTURES=str(APKS), MALLOC_PERTURB_="85", **extra)


def atl(work: Path, name: str, args: list[str], prefix: Path, **extra: str) -> subprocess.CompletedProcess:
    """Runs the headless build; its output lands in work/<name>.stdout and .stderr."""
    work.mkdir(parents=True, exist_ok=True)
    cmd = ["./android-translation-layer", *args, "-X", "-Xint"]
    with open(work / f"{name}.stdout", "w") as out, open(work / f"{name}.stderr", "w") as err:
        try:
            return subprocess.run(cmd, cwd=BUILD.dir, env=env(prefix, **extra), stdout=out, stderr=err,
                                  timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(cmd, -1)


def rows(prefix: Path) -> dict[str, dict]:
    """The registry's packages table, by package name."""
    db = sqlite3.connect(f"file:{prefix / 'registry.sqlite'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        return {r["name"]: dict(r) for r in db.execute("SELECT * FROM packages")}
    finally:
        db.close()


# cli:<name> -> check(work, prefix); raises AssertionError on failure
CHECKS: dict = {}
GENERATED = ("com.google.android.gms", "com.google.android.gsf", "com.android.vending")


def check(fn):
    CHECKS[fn.__name__] = fn
    return fn


def run(work: Path, prefix: Path, name: str, *args: str, status: int = 0) -> None:
    proc = atl(work, name, list(args), prefix)
    assert proc.returncode == status, f"{name}: exit {proc.returncode}, expected {status}"


def stored(prefix: Path, row: dict) -> Path:
    return prefix / row["apks"].split(":")[0]


@check
def install(work: Path, prefix: Path) -> None:
    run(work, prefix, "install", "--install", str(APKS / "ext.apk"))
    r = rows(prefix)
    assert sorted(r) == sorted((*GENERATED, "dev.dine.pkg.ext")), sorted(r)
    ext = r["dev.dine.pkg.ext"]
    assert ext["generated"] == 0 and ext["uid"] >= 10000 and ext["version_code"] == 1, ext
    assert stored(prefix, ext).read_bytes() == (APKS / "ext.apk").read_bytes(), "stored APK differs"
    assert (prefix / "data/dev.dine.pkg.ext").is_dir(), "no data dir"
    for name in GENERATED:
        assert r[name]["generated"] == 1 and r[name]["apks"] is None, r[name]
    assert len({row["uid"] for row in r.values()}) == len(r), "uids not unique"
    run(work, prefix, "install-again", "--install", str(APKS / "ext.apk"))
    assert rows(prefix)["dev.dine.pkg.ext"]["generation"] == ext["generation"], "the same file was installed again"


@check
def replace(work: Path, prefix: Path) -> None:
    run(work, prefix, "install-v2", "--install", str(APKS / "app.apk"))
    old = rows(prefix)["dev.dine.pkg.app"]
    run(work, prefix, "install-v3", "--install", str(APKS / "app-v3.apk"))
    new = rows(prefix)["dev.dine.pkg.app"]
    assert new["uid"] == old["uid"] and new["version_code"] == 3, (old, new)
    assert new["first_install_time"] == old["first_install_time"], (old, new)
    assert not stored(prefix, old).parent.exists(), "the replaced version's dir is left"
    assert stored(prefix, new).read_bytes() == (APKS / "app-v3.apk").read_bytes()


@check
def cli_replaces_anything(work: Path, prefix: Path) -> None:
    run(work, prefix, "install", "--install", str(APKS / "app.apk"))
    run(work, prefix, "other-signer", "--install", str(APKS / "app-keyb.apk"))
    assert rows(prefix)["dev.dine.pkg.app"]["version_code"] == 4
    run(work, prefix, "downgrade", "--install", str(APKS / "app-v1.apk"))
    assert rows(prefix)["dev.dine.pkg.app"]["version_code"] == 1


@check
def uninstall(work: Path, prefix: Path) -> None:
    run(work, prefix, "install", "--install", str(APKS / "app.apk"))
    run(work, prefix, "uninstall", "--uninstall", "dev.dine.pkg.app")
    assert "dev.dine.pkg.app" not in rows(prefix)
    for left in ("apps/dev.dine.pkg.app", "data/dev.dine.pkg.app"):
        assert not (prefix / left).exists(), f"{left} is left"
    assert not any((prefix / ".trash").iterdir()), "trash is left"
    run(work, prefix, "uninstall-again", "--uninstall", "dev.dine.pkg.app", status=1)
    run(work, prefix, "uninstall-generated", "--uninstall", "com.android.vending", status=1)
    assert rows(prefix)["com.android.vending"]["generated"] == 1


@check
def replace_generated(work: Path, prefix: Path) -> None:
    run(work, prefix, "install-gms", "--install", str(APKS / "gms.apk"))
    gms = rows(prefix)["com.google.android.gms"]
    assert gms["generated"] == 0 and gms["uid"] == 10000, gms
    run(work, prefix, "uninstall-gms", "--uninstall", "com.google.android.gms")
    gms = rows(prefix)["com.google.android.gms"]
    assert gms["generated"] == 1 and gms["uid"] == 10000 and gms["version_code"] == 250932030, gms


@check
def concurrent_installs(work: Path, prefix: Path) -> None:
    """Processes that write one registry at once, the first of them creating it; two install one package."""
    fixtures = ("ext", "extb", "plain", "spoof", "gms", "app", "app-v3")
    with concurrent.futures.ThreadPoolExecutor(len(fixtures)) as pool:
        procs = dict(zip(fixtures, pool.map(
            lambda f: atl(work, f"install-{f}", ["--install", str(APKS / f"{f}.apk")], prefix), fixtures)))
    failed = [f for f, p in procs.items() if p.returncode]
    assert not failed, f"installs failed: {failed}"
    r = rows(prefix)
    want = {"dev.dine.pkg.ext", "dev.dine.pkg.extb", "dev.dine.pkg.plain", "dev.dine.pkg.spoof", "com.google.android.gms",
            "dev.dine.pkg.app"}
    assert want <= set(r), sorted(want - set(r))
    assert r["com.google.android.gms"]["generated"] == 0, "gms kept its generated row"
    assert len({row["uid"] for row in r.values()}) == len(r), "uids not unique"
    app = r["dev.dine.pkg.app"]
    assert app["version_code"] in (2, 3), app
    versions = list((prefix / "apps/dev.dine.pkg.app").iterdir())
    assert versions == [stored(prefix, app).parent], f"version dirs {versions}"
    assert not any((prefix / "apps/.staging").iterdir()), "staging is left"


@check
def path_run(work: Path, prefix: Path) -> None:
    run(work, prefix, "run", str(APKS / "app.apk"))
    first = rows(prefix)["dev.dine.pkg.app"]
    assert (prefix / "data/dev.dine.pkg.app").is_dir(), "no data dir"
    run(work, prefix, "run-again", str(APKS / "app.apk"))
    assert rows(prefix)["dev.dine.pkg.app"]["generation"] == first["generation"], "the same file was installed again"
    run(work, prefix, "run-v3", str(APKS / "app-v3.apk"))
    v3 = rows(prefix)["dev.dine.pkg.app"]
    assert v3["version_code"] == 3 and v3["uid"] == first["uid"], (first, v3)


def authority_holders(prefix: Path, authority: str) -> list[str]:
    db = sqlite3.connect(f"file:{prefix / 'registry.sqlite'}?mode=ro", uri=True)
    try:
        return sorted(r[0] for r in db.execute("SELECT pkg FROM authorities WHERE authority = ?", (authority,)))
    finally:
        db.close()


@check
def provider_conflict(work: Path, prefix: Path) -> None:
    """provdup is app under another name with app's provider authority: Android refuses it."""
    run(work, prefix, "install", "--install", str(APKS / "app.apk"))
    run(work, prefix, "install-dup", "--install", str(APKS / "provdup.apk"), status=1)
    out = (work / "install-dup.stdout").read_text(errors="replace")
    assert "Failure [status 5]" in out and "dev.dine.pkg.app.prov" in out and "held by dev.dine.pkg.app" in out, out
    proc = atl(work, "run-dup", [str(APKS / "provdup.apk")], prefix)
    assert proc.returncode != 0, "a path run of provdup started"
    log = (work / "run-dup.stdout").read_text(errors="replace") + (work / "run-dup.stderr").read_text(errors="replace")
    assert "dev.dine.pkg.app.prov" in log, "the run's output doesn't name the authority"
    assert "dev.dine.pkg.provdup" not in rows(prefix), "provdup is installed"
    assert authority_holders(prefix, "dev.dine.pkg.app.prov") == ["dev.dine.pkg.app"]
    staging = prefix / "apps/.staging"
    assert not staging.exists() or not any(staging.iterdir()), f"left in {staging}: {list(staging.iterdir())}"


@check
def package_run(work: Path, prefix: Path) -> None:
    run(work, prefix, "install", "--install", str(APKS / "app.apk"))
    run(work, prefix, "run", "--package", "dev.dine.pkg.app")
    assert "app: started" in (work / "run.stdout").read_text(), "the app didn't start"
    run(work, prefix, "run-missing", "--package", "dev.dine.pkg.missing", status=1)


@dataclass(frozen=True)
class Scenario:
    """The driver app installs the way apps do; one process each, its dialogs answered in order."""
    name: str
    arg: str                       # DINE_TEST_SCENARIO: <kind>:<fixture or package>
    answers: str                   # ATL_DIALOG_ANSWERS
    want: tuple[str, ...]          # "scenario: " lines it must print
    setup: tuple[str, ...] = ()    # fixtures the CLI installs first
    never: tuple[str, ...] = ("unscoped",)
    rows: Callable[[dict], str | None] = lambda rows: None


def _row(name: str, **want) -> Callable[[dict], str | None]:
    def check(rows: dict) -> str | None:
        if want.get("absent"):
            return f"{name} is installed" if name in rows else None
        if name not in rows:
            return f"{name} is not installed"
        row = rows[name]
        bad = {k: (row.get(k), v) for k, v in want.items() if row.get(k) != v}
        return f"{name}: {bad}" if bad else None
    return check


SCENARIOS = (
    Scenario("session_install", "session:ext", "Install",
             ("status -1 dev.dine.pkg.ext", "status 0 dev.dine.pkg.ext", "added dev.dine.pkg.ext replacing=false"),
             rows=_row("dev.dine.pkg.ext", installer="dev.dine.pkg.driver")),
    Scenario("session_cancel", "session:ext", "Cancel", ("status 3 dev.dine.pkg.ext",),
             never=("unscoped", "added"), rows=_row("dev.dine.pkg.ext", absent=True)),
    Scenario("session_other_signer", "session:app-keyb", "Install", ("status 5 dev.dine.pkg.app",), setup=("app",), never=("unscoped", "added"),
             rows=_row("dev.dine.pkg.app", version_code=2)),
    Scenario("session_downgrade", "session:app-v1", "Install", ("status 7 dev.dine.pkg.app",), setup=("app",), never=("unscoped", "added"),
             rows=_row("dev.dine.pkg.app", version_code=2)),
    Scenario("session_update", "session:app-v3", "Install",
             ("status 0 dev.dine.pkg.app", "removed dev.dine.pkg.app replacing=true", "added dev.dine.pkg.app replacing=true",
              "replaced dev.dine.pkg.app replacing=true"), setup=("app",), rows=_row("dev.dine.pkg.app", version_code=3)),
    Scenario("spoof_allow", "session:spoof", "Install;Allow", ("status 0 dev.dine.pkg.spoof",),
             rows=_row("dev.dine.pkg.spoof", fake_signature=1)),
    Scenario("spoof_deny", "session:spoof", "Install;Deny", ("status 0 dev.dine.pkg.spoof",),
             rows=_row("dev.dine.pkg.spoof", fake_signature=0)),
    Scenario("app_context", "session-app-context:ext", "Install", ("status 0 dev.dine.pkg.ext",),
             rows=_row("dev.dine.pkg.ext")),
    Scenario("intent_install", "intent-install:ext", "Install", ("result -1 1", "added dev.dine.pkg.ext replacing=false"),
             rows=_row("dev.dine.pkg.ext")),
    Scenario("session_provider_conflict", "session:provdup", "Install", ("status 5 dev.dine.pkg.provdup",), setup=("app",),
             never=("unscoped", "added"), rows=_row("dev.dine.pkg.provdup", absent=True)),
    Scenario("intent_provider_conflict", "intent-install:provdup", "Install", ("result 1 -13",), setup=("app",),
             never=("unscoped", "added"), rows=_row("dev.dine.pkg.provdup", absent=True)),
    Scenario("intent_uninstall", "intent-uninstall:dev.dine.pkg.ext", "Uninstall",
             ("result -1 0", "removed dev.dine.pkg.ext replacing=false"), setup=("ext",),
             rows=_row("dev.dine.pkg.ext", absent=True)),
    # ends by itself after the result, as Android kills an app it replaced
    Scenario("self_update", "self-update:driver-v2", "Install", ("status 0 dev.dine.pkg.driver",),
             rows=_row("dev.dine.pkg.driver", version_code=2)),
)


def run_scenario(s: Scenario, runs: Path) -> tuple[str, str, str]:
    work = runs / f"scenario-{s.name}"
    prefix = work / "prefix"
    row = f"scenario:{s.name}"
    for name in s.setup:
        if atl(work, f"install-{name}", ["--install", str(APKS / f"{name}.apk")], prefix).returncode:
            return row, "fail", f"setup install of {name} failed"
    proc = atl(work, "driver", [str(APKS / "driver.apk")], prefix, DINE_TEST_SCENARIO=s.arg, ATL_DIALOG_ANSWERS=s.answers)
    problems = grade_scenario(s, proc.returncode, (work / "driver.stdout").read_text(errors="replace"), rows(prefix))
    return row, "fail" if problems else "pass", "; ".join(problems)


def grade_scenario(s: Scenario, returncode: int, stdout: str, registry: dict) -> list[str]:
    lines = [line[len("scenario: "):] for line in stdout.splitlines() if line.startswith("scenario: ")]
    problems = [f"exit {returncode}"] if returncode else []
    problems += [f"no {w!r}" for w in s.want if w not in lines]
    problems += [f"printed {line!r}" for line in lines if any(line.startswith(n) for n in s.never)]
    problem = s.rows(registry)
    if problem:
        problems.append(problem)
    return problems


def run_check(name: str, check, runs: Path) -> tuple[str, str, str]:
    work = runs / f"cli-{name}"
    try:
        check(work, work / "prefix")
    except AssertionError as e:
        return f"cli:{name}", "fail", str(e)
    except Exception as e:   # noqa: BLE001 - any harness error grades the row as failed
        return f"cli:{name}", "fail", f"{type(e).__name__}: {e}"
    return f"cli:{name}", "pass", ""


# what the JUnit suite queries: (fixture, extra --install flags)
JUNIT_FIXTURES = (("ext", ()), ("extb", ()), ("app", ()), ("plain", ()), ("spoof", ("--allow-fake-signature",)),
                  ("spoofdeny", ()), ("gone", ()))
STALE = "dev.dine.pkg.ext"   # its row is set to an older parse version; the suite's read must parse it again


def install_fixtures(work: Path, prefix: Path) -> list[str]:
    problems = []
    for name, flags in JUNIT_FIXTURES:
        if atl(work, f"install-{name}", ["--install", *flags, str(APKS / f"{name}.apk")], prefix).returncode:
            problems.append(f"install of {name} failed")
    db = sqlite3.connect(prefix / "registry.sqlite")
    with db:
        db.execute("UPDATE packages SET parse_version = 0, parsed = x'00' WHERE name = ?", (STALE,))
    db.close()
    return problems


def run_junit(runs: Path) -> tuple[dict[str, str], list[str]]:
    work = runs / "junit"
    suite_apk = OUT / "suite.apk"
    try:
        apk.build(SUITE / "suite", suite_apk, BUILD.classpath())
    except (subprocess.CalledProcessError, SystemExit) as e:
        return {"suite:junit": "fail"}, [f"APK build failed: {e}"]
    prefix = work / "prefix"
    problems = install_fixtures(work, prefix)
    proc = atl(work, "junit", ["--instrument", framework.RUNNER, str(suite_apk)], prefix)
    run = framework.parse((work / "junit.stdout").read_text(errors="replace"))
    if proc.returncode != 0:
        run.problems.append(f"exit {proc.returncode}")
    problems += run.problems
    results = {"suite:junit": "fail" if problems else "pass", **run.tests}
    stale = rows(prefix).get(STALE, {})
    results["cli:reparse"] = "pass" if stale.get("parse_version", 0) > 0 and len(stale.get("parsed", b"")) > 1 else "fail"
    if results["cli:reparse"] == "fail":
        problems.append(f"{STALE}'s row still has the old parse version")
    return results, problems


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("-f", "--filter", help="regex on row names (cli:, scenario:, Class#test); the JUnit suite runs "
                                          "whole when any of its rows could match")
    p.add_argument("--update-expectations", action="store_true",
                   help="record this run's failures as expected (passes clear their entries)")
    a = p.parse_args()

    for f in (BUILD.dir / "android-translation-layer", BUILD.dir / "test_runner.jar"):
        if not f.exists():
            sys.exit(f"missing {f}: run tools/dine linux build")
    match = (lambda n: re.search(a.filter, n)) if a.filter else (lambda n: True)
    errors = [e for e in parallel(build_fixture, list(FIXTURES), BUILD.jobs, "fixtures") if e]
    if errors:
        sys.exit("fixture build failed:\n" + "\n".join(errors))

    runs = OUT / "runs" / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    results: dict[str, str] = {}
    checks = [(n, c) for n, c in CHECKS.items() if match(f"cli:{n}")]
    for row, status, problem in sorted(parallel(lambda nc: run_check(*nc, runs), checks, BUILD.jobs, "cli")):
        results[row] = status
        if problem:
            print(f"{row}: {problem} (log: {runs / ('cli-' + row[4:])})")
    scenarios = [sc for sc in SCENARIOS if match(f"scenario:{sc.name}")]
    for row, status, problem in sorted(parallel(lambda sc: run_scenario(sc, runs), scenarios, BUILD.jobs, "scenarios")):
        results[row] = status
        if problem:
            print(f"{row}: {problem} (log: {runs / ('scenario-' + row[9:])})")
    if not a.filter or not re.match(r"^\^?(cli|scenario):", a.filter):
        tests, problems = run_junit(runs)
        results.update(tests)
        for problem in problems:
            print(f"junit: {problem} (log: {runs / 'junit'})")

    expectations = expect.load(EXPECTATIONS)
    if a.update_expectations:
        EXPECTATIONS.parent.mkdir(parents=True, exist_ok=True)
        expect.save(EXPECTATIONS, expect.update(results, expectations, "new failure"))
        print(f"updated {EXPECTATIONS}")
        return 0
    c = expect.compare(results, expectations)
    passed = sum(s == "pass" for s in results.values())
    print(f"package: {passed}/{len(results)} rows pass, {len(c.expected_failures)} expected failures → {runs}")
    for name in c.fixed:
        print(f"fixed: {name} (run with --update-expectations)")
    for name in c.regressions:
        print(f"REGRESSION: {name} {results[name]}")
    return 1 if c.regressions else 0


if __name__ == "__main__":
    sys.exit(main())
