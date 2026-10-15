# Shared helpers for ios-*.sh. Source, don't run.
source "$(dirname "${BASH_SOURCE[0]}")/../env.sh"

# Installed bundle ID: free-account xtool builds are prefixed "XTL-<TeamID>.".
ios_bundle_id() {
  local app=$1 base team
  base=$(sed -n 's/^bundleID: *//p' "$DINE_ROOT/apps/$app/xtool.yml")
  team=$(xtool auth status 2>/dev/null | sed -n 's/.*Team ID: *//p')
  local apps
  apps=$(pymobiledevice3 apps list 2>/dev/null)   # not piped into grep -q: SIGPIPE + pipefail
  if [[ $apps == *"\"XTL-$team.$base\""* ]]; then
    echo "XTL-$team.$base"
  else
    echo "$base"
  fi
}

# iOS 17+ developer services need the RemoteXPC tunnel + personalized DDI.
ios_ensure_tunnel() {
  systemctl is-active --quiet dine-tunneld || sudo systemctl start dine-tunneld
  for _ in $(seq 20); do
    curl -sf http://127.0.0.1:49151/ | grep -q tunnel-address && break
    sleep 1
  done
  pymobiledevice3 mounter auto-mount --tunnel '' >/dev/null 2>&1 || true
}

# ios_launch [dvt launch options...] <bundle>  → prints the pid
ios_launch() {
  pymobiledevice3 developer dvt launch --tunnel '' "$@" | grep -oE '[0-9]+$'
}

# lldb_setup=(-o … ...): lldb commands every ios-lldb*.sh session runs right after `target create`.
# - target.sdk-path: lldb can't map the DWARF SDK name to a path on Linux (HostInfoError), and
#   without it the Swift expression context can't import Darwin.
# - DINE_LLDB_LOG=<dir>: opt-in file logs (Swift type system + expressions, Swift health,
#   gdb-remote packets with timestamps) that survive a killed or hung session.
ios_lldb_setup() {
  lldb_setup=(-o "settings set target.sdk-path \"$DINE_IOS_SDK\"")
  if [[ -n ${DINE_LLDB_LOG:-} ]]; then
    mkdir -p "$DINE_LLDB_LOG"
    lldb_setup+=(
      -o "log enable -T -f \"$DINE_LLDB_LOG/lldb.log\" lldb types expr"
      -o "log enable -T -f \"$DINE_LLDB_LOG/swift-health.log\" swift health"
      -o "log enable -T -f \"$DINE_LLDB_LOG/gdb-remote.log\" gdb-remote packets"
    )
  fi
}

# out/ios-symbols/<ProductVersion> (<BuildVersion>) for the connected phone (scripts/ios-symbols.sh).
ios_symbols_dir() {
  local v
  v=$(pymobiledevice3 lockdown info 2>/dev/null | python3 -I -c \
    'import json, sys; d = json.load(sys.stdin); print("%s (%s)" % (d["ProductVersion"], d["BuildVersion"]))')
  echo "$DINE_ROOT/out/ios-symbols/$v"
}
