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
