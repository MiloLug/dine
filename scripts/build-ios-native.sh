#!/usr/bin/env bash
# Cross-compile native/<lib> for arm64-apple-ios into out/ios (static libs + headers).
# Usage: scripts/build-ios-native.sh [lib...]   (default: every dir in native/)
# Build type: DINE_IOS_BUILD_TYPE (default RelWithDebInfo). For C++ debugging without optimized-out
# locals: DINE_IOS_BUILD_TYPE=Debug scripts/ios-run.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/env.sh"

libs=("$@")
[[ ${#libs[@]} -eq 0 ]] && libs=($(cd "$ROOT/native" && ls -d */ | tr -d /))

for lib in "${libs[@]}"; do
  echo "==> $lib"
  cmake -S "$ROOT/native/$lib" -B "$ROOT/out/ios/build/$lib" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ROOT/tools/ios.toolchain.cmake" \
    -DCMAKE_BUILD_TYPE="${DINE_IOS_BUILD_TYPE:-RelWithDebInfo}" \
    -DCMAKE_INSTALL_PREFIX="$ROOT/out/ios"
  cmake --build "$ROOT/out/ios/build/$lib"
  cmake --install "$ROOT/out/ios/build/$lib"
done
