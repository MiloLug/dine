#!/usr/bin/env python3
"""Builds an authored test APK: tests/harness/apk.py <src dir> <out.apk> [--atl DIR] [--classpath JAR]... [--key P12]

<src dir> holds AndroidManifest.xml, src/**/*.java and an optional res/; the Java, with the link's
R.java, compiles against ATL's android.* classes and any --classpath jars (not dexed into the APK).
With --key the APK is v1-signed (JAR signing only: ATL reads no v2/v3 block) by the PKCS12 store,
whose alias is its file stem and whose password is KEY_PASSWORD.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from common import CORE_JAR, D8, ROOT

HEADLESS = ROOT / "out/linux/build/dine-atl-headless"
KEY_PASSWORD = "dine-test"


def build(src: Path, out: Path, classpath: tuple[Path, ...] = (), link_args: tuple[str, ...] = (),
          key: Path | None = None, manifest: Path | None = None, atl: Path = HEADLESS) -> None:
    """link_args go to aapt2 link (e.g. --version-code, --rename-manifest-package); manifest replaces
    src's AndroidManifest.xml; atl is the ATL build dir whose android.* classes and framework
    resources the APK compiles against."""
    hax_jar = atl / "src/api-impl/hax.jar"   # ATL's android.*, not dexed
    framework_res = atl / "res/framework-res/framework-res.apk"
    for f in (hax_jar, framework_res, CORE_JAR, *classpath):
        if not f.exists():
            sys.exit(f"missing {f}: run tools/dine linux build")
    cp = ":".join(str(f) for f in (hax_jar, *classpath))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        classes = tmp / "classes"
        classes.mkdir()
        gen = tmp / "gen"
        base = tmp / "base.apk"
        link = ["aapt2", "link", "-o", base, "--manifest", manifest or src / "AndroidManifest.xml", "-I", framework_res,
                *link_args]
        if (src / "res").is_dir():
            compiled = tmp / "res.zip"
            subprocess.run(["aapt2", "compile", "--dir", src / "res", "-o", compiled], check=True)
            link += ["--java", gen, compiled]
        subprocess.run(link, check=True)
        sources = sorted((src / "src").rglob("*.java")) + sorted(gen.rglob("*.java"))
        subprocess.run(["javac", "-g", "-Xlint:-options", "-source", "1.8", "-target", "1.8",
                        "-bootclasspath", CORE_JAR, "-cp", cp, "-d", classes, *sources], check=True)
        subprocess.run([D8, "--min-api", "27", "--lib", CORE_JAR,
                        *(a for f in (hax_jar, *classpath) for a in ("--classpath", f)),
                        "--output", tmp, *sorted(classes.rglob("*.class"))], check=True)
        # stored and 4-byte aligned, so ART maps the dex instead of inflating a copy
        with zipfile.ZipFile(base, "a") as apk:
            apk.write(tmp / "classes.dex", "classes.dex", compress_type=zipfile.ZIP_STORED)
        aligned = tmp / "aligned.apk"
        subprocess.run(["zipalign", "-f", "4", base, aligned], check=True)
        if key:
            subprocess.run(["apksigner", "sign", "--ks", key, "--ks-key-alias", key.stem,
                            "--ks-pass", f"pass:{KEY_PASSWORD}", "--v1-signing-enabled", "true",
                            "--v2-signing-enabled", "false", "--v3-signing-enabled", "false",
                            "--v4-signing-enabled", "false", "--min-sdk-version", "21", aligned], check=True)
        # renamed into place: a VM that maps the old file keeps it, and no reader sees half an APK
        out.parent.mkdir(parents=True, exist_ok=True)
        staged = out.with_name(f".{out.name}.{os.getpid()}")
        shutil.copyfile(aligned, staged)
        staged.replace(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("src", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--atl", type=Path, default=HEADLESS, help="ATL build dir to compile against (default: headless)")
    p.add_argument("--classpath", type=Path, action="append", default=[])
    p.add_argument("--key", type=Path)
    a = p.parse_args()
    build(a.src, a.out, tuple(a.classpath), key=a.key, atl=a.atl)
