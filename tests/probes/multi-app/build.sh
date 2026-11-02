#!/usr/bin/env bash
# Builds the multi-app probes into out/probes/multi-app: driver.jar, app-a.jar, app-b.jar and
# libprobe.so. DINE_PROBE_PREFIX: the ART prefix to build against (default out/linux/prefix).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
out=$root/out/probes/multi-app
prefix=${DINE_PROBE_PREFIX:-$root/out/linux/prefix}
core=$prefix/lib/java/core-all_classes.jar
javac=(/usr/lib/jvm/java-8-openjdk/bin/javac -g -Xlint:-options -source 1.8 -target 1.8 -bootclasspath "$core")
d8=$root/tools/bin/d8
mkdir -p "$out"

shopt -s globstar
dex() {  # dex <jar> <classes dir>
  local classes=("$2"/**/*.class)
  "$d8" --release --min-api 21 --lib "$core" --output "$1" "${classes[@]}"
}

rm -rf "$out/classes" && mkdir -p "$out/classes/driver"
"${javac[@]}" -d "$out/classes/driver" "$here"/driver/probe/*.java
dex "$out/driver.jar" "$out/classes/driver"

# Two jars of one source: two loaders, two sets of classes. G0..G199 give the app classes to unload.
gen=$out/classes/gen/app && mkdir -p "$gen"
{ echo "package app;"; for i in $(seq 0 199); do echo "class G$i { int v = $i; }"; done; } > "$gen/Gen.java"
for name in a b; do
  mkdir -p "$out/classes/app-$name"
  "${javac[@]}" -d "$out/classes/app-$name" "$here"/app/app/*.java "$gen/Gen.java"
  dex "$out/app-$name.jar" "$out/classes/app-$name"
done

# libart's compile line for one of its objects, from a make dry run (nothing is built).
flags=$out/cxxflags
if [[ ! -s $flags ]]; then
  make -C "$root/dine-art" -n -W art/runtime/thread.cc ____PREFIX="$prefix" ____LIBDIR=lib \
    out/host/linux-x86/lib64/libart.so 2>/dev/null |
    grep -- '-o out/host/linux-x86/obj/SHARED_LIBRARIES/libart_intermediates/thread\.o' |
    sed -e 's/^ *g++ //' -e 's/ -MD -MF .*//' -e 's/ -c / /' \
      > "$flags.tmp"
  [[ -s $flags.tmp ]] || { echo "build.sh: no libart compile line from make -n" >&2; exit 1; }
  mv "$flags.tmp" "$flags"
fi
read -ra cxxflags < "$flags"
# probe.cc copies libart's gHeapReferenceBase from this load-base-relative address (JNI_OnLoad)
base=$(nm -D --defined-only "$prefix/lib/art/libart.so" | awk '$3 == "_ZN3art6mirror18gHeapReferenceBaseE" {print $1}')
[[ -n $base ]] || { echo "build.sh: no gHeapReferenceBase in libart.so" >&2; exit 1; }
(cd "$root/dine-art" && g++ "${cxxflags[@]}" -w -DLIBART_HEAP_REFERENCE_BASE=0x"$base" -shared -Wl,-z,defs \
  -o "$out/libprobe.so" "$here/native/probe.cc" -L"$prefix/lib/art" -lart -lartbase -ldexfile -lbase -llog)
# A real app's dex for run.sh's DINE_PROBE_EXTRA_JAR: ATL's api-impl dex, deflated as in most APKs.
api=$prefix/lib/java/dex/android_translation_layer/api-impl.jar
if [[ -f $api ]]; then
  rm -rf "$out/dex-tmp" "$out/api-impl-deflated.jar" && mkdir "$out/dex-tmp"
  unzip -q "$api" classes.dex -d "$out/dex-tmp"
  (cd "$out/dex-tmp" && zip -q -9 ../api-impl-deflated.jar classes.dex)
  rm -rf "$out/dex-tmp"
fi
echo "built $out"
