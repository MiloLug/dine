#!/usr/bin/env bash
# Build the Linux ATL stack from third_party/ into a local prefix (no sudo).
# Order: bionic_translation -> art_standalone -> libopensles-standalone -> android_translation_layer
#
# Usage: scripts/build-linux-stack.sh [stage...]   stages: bionic art opensles atl (default: all)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/third_party"
PREFIX="${DINE_LINUX_PREFIX:-$ROOT/out/linux/prefix}"
BUILD="$ROOT/out/linux/build"
JOBS="${JOBS:-$(nproc)}"

export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-8-openjdk}"
export PATH="$JAVA_HOME/bin:$PREFIX/bin:$PATH"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig:$PREFIX/share/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export LD_LIBRARY_PATH="$PREFIX/lib:$PREFIX/lib/art${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# art_standalone's make links -ldl_bio etc. without pkg-config; let gcc find the local prefix.
export LIBRARY_PATH="$PREFIX/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
export CPATH="$PREFIX/include${CPATH:+:$CPATH}"

meson_stage() {
  local name=$1; shift
  echo "==> $name"
  if [[ ! -f "$BUILD/$name/build.ninja" ]]; then
    meson subprojects download --sourcedir "$SRC/$name" >/dev/null 2>&1 || true
    meson setup "$BUILD/$name" "$SRC/$name" --prefix="$PREFIX" --libdir=lib \
      --buildtype=debugoptimized "$@"
  fi
  meson compile -C "$BUILD/$name" -j "$JOBS"
  meson install -C "$BUILD/$name" --quiet
}

art_stage() {
  echo "==> art_standalone"
  make -C "$SRC/art_standalone" -j "$JOBS" ____PREFIX="$PREFIX" ____LIBDIR=lib
  make -C "$SRC/art_standalone" ____PREFIX="$PREFIX" ____LIBDIR=lib ____INSTALL_ETC="$PREFIX/etc" install
}

stages=("$@")
[[ ${#stages[@]} -eq 0 ]] && stages=(bionic art opensles atl)

for s in "${stages[@]}"; do
  case $s in
    bionic)   meson_stage bionic_translation ;;
    art)      art_stage ;;
    opensles) meson_stage libopensles-standalone ;;
    atl)      meson_stage android_translation_layer ;;
    *) echo "unknown stage: $s" >&2; exit 1 ;;
  esac
done

echo "done -> $PREFIX"
