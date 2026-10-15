#!/usr/bin/env bash
# Build native libs, build/sign/install an xtool app, then launch it.
# Usage: scripts/ios-run.sh [App]   (default: Dine)
# `xtool launch` uses the pre-iOS-17 debugserver and fails on this device, so launch via DVT.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/ios-common.sh"
app=${1:-Dine}

"$DINE_ROOT/scripts/build-ios-native.sh"
# Installs fine, then its own launch step fails; tolerate only that error.
log=$(mktemp)
if ! (cd "$DINE_ROOT/apps/$app" && xtool dev run 2>&1 | tee "$log"); then
  grep -q "DebugserverClient" "$log" || { rm -f "$log"; exit 1; }
fi
rm -f "$log"
ios_ensure_tunnel
bundle=$(ios_bundle_id "$app")
pid=$(ios_launch "$bundle")
echo "launched $bundle pid $pid"
