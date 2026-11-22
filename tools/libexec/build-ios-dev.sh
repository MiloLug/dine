#!/usr/bin/env bash
# Build the dev build's bundle payload from its sources and stage it in out/ios/dev (bundled as
# dev/): ATL's test APKs, the third-party APKs AtlView has tiles for, the runtime suite's authored
# jars, ART's junit boot jars, and the package suite's installer app with the APK it installs
# (dev/package/). Needs the Linux builds, whose jars the APKs compile against.
# DINE_RELEASE=1 leaves it empty.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/env.sh"   # the jars' build wants dalvikvm on PATH
DEV="$ROOT/out/ios/dev"
HARNESS="$ROOT/tests/harness"

rm -rf "$DEV"
mkdir -p "$DEV"
[[ ${DINE_RELEASE:-} == 1 ]] && exit 0

real=("$ROOT"/third_party/apks/{demo_app,org.happysanta.gd_29,AdaptiveIconDemo,views_widgets_samples_flower_finder,com.leocardz.multitouch.test_19,com.ashwin.example.accelerometerdemo}.apk)
for f in "${real[@]}"; do
  [[ -f $f ]] || { echo "missing $f: docs/first-run.md lists the APKs" >&2; exit 1; }
done
apks=()
for name in looper dialog nav views widgets windows; do
  apk="$ROOT/out/tests/apks/$name.apk"
  python3 "$HARNESS/apk.py" "$ROOT/dine-atl/tests/headless/$name" "$apk" --atl "$ROOT/out/linux/build/dine-atl"
  apks+=("$apk")
done
shopt -s nullglob
jars=("$ROOT"/out/ios/share/art-junit/*.jar)
[[ ${#jars[@]} -gt 0 ]] || { echo "no junit jars in out/ios/share/art-junit: run tools/dine ios build-art" >&2; exit 1; }
tests=(dine-0001-hello dine-0002-jni-args dine-0003-https dine-0004-park dine-0006-cleanup-domains
  dine-0008-thread-cpu-time dine-0010-netif)
# both builds are the suites' own; the runtime one rebuilds only what changed
python3 "$HARNESS" build -f "^($(IFS='|'; echo "${tests[*]}"))\$"
for test in "${tests[@]}"; do
  bundle="$ROOT/out/tests/runtime/build/$test/bundle.json"
  # it keeps its exit status 0 over a test whose build failed
  grep -q '"status": "ok"' "$bundle" || { echo "$test didn't build: see ${bundle%/*}/build-output.txt" >&2; exit 1; }
  jars+=("${bundle%/*}/$test.jar")
done
python3 "$HARNESS/package.py" --build
package=("$ROOT"/out/tests/package/apks/{driver,ext}.apk)
install -m644 -t "$DEV" "${real[@]}" "${apks[@]}" "${jars[@]}"
install -m644 -D -t "$DEV/package" "${package[@]}"
