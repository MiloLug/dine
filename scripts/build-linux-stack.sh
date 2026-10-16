#!/usr/bin/env bash
# Build the Linux ATL stack into a local prefix (no sudo). ART comes from the dine-art submodule
# (our fork of art_standalone), the rest from third_party/ clones.
# Order: bionic_translation -> dine-art -> libopensles-standalone -> android_translation_layer
#
# Usage: scripts/build-linux-stack.sh [stage...]   stages: bionic art opensles atl (default: all)
# Before building, applies patches/<repo>/*.patch to each third_party clone (skipping applied ones).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/env.sh"   # meson comes from the .venv
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

# third_party/ clones are gitignored; fixes we need live in patches/<repo>/.
apply_patches() {
  local name=$1 p
  for p in "$ROOT/patches/$name"/*.patch; do
    [[ -e $p ]] || continue
    if git -C "$SRC/$name" apply --check "$p" 2>/dev/null; then
      echo "applying $(basename "$p")"
      git -C "$SRC/$name" apply "$p"
    elif ! git -C "$SRC/$name" apply --reverse --check "$p" 2>/dev/null; then
      echo "patch doesn't apply: $p" >&2; exit 1
    fi
  done
}

meson_stage() {
  local name=$1; shift
  echo "==> $name"
  apply_patches "$name"
  if [[ ! -f "$BUILD/$name/build.ninja" ]]; then
    meson subprojects download --sourcedir "$SRC/$name" >/dev/null 2>&1 || true
    meson setup "$BUILD/$name" "$SRC/$name" --prefix="$PREFIX" --libdir=lib \
      --buildtype=debugoptimized "$@"
  fi
  meson compile -C "$BUILD/$name" -j "$JOBS"
  meson install -C "$BUILD/$name" --quiet
}

# Our ART changes are commits on dine-art's `dine` branch, not patches.
art_stage() {
  echo "==> dine-art"
  [[ -f "$ROOT/dine-art/Makefile" ]] || git -C "$ROOT" submodule update --init dine-art
  make -C "$ROOT/dine-art" -j "$JOBS" ____PREFIX="$PREFIX" ____LIBDIR=lib
  make -C "$ROOT/dine-art" ____PREFIX="$PREFIX" ____LIBDIR=lib ____INSTALL_ETC="$PREFIX/etc" install
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
