"""Turn one test's VM output into a verdict, the way upstream run-test does.

Upstream (etc/default-check): pass = run exit status 0 and
`diff --strip-trailing-cr expected output` is empty, with stdout and stderr merged.
"""

import difflib
import re
from pathlib import Path

# ART's native crash dump. A dump from the runtime's "Shutdown thread" comes after main() has
# returned, so the test's own output is complete; see strip_shutdown_abort.
DUMP_START = re.compile(r"^\*\*\* \*\*\* \*\*\*.*$", re.M)
SHUTDOWN_THREAD = re.compile(r'^Thread: \d+ "Shutdown thread', re.M)


def expected_file(test_dir: Path) -> Path | None:
    """The expected-output file. ART <= 11 uses expected.txt; 12+ splits it into
    expected-stdout.txt / expected-stderr.txt (not supported yet)."""
    p = test_dir / "expected.txt"
    return p if p.exists() else None


def strip_shutdown_abort(output: str) -> tuple[str, bool]:
    """Drop a trailing crash dump from the "Shutdown thread". Returns (output, stripped).

    ART 10 calls libjavacore's JNI_OnUnload with no thread attached, and stock libcore 8.1/9 aborts
    there at VM shutdown (dine-art's Register.cpp doesn't). Stripping keeps trees without that fix
    usable and shows such aborts as a count instead of failing every test.
    """
    starts = list(DUMP_START.finditer(output))
    if not starts:
        return output, False
    start = starts[-1].start()
    if not SHUTDOWN_THREAD.search(output, start):
        return output, False
    return output[:start], True


def _lines(text: str) -> list[str]:
    return [l.removesuffix("\r") for l in text.split("\n")]


def outputs_match(expected: str, actual: str) -> bool:
    return _lines(expected) == _lines(actual)


def diff(expected: str, actual: str) -> str:
    return "".join(l + "\n" for l in difflib.unified_diff(
        _lines(expected), _lines(actual), "expected", "output", lineterm=""))


def verdict(returncode: int, shutdown_abort: bool, matched: bool, *, strict: bool) -> str:
    exit_ok = returncode == 0 or (shutdown_abort and not strict)
    return "pass" if exit_ok and matched else "fail"
