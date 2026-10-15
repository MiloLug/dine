#!/usr/bin/env bash
# Local copies of the phone's system dylibs, so lldb reads their symbols from disk instead of
# device memory. Swift `po` (and any expression calling into the stdlib) needs them, and system
# frames get symbolicated. Pulls the dyld shared cache off the phone (~7 GB, ~5 min) and splits it
# with ipsw into out/ios-symbols/<version> (<build>)/Symbols/<install path>; ios-lldb.sh passes
# that dir to `platform select remote-ios --sysroot`. Rerun after an iOS update.
# Needs ipsw (AUR ipsw-bin).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/ios-common.sh"
command -v ipsw >/dev/null || { echo "ipsw not found: paru -S ipsw-bin" >&2; exit 1; }

ios_ensure_tunnel
dir=$(ios_symbols_dir)
[[ -d $dir/Symbols ]] && { echo "already there: $dir"; exit 0; }
mkdir -p "$dir"
dsc="$dir/dsc"
pymobiledevice3 developer fetch-symbols download --tunnel '' "$dsc"
cache=$(find "$dsc" -path '*/Caches/com.apple.dyld/dyld_shared_cache_arm64e' -print -quit)
# --all keeps the install paths, which is the DeviceSupport Symbols/ layout lldb expects.
ipsw dyld extract "$cache" --all -o "$dir/Symbols.tmp"
mv "$dir/Symbols.tmp" "$dir/Symbols"
rm -rf "$dsc"
echo "symbols ready: $dir"
