#!/usr/bin/env python3
"""Builds an authored test APK: tests/harness/apk.py <src dir> <out.apk> [--classpath JAR]...

<src dir> holds AndroidManifest.xml and src/**/*.java, compiled against ATL's android.* classes
and any --classpath jars (not dexed into the APK).
"""

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from common import CORE_JAR, D8, PREFIX, ROOT

HAX_JAR = ROOT / "out/linux/build/dine-atl/src/api-impl/hax.jar"   # ATL's android.*, not dexed
FRAMEWORK_RES = PREFIX / "lib/java/dex/android_translation_layer/framework-res.apk"


def build(src: Path, out: Path, classpath: tuple[Path, ...] = ()) -> None:
    for f in (HAX_JAR, FRAMEWORK_RES, CORE_JAR, *classpath):
        if not f.exists():
            sys.exit(f"missing {f}: run tools/dine linux build")
    cp = ":".join(str(f) for f in (HAX_JAR, *classpath))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        classes = tmp / "classes"
        classes.mkdir()
        sources = sorted((src / "src").rglob("*.java"))
        subprocess.run(["javac", "-g", "-Xlint:-options", "-source", "1.8", "-target", "1.8",
                        "-bootclasspath", CORE_JAR, "-cp", cp, "-d", classes, *sources], check=True)
        subprocess.run([D8, "--min-api", "27", "--lib", CORE_JAR,
                        *(a for f in (HAX_JAR, *classpath) for a in ("--classpath", f)),
                        "--output", tmp, *sorted(classes.rglob("*.class"))], check=True)
        base = tmp / "base.apk"
        subprocess.run(["aapt2", "link", "-o", base, "--manifest", src / "AndroidManifest.xml",
                        "-I", FRAMEWORK_RES], check=True)
        # stored and 4-byte aligned, so ART maps the dex instead of inflating a copy
        with zipfile.ZipFile(base, "a") as apk:
            apk.write(tmp / "classes.dex", "classes.dex", compress_type=zipfile.ZIP_STORED)
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["zipalign", "-f", "4", base, out], check=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("src", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--classpath", type=Path, action="append", default=[])
    a = p.parse_args()
    build(a.src, a.out, tuple(a.classpath))
