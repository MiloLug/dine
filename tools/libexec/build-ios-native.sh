#!/usr/bin/env bash
# Cross-compile native/<lib> for arm64-apple-ios into out/ios (static libs + headers).
# Usage: tools/dine ios build-native [lib...]   (default: every lib in native/, plus native/dev/*
# unless DINE_RELEASE=1; a dev lib is named dev/<lib>). DINE_RELEASE=1 also builds artbridge
# without its dev sources (CMake DINE_DEV); tools/dine first removes what a dev build installed of
# native/dev (ios.py build_native).
# Build type: DINE_IOS_BUILD_TYPE (default RelWithDebInfo). For C++ debugging without optimized-out
# locals: DINE_IOS_BUILD_TYPE=Debug tools/dine ios run
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/env.sh"

dev=ON
[[ ${DINE_RELEASE:-} == 1 ]] && dev=OFF
libs=("$@")
if [[ ${#libs[@]} -eq 0 ]]; then
  shopt -s nullglob
  for dir in "$ROOT"/native/*/ "$ROOT"/native/dev/*/; do
    lib=${dir#"$ROOT/native/"}
    lib=${lib%/}
    [[ $lib == dev || ($lib == dev/* && $dev == OFF) ]] && continue
    libs+=("$lib")
  done
fi

source "$ROOT/tools/libexec/ios-cmake.sh"
for lib in "${libs[@]}"; do
  echo "==> $lib"
  build="$ROOT/out/ios/build/$lib"
  ios_cmake "$ROOT/native/$lib" "$build" -DDINE_DEV="$dev" -DCMAKE_INSTALL_PREFIX="$ROOT/out/ios"
  cmake --install "$build"
done
"$ROOT/tools/libexec/jni-symbols.sh"
