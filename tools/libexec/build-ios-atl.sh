#!/usr/bin/env bash
# Cross-compile dine-atl's iOS build (out/ios/lib/libtranslation_layer_main.a) and stage the
# bundle's jars and APKs in out/ios/share/atl. Needs `tools/dine linux build atl` first: the
# jars and the JNI headers come from that build.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/env.sh"   # meson comes from the .venv
JOBS="${JOBS:-$(nproc)}"
OUT="$ROOT/out/ios"
BUILD="$OUT/build/dine-atl"
LINUX_JARS="$DINE_LINUX_PREFIX/lib/java/dex/android_translation_layer"
DEMO_APK="$ROOT/third_party/atl_test_apks/demo_app.apk"
APKS="$ROOT/out/tests/apks"

for f in "$LINUX_JARS/api-impl.jar" "$LINUX_JARS/framework-res.apk" "$OUT/include/jni.h" \
         "$OUT/include/androidfw/androidfw_c_api.h" "$DEMO_APK"; do
  [[ -e $f ]] || { echo "missing $f: run tools/dine linux build atl and tools/dine ios build-art" >&2; exit 1; }
done

mkdir -p "$BUILD"
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
         -Dhost=embedded -Dloop=cfrunloop -Dui=uikit -Dgfx=record)
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

for apk in looper dialog nav; do
  python3 "$ROOT/tests/harness/apk.py" "$ROOT/dine-atl/tests/headless/$apk" "$APKS/$apk.apk"
done
# ATLPaths expects gstub.jar and ghax.jar next to api-impl.jar
install -m644 -Dt "$OUT/share/atl" "$LINUX_JARS"/{api-impl,gstub,ghax}.jar "$LINUX_JARS/framework-res.apk" \
  "$DEMO_APK" "$APKS"/{looper,dialog,nav}.apk
