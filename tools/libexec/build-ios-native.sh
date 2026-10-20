#!/usr/bin/env bash
# Cross-compile native/<lib> for arm64-apple-ios into out/ios (static libs + headers).
# Usage: tools/dine ios build-native [lib...]   (default: every dir in native/)
# Build type: DINE_IOS_BUILD_TYPE (default RelWithDebInfo). For C++ debugging without optimized-out
# locals: DINE_IOS_BUILD_TYPE=Debug tools/dine ios run
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/env.sh"

libs=("$@")
[[ ${#libs[@]} -eq 0 ]] && libs=($(cd "$ROOT/native" && ls -d */ | tr -d /))

toolchain="$ROOT/tools/cmake/ios.toolchain.cmake"
for lib in "${libs[@]}"; do
  echo "==> $lib"
  build="$ROOT/out/ios/build/$lib"
  # CMake keeps the toolchain path from the first configure; a moved toolchain needs a fresh dir.
  if [[ -f $build/CMakeCache.txt ]] && ! grep -qF "CMAKE_TOOLCHAIN_FILE:FILEPATH=$toolchain" "$build/CMakeCache.txt"; then
    rm -rf "$build"
  fi
  cmake -S "$ROOT/native/$lib" -B "$build" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$toolchain" -DDINE_IOS_MIN="$DINE_IOS_MIN" \
    -DCMAKE_BUILD_TYPE="${DINE_IOS_BUILD_TYPE:-RelWithDebInfo}" \
    -DCMAKE_INSTALL_PREFIX="$ROOT/out/ios"
  cmake --build "$build"
  cmake --install "$build"
done
