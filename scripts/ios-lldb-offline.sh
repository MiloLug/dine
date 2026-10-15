#!/usr/bin/env bash
# lldb on the local build with no phone: loads a synthetic core (tools/ios-core.py) whose only
# thread is stopped at <breakpoint>, with the same setup as ios-lldb.sh. Good for checking the
# Swift expression context (`type lookup`, module imports in DINE_LLDB_LOG) in seconds. Nothing
# can run and a core has no OS version, so `expr` itself fails (`@available(iOS 0, *)` parse
# errors, then dlopen/JIT); `v` can't read locals either (no stack contents).
# Usage: scripts/ios-lldb-offline.sh [App] <breakpoint> [lldb args...]   (default: Dine)
#   e.g. scripts/ios-lldb-offline.sh HelloView.swift:8 -b -o "type lookup DineApp"
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/ios-common.sh"
app=Dine
if [[ $# -ge 2 && -d $DINE_ROOT/apps/$1 ]]; then app=$1; shift; fi
bp=${1:?usage: $0 [App] <breakpoint> [lldb args...]}; shift

local_app="$DINE_ROOT/apps/$app/xtool/$app.app/$app"
pc=$("$DINE_LLDB" -b -o "target create \"$local_app\"" -o "b $bp" 2>&1 \
  | grep -oE 'address = 0x[0-9a-f]+' | head -n1 | cut -d' ' -f3) || true
[[ -n $pc ]] || { echo "no address for breakpoint '$bp' in $local_app" >&2; exit 1; }
core="$DINE_ROOT/out/ios/$app.core"
mkdir -p "${core%/*}"
python3 -I "$DINE_ROOT/tools/ios-core.py" "$local_app" "$core" "$pc"
ios_lldb_setup

exec "$DINE_LLDB" \
  -o "target create \"$local_app\" --core \"$core\"" \
  "${lldb_setup[@]}" \
  -o "target modules load --file $app --slide 0" \
  "$@"
