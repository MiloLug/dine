#!/usr/bin/env bash
# Stage the dev build's bundle payload in out/ios/dev (bundled as dev/): ATL's test APKs, the
# third-party APKs AtlView has tiles for, the runtime suite's authored jars, ART's junit boot jars,
# and the package suite's installer app with the APK it installs (dev/package/).
# DINE_RELEASE=1 leaves it empty.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEV="$ROOT/out/ios/dev"

rm -rf "$DEV"
mkdir -p "$DEV"
[[ ${DINE_RELEASE:-} == 1 ]] && exit 0

real=("$ROOT"/third_party/apks/{demo_app,org.happysanta.gd_29,AdaptiveIconDemo,views_widgets_samples_flower_finder,com.leocardz.multitouch.test_19,com.ashwin.example.accelerometerdemo}.apk)
for f in "${real[@]}"; do
  [[ -f $f ]] || { echo "missing $f: docs/first-run.md lists the APKs" >&2; exit 1; }
done
shopt -s nullglob
apks=("$ROOT"/out/tests/apks/*.apk)
[[ ${#apks[@]} -gt 0 ]] || { echo "no test APKs in out/tests/apks: run tools/dine ios build-atl" >&2; exit 1; }
jars=("$ROOT"/out/ios/share/art-junit/*.jar)
[[ ${#jars[@]} -gt 0 ]] || { echo "no junit jars in out/ios/share/art-junit: run tools/dine ios build-art" >&2; exit 1; }
for test in dine-0001-hello dine-0002-jni-args dine-0003-https dine-0004-park dine-0008-thread-cpu-time; do
  jars+=("$ROOT/out/tests/runtime/build/$test/$test.jar")
done
for f in "${jars[@]}"; do
  [[ -f $f ]] || { echo "missing $f: run tools/dine test runtime build -f '^dine-'" >&2; exit 1; }
done
package=("$ROOT"/out/tests/package/apks/{driver,ext}.apk)
for f in "${package[@]}"; do
  [[ -f $f ]] || { echo "missing $f: run tools/dine test package" >&2; exit 1; }
done
install -m644 -t "$DEV" "${real[@]}" "${apks[@]}" "${jars[@]}"
install -m644 -D -t "$DEV/package" "${package[@]}"
