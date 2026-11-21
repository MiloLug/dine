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
no machine code) would avoid both (unchecked). `OatFileAssistant::GetBestOatFile` returns no oat
file either ([ART-23](bug-tracker.md#art-23)).

### ART-31

**Runtime behaviour no test would see break** (overhaul A2, 2026-11-14):
- jars with a stored, aligned `classes.dex` are mapped, not inflated (`definitions.mk`,
  `d8-jar.sh`): nothing reads the mapping back;
- `OatFileAssistant::GetBestOatFile` answering nothing when an old dalvik cache holds an oat file;
- `ProcessCpuNanoTime` and `Thread::GetCpuMicroTime`'s Apple branch (GC statistics and CheckJNI
  read them); `dine-0008` grades `ThreadCpuNanoTime` only;
- the hidden-API warning gate, the sentinel fault page left out on Apple arm64 and the invoke
  stub's 32-bit frame size: arm64 or log-only, with no output a test compares;
- `dine_atl_run`'s refusals (while the first run starts; after the art screen made the VM) and the
  `exited` it sends when `JNI_CreateJavaVM` fails: no smoke step reaches them;
- `tests/probes/multi-app/` (`run.sh`: storm, juclock): no `tools/dine` command runs it.

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

### ATL-126

**`Region.setPath` walks every pixel row of its area and every edge on each row.** With no clip the
area is the path's bounds (`Path.op` passes none), so a tall path costs rows times edges
(`region_set_path`, `rasterize` in `dine-atl/src/shared/region.c`). An edge table sorted by its top
row would visit only the edges a row crosses.

### ATL-127

**Graphics behaviour no test would see break** (overhaul A1, 2026-11-14; A4 added the last two):
- a nine-patch with an empty patch, a transparent patch or an axis without a stretch section
  (`ninepatch_slices`; the golden's one nine-patch reaches none);
- `RGBA_F16` conversions (`bitmap_pack`, `bitmap_unpack`);
- the frees of paints, paths, shaders and a display list's refs: only drawables, dialogs and views
  print a line a script greps;
- gsk Paints taking GTK's text settings again after a `GtkSettings` change (`gsk_text_follow_gtk`'s
  notify path): `TextViewTest` checks the first copy only, and nothing sets `gtk-font-name`;
- `BitmapNdkTest` on headless runs the test hook's own lock and unlock code, not
  `src/libandroid/bitmap.c` (`--gtk` runs it);
- gsk's bitmap-shader transform branches (A4's second round): a shader matrix with rotation, skew
  or a mirror, and REPEAT or MIRROR under a scale (`transform_affine_unscaled`, `append_bitmap_shader`);
  only a scale with CLAMP is read.

### ATL-129

**Host and lifecycle behaviour no test would see break** (overhaul A3, 2026-11-14):
- a thread attached without a group takes the host's app on gtk and on a headless run of one app
  (`host/cli/main.c`, `main-executable/main.c`); only ART's half has a test (`dine-0005`);
- the gtk host's brightness path (GNOME's power settings over D-Bus, else `/sys/class/backlight`,
  its save file and restore): the scripts read only the cli host's `host: brightness` lines;
- a throw in `Application.onCreate`, in an activity's `onStop`, in an insets or observer callback:
  the crash APK covers onCreate, onResume, a posted Runnable, onLayout, onPause, onDestroy (end the
  app) and onMeasure, onDraw (printed and cleared);
- the results of activities that `FLAG_ACTIVITY_CLEAR_TOP` closes (`RESULT_CANCELED` at their
  callers), and `recreate()` handing its caller over;
- the embedded host keeping a night mode set before the app's start (`embedded.c`): iOS only, and
  no run sets one in that window.

### ATL-133

**App-supplied fonts draw in the system sans.** `Typeface.createFromAsset`, `createFromFile`,
`Typeface.Builder.build` and `res/font` return DEFAULT (`Typeface.java`), so an app's icon font or
brand font is lost. The gfx slot loads no font file.
- Related: ATL-15 (TextView's family), ATL-19 (iOS serif), ATL-20 (Roboto's widths).
- Where: `dine-atl/src/api-impl/android/graphics/Typeface.java`, `src/slots/gfx.h`.
- Found 2026-11-15 (overhaul A4, stage row M5c-8).

