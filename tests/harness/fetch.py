"""Fetch stage: the pinned upstream tests, the fake build tree, and a tool check."""

import shutil
import subprocess
from pathlib import Path

from common import CORE_JAR, D8, SHIMS, TOP, UPSTREAM


def _git(*args: str, cwd: Path | None = None) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{p.stderr}")
    return p.stdout.strip()


def _head() -> str | None:
    try:
        return _git("rev-parse", "HEAD", cwd=UPSTREAM)
    except (RuntimeError, FileNotFoundError):
        return None


def _clone(repo: str, tag: str) -> None:
    UPSTREAM.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Only art/test/: blobless shallow clone + sparse checkout (~40 MB, seconds).
        _git("clone", "--quiet", "--filter=blob:none", "--depth", "1", "--no-checkout",
             "--branch", tag, repo, str(UPSTREAM))
        _git("sparse-checkout", "set", "--no-cone", "/test/", cwd=UPSTREAM)
        _git("checkout", "--quiet", cwd=UPSTREAM)
    except RuntimeError:
        shutil.rmtree(UPSTREAM, ignore_errors=True)
        _git("clone", "--quiet", "--depth", "1", "--branch", tag, repo, str(UPSTREAM))


def _link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    link.unlink(missing_ok=True)
    link.symlink_to(target)


def check_tools() -> None:
    missing = [t for t in ("javac", "smali", "jasmin", "zipalign", "zip", "unzip", "dalvikvm")
               if not shutil.which(t)]
    if not CORE_JAR.exists():
        missing.append(str(CORE_JAR))
    if subprocess.run([D8, "--version"], capture_output=True).returncode:
        missing.append("d8 (android-sdk-build-tools + jdk21-openjdk)")
    if missing:
        raise SystemExit("missing: " + ", ".join(missing) +
                         "\n(tools: docs/first-run.md; dalvikvm/libcore: tools/dine linux build art;"
                         " and source env.sh)")


def fetch(corpus: dict) -> None:
    up = corpus["upstream"]
    if _head() != up["commit"]:
        print(f"fetching {up['repo']} {up['tag']} (test/)")
        shutil.rmtree(UPSTREAM, ignore_errors=True)
        _clone(up["repo"], up["tag"])
        if _head() != up["commit"]:
            raise SystemExit(f"{UPSTREAM}: HEAD {_head()} != pinned {up['commit']}")
    _link(TOP / "art/test", UPSTREAM / "test")
    _link(TOP / "art/tools/javac-helper.sh", SHIMS / "javac-helper.sh")
    _link(TOP / "art/tools/bootjars.sh", SHIMS / "bootjars.sh")
    _link(TOP / "development/docs/copyright-templates", SHIMS / "copyright-templates")
    check_tools()
