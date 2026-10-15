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

# Our binary + debug info come from the local build; system dylibs are only in device memory
# (lldb on Linux can't use the raw dyld shared cache), so read just minimal info from those.
local_app="$DINE_ROOT/apps/$app/xtool/$app.app/$app"   # Linux lldb wants the Mach-O, not the bundle

echo "attaching to $bundle pid $pid via $url${launch_opts:+ (suspended: set breakpoints, then continue)}"
# `process connect` with no process blocks in sync mode, hence the SetAsync dance.
exec "$DINE_LLDB" \
  -o "platform select remote-ios" \
  -o "settings set target.memory-module-load-level minimal" \
  -o "target create \"$local_app\"" \
  -o "script lldb.debugger.SetAsync(True)" \
  -o "process connect $url" \
  -o "script import time; time.sleep(2); lldb.debugger.SetAsync(False)" \
  -o "process attach -p $pid" \
  "$@"