### ATL-134

**`<animated-vector>` inflates an empty drawable, and ColorStateListDrawable draws nothing.**
`Drawable.createFromXmlInner` returns an empty AnimatedVectorDrawable without reading the XML; it
has no paintable, so its `draw` returns. ColorStateListDrawable's `draw` is empty, and a copy of
either through `StubState` is another empty one.
- Where: `dine-atl/src/api-impl/android/graphics/drawable/{Drawable,AnimatedVectorDrawable,ColorStateListDrawable}.java`.
- Found 2026-11-15 (overhaul A4, stage row M6a-16).

### ATL-135

**On the phone a color filter is computed per pixel on UIKit's thread at each replay of a view's
list.** A bitmap op keeps its filtered image on the op (`bitmap_op_image`), but every redraw of a
view records new ops, so a tinted nine-patch (one op per slice, each filtering and keeping a copy
of the whole bitmap) runs `filtered_image` nine times per redraw; a shader through a color filter
(`draw_filtered_shader`) has no cache at all and filters each device pixel of the clip, up to
1170 x 2532, per replay. Nothing was timed.
- Design: filter where the list is published, on the Android thread (`cg_list_publish`), into a
  cache kept on the bitmap and keyed by filter, alpha and generation, so slices and later
  recordings share one filtered image; render a filtered shader's pixels once per op at publish.
- Where: `dine-atl/src/backends/gfx/coregraphics/draw.c`.
- Found 2026-11-15 (overhaul A4, audit A4-16, stage row M6b1-9).

### ATL-139

**Views redraw whole, and the display link runs on UIKit's main run loop.** A draw replaces a view's
whole display list (`draw_view` in `records/ui.c`): no dirty rects, so a small invalidate records
and replays everything. uikit's `CADisplayLink` is added to the main run loop and posts each
waiting app's pass to its Android thread; one on the Android thread's own run loop would save the
hop (unverified on iOS 27).
- Where: `dine-atl/src/backends/ui/records/ui.c`, `src/backends/ui/uikit/view.m` (`records_draw_wanted`).
- Found 2026-11-20 (overhaul A5a, stage row M5b-6), from M5b's Open line.

### ATL-141

