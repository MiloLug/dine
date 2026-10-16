"""Expectations: the committed baseline of tests that don't pass yet.

File format: {"<test>": {"expect": "fail|timeout|build-fail|flaky", "reason": "..."}}.
A test with no entry is expected to pass. Skipped tests are never recorded here; their reason is
recomputed from the test tree on every build.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Comparison:
    regressions: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)
    expected_failures: list[str] = field(default_factory=list)


def load(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def save(path: Path, expectations: dict) -> None:
    path.write_text(json.dumps(expectations, indent=2, sort_keys=True) + "\n")


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
