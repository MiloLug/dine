"""Turn one test's VM output into a verdict, the way upstream run-test does.

Upstream (etc/default-check): pass = run exit status 0 and
`diff --strip-trailing-cr expected output` is empty, with stdout and stderr merged.
"""

import difflib
from pathlib import Path


def expected_file(test_dir: Path) -> Path | None:
    """The expected-output file. ART <= 11 uses expected.txt; 12+ splits it into
    expected-stdout.txt / expected-stderr.txt (not supported yet)."""
    p = test_dir / "expected.txt"
    return p if p.exists() else None


def _lines(text: str) -> list[str]:
    return [l.removesuffix("\r") for l in text.split("\n")]


def outputs_match(expected: str, actual: str) -> bool:
    return _lines(expected) == _lines(actual)


def diff(expected: str, actual: str) -> str:
    return "".join(l + "\n" for l in difflib.unified_diff(
        _lines(expected), _lines(actual), "expected", "output", lineterm=""))


def verdict(returncode: int, matched: bool) -> str:
    if returncode < 0:
        return "crash"   # ended by a signal
    return "pass" if returncode == 0 and matched else "fail"
