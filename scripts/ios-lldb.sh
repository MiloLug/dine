#!/usr/bin/env bash
# Attach the Swift toolchain lldb to a running app on the device (launches it if needed).
# Usage: scripts/ios-lldb.sh [--suspended] [App] [lldb args...]   (default: Dine)
# --suspended: the app waits for the debugger before running any of its code, so breakpoints in
# startup code (static init, App.init, first render) hit. Set breakpoints, then `continue`.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/ios-common.sh"
launch_opts=()
if [[ ${1:-} == --suspended ]]; then launch_opts=(--suspended); shift; fi
app=${1:-Dine}; [[ $# -gt 0 ]] && shift

ios_ensure_tunnel
bundle=$(ios_bundle_id "$app")
pid=$(ios_launch "${launch_opts[@]}" "$bundle")
url=$(pymobiledevice3 developer debugserver start-server --tunnel '' 2>&1 | grep -oE 'connect://\[[^]]+\]:[0-9]+' | head -n1)

# Our binary + debug info come from the local build. System dylibs come from the phone's shared
# cache split by scripts/ios-symbols.sh (--sysroot); Swift `po` needs their symbols. Anything not
# found there is read from device memory, minimal info only (DINE_LLDB_LOAD_LEVEL=complete also
# reads symbols: ~30 s slower, but `po` works without local symbols). Each memory read is a ~50 ms
# tunnel round trip, so read a 16 KiB page (the device page size: a line never straddles an
# unmapped page) per trip instead of the default 512 bytes.
local_app="$DINE_ROOT/apps/$app/xtool/$app.app/$app"   # Linux lldb wants the Mach-O, not the bundle
ios_lldb_setup
platform="platform select remote-ios"
symbols=$(ios_symbols_dir)
if [[ -d $symbols/Symbols ]]; then
  platform+=" --sysroot \"$symbols\""
else
  echo "no local system symbols for this iOS ($symbols): run scripts/ios-symbols.sh for Swift po" >&2
fi

echo "attaching to $bundle pid $pid via $url${launch_opts:+ (suspended: set breakpoints, then continue)}"
# `process connect` with no process blocks in sync mode, hence the SetAsync dance.
exec "$DINE_LLDB" \
  -o "$platform" \
  -o "settings set target.memory-module-load-level ${DINE_LLDB_LOAD_LEVEL:-minimal}" \
  -o "settings set target.process.memory-cache-line-size 16384" \
  -o "target create \"$local_app\"" \
  "${lldb_setup[@]}" \
  -o "script lldb.debugger.SetAsync(True)" \
  -o "process connect $url" \
  -o "script import time; time.sleep(2); lldb.debugger.SetAsync(False)" \
  -o "process attach -p $pid" \
  "$@"
