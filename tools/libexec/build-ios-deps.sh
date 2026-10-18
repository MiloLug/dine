#!/usr/bin/env bash
# Cross-compile ART's third-party libraries (ICU, liblzma, lz4) for arm64-apple-ios into out/ios.
# zlib and expat come from the SDK; sources are third_party/ clones. Installed ones are skipped.
# Usage: tools/libexec/build-ios-deps.sh   (run by tools/dine ios build-art)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/env.sh"
SRC="$ROOT/third_party"
PREFIX="$ROOT/out/ios"
BUILD="$ROOT/out/ios/build"
JOBS="${JOBS:-$(nproc)}"
toolchain="$ROOT/tools/cmake/ios.toolchain.cmake"

need() {
  [[ -d $SRC/$1 ]] || { echo "missing third_party/$1; clone it: $2" >&2; exit 1; }
}

# name, source dir, installed library, cmake args...
cmake_dep() {
  local name=$1 src=$2 lib=$3; shift 3
  [[ -f $PREFIX/lib/$lib ]] && return
  echo "==> $name"
  cmake -S "$src" -B "$BUILD/$name" -G Ninja -DCMAKE_TOOLCHAIN_FILE="$toolchain" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX" -DBUILD_SHARED_LIBS=OFF \
    -DBUILD_TESTING=OFF "$@"
  cmake --build "$BUILD/$name"
  cmake --install "$BUILD/$name"
}

icu() {
  [[ -f $PREFIX/lib/libicuuc.a ]] && return
  local src="$SRC/icu/icu4c/source" host="$BUILD/icu-host" cross="$BUILD/icu"
  # Cross builds run ICU's data tools from a host build of the same tree.
  if [[ ! -x $host/bin/icupkg ]]; then
    echo "==> icu (host tools)"
    mkdir -p "$host"
    (cd "$host" && "$src/configure" --disable-tests --disable-samples --disable-extras)
    make -C "$host" -j "$JOBS"
  fi
  echo "==> icu"
  mkdir -p "$cross"
  (cd "$cross" && "$src/configure" --host=aarch64-apple-darwin --with-cross-build="$host" \
    --prefix="$PREFIX" --enable-static --disable-shared --disable-tools --disable-tests \
    --disable-samples --disable-extras --with-data-packaging=static \
    CC="clang -target arm64-apple-ios$DINE_IOS_MIN -isysroot $DINE_IOS_SDK" \
    CXX="clang++ -target arm64-apple-ios$DINE_IOS_MIN -isysroot $DINE_IOS_SDK" \
    AR=llvm-ar RANLIB=llvm-ranlib LDFLAGS="-fuse-ld=lld -B$DINE_IOS_TOOLSET_BIN")
  make -C "$cross" -j "$JOBS"
  make -C "$cross" install
}

need lz4 "git clone --depth 1 --branch v1.10.0 https://github.com/lz4/lz4.git third_party/lz4"
need xz "git clone --depth 1 --branch v5.8.4 https://github.com/tukaani-project/xz.git third_party/xz"
need icu "git clone --depth 1 --branch release-78.3 --filter=blob:none --sparse https://github.com/unicode-org/icu.git third_party/icu && git -C third_party/icu sparse-checkout set icu4c"

cmake_dep lz4 "$SRC/lz4/build/cmake" liblz4.a -DLZ4_BUILD_CLI=OFF
cmake_dep xz "$SRC/xz" liblzma.a -DXZ_NLS=OFF -DXZ_DOC=OFF -DXZ_TOOL_XZ=OFF -DXZ_TOOL_XZDEC=OFF \
  -DXZ_TOOL_LZMADEC=OFF -DXZ_TOOL_LZMAINFO=OFF
icu
