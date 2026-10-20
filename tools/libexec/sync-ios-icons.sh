#!/usr/bin/env bash
# Regenerate apps/Dine/Resources/Icons.xcassets from its sources.txt: one template imageset per
# listed pack file, plus the pack's LICENSE. Only the listed icons ship.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CATALOG="$ROOT/apps/Dine/Resources/Icons.xcassets"
# built apart and swapped in at the end: a missing clone or file leaves the catalog as it was
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

pack=
while read -r name path || [[ -n $name ]]; do
  [[ -z $name || $name == \#* ]] && continue
  if [[ $name == pack ]]; then
    pack="$ROOT/third_party/$path"
    [[ -f $pack/LICENSE ]] || { echo "missing $pack/LICENSE: clone the pack (docs/first-run.md)" >&2; exit 1; }
    continue
  fi
  [[ -n $pack ]] || { echo "sources.txt: a pack line must come first" >&2; exit 1; }
  [[ -f $pack/$path ]] || { echo "missing $pack/$path" >&2; exit 1; }
  file=${path##*/}
  [[ $file != *[\"\\]* ]] || { echo "$file: \" or \\ in a file name breaks Contents.json" >&2; exit 1; }
  mkdir "$work/$name.imageset"
  install -m644 "$pack/$path" "$work/$name.imageset/$file"
  cat > "$work/$name.imageset/Contents.json" <<JSON
{
  "images" : [
    {
      "filename" : "$file",
      "idiom" : "universal"
    }
  ],
  "info" : {
    "author" : "xcode",
    "version" : 1
  },
  "properties" : {
    "template-rendering-intent" : "template"
  }
}
JSON
done < "$CATALOG/sources.txt"
[[ -n $pack ]] || { echo "sources.txt names no pack" >&2; exit 1; }

rm -rf "$CATALOG"/*.imageset
mv "$work"/*.imageset "$CATALOG"/
install -m644 "$pack/LICENSE" "$CATALOG/LICENSE"
cat > "$CATALOG/Contents.json" <<JSON
{
  "info" : {
    "author" : "xcode",
    "version" : 1
  }
}
JSON
