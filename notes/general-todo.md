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

### ATL-23

**BitmapShader and ComposeShader don't shade.** M5d's shaders are the gradients; a paint with
either shader fills in its color (Canvas's `drawRoundRect` special case draws a BitmapShader's
bitmap at 0,0). AdaptiveIconDrawable's `draw()` (commented out) and rounded image views use
BitmapShader. Owner: M6b's drawables.

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

**The AtlView dev screen's run states:** while an app runs, its button brings it to the front and
the other run buttons are disabled with the footer "ATL runs once per process: relaunch Dine";
after the app exits every run button is disabled (`notes/nav-gestures.md` "Behaviour", one run per
process). M8a builds the same states on the launcher's tiles only.

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

## Done

### ATL-18

**A CTFont cache on iOS.** 2026-11-01, dine-atl 4fd8005c.