**gtk prints no `viewfreed:` line.** `ATL_DUMP_VIEWTREE` makes the records backends print a
`viewfreed:` line for each view freed, which `run-views.sh --headless` checks; gtk's `ui_view_free`
prints nothing, so a wrapper that is never unreffed fails no check.
- Where: `dine-atl/src/backends/ui/gtk/view.c`, `tests/headless/run-views.sh`.
- Found 2026-11-20 (overhaul A5a, audit A5-17's last clause).

### ATL-144

**Hand checks on the phone that no run makes: input, and looks and facts no step reads.** Input:
no run drags or types on the phone (the debug agent has `tap` only and UIKit makes no `UITouch`; a
hardware keyboard needs a keyboard). The last bullets (looks and facts) are checks the phone's
smoke steps would need a new line or agent output for.
- A hardware keyboard (M4a): Tab, the arrows, Enter, Esc, a typed letter, and the character an arrow
  key carries (`input.m` takes the first UTF-16 unit of `UIKey.characters` for every key; what
  UIKit returns for arrows and function keys was never observed); a held key cancelled by the
  system (Control Center) clicks nothing (`pressesCancelled` sets `FLAG_CANCELED`; headless
  proves the shared half, `key cancel`).
- A drag through the real touch path (UITouch ids 0 and 1 for two fingers, `delaysContentTouches`,
  the scroll pan against a child, [ATL-142](bug-tracker.md#atl-142)).
- A press on a selector row on the phone and on gtk (M5b); the redraw `View.invalidateDrawable` asks
  for is graded nowhere (`run-widgets.sh` reads `getCurrent()`; display lists are dumped by
  `run-draw.sh` only).
- The three cases of `ATLOutsideWatch` (M6b3b): a tap on a second field closes an open drop-down, a
  touch-modal window without a dim catches the touches outside it, a NOT_TOUCHABLE one lets them
  through. The agent's activation never passes through UIKit's hit test.
- M6b3c's hand checks on the final build: the home indicator's swipe with `hideNavigation` and not
  `immersive`, the keyboard's corners (`frame.background` on the surface), the top edge's deferral
  with the status bar hidden (`Navigation.swift`, `prefersHomeIndicatorAutoHidden`).
- M6b3c's experiment K2: whether UIKit scrolls an `ATLScrollView` to a first-responder field on its
  own (a scroll report with no touch after `type` into `ResizeActivity`'s field); the stage's
  Status records neither the result nor an Open line, and `view.m` has no suppression.
- `Configuration`'s keyboard fields and the keyboard's show and hide (late fix `76313409`): no phone
  scenario reads them (`atl-config` matches night lines; `atl-text` has no show, hide, Back or Next
  step), so they stay unverified on iOS; the code is shared with headless, where `KeyboardConfigTest`
  covers it.
- Looks and facts no phone step reads (overhaul A5b, round 1): `nav: frame` prints neither the
  frame's color nor its light flag (M3-4: `atl-demo` could wait for `1a1b20`, `atl-nav` for B's
  `2196f3` light); a TextView's background color and padding on UILabel (M3-7: the agent's `ui ls`
  prints neither); the release of the surface when a window closes (M3-12: no line, no count); a
  field changed in kind while it edits, two changes before a delivery, a field's deferred first
  responder (M4c-11); the in-flight frame skip, a view that stops drawing clearing its layer and
  `replace_native`'s hand-over (M5b-5); the capped field's growth and its last lines on the phone
  (M5c-2: `atl-text` types into `name` only); a Button with a background and padding keeping no
  UIKit insets (M6b3a-5: no `framed` step in `atl-controls`); VoiceOver staying in the topmost
  modal window (M6b3a-7: an absence check in `atl-dialog-content` if the agent's walk honours
  `accessibilityViewIsModal`); one night switch reaching every running app and the uikit panel's
  room after a window resize (M6b3c-12, M6b3c-13: `atl-config` runs one app).
- State: open; found 2026-11-20 (overhaul A5b, stage rows PreM4-M4a-1, M5b-4, M6b3b-2, M6b3c-3,
  M6b3c-15, late-5, from the old plans and the audit; round 1: M3-4, M3-7, M3-12, M4c-11, M5b-5,
  M5c-2, M6b3a-5, M6b3a-7, M6b3c-12, M6b3c-13).

### ATL-146

**META+TAB cluster navigation isn't wired.** `ATLInput.performFocusNavigation` has no cluster
branch (`FOCUS_FORWARD` between keyboard navigation clusters); M4a's plan listed it as a default
taken and it reached neither the stage's section nor an entry.
- Where: `dine-atl/src/api-impl/android/view/ATLInput.java` (`performFocusNavigation`).
- Found 2026-11-20 (overhaul A5b, stage row PreM4-M4a-4).

### ATL-147

**`dbg smoke atl-text` reads no field's own text.** Its steps assert Java's log lines only, so a
uikit that applied no snapshot (`ui_edit_set_state`, M4c) would still pass: after `fill` the report
with a stale base lands at Java's cursor and logs `text after "filled!"`. The drop rule is graded on
headless only (`run-text.sh`). Fix: label an iOS text field `hint: text` in the debug agent as the
gtk agent does, and add `ui=('name: hi',)` and `ui=('name: filled',)` to `atl-text` (the agent's
text insertion in `native/dev/dbgagent/agent.mm` is frozen for the overhaul: A6's).
- Where: `tools/py/dine/dbg/smoke.py` (`atl-text`), `native/dev/dbgagent/agent.mm`.
- Found 2026-11-20 (overhaul A5b, stage row M4c-2).

### ATL-148

**Callbacks that print an app's exception and go on are not yet taken up by multi-app's per-app
handler.** The measure, draw, input, click and dialog-result upcalls (`atl_upcall_*` in
`src/shared/upcall.c` and `input.c`, `windows.c`, `android_widget_PopupMenu.c`) print and clear
the exception; MA3's first item names only `ThreadGroup.uncaughtException`.
- Owner: MA3 (`notes/multi-app-support/todo.md`, first item).
- Found 2026-11-20 (overhaul A5b, stage row M6a-3).

### ATL-149

**Gaps a Linux run could close, found in the stage claims of the input and view code.** Each is a
claim some stage's notes make that no check would fail without; none shows a defect.
- gtk's view-tree dump (`ATL_DUMP_VIEWTREE`) is read by no gtk run: `run-views.sh` diffs the tree
  under `--headless` only, so a broken gtk dump or a gtk layout that drifts from the headless shape
  fails nothing (M0-4). Compare its shape with the headless golden, as `smoke.py`'s
  `viewtree_problem` does for the phone.
- `fitsSystemWindows` from the XML attribute and `requestApplyInsets` have no test
  (`WindowInsetsTest` covers the setter), and AppCompat's subdecor padding was never seen in an
  apps-suite APK (nav-9, PreM4-M4a-16): a framework case that inflates `android:fitsSystemWindows`,
  one that calls `requestApplyInsets`, and a flower_finder marker for the padding.
- `ViewConfiguration`'s scaled values are dp, and every touch test runs at 160 dpi
  (PreM4-M4a-18): a framework test of `getScaledTouchSlop() == round(8 * density)` run once with
  `-d 480`.
- `View.atlDraw` clears the canvas after the draw so a kept Canvas draws nothing (M5a-4): a
  framework test that keeps the Canvas, draws on it after the pass and after a second draw, under
  `MALLOC_PERTURB_`.
- The text-measure cache's hit count (`text measures N cached M`) is read by no check, and a key
  that loses a field fails nothing (M6b1-7): `run-lists.sh` requires cached above 0 after the
  scroll; a framework test of two TextViews that differ only in runs or max lines.
- The release library must hold no test line (M6b3a-14): a release-build step that greps the built
  library for the known test-line prefixes.
- gtk's dispatch of ACTION_OUTSIDE to watching windows and the drop-down's registry entry have no
  gtk run (M6b3b-4): `windows-gtk` dismisses its popup from code; a step that taps outside an
  outside-touchable popup and opens the drop-down through the agent.
- adjustPan's offset applying to touch (M6b3c-9: `run-keyboard.sh` sends `insets` and `dump` only:
  a `touch` at the field's panned y), `getWindowVisibleDisplayFrame` leaving out the bars and the
  keyboard (M6b3c-10: log the rect after the 20-number `insets`), and `atl_exclusion_update` reading
  the app's size (M6b3c-12: a `size` while B shows, then B's exclusion line at the new width).
- Two `-l` groups of one headless run, and the refusal of a package that already runs
  (`ATLInstaller`, `already runs in this process`) have no script (MA2-3): `-l A a.apk -l B b.apk`
  waiting for both apps' markers and exit 0 after the last one, and the same APK twice expecting
  exit 1.
- gtk's portal path for night (`settings_changed_cb`, `display.c`) is driven by nothing; the gtk
  framework run sets night through `ATLTestHooks.setNight` (M6b3c-13).
- State: open; found 2026-11-21 (overhaul A5b round 1, stage rows M0-4, nav-9, PreM4-M4a-16,
  PreM4-M4a-18, M5a-4, M6b1-7, M6b3a-14, M6b3b-4, M6b3c-9, M6b3c-10, M6b3c-12, M6b3c-13, MA2-3).

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

### TOOL-14

**The runtime suite on the phone is seven authored tests behind buttons.** The phone runner of
`notes/atl-port.md` "Test strategy" (a test mode in Dine, tests pushed and pulled, batches in one
VM) has no stage. Until it exists the AOSP run-tests never run on arm64, and of the authored ones
`dine-0005-embedder-tag`, `dine-0007-native-libs` (their JNI code isn't linked into
`native/dev/runtimetests`) and `dine-0009-no-dex2oat` (a `run` script) stay Linux-only: the Apple
rule that a library outside the embedder's symbol lists doesn't load has no test.

## Done

### ATL-18

**A CTFont cache on iOS.** 2026-11-01, dine-atl 4fd8005c.

### ATL-23

**BitmapShader and ComposeShader didn't shade.** 2026-11-03, M6b1, dine-atl cff73b6f.

### DINE-11

**An app's screen brightness on iOS.** 2026-11-04, a no-op: no public API withdraws an app's
request (findings: `~/.claude/plans/dine-brightness-restore.md`); dine-atl 73077776.
