#!/usr/bin/env bash
# Build the Linux ATL stack into a local prefix (no sudo). ART and ATL come from our forks (the
# dine-art and dine-atl submodules), bionic_translation and libopensles from third_party/ clones.
#
# Usage: tools/dine linux build [stage...]   stages, in build order: bionic art opensles atl
# atl-headless (default: all)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
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

# Only init an empty checkout: `submodule update` would detach a working one from its `dine` branch.
submodule() {
  [[ -n "$(ls -A "$ROOT/$1" 2>/dev/null)" ]] || git -C "$ROOT" submodule update --init "$1"
}

meson_stage() {
  local src=$1 name; name=$(basename "$src"); shift
  echo "==> $name"
  if [[ ! -f "$BUILD/$name/build.ninja" ]]; then
    meson subprojects download --sourcedir "$src" >/dev/null 2>&1 || true
    meson setup "$BUILD/$name" "$src" --prefix="$PREFIX" --libdir=lib \
      --buildtype=debugoptimized "$@"
  fi
  meson compile -C "$BUILD/$name" -j "$JOBS"
  meson install -C "$BUILD/$name" --quiet
}

# Not installed: it runs from its build dir with RUN_FROM_BUILDDIR. Runs after `atl`, never beside
# it: both builds write dine-atl/src/api-impl-jni/generated_headers.
atl_headless_stage() {
  local dir="$BUILD/dine-atl-headless"
  echo "==> dine-atl-headless"
  if [[ ! -f "$dir/build.ninja" ]]; then
    meson setup "$dir" "$ROOT/dine-atl" --prefix="$PREFIX" --libdir=lib --buildtype=debugoptimized \
      -Dhost=cli -Dloop=poll -Dui=headless -Dgfx=record
  fi
  meson compile -C "$dir" -j "$JOBS"
}

art_stage() {
  echo "==> dine-art"
  submodule dine-art
  make -C "$ROOT/dine-art" -j "$JOBS" ____PREFIX="$PREFIX" ____LIBDIR=lib
  make -C "$ROOT/dine-art" ____PREFIX="$PREFIX" ____LIBDIR=lib ____INSTALL_ETC="$PREFIX/etc" install
}

stages=("$@")
[[ ${#stages[@]} -eq 0 ]] && stages=(bionic art opensles atl atl-headless)

for s in "${stages[@]}"; do
  case $s in
    bionic)   meson_stage "$SRC/bionic_translation" ;;
    art)      art_stage ;;
    opensles) meson_stage "$SRC/libopensles-standalone" ;;
    atl)      submodule dine-atl; meson_stage "$ROOT/dine-atl" ;;
    atl-headless) submodule dine-atl; atl_headless_stage ;;
    *) echo "unknown stage: $s" >&2; exit 1 ;;
  esac
done

echo "done -> $PREFIX"
