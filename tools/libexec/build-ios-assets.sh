#!/usr/bin/env bash
# accord: apps/<App>/Resources/{*.icon,*.xcassets} -> out/ios/assets/<App>, which xtool.yml lists.
# Dev.xcassets holds the dev screens' assets; DINE_RELEASE=1 leaves it out.
# Usage: tools/libexec/build-ios-assets.sh <App>
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/env.sh"

app=$1
res="$ROOT/apps/$app/Resources"
[[ -d $res ]] || exit 0
[[ -f $DINE_ACCORD/Cargo.toml ]] || { echo "no accord checkout at $DINE_ACCORD (docs/first-run.md)" >&2; exit 1; }

cargo build --release --quiet --manifest-path "$DINE_ACCORD/Cargo.toml"
out="$ROOT/out/ios/assets/$app"
rm -rf "$out"
mkdir -p "$out"
shopt -s nullglob
catalogs=()
for catalog in "$res"/*.xcassets; do
  [[ ${DINE_RELEASE:-} == 1 && ${catalog##*/} == Dev.xcassets ]] || catalogs+=("$catalog")
done
# Xcode's defaults: the primary icon is AppIcon, the accent colour AccentColor; xtool's
# UIDeviceFamily is iPhone and iPad.
"$DINE_ACCORD/target/release/accord" --compile "$out" --platform iphoneos \
  --minimum-deployment-target "$DINE_IOS_MIN" --app-icon AppIcon --accent-color AccentColor \
  --include-all-app-icons --target-device iphone --target-device ipad \
  --output-partial-info-plist "$out/Info.plist" --output-format human-readable-text \
  "$res"/*.icon "${catalogs[@]}"
