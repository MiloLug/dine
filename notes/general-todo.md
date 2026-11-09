# General todo

Non-defect work no stage of `notes/atl-port.md` owns: ideas, checks to run, claims nobody has
checked. Defects are in `notes/bug-tracker.md`; work a stage owns stays in that stage. Codes,
numbering and links follow `notes/bug-tracker.md`; the two files share the numbers.

- **A new find:** work no stage owns gets a code here; once a stage takes it, the entry moves into
  that stage.
- **Done:** the entry moves under `## Done`, keeps its heading, and shrinks to one line: title,
  date, commit.

## ART

### ART-19

**Port mterp, the assembly interpreter, to heap-base references.** dine-art runs the C++ switch
interpreter (`ART_USE_CXX_INTERPRETER`, `dine-art/art/build/Android.common_build.mk`), because
mterp uses references as pointers. The Linux runtime suite takes ~78 s with it, ~52 s with mterp.
Proposal, test order and findings: `notes/mterp/`.

### ART-20

**Trim ICU's data.** `out/ios/lib/libicudata.a` is 33 MB: ICU is built with
`--with-data-packaging=static` and no data filter (`tools/libexec/build-ios-deps.sh`).

### ART-21

**Trim the boot class path.** Release builds boot 7 jars (`kBootJars` in
`native/artbridge/artbridge.cpp`), dev builds 10 (`DevVmArgs` adds the junit jars). Each one is
opened at startup; the gain is unmeasured.

### ART-22

**A prebuilt boot image to win back startup time.** dine-art loads no boot image and no compiled
code: both hold absolute 32-bit references, while its heap references are offsets from one heap
reservation (`notes/art-findings.md` "Runs on the phone"). An image would need its references
relocated to that base (unchecked). Without an image `dine-0001-hello` takes 0.15 to 0.20 s on
Linux, against 0.03 s warm with one (`notes/art-findings.md`).

### ART-25

**Think about a "standard" unwind method for shared objects after a thread crash**: a Java
extension where an object defines a method that undoes a half-done change to its state. When a
thread is parked after a fault while holding that object's monitor, ART would force-release the
lock and run the method, instead of ending Dine when another app blocks on it. Low priority, much
later. Context: `notes/multi-app-support/design.md` "Native faults" (the monitor rule).

### ART-27

