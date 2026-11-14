"""Build stage: each test -> build/<test>/ with dex jars and bundle.json.

Builds go through upstream's own etc/default-build (and a test's custom `build` script, which
wraps it), with the environment upstream run-test exports and our shims standing in for the AOSP
tree. bundle.json is all the run stage reads; it is reused while its key (the test's sources plus
`_shared_key`) matches.
"""

import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from classify import classify
from common import BUILD, CORE_JAR, D8, HARNESS, ROOT, SHIMS, TOP, UPSTREAM, load_corpus, parallel, run
from grade import expected_file

BUILD_TIMEOUT = 600


def _hash_tree(h, root: Path) -> None:
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode() + b"\0")
            h.update(p.read_bytes())


def _shared_key() -> bytes:
    """Inputs common to every test."""
    h = hashlib.sha256()
    # Only the corpus pin: [run] and [timeouts] don't change what gets built.
    h.update(json.dumps(load_corpus()["upstream"], sort_keys=True).encode())
    for p in [UPSTREAM / "test/etc/default-build", HARNESS / "build.py", HARNESS / "classify.py", D8]:
        h.update(p.read_bytes())
    # tools/bin/d8 picks the newest installed build-tools; javac comes from PATH
    for tool in ([str(D8), "--version"], ["javac", "-version"]):
        version = subprocess.run(tool, capture_output=True)
        h.update(version.stdout + version.stderr)   # JDK 8's javac prints it on stderr
    _hash_tree(h, SHIMS)
    # Entry names + CRCs, not the jar bytes: a clean ART rebuild rewrites zip timestamps.
    with zipfile.ZipFile(CORE_JAR) as jar:
        for info in sorted(jar.infolist(), key=lambda i: i.filename):
            h.update(f"{info.filename}\0{info.CRC}\0".encode())
    return h.digest()


def _hash_inputs(h, src: Path) -> None:
    """A test's `build-inputs` file names what its build reads outside its dir, one path per line,
    from the repo root or with an environment variable in front: a file, or a directory hashed
    whole."""
    listing = src / "build-inputs"
    if not listing.exists():
        return
    for line in listing.read_text().split():
        p = ROOT / os.path.expandvars(line)
        if p.is_dir():
            _hash_tree(h, p)
        else:
            h.update(p.read_bytes())


def _env() -> dict:
    return os.environ | {
        # As upstream run-test (host mode) exports them.
        "JAVA": "java",
        "JAVAC": "javac -g -Xlint:-options -source 1.8 -target 1.8",
        "D8": str(D8),
        "DEXMERGER": str(D8),
        "SMALI": "smali",
        "SMALI_ARGS": "",
        "JASMIN": "jasmin",
        "ZIPALIGN": "zipalign",
        "NEED_DEX": "true",
        "USE_D8": "true",
        "USE_DESUGAR": "true",
        "USE_HIDDENAPI": "false",   # no hiddenapi tool; only matters for a few tests
        "ANDROID_BUILD_TOP": str(TOP),
        # For the shims.
        "DINE_CORE_JAR": str(CORE_JAR),
    }


def build_one(name: str, src: Path, env: dict, shared: bytes, retry_failed: bool) -> dict:
    """retry_failed: a stored failed build is not reused, since its cause may be gone (a full disk,
    a prefix that was being installed). A test with a `check` script grades its own build output,
    so its failed build may be the expected one and stays."""
    dst = BUILD / name
    h = hashlib.sha256(shared)
    _hash_tree(h, src)
    _hash_inputs(h, src)
    key = h.hexdigest()
    bundle_path = dst / "bundle.json"
    try:
        bundle = json.loads(bundle_path.read_text())
    except (OSError, ValueError):
        bundle = {}   # absent, or cut short by a stopped build
    retry = retry_failed and bundle.get("status") == "build-fail" and not (src / "check").exists()
    if bundle.get("key") == key and not retry:
        return bundle | {"cached": True}

    shutil.rmtree(dst, ignore_errors=True)
    bundle = {"name": name, "key": key}
    spec, reason = classify(src)
    if reason:
        dst.mkdir(parents=True)
        bundle |= {"status": "skip", "reason": reason}
    else:
        shutil.copytree(src, dst, symlinks=True)
        shutil.copy(UPSTREAM / "test/etc/default-build", dst / "default-build")
        script = "./build" if (dst / "build").exists() else "./default-build"
        with open(dst / "build-output.txt", "w") as log:
            rc = run(["bash", script, "--host"], BUILD_TIMEOUT, cwd=dst, env=env | {"TEST_NAME": name},
                     stdout=log, stderr=subprocess.STDOUT)
        if rc is None:
            rc = "timeout"
        expected = expected_file(dst)
        if rc != 0:
            bundle |= {"status": "build-fail", "reason": f"build exit {rc}"}
        elif not (dst / f"{name}.jar").exists():
            bundle |= {"status": "build-fail", "reason": f"no {name}.jar"}
        elif not expected:
            bundle |= {"status": "build-fail", "reason": "no expected output"}
        else:
            bundle |= {
                "status": "ok",
                "jar": f"{name}.jar",
                "ex_jar": f"{name}-ex.jar" if (dst / f"{name}-ex.jar").exists() else None,
                "expected": expected.name,
                "check": (dst / "check").exists(),
                "main": spec.main,
                "main_args": spec.main_args,
                "vm_args": spec.vm_args,
                "secondary": spec.secondary,
                "timeout": spec.timeout,
                "network": spec.network,
            }
    bundle_path.write_text(json.dumps(bundle, indent=2) + "\n")
    return bundle


def build_all(tests: dict[str, Path], jobs: int, expected_build_fail: set[str]) -> dict[str, dict]:
    env = _env()
    shared = _shared_key()
    bundles = parallel(lambda item: build_one(*item, env, shared, item[0] not in expected_build_fail),
                       list(tests.items()), jobs, "build")
    return {b["name"]: b for b in bundles}
