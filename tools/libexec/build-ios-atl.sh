#!/usr/bin/env bash
# Cross-compile dine-atl's iOS build (out/ios/lib/libtranslation_layer_main.a) and stage ATL's
# jars in out/ios/share/atl. Needs `tools/dine linux build atl` first: the jars and the JNI headers
# come from that build. Without DINE_RELEASE=1: with test_hooks, and the test APKs built into
# out/tests/apks (`ios run` bundles them).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/env.sh"   # meson comes from the .venv
JOBS="${JOBS:-$(nproc)}"
OUT="$ROOT/out/ios"
BUILD="$OUT/build/dine-atl"
LINUX_JARS="$DINE_LINUX_PREFIX/lib/java/dex/android_translation_layer"
APKS="$ROOT/out/tests/apks"
hooks=true
[[ ${DINE_RELEASE:-} == 1 ]] && hooks=false

for f in "$LINUX_JARS/api-impl.jar" "$LINUX_JARS/framework-res.apk" "$OUT/include/jni.h" \
         "$OUT/include/androidfw/androidfw_c_api.h"; do
  [[ -e $f ]] || { echo "missing $f: run tools/dine linux build atl and tools/dine ios build-art" >&2; exit 1; }
done

mkdir -p "$BUILD"
# meson-info records test_hooks at configure; a compile that fails after it must leave no archive
# of the other kind for `ios run` to link
rm -f "$OUT/lib/libtranslation_layer_main.a"
# outside the build dir, which a wipe empties
cross="$OUT/build/dine-atl.cross"
target="arm64-apple-ios$DINE_IOS_MIN"
cat > "$cross.new" <<EOF
[binaries]
c = ['clang', '-target', '$target', '-isysroot', '$DINE_IOS_SDK']
objc = ['clang', '-target', '$target', '-isysroot', '$DINE_IOS_SDK']
ar = 'llvm-ar'
strip = 'llvm-strip'

[built-in options]
c_args = ['-I$OUT/include']
c_link_args = ['-fuse-ld=lld', '-B$DINE_IOS_TOOLSET_BIN']
objc_args = ['-I$OUT/include']
objc_link_args = ['-fuse-ld=lld', '-B$DINE_IOS_TOOLSET_BIN']

[properties]
pkg_config_libdir = ['$OUT/lib/pkgconfig']

[host_machine]
system = 'ios'
subsystem = 'ios'
kernel = 'xnu'
cpu_family = 'aarch64'
cpu = 'arm64'
endian = 'little'
EOF

options=(--prefix="$OUT" --libdir=lib --buildtype=debugoptimized
         -Dhost=embedded -Dloop=cfrunloop -Dui=uikit -Dgfx=coregraphics -Dtest_hooks=$hooks)
if [[ ! -f $BUILD/build.ninja ]]; then
  mv "$cross.new" "$cross"
  meson setup "$BUILD" "$ROOT/dine-atl" --cross-file "$cross" "${options[@]}"
elif ! cmp -s "$cross.new" "$cross"; then
  # meson keeps the compilers it found at setup
  mv "$cross.new" "$cross"
  meson setup --wipe "$BUILD" "$ROOT/dine-atl" --cross-file "$cross" "${options[@]}"
else
  rm "$cross.new"
  meson configure "$BUILD" "${options[@]}"
fi
meson compile -C "$BUILD" -j "$JOBS"
meson install -C "$BUILD" --quiet

if [[ $hooks == true ]]; then
  for apk in looper dialog nav views widgets; do
    python3 "$ROOT/tests/harness/apk.py" "$ROOT/dine-atl/tests/headless/$apk" "$APKS/$apk.apk"
  done
fi
# the whole dir is bundled: nothing else may stay in it. ATLPaths expects gstub.jar and ghax.jar
# next to api-impl.jar.
rm -rf "$OUT/share/atl"
install -m644 -Dt "$OUT/share/atl" "$LINUX_JARS"/{api-impl,gstub,ghax}.jar "$LINUX_JARS/framework-res.apk"
