#!/usr/bin/env bash
# Cross-compile native/<lib> for arm64-apple-ios into out/ios (static libs + headers).
# Usage: tools/dine ios build-native [lib...]   (default: every lib in native/, plus native/dev/*
# unless DINE_RELEASE=1; a dev lib is named dev/<lib>). DINE_RELEASE=1 also builds artbridge
# without its dev.cpp (CMake DINE_DEV).
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

toolchain="$ROOT/tools/cmake/ios.toolchain.cmake"
for lib in "${libs[@]}"; do
  echo "==> $lib"
  build="$ROOT/out/ios/build/$lib"
  # CMake keeps the toolchain path from the first configure; a moved toolchain needs a fresh dir.
  if [[ -f $build/CMakeCache.txt ]] && ! grep -qF "CMAKE_TOOLCHAIN_FILE:FILEPATH=$toolchain" "$build/CMakeCache.txt"; then
    rm -rf "$build"
  fi
  cmake -S "$ROOT/native/$lib" -B "$build" -G Ninja -Wno-unused-cli \
    -DCMAKE_TOOLCHAIN_FILE="$toolchain" -DDINE_IOS_MIN="$DINE_IOS_MIN" -DDINE_DEV="$dev" \
    -DCMAKE_BUILD_TYPE="${DINE_IOS_BUILD_TYPE:-RelWithDebInfo}" \
    -DCMAKE_INSTALL_PREFIX="$ROOT/out/ios"
  cmake --build "$build"
  cmake --install "$build"
done
