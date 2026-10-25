# Icons

How Dine gets its icons. The commands are in CLAUDE.md.

## Rule

- Where iOS has a standard icon, Dine uses the SF Symbol (`Image(systemName:)`) and ships nothing.
- Icons iOS lacks come from one open pack. Only the icons Dine uses ship, and all of them sit in
  one catalog, so the pack can be swapped.
- Exception: a glyph that stands in for an app's icon (the launcher's default) comes from the pack.
  Apple's SF Symbols license bars symbols in app icons.

## Pack

- Fluent UI System Icons (Microsoft, MIT), tag `1.1.344`, cloned in
  `third_party/fluentui-system-icons`. The clone holds only `assets/*/SVG/` (sparse checkout, about
  150 MB); `docs/first-run.md` has the command.
- Chosen over Framework7 Icons, which looks more like iOS: its SF-like set has unknown provenance.
  Also over Ionicons, whose stroke icons on a 512 grid need resizing.

## Catalog

- `apps/Dine/Resources/Icons.xcassets` is a product catalog, so release builds ship it too.
- `sources.txt` has a `pack <dir in third_party>` line, then one `<Role> <pack file>` line per
  icon. Imagesets are named by role (`DefaultApp`), so Swift never sees pack names.
- `tools/dine ios icons` (`tools/libexec/sync-ios-icons.sh`) regenerates the imagesets and the
  pack's `LICENSE` from `sources.txt`. It builds them apart and swaps them in only when every file
  was found. The copies are committed, so builds don't need the clone.
- `build-ios-assets.sh` bundles each catalog's `LICENSE` as `licenses/<catalog>.txt`: the MIT
  notice has to ship with the copies, and `Assets.car` can't carry it.
- Add an icon: one line in `sources.txt`, then `tools/dine ios icons`. Swap the pack: clone the
  new one, change the `pack` line and the paths, then rerun.

## Rendering

- Imagesets are template SVGs, but accord stores the template intent only on the rasters, not on
  the vector rendition ([TOOL-3](bug-tracker.md#tool-3)). Tint in code:
  `.renderingMode(.template)` with `.foregroundStyle(...)`.
- Use `Image(decorative:)`. A plain `Image("Role")` adds the asset name to the accessibility label,
  and the debug agent's taps match labels.
- Pick the pack's largest size that fits. accord rasterizes at 1x, 2x and 3x the SVG's own size, so
  `app_generic_48` gives 144 px at 3x for a glyph of about 33 pt.
- `UIImage.draw(at:)` renders a template image black. The probe's `DefaultApp` check expects black
  at (7, 24), on the window frame's left edge.

## Default app icon

`AppIconView` draws `DefaultApp` (`app_generic_48_filled`) in white on a gradient whose hue comes
from the app's name. Every app uses it until the launcher reads icons from APKs (M8a).
