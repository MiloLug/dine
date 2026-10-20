#!/usr/bin/env bash
# Stage the dev build's bundle payload in out/ios/dev (bundled as dev/): ATL's test APKs, the
# runtime suite's authored jars and ART's junit boot jars. DINE_RELEASE=1 leaves it empty.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEV="$ROOT/out/ios/dev"

rm -rf "$DEV"
mkdir -p "$DEV"
[[ ${DINE_RELEASE:-} == 1 ]] && exit 0

demo="$ROOT/third_party/atl_test_apks/demo_app.apk"
[[ -f $demo ]] || { echo "missing $demo: clone third_party/atl_test_apks (docs/first-run.md)" >&2; exit 1; }
shopt -s nullglob
apks=("$ROOT"/out/tests/apks/*.apk)
[[ ${#apks[@]} -gt 0 ]] || { echo "no test APKs in out/tests/apks: run tools/dine ios build-atl" >&2; exit 1; }
jars=("$ROOT"/out/ios/share/art-junit/*.jar)
[[ ${#jars[@]} -gt 0 ]] || { echo "no junit jars in out/ios/share/art-junit: run tools/dine ios build-art" >&2; exit 1; }
for test in dine-0001-hello dine-0002-jni-args dine-0003-https dine-0004-park; do
  jars+=("$ROOT/out/tests/runtime/build/$test/$test.jar")
done
for f in "${jars[@]}"; do
  [[ -f $f ]] || { echo "missing $f: run tools/dine test runtime build -f '^dine-'" >&2; exit 1; }
done
install -m644 -t "$DEV" "$demo" "${apks[@]}" "${jars[@]}"