**Bring dex2oat back, run once per install, after multi-app MA1.** dine-art has no oat or vdex for
app dex, so every start verifies the dex at run time (`notes/art-findings.md` "How ART starts on
Linux") and inflates a deflated dex into anonymous dirty memory. dex2oat's default
`--copy-dex-files=true` copies a compressed dex into the vdex, which ART maps from the file
(unchecked in dine-art), so the stored APK stays the original. Headless build, 10 starts each, the
APK's dex deflated vs stored and 4-byte aligned: dirty memory 15.7 vs 11.3 MiB with a 4.2 MB dex,
21.9 vs 14.5 MiB with a 6.9 MB dex, the difference moving to clean file pages; start time equal
within the spread. Whether iOS leaves clean file pages out of Dine's memory limit: unchecked. Trap
when measuring: an APK on tmpfs, or copied and not yet written back (`sync`), shows its mapped
pages as dirty. iOS can't fork or exec, so dex2oat would run in-process there (unchecked). Compiled code has ART-22's absolute-reference problem, and iOS
may refuse to execute pages that aren't signed (unchecked for Dine); a verify-only output (vdex,
no machine code) would avoid both (unchecked). The side path that still reaches dex2oat:
[ART-23](bug-tracker.md#art-23).

## ATL

### ATL-6

**Cut draw cost under `-Xint`, after M5d's frame-time measurement.** Candidates: the `Matrix`
allocated per `ATLCanvas.save()` (the current matrix could live in C), Canvas ops batched into one
JNI call per draw, JIT through StikDebug where the phone has it ([DINE-6](#dine-6)).

### ATL-7

**Apps that are keyboards:** `InputMethodService` over the Wayland input-method protocol, gtk-only.
After M9, if ever.

### ATL-19

**The system serif design on iOS.** Serif text is Times New Roman: CoreText has no public call
for the system font's serif design (New York), which UIKit reaches through
`UIFontDescriptorSystemDesignSerif`. uikit could hand `cg_font` the serif font it builds.

### ATL-20

**Roboto on iOS, for Android's text widths.** SF is wider than Roboto and its lines taller (M5c's
metric table in `notes/atl-port.md`), so a layout sized in dp around Roboto text can wrap or cut a
word. Roboto (Apache 2.0) as the default sans of TextViews and Paint would match Android, at the
cost of the font files in the app and of iOS's own look.

### ATL-21

**TextKeyListener for text fields.** A text EditText has no key listener: `getKeyListener()` is
null, where AOSP returns a TextKeyListener, so app code that reads it (editability, its
capitalization) finds none.

### ATL-22

**Check CoreText off UIKit's thread.** gfx measures and lays out text with CoreText on the Android
thread and on workers, on Apple's word that its objects are thread-safe; no run has stressed it
on iOS 27.

### ATL-29

**An optional Linux service for alarms and background work of apps that aren't running**, only
where systemd or D-Bus have no standard mechanism for it. Planned on its own; without it nothing
breaks and those alarms don't fire. Lowest priority. Context: `notes/multi-app-support/design.md`
"Platform mechanisms".

### ATL-30

**Service management:** a slot that lets the user enable, start and stop apps as services (systemd
user units on Linux, an internal manager in Dine on iOS) with a UI for it. A proposal, separate
from multi-app support: `notes/service-management/proposal.md`.

### ATL-31

**Think about an optional alarm connector for AlarmKit**, so an Android alarm clock app
(`AlarmManager.setAlarmClock`, the `AlarmClock.ACTION_SET_ALARM` intent) sets a system alarm on
iOS. Very low priority. The mapping and its open question are in `notes/background-tasks.md`
(question 9). iOS knowledge, untested:
- AlarmKit (iOS 26 and later) lets an app schedule alarms and timers that ring like the Clock
  app's, through the silent switch and Focus, shown on the lock screen, after a one-time permission
  prompt and with a usage string in Info.plist. No paid-only entitlement for it is known.
- Without it, iOS alarm apps use a scheduled local notification (its sound plays at most 30 s; the
  silent switch and Focus mute it) or stay alive in the background playing silent audio (no alarm
  after a force-quit). Critical alerts ring through mute but need an entitlement Apple grants on
  request.
- `AlarmManager` wake-ups that run app code have no iOS equivalent besides a keep-alive; they stay
  in the jobs item of `notes/os-features.md`.

### ATL-32

**Think about file isolation between apps**: today every app can read the others' files, since all
of them run as one OS user under one prefix on Linux and in one sandbox on iOS
(`notes/multi-app-support/design.md`, the trust point). Much later. On Linux a per-app sandbox
(bubblewrap or similar) is one candidate; iOS gives one sandbox to all of Dine, so there the layer
would have to do it. Nothing checked. Linux mounts and storage permissions are the later stage of
the filesystem slot (`notes/filesystem/proposal.md`).

### ATL-42

**An action bar on screen.** M6b1 gives `getActionBar()` Android 10's whole API with nothing
drawn: the title, the Up button, tabs (`NAVIGATION_MODE_TABS`) and the options menu
(`onCreateOptionsMenu`, action items, overflow) reach no build. gtk's header bar comes from the
gtk host, not from ActionBar. A native bar per backend (UINavigationBar and a UIMenu on iOS, the
header bar and a menu on gtk) would show them; no stage owns it.

### ATL-43

**`getOnBackInvokedDispatcher` (API 33).** androidx calls it only when `SDK_INT` is 33 or more,
and M6b1 raises the level to 29, so nothing reaches it yet. It comes with the next raise: an
`android.window` dispatcher per window that Back consults before `onBackPressed`. Predictive back
stays out of scope (`notes/nav-gestures.md`).

### ATL-49

**Clickable links in text.** M6b1 draws a `ClickableSpan` or `URLSpan` run as a link (underline,
`linkColor`), but no build routes a tap on it: `LinkMovementMethod` and `setAutoLinkMask` /
`Linkify` do nothing, and a toolkit label reports no character offset under a touch. A tap would
need an offset-at-point call per backend (Pango `xy_to_index`, TextKit's glyph lookup).

### ATL-50

**Styled resource strings.** A string resource with `<b>`, `<i>` or `<u>` reaches apps as plain
text: `AssetManager.getResourceText` (`AssetManager.java:191`) returns `TypedValue.coerceToString`,
and `StringBlock.get`'s span code (`StringBlock.java:60`) is commented out. Restoring it needs
dine-art's androidfw style data (`nativeGetStyle`) and spans built as AOSP's `applyStyles`; the
runs then reach TextView as M6b1's do.

### ATL-51

**Native scrolling for ListView and RecyclerView (to be decided).** ScrollView and
HorizontalScrollView are native scroll nodes since M4a (`ui_scroll_new`; UIScrollView on uikit),
while ListView and RecyclerView scroll in their own Java code, so on iOS they lack UIKit's fling
and bounce. The approach is open: a scroll node per list, a native list view (UICollectionView),
or UIKit's scroll physics fed into the Java scrolling. RecyclerView ships inside the app (androidx).

### ATL-63

**Spinner's drop-down off gtk.** `Spinner` is a gtk widget (`native_constructor`,
`native_setAdapter`, `Spinner.java:34-35`, legacy natives built only with ui=gtk), so a layout with
a Spinner throws `UnsatisfiedLinkError` on headless and uikit. M6b3b's PopupWindow and
ListPopupWindow on the window registry are the path AOSP's Spinner takes (`DropdownPopup`); they
work on every backend since M6b3b (2026-11-08). The user left it out of M6b3 (2026-11-07).

### ATL-65

**`Dialog.create`, `onStart` and `onStop`.** Android 10's Dialog has them (`create` runs `onCreate`
early, so `findViewById` and `getButton` work before `show`; `onStart` and `onStop` come with each
show and dismiss); ATL's has none, so an app that calls `create()` or overrides them (AppCompat's
dialogs, DialogFragment) gets a NoSuchMethodError or no callback.
- Found 2026-11-07 (M6b3a review).
- Where: `dine-atl/src/api-impl/android/app/Dialog.java`.

