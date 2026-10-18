#!/usr/bin/env bash
# Cross-compile dine-art (ART runtime + libcore natives) into static arm64-apple-ios archives in
# out/ios/lib. The boot classpath jars are the Linux build's.
# Usage: tools/dine ios build-art
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/env.sh"
JOBS="${JOBS:-$(nproc)}"

"$ROOT/tools/libexec/build-ios-deps.sh"

ios=(____TARGET=ios ____IOS_SDK="$DINE_IOS_SDK" ____IOS_MIN="$DINE_IOS_MIN" ____PREFIX="$ROOT/out/ios"
     ____LIBDIR=lib)
make -C "$ROOT/dine-art" -j "$JOBS" "${ios[@]}" ____art_ios_all
make -C "$ROOT/dine-art" "${ios[@]}" install-ios
