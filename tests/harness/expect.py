"""A suite's committed baseline, and the verdict of a run against it.

`<name>.json`: {"<test>": {"expect": "fail|crash|timeout|build-fail|flaky", "reason": "..."}}, the
tests that don't pass yet. A test with no entry is expected to pass. Skipped tests are never recorded
here; their reason is recomputed from the test tree on every build.
`<name>.tests.txt`: the tests a whole run executes, one per line.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

NO_TESTS = 2   # exit status of a run that executed nothing


@dataclass
class Comparison:
    regressions: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)
    expected_failures: list[str] = field(default_factory=list)


def load(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def save(path: Path, expectations: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(expectations, indent=2, sort_keys=True) + "\n")


def inventory_path(path: Path) -> Path:
    return path.with_suffix(".tests.txt")


def load_inventory(path: Path) -> set[str] | None:
    """None when the suite has no inventory yet."""
    p = inventory_path(path)
    return set(p.read_text().split("\n")) - {""} if p.exists() else None


def save_inventory(path: Path, names: set[str]) -> None:
    p = inventory_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(n + "\n" for n in sorted(names)))


def compare(results: dict[str, str], expectations: dict) -> Comparison:
    """results: test -> status. Only tests in `results` are compared."""
    c = Comparison()
    for name in sorted(results):
        status = results[name]
        expect = expectations.get(name, {}).get("expect", "pass")
        if status == "skip" or expect == "flaky":
            continue
        if status == expect:
            if status != "pass":
                c.expected_failures.append(name)
        elif status == "pass":
            c.fixed.append(name)
        else:
            c.regressions.append(name)
    return c


def update(results: dict[str, str], expectations: dict, new_reason: str) -> dict:
    """New expectations from this run. Tests that didn't run, and flaky entries, are kept."""
    new = dict(expectations)
    for name, status in results.items():
        old = expectations.get(name)
        if old and old["expect"] == "flaky" or status == "skip":
            continue
        if status == "pass":
            new.pop(name, None)
        else:
            new[name] = {"expect": status, "reason": old["reason"] if old else new_reason}
    return new


def settle(results: dict[str, str], path: Path, *, whole: bool, record: bool, new_reason: str,
           optional: frozenset[str] = frozenset(), listed: Callable[[str], bool] = lambda name: True,
           describe: Callable[[str], str] | None = None, out=print) -> tuple[Comparison, int]:
    """Grades a run against the baseline at `path`: prints what differs, returns the comparison and
    the exit status. The rules are in README.md "Baselines".

    whole: the run had no filter, so the test list applies; `optional` names tests this run's
    options leave out, `listed` which result names the list holds.
    record: `--update-expectations`.
    """
    ran = {n for n, s in results.items() if s != "skip"}
    if not ran:
        out("no test ran")
        return Comparison(), NO_TESTS
    expectations = load(path)
    if record and not path.exists():
        expectations = update(results, expectations, new_reason)
    c = compare(results, expectations)
    known = load_inventory(path) if whole else None
    tracked = {n for n in ran if listed(n)}
    missing = sorted(known - tracked - optional) if known is not None else []
    unrecorded = sorted(tracked - known) if known is not None else []

    for name in c.regressions:
        out(f"REGRESSION: {describe(name) if describe else f'{name} {results[name]}'}")
    for name in missing:
        out(f"MISSING: {name} did not run (listed in {inventory_path(path).name})")
    broken = bool(c.regressions or missing)
    if record:
        if broken:
            out(f"nothing recorded: a regression stands. A failure that is to stay goes into {path} by hand, "
                "with a tracker code as its reason; a removed test comes out of "
                f"{inventory_path(path).name} by hand.")
            return c, 1
        kept = {n: e for n, e in expectations.items() if n not in c.fixed}
        save(path, kept)
        if whole:
            save_inventory(path, tracked | ((known or set()) & optional))
        out(f"recorded: {len(kept)} expected failures, {len(c.fixed)} dropped"
            + (f", {len(tracked)} tests listed" if whole else "") + f" → {path}")
        return c, 0
    if c.fixed:
        out(f"fixed ({len(c.fixed)}): {' '.join(c.fixed)}")
        out("  their entries are stale: record with --update-expectations")
    if whole and known is None:
        out(f"no {inventory_path(path).name} yet: record with --update-expectations")
    elif unrecorded:
        shown = " ".join(unrecorded[:8]) + (" …" if len(unrecorded) > 8 else "")
        out(f"not listed yet ({len(unrecorded)}): {shown}\n  record with --update-expectations")
    return c, 1 if broken or c.fixed else 0
