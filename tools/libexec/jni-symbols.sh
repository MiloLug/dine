#!/usr/bin/env bash
# out/ios/lib/libjnisymbols.a: the Java_* names of each JNI archive apps/Dine/Package.swift
# force-loads, keyed by its JNI_OnLoad_<stem>. Every library's handle on Apple is the app's
# image, so ART resolves a library's natives only from the list artbridge registers.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/env.sh"

lib="$ROOT/out/ios/lib"
out="$ROOT/out/ios/build/jnisymbols"
mkdir -p "$out"
c="$out/jni_symbols.c"

mapfile -t archives < <(grep -o 'nativeLibDir + "/lib[^"]*\.a"' "$ROOT/apps/Dine/Package.swift" | sed 's|.*"/||; s|"$||')
{
  echo '// tools/libexec/jni-symbols.sh writes this file'
  echo '#include "jni_symbols.h"'
  entries=()
  n=0
  for archive in "${archives[@]}"; do
    [[ -f $lib/$archive ]] || continue # a dev-only archive in a release build
    symbols=$(llvm-nm --defined-only --extern-only --just-symbol-name "$lib/$archive" 2>/dev/null | sort -u)
    mapfile -t java < <(grep '^_Java_' <<<"$symbols" | sed 's/^_//' || true)
    [[ ${#java[@]} -gt 0 ]] || continue # it registers its natives in its hook
    mapfile -t hooks < <(grep '^_JNI_OnLoad_' <<<"$symbols" | sed 's/^_JNI_OnLoad_//' || true)
    if [[ ${#hooks[@]} -ne 1 ]]; then
      echo "jni-symbols: $archive has Java_* symbols and ${#hooks[@]} JNI_OnLoad_<lib> hooks, not one" >&2
      exit 1
    fi
    echo "static const char *const list$n[] = {"
    printf '  "%s",\n' "${java[@]}"
    echo "};"
    entries+=("  {\"${hooks[0]}\", list$n, ${#java[@]}},")
    n=$((n + 1))
  done
  echo "const struct dine_jni_symbols dine_jni_symbols[] = {"
  printf '%s\n' "${entries[@]}"
  echo "};"
  echo "const size_t dine_jni_symbols_count = $n;"
} >"$c.new"
mv "$c.new" "$c"

clang -target "arm64-apple-ios$DINE_IOS_MIN" -isysroot "$DINE_IOS_SDK" -O2 -I "$ROOT/native/artbridge" \
  -c "$c" -o "$out/jni_symbols.o"
rm -f "$lib/libjnisymbols.a"
llvm-ar rcs "$lib/libjnisymbols.a" "$out/jni_symbols.o"
echo "jni-symbols: $n libraries -> $lib/libjnisymbols.a"