### ATL-68

**Glass drop-downs on iOS.** ListPopupWindow, AutoCompleteTextView's drop-down and Spinner fall back
to the theme's `popupBackground` when the app sets none; on uikit that default could be a glass
material behind the app's rows, as the dialog panels mirror iOS's alert. A popup whose app set a
background keeps it. Lowest priority (the user, 2026-11-08).
- Where: `dine-atl/src/api-impl/android/widget/PopupWindow.java` (`setBackgroundDrawable`),
  `src/backends/ui/uikit/view.m` (the window containers).

### ATL-69

**Report the display cutout's shape.** Android apps read the notch through
`WindowInsets.getDisplayCutout()` (API 28: safe insets and bounding rects; Developer options
"Simulate a display with a cutout" fakes one). ATL has a `DisplayCutout` stub that is always
`NO_CUTOUT` (`Display.java:72`), and `WindowInsets.getDisplayCutout()` returns null, so a window
that takes the notch (M6b3c's `cover_top` with `SHORT_EDGES`) can put content under it. The user
(2026-11-08): it must depend on the iPhone model, or better use an iPhone cutout API if one exists.
iOS has no public notch-shape API: `safeAreaInsets` gives only the strip's height. A private
`-[UIScreen _exclusionArea]` is reported to return the notch's rect (unverified on iOS 27); else a
table keyed on the device model (`utsname.machine`). Dine would send it with the insets.
- Found 2026-11-08 (M6b3c planning).
- Where: `dine-atl/src/api-impl/android/view/DisplayCutout.java`, `WindowInsets.java`, `Display.java`;
  Dine's `Navigator.sendInsets`.

### ATL-73

**`Resources.Theme.rebase`.** Android's re-applies the styles a theme was built from against its
Resources' current configuration, so `?attr` colors and drawables follow a night change. ATL's is
empty, and `Theme.applyStyle` doesn't record its styles in the theme's `ThemeKey` (`mKey.append`),
so there is nothing to re-apply yet. After an M6b3c night change, Resources lookups re-resolve
but an existing theme's attributes keep their day values, also in the activities that cover uiMode,
and so may the color behind the window (`Window.backgroundColor`, from the theme's
`colorBackground` when the root has no color drawable; unchecked).
- Found 2026-11-08 (M6b3c).
- Where: `dine-atl/src/api-impl/android/content/res/Resources.java` (`Theme.rebase`,
  `Theme.applyStyle`, `ThemeKey`); the night change in `ATLLoadedApp.applyNight`.

### ATL-74

**`WindowInsets.java`'s AOSP blocks have no notice.** The file has two marked blocks and neither a
"Portions Copyright" header nor a `doc/AOSP.md` row, which `doc/AOSP.md` asks for:
`Builder.setSystemWindowInsets` (`/* Copyright (C) 2019 … */`, ours, 407f24fd, 2026-10-21's insets
work) and `Type` (`/* Copyright (C) 2014 … */`, upstream ATL's, 9ab58e47). Which AOSP tag each came
from is unchecked; if `Builder` came with API 29 and `Type` with API 30, ours may be from
`android-security-10.0.0_r75` and upstream's from a later tag.
- Found 2026-11-08 (M6b3c review).
- Where: `dine-atl/src/api-impl/android/view/WindowInsets.java`, `dine-atl/doc/AOSP.md`.

### ATL-103

**The `fs` slot and the Android path layer.** `notes/filesystem/proposal.md` designs it and says its
stage is "to be added … when the fs todo is written": this entry is that todo, and the stage isn't
planned. Built: the prefix root, the registry, `apps/<pkg>/` and `data/<pkg>/` (multi-app MA1). Not
built:
- the slot, with `linux` and `ios` backends and one native for every root, in place of
  `ATLPaths.java`'s copy of the env logic;
- the mapping between Android paths and host paths: `/sdcard`, `/data/data/<pkg>` and the like have
  none, and Java file I/O, the headless build and iOS never see the gtk executable's libc override;
- Context's dirs: `getExternalFilesDir(type)` returns `getFilesDir()` and ignores the type, and
  `getCacheDir()` is `/tmp/atl_cache/<pkg>` on every build (both code-checked);
- shared storage with Android's public dirs, and the hidden `Android/data`, `Android/obb` and
  `Android/media`;
- install-time storage permissions in place of today's grant to every app;
- a `DocumentsProvider`: `createDocument` and `copyDocument` throw, and a tree URI from the picker
  has no provider behind it;
- later, platform things: `FileObserver` notifications, a MediaStore scan, iOS backup exclusion.

Linux mounts and isolation between apps are [ATL-32](#atl-32). Items not marked code-checked are
from `notes/filesystem/findings.md`, not rechecked.
- Where: `dine-atl/src/api-impl/android/content/Context.java`,
  `src/api-impl/android/atl/ATLPaths.java`; `notes/filesystem/`.

### ATL-104

**A camera bridge.** `notes/meta.md` lists camera among the platform bridges and says it has no item
yet. No stage, `notes/os-features.md` item or entry covers it: a search of `notes/` for "camera"
finds that one line. What ATL does for `android.hardware.Camera` today: unchecked.

### ATL-105

**SeekBar, DatePicker, TimePicker and MemoryFile exist only as gtk natives.** `dine-atl/meson.build`
lists `android_widget_SeekBar.c`, `android_widget_DatePicker.c`, `android_widget_TimePicker.c` and
`android_os_MemoryFile.c` under `legacy_srcs`, built only with ui=gtk. By the rule in
`notes/atl-port.md` "How the interface grows", a call to one throws `UnsatisfiedLinkError` on
headless and uikit (not run). Spinner is [ATL-63](#atl-63). For MemoryFile the plan is a small map
in place of the GHashTable and a platform helper for `memfd_create` (`notes/atl-port.md` "Shared C
without glib").
- Where: `dine-atl/meson.build`, `src/api-impl-jni/widgets/`, `src/api-impl-jni/android_os_MemoryFile.c`.

### ATL-106

**The cli host doesn't unpack an APK's `lib/<arch>/`; only the gtk host does.** A native-library
app's headless stop is that gap (`notes/atl-port.md` M9).
- State: the gtk side is code-checked; the cli side is from the notes, not checked in code.
- Where: `dine-atl/src/main-executable/main.c` (`extract_from_apk`); the cli host's APK loading.

### ATL-120

**Named constants for Android's values in native code, then a sweep for unexplained magic
numbers.**
- Configuration constants are written in C as literals with the Java name in a comment:
  - `/*KEYBOARD_QWERTY*/ 2`, `/*UI_MODE_NIGHT_YES*/ 0x20`, `/*SCREENLAYOUT_SIZE_LARGE*/ 0x03`;
  - 12 sites on 2026-11-09, in `dine-atl/src/shared/android_content_Context.c`,
    `src/backends/ui/gtk/display.c`, `src/backends/host/cli/main.c` and
    `src/api-impl-jni/android_content_res_AssetManager.c`.
- Proposal, from one source:
  - mark the constants native code uses with `@java.lang.annotation.Native` in
    `src/api-impl/android/content/res/Configuration.java`, so that `javac -h` writes them into
    `generated_headers/android_content_res_Configuration.h`. Unchecked: that the meson rule emits
    a header for a class with `@Native` constants and no native methods.
- ATL's own two-value fields get typed enums: `ui_display.keys` (`UI_DISPLAY_KEYS_SOFT`/`_HARD`
  are `#define`s in `src/slots/ui.h`). `UI_DISPLAY_UNKNOWN` stays the shared "not reported".
- Night stays Android's int: it crosses JNI, `atl_window_config`, `native/artbridge/include/dineart.h`
  and Swift (`apps/Dine/Sources/Dine/Navigation.swift`, a literal `0x20`). A named constant in
  `dineart.h` would serve the Swift side.
- Then sweep dine-atl, artbridge and Dine for other numbers without a name or an explanation
  (flags, masks, sizes, timeouts); name each or say why.

### ATL-121

**Check FILL_AND_STROKE text on gtk: the fill and the outline may sit a subpixel apart.**
`draw_text` fills with GSK's text node (`gtk_snapshot_append_layout`, hinted glyphs) and strokes
the layout's outline (`gsk_path_builder_add_layout`), which may follow unhinted shapes. Unchecked:
draw large FILL_AND_STROKE text into a bitmap and compare where the stroke's middle and the
glyphs' edges fall.
- Where: `dine-atl/src/backends/gfx/gsk/canvas.c` `draw_text`.

## DINE

### DINE-6

**Try JIT through StikDebug on the dev phone (iPhone 13, iOS 27.0.1).** Sideloaded, dev-signed
apps can get JIT through StikDebug from iOS 17.4; iOS 26.4 broke it for some users
(`notes/meta.md` "iOS constraints").

### DINE-7

**Navigation checks on the phone:**
- a vertical scroll in the middle of the screen never fires Home, and a swipe from the top-left
  corner opens Notification Center, not Home (`notes/nav-gestures.md` "By hand on the phone");
- the safe-area values Dine sends on the iPhone;
- the iOS 26+ full-content pop gesture.

The settings check waits for M8c; the excluded-span check is M4a's "Open:" in `notes/atl-port.md`.

### DINE-8

**A navigation settings screen bound to the `NavigationSettings` model.** M8c builds the store,
the model and the agent command, not a screen (`notes/nav-gestures.md` "Settings").

### DINE-9

**The AtlView dev screen's run states:** a button whose app runs brings it to the front, and the
others start their apps beside it (`notes/nav-gestures.md` "Behaviour"). A package that ran and
ended can't start again in this process (an app starts once per VM until multi-app MA4's drop):
its button stays enabled, and a tap logs the refusal while the app's container opens and closes
again. It should be disabled with a footer that says why. M8a builds the same states on the launcher's tiles only.

### DINE-10

**Licensing checks for a packaged app** (`notes/licensing-future.md`):
- ATL's `uikit` backend, for private APIs;
- whether the backends written for Dine (`uikit`, `cfrunloop`, `embedded`, `headless`, `cli`,
  `poll`, `record`, `records`) carry code moved from ATL files;
- the last ~14k characters of the App Store Review Guidelines page, which shows no update date;
- a private-API scan of the linked binary beyond the grep and the required-reason symbols;
- how many of the 505 dine-atl Java files without an AOSP header are AOSP copies with the headers
  stripped; those would be Apache 2.0 and shrink a rewrite;
- uploading without a Mac, and the Xcode license (`notes/meta.md`).

### DINE-12

**Native code of an APK on iOS.** iOS can't load an APK's `.so` files and there is no JIT, so the
`native` slot is `none` there. For the no-JIT case `notes/meta.md` plans to "substitute iOS builds of
known libraries"; `notes/interpreter-optimization-thoughts/findings.md` studies interpreting the
`.so` instead and says no stage owns it and nothing schedules it. Nothing decides between the two or
builds either. TachiyomiSY's native dependencies to rebuild for iOS or replace are in
`notes/meta.md`: SQLCipher, QuickJS, a libvips-based decoder, libarchive and zstd, and a WebGPU
viewer for the optional renderer. JIT is [DINE-6](#dine-6).
- Also in: M8a warns at import about an APK's native libraries (`notes/atl-port.md`).

### DINE-13

**A bridge from an app's own HTTP downloads to a background `URLSession`.**
`notes/background-tasks.md` names a "split plan" as one way a conversational downloader continues in
the background: the part that needs app logic runs while Dine is in front, and the images go to a
background `URLSession` in one batch. It needs a bridge in Dine's HTTP layer, because the app does
its own downloads. No Option in that file builds it (Option 1's `DownloadManager` backend serves apps
that call `DownloadManager`; Option 4 documents the limit), and M8d's questions don't test it.
- Where: `notes/background-tasks.md` "Split plan"; Dine's HTTP layer (not located).

## TOOL

### TOOL-4

**`tools/dine dbg ui type` can't press return.** The agent inserts text with `insertText:`, and a
UITextField takes an inserted newline as a space (`notes/dev-reference.md` "Debug agent").

### TOOL-5

**gtk `ui back` reports only whether ATL's main loop was up,** not what Back did: it is
`atl_nav_back`'s result.

### TOOL-6

**An ATL test hook `ATL_SCREENSHOT=<file>` that saves a window to PNG after its first frame,** and
optionally its GTK render node as text: a diffable golden of what gsk draws, like the headless
display-list golden. Its timing is exact, and it needs no compositor screenshot (`grim` on the
hidden sway does that part today), but GTK still needs a display. `gtk4-rendernode-tool render`
(installed with gtk4) turns a saved render node into a PNG. ATL already renders GTK
drawings to images (`dine-atl/src/api-impl-jni/graphics/android_graphics_Bitmap.c`) and saves PNGs
(`gdk_texture_save_to_png` in `android_app_WallpaperManager.c`); the gtk test hooks have a
window-ready point (`src/main-executable/main.c`, `src/backends/ui/gtk/dump.c`).

### TOOL-7

**Runtime-suite tests that fail for want of a tool:** `952-invoke-custom` and
`979-const-method-handle` need ASM 6, `701-easy-div-rem` has a Python 2 generator, `130-hprof`
needs `hprof-conv`, `141-class-unload` and `150-loadlibrary` need upstream's native test lib
`libarttest` (which 100 skipped tests need too). `071-dexfile-map-clean`, `677-fsi` and
`707-checker-invalid-profile` need dex2oat, which dine-art never runs: they stay expected
failures. Reasons per test: `dine-art/tests/runtime/expectations/linux-x86_64.json`.

### TOOL-8

**Evaluate XCUITest for phone UI checks.** The debug agent (`native/dev/dbgagent`) walks the
accessibility tree and activates elements; it can't synthesize touches, so taps at a point, a
real touch on a field and swipes stay hand checks. Apple's UI automation (XCUITest, which
Appium's WebDriverAgent also runs on) synthesizes taps and swipes at coordinates, and its test
daemon should turn app accessibility on for each session. Our agent needs that flag too
(`_AXSApplicationAccessibilityEnabled`): on 2026-11-08 it read 0 after a VoiceOver test, SwiftUI
built no tree and `dbg ui` found nothing (the VoiceOver link is a guess from the log's timing);
the agent now sets it for its own process at start.
- Unchecked: building and signing an XCTest runner without Xcode (xtool builds apps; the runner
  is a second app, one of a free Apple ID's three app IDs per 7 days); starting a session from
  Linux (pymobiledevice3's testmanagerd client); whether a synthesized swipe triggers iOS's own
  edge gestures (Home, Control Center); whether the daemon turns the flag on by itself on iOS 27.
- Found 2026-11-08 (M6b3c's hand checks; the user asked to note it).

### TOOL-9

**`tools/dine dbg ui` sees the key window only.** The walk misses a keyboard's `inputAccessoryView`
(the pads' round return button), which sits in the keyboard's window: `ls` doesn't list it and a
screenshot may not show it (`notes/dev-reference.md` "Debug agent").
- Where: `native/dev/dbgagent`.

## Done

### ATL-18

**A CTFont cache on iOS.** 2026-11-01, dine-atl 4fd8005c.

### ATL-23

**BitmapShader and ComposeShader didn't shade.** 2026-11-03, M6b1, dine-atl cff73b6f.

### DINE-11

**An app's screen brightness on iOS.** 2026-11-04, a no-op: no public API withdraws an app's
request (findings: `~/.claude/plans/dine-brightness-restore.md`); dine-atl 73077776.
