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
- `tests/probes/multi-app/` (`run.sh`: storm, juclock): no `tools/dine` command runs it;
- `parkNanos` and `parkUntil` with MAX_VALUE on Apple: `dine-0004` guards the clamp, and no build
  without it was ever run;
- whether a second class loader works for a JNI library linked into the app (A2-11): untried;
- `dine-0009-no-dex2oat` passes on two absences: no run shows its fake dex2oat's marker appears on a
  runtime that does exec it;
- `dine-0006` gives the idle thread 1 s over its 10 s timer, so a loaded machine can fail it, and
  `dine-0003-https` rests on badssl.com's hosts staying as they are.

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
capitalization) finds none. The number, phone and datetime classes have theirs.

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

**`Dialog.create`.** Android 10's Dialog has it (`create` runs `onCreate` early, so `findViewById` and
`getButton` work before `show`); ATL's has none, so an app that calls `create()` (AppCompat's dialogs,
DialogFragment) gets a NoSuchMethodError. `onStart` and `onStop` came with overhaul A7 (2026-11-21).
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

**The cli host doesn't unpack an APK's `lib/<arch>/`, and the gtk host's unpacking throws.** A
native-library app's headless stop is that gap (`notes/atl-port.md` M9). The gtk host calls
`extract_from_apk` before `atl_app_create` joins its thread to the app; `AssetManager.extractFromAPK`
writes under `Environment.getExternalStorageDirectory()`, which reads the calling thread's app
(`ofCurrentThreadOrThrow`) and throws there for an APK with a `lib/<arch>/` entry.
- State: the gtk side is code-checked (overhaul A9, 2026-11-21; no run with such an APK); the cli side
  is from the notes, not checked in code.
- Where: `dine-atl/src/main-executable/main.c` (`extract_from_apk`), `src/api-impl/android/content/res/AssetManager.java`
  (`extractFromAPK`); the cli host's APK loading.

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

**Graphics behaviour no test would see break** (overhaul A1, 2026-11-14; A4 and A11 added to it):
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
  only a scale with CLAMP is read;
- gsk's isolation of each Java-drawn view (`WrapperWidget`): a CLEAR rect of a child over a coloured
  parent read from the window would show it; its cost in frames is unmeasured, as is cairo's group per
  fill-and-stroke (M6b1-10, M6b2-6, A3's review);
- `GLUtils.texImage2D`'s packing of bitmap words (M6b1-14): gtk's GL only, with M9's GL work;
- an ImageButton's themed background in a display list (M5d-11): `run-controls.sh` dumps none; a
  `round_rect` line in the button's block would show it;
- gsk's guard for an empty or non-finite bitmap rect on a view (code-path proof only), and stroked
  text on the phone's view path (A4);
- `BlendModeTest#testShadedTextIsFiltered` and `#testModulateOfManyColors`' text loop compare two
  bitmaps with no check for ink, so they pass where no text draws (framework-r2-2);
- a gradient's negative periods and the period cap have no pixel test (A1-20).

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
  no run sets one in that window;
- code-path proof only (A3): the local refs the gtk host drops for the activities it starts, and the
  class ref of a popup answer; the cost of glib's `g_main_context_pending` per message is unmeasured;
- a view whose `onDraw` threw drawing again at a later `invalidate()` (M5a-3: the crash APK shows
  only that the app goes on).

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
the smoke makes one finger's tap, back swipe and list scroll (`touch`) and presses Return in a
field (`atl-text`). Automatable: `dbg ui tap` and `drag` make real touches and `press` hardware
key events (uidrive); the checks are later work. iOS's own system gestures (the home indicator,
Control Center) stay by hand. The last bullets (looks and facts) are checks the phone's smoke steps
would need a new line or agent output for.
- A hardware keyboard (M4a): Tab, the arrows, Enter, Esc, a typed letter, and the character an arrow
  key carries (`input.m` takes the first UTF-16 unit of `UIKey.characters` for every key; what
  UIKit returns for arrows and function keys was never observed); a held key cancelled by the
  system (Control Center) clicks nothing (`pressesCancelled` sets `FLAG_CANCELED`; headless
  proves the shared half, `key cancel`).
- Text input (M4c-5, M4c-13): the software keyboard's own typing, a CJK keyboard's marked text,
  the selection handles and edit menu, a selectable TextView's Copy, the return keys and the pads'
  Done bar, password dots, the number keyboard, the keyboard after Home and front; toggling
  `secureTextEntry` or swapping the field while it is first responder (the multi-line change) may
  drop the keyboard or clear the text; on gtk typing, Enter and the selection, the signal order
  inside `gtk_editable_insert_text`, focus leave on window deactivation. A keyboard shown with an
  empty `inputView` (a field with no `tap_keyboard`) was seen on iOS 27 (overhaul A6): no keyboard,
  the caret stays.
- Drags through the real touch path beyond `touch`'s one-finger list scroll: UITouch ids 0 and 1 for
  two fingers, `delaysContentTouches`, the scroll pan against a child
  ([ATL-142](bug-tracker.md#atl-142)).
- A press on a selector row on the phone and on gtk (M5b); the redraw `View.invalidateDrawable` asks
  for is graded nowhere (`run-widgets.sh` reads `getCurrent()`; display lists are dumped by
  `run-draw.sh` only).
- The three cases of `ATLOutsideWatch` (M6b3b): a tap on a second field closes an open drop-down, a
  touch-modal window without a dim catches the touches outside it, a NOT_TOUCHABLE one lets them
  through. `dbg ui activate` never passes through UIKit's hit test; `dbg ui tap` does.
- M6b3c's hand checks on the final build: the home indicator's swipe with `hideNavigation` and not
  `immersive`, the top edge's deferral with the status bar hidden (`Navigation.swift`,
  `prefersHomeIndicatorAutoHidden`; [DINE-7](general-todo.md#dine-7)). The keyboard's corners show
  the window's background (`frame.background` on the surface; screenshot 2026-11-22).
- M6b3c's experiment K2: whether UIKit scrolls an `ATLScrollView` to a first-responder field on its
  own (a scroll report with no touch after `insert` into `ResizeActivity`'s field); the stage's
  Status records neither the result nor an Open line, and `view.m` has no suppression.
- `Configuration`'s keyboard fields (late fix `76313409`): no phone
  scenario reads them (`atl-config` matches night lines; `atl-text` has no Back or Next
  step), so they stay unverified on iOS; the code is shared with headless, where `KeyboardConfigTest`
  covers it.
- Looks and facts no phone step reads (overhaul A5b, round 1): `nav: frame` prints neither the
  frame's color nor its light flag (M3-4: `atl-demo` could wait for `1a1b20`, `atl-nav` for B's
  `2196f3` light; both seen in screenshots 2026-11-22); a TextView's background color and padding on UILabel (M3-7: the agent's `ui ls`
  prints neither); the release of the surface when a window closes (M3-12: no line, no count); a
  field changed in kind while it edits, two changes before a delivery, a field's deferred first
  responder (M4c-11); the in-flight frame skip, a view that stops drawing clearing its layer and
  `replace_native`'s hand-over (M5b-5); the capped field's growth and its last lines on the phone
  (M5c-2: `atl-text` inserts into `name` and `calc` only); a Button with a background and padding
  keeping no UIKit insets (M6b3a-5: no `framed` step in `atl-controls`); VoiceOver staying in the topmost
  modal window (M6b3a-7: an absence check in `atl-dialog-content` if the agent's walk honours
  `accessibilityViewIsModal`); the uikit panel's room after a window resize (M6b3c-13).
- Code-path proof only on uikit (overhaul A4 to A8): the edit refusal (`editable`; the agent's
  `insertText:` skips the delegate), a refused toolkit focus under FOCUS_BLOCK_DESCENDANTS, touches
  of a disabled or transparent container's children, ATLScrollView's pan under its `hitTest:`
  (a hand scroll of `lists` or `scrolled`), the touch state per app with fingers on two apps, the
  draw layer of a view that `scrollTo`s itself.
- State: open; found 2026-11-20 (overhaul A5b, stage rows PreM4-M4a-1, M5b-4, M6b3b-2, M6b3c-3,
  M6b3c-15, late-5, from the old plans and the audit; round 1: M3-4, M3-7, M3-12, M4c-11, M5b-5,
  M5c-2, M6b3a-5, M6b3a-7, M6b3c-12, M6b3c-13).

### ATL-146

**META+TAB cluster navigation isn't wired.** `ATLInput.performFocusNavigation` has no cluster
branch (`FOCUS_FORWARD` between keyboard navigation clusters); M4a's plan listed it as a default
taken and it reached neither the stage's section nor an entry.
- Where: `dine-atl/src/api-impl/android/view/ATLInput.java` (`performFocusNavigation`).
- Found 2026-11-20 (overhaul A5b, stage row PreM4-M4a-4).

### ATL-155

**Text and widget behaviour no run fails without.** Claims of the text and widget stages that the
overhaul's area A6 read and left unproven; none shows a defect. Each names the run that would close
it.
- Typeface style: the dump prints no base style, so a `setTypeface(BOLD)` that stopped reaching a
  backend fails nothing (M3-8): a `textstyle:` line in `records/dump.c` and a bold TextView in
  `run-controls.sh`. Likewise the alignment (`ui_text_set_alignment`, M4b-6): a dump word and the
  `centered` TextView.
- `HorizontalScrollView` has no test of its scroll (PreM4-M4a-7; `linux smoke pan` drags one whose content fits):
  a ScrollTest case (clamp, echo).
- Inflated controls and fields (M4b-7, M4c-4, M5c-6, M5c-11): no test APK inflates a ToggleButton
  with `textOn`, a CheckBox with `checked`, an EditText with `inputType`, `maxLength`, `digits`,
  `imeOptions` or `singleLine`, a TextView with `maxLines`, `minLines` or `lines`; `android:height`
  isn't read; `setMinHeight` and `setHeight` have no `LineLimitTest` case.
- Keyboard follow (M4c-8, M4c-9, late-1 to late-4): no test moves focus off every EditText and reads
  the keyboard; a toolkit tap's request following Java's focus to a next field (`text tap`, then a
  `text action` Next); `atlToolkitFocus(false, false)` after a show.
- `setText` makes a different Editable and the old one stops reporting (M4c-10): `assertNotSame`
  across two `setText` calls and a watcher the old Editable's edits don't reach.
- gtk: a non-ASCII run before a styled run, to prove `atl_utf8_offset` in `text.c` against Paint's
  width (M6b1-11); a TextView with no `setTextSize` against its own Paint (bugs-ab-6, M5c-12);
  `getLineHeight` against `getFontMetricsInt` (M5c-12); the CSS providers a view frees when it
  replaces them (M6a-7).
- `getLayout` rebuilds when the typeface changes (bugs-ab-7): `testLayoutFollowsTypeface`.
  `getLayout`'s lines and `getLayout` under `setTextAlignment` come from Paint, not the toolkit's
  label (bugs-ab-3): accepted, as the plan says; no test compares them.
- Phone: ATL-13's uikit EditText and ATL-37's installer tile were never run (bugs-ab-8). On
  headless and uikit a compound drawable takes no space, so `getLineCount` counts for a narrower
  width than the label has ([ATL-86](bug-tracker.md#atl-86), bugs-ab-2).
- Code-path proof only (overhaul A6, A8): gtk's ellipsis, alignment, `editable` and
  `focus_on_click` on a GtkText, its report flush in `input_tap`; a theme without a text color on
  gtk and the phone; the text color after uikit's selectable swap; ellipsize in the measure key.
- State: open; found 2026-11-21 (overhaul A6, stage rows M3-8, PreM4-M4a-7, M4b-6, M4b-7, M4c-4,
  M4c-8 to M4c-10, M5c-6, M5c-11, M5c-12, M6a-7, M6b1-11, bugs-ab-2, -3, -6, -7, -8, late-1 to
  late-4).

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
  `viewtree_problem` does for the phone. The gtk dump also prints an EditText as `GtkText` without its
  text, an ImageView as `GtkPicture`, a ProgressBar as a fixed name, and skips a scroll node's
  subtree (`gtk/dump.c`, overhaul A8-7): a shape compare needs those first.
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
  library for the known test-line prefixes (`DEV_MARKERS` reads three names of the test hooks only).
- The drop-down's registry entry has no gtk run (M6b3b-4): a step that opens the drop-down through
  the agent.
- adjustPan's offset applying to touch (M6b3c-9: `run-keyboard.sh` sends `insets` and `dump` only:
  a `touch` at the field's panned y), and `getWindowVisibleDisplayFrame` leaving out the bars
  (M6b3c-10: log the rect after the 20-number `insets`; `run-keyboard.sh` reads the keyboard half).
- Two `-l` groups of one headless run, and the refusal of a package that already runs
  (`ATLInstaller`, `already runs in this process`) have no script (MA2-3): `-l A a.apk -l B b.apk`
  waiting for both apps' markers and exit 0 after the last one, and the same APK twice expecting
  exit 1.
- gtk's portal path for night (`settings_changed_cb`, `display.c`) is driven by nothing; the gtk
  framework run sets night through `ATLTestHooks.setNight` (M6b3c-13).
- A translated frame on gtk is read by nothing (A5a), and GTK's own placement of a popup neither
  (smoke-c-r2-8).
- gtk's hover exit after a delivery (A5b: code-path proof only, no feed makes GTK's pointer motion)
  and GtkScrolledWindow's own pan against a child's refusal (never read or run).
- gtk's keypad Enter reaching Java as 160 (M6a-9): `input-gtk` can feed `GDK_KEY_KP_Enter`.
- A `touch` line before headless's first shown layout is dropped (A5b): the scripts sync with a
  `dump` first.
- State: open; found 2026-11-21 (overhaul A5b round 1, stage rows M0-4, nav-9, PreM4-M4a-16,
  PreM4-M4a-18, M5a-4, M6b1-7, M6b3a-14, M6b3b-4, M6b3c-9, M6b3c-10, M6b3c-13, MA2-3);
  2026-11-21 (A8): gtk's ACTION_OUTSIDE runs in `input-gtk`; the gtk dump's gaps.

### ATL-164

**Window behaviour no test shows.** Claims of M2 to M6b3c whose checks need the phone or two running
apps, or that no suite reads; each is a line to turn into a check when a stage next touches it.
- Phone: the Cancel action of a cancelable list and its absence from an alert that isn't cancelable (the agent
  lists neither; `dialog.m` `build`); light mode of the menu, the toast capsule and the panels, a text toast over a plain alert,
  VoiceOver on the menu and on the toast's announcement, Dynamic Type and a long list (M6b3a-1, M6b3b-6);
  a panel's field panning, popups and drop-downs following their anchor in a panned or resized window,
  a popup's own soft input mode (M6b3a-4, M6b3b-3, M6b3c-1, M6b3c-5, M6b3c-6); non-sticky immersive that
  never clears (M6b3c-4, nav-5); `OnSystemUiVisibilityChangeListener` from the controller paths
  (M6b3c-8); pre-iOS-26 panel look (M6b3a-12).
- gtk: a click outside a plain alert and the alert's close request (M2-6, ATL-162), the host refusing the
  move to the back (M2-3), custom-content dialogs driven through the agent (M6b2-3).
- Checks to add: a targetSdk 19 fixture's
  `window: frame none` and the light status bar flag (M3-6), layout XML attributes of the View
  constructor (PreM4-M4a-6), `check` and `switch` control sizes in `run-controls.sh` (M4b-8), flower_finder's
  list scrolled by `dbg ui drag` (M6b1-2), a Fragment's permission result (M6b1-16),
  a focusable popup closed by an outside tap and a `ListPopupWindow` case (M6b3b-11), the drop-down not
  taking keys (M6b3b-12), `SystemUiTest` cases for `setDecorFitsSystemWindows(false)`,
  `FLAG_LAYOUT_NO_LIMITS`, cutout mode ALWAYS and show after hide (M6b3c-11, nav-8), the AOSP rows of
  `AlertDialog` against its Cursor and `ListAdapter` lists (M6b3a-8), a worker thread's `setProgress`
  (M6b3a-10), a thread in the root ThreadGroup (MA2-4).
- Pending lines with no owner until now: AppCompat and Material dialogs draw Android's own layouts
  (M6b3a-2); `setIcon`, `setIconAttribute` and ProgressDialog's secondary progress and number formats
  are ignored (M6b3a-9); `dbg ui activate` still reaches Android views under an open menu, which a
  finger's touch closes (M6b3b-7).
- Code-path proof only (overhaul A7, A8): a toast's frame on uikit and gtk, uikit's autorelease pools,
  `ATLDialog`'s actions after a free, gtk's panel colours, gtk's one placement per allocation.
- No test of Gravity FILL_HORIZONTAL on a dialog (M6b2-7); `atl-dialog-progress` doesn't compare the
  chrome and nothing reads a panel row's check mark (M6b3a-6).

### ATL-166

**uikit: present only the topmost plain alert.** UIKit stacks `UIAlertController`s in the order they
present, so `dialog.m` puts an alert under another by taking the upper one down and presenting it
again (`uppers_of`, the lift in `present`, `take_down`), which blinks. On the phone (2026-11-21,
windows APK `AlertsActivity`): "Show second" shows Second, First flashes on top for a moment, then
goes under it. "Later" (First rebuilt at 1.5 s and dismissed at 6 s, under Second) blinks Second
twice. The order is right in each case. Plan, chosen over drawing every alert ourselves (that would
mean rebuilding UIAlertController's accessibility, Dynamic Type, keys, iPad popover and system look):
- A plain alert with any window above it in the registry, another plain alert included, waits
  dismissed, as `covered` does for windows with a view. It presents again when the windows above
  it go.
- The stacking code goes. A lower alert's rebuild or close changes only the model, and a tap
  presents only the new top.
- Content dialogs and panels are views in the overlay, already in z-order: unchanged. gtk's plain
  alerts (separate windows, [ATL-162](bug-tracker.md#atl-162)) can take the same rule.
- Where: `dine-atl/src/backends/ui/uikit/dialog.m`, `view.m` (`records_roots_changed`).

### ATL-170

**Shared user ids aren't built.** Each package gets its own uid at install (`ATLInstaller.commit`;
the registry's `uid` column is UNIQUE) whatever its `android:sharedUserId`; `PackageInfo.sharedUserId`
reports the manifest's value (upstream's parser), `getPackagesForUid` lists one package and
`getUidForSharedUser` returns 1000. Android gives the packages that share the id, with one signer, one
uid. Recorded in `notes/decisions.md`.
- Where: `dine-atl/src/api-impl/android/atl/ATLInstaller.java`, `ATLRegistry.java` (schema,
  `rowsForUid`), `src/api-impl/android/content/pm/PackageManager.java`.

### ATL-173

**No run drives the gtk-only paths MA2a moved to the app's handle or Context:** D-Bus actions
(`src/main-executable/actions.c`), `intent_deserialize` (`src/api-impl-jni/gtk_util.c`), notifications
(`src/api-impl-jni/app/android_app_NotificationManager.c`), UnifiedPush (`Context.exportUnifiedPush`)
and MPRIS. A check: one D-Bus action and one notification on the gtk build, in `linux smoke` (hidden
display).
- Where: as named; `tools/py/dine/linux.py`.

### ATL-175

**The `native` slot.** `notes/atl-port.md` names it in the slot and build tables; `meson_options.txt`
has no option for it and `src/slots/` no header. libandroid and the bionic pieces, `native_window.c`
with them, build only for the desktop build.
- Wanted: the meson option, the `bionic` and `none` backends, the move of `native_window.h` into
  the slot.
- State: open; found 2026-11-14 (overhaul stage claims M0-2). DINE-12 covers iOS substitutes for an
  APK's own `.so` files only.

### ATL-176

**Measure typing lag under `-Xint`.** M4c left it unmeasured: each edit of a field runs Java's
filters, watchers and a snapshot back to the toolkit. Wanted: the time on the phone from an inserted
character to the `text after` line and to the field showing Java's text, in a plain and in a
filtered field of the widgets APK's TextActivity, for one character and for a held key.
- State: open; found 2026-11-22 (overhaul stage row M4c-12). Owner: none.
- Where: `dine-atl/src/backends/ui/uikit/view.m` (the field's edit path),
  `src/api-impl/android/widget/EditText.java`.

### ATL-179

**api-impl's signatures differ from AOSP 10's where only compiling against it shows it** (overhaul A6
and A7): `View.onDraw` is public (AOSP: protected), so a test activity compiled against `hax.jar`
must override it as public; `InputMethodManager` has none of the `SHOW_*` and `HIDE_*` flag
constants. An app built with the SDK runs unaffected (it inlines constants), one that reads them by
reflection doesn't. Wanted: a compare of api-impl's public and protected API against
`current-10.txt` for the classes we touched.

## DINE

### DINE-6

**Try JIT through StikDebug on the dev phone (iPhone 13, iOS 27.2).** Sideloaded, dev-signed
apps can get JIT through StikDebug from iOS 17.4; iOS 26.4 broke it for some users
(`notes/meta.md` "iOS constraints").

### DINE-7

**Navigation checks on the phone:**
- a vertical scroll in the middle of the screen never fires Home, and a swipe from the top-left
  corner opens Notification Center, not Home (`notes/nav-gestures.md` "By hand on the phone");
- a short swipe cancels, and a swipe over a span the app excluded reaches the app and fires
  nothing (the nav APK's B, right edge, 200-540 px from the window's top; the classifier alone is
  `tests/launcher/`'s test);
- immersive (the atl screen's "nav immersive"; its window reaches the screen's top and bottom,
  screenshot 2026-11-22; a DVT screenshot shows no home indicator on any screen, so the indicator
  is a hand check): the first swipe up only reveals and the second
  leaves; the same from the top with the status bar hidden (`.top` deferred);
- dismissing the apps list by swiping it down returns to the app it was opened from;
- the safe-area values Dine sends on the iPhone;
- the iOS 26+ full-content pop gesture.

The settings check waits for M8c.

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

### DINE-14

**Check the licences of the APKs dev builds bundle.** `tools/libexec/build-ios-dev.sh` puts six
third-party APKs from atl_test_apks into `Dine.app/dev`; that repo's README says "to our knowledge"
they allow redistribution, and no upstream licence was read (Gravity Defied's first).
- Until then dev builds go to nobody (`docs/first-run.md` §8). Release builds bundle none.
- Wanted: each APK's licence, next to its row there. DINE-5 covers api-impl.jar's notices only.

### DINE-15

**A launcher test.** No step opens Add App, adds an app or reads a launcher tile: `dbg smoke` waits
for `loaded N apps`, which an empty table passes. Wanted, once M8a's launcher lists the registry's
rows: a row added, shown again after a relaunch (`tests/launcher/`, which has the edge classifier's
test only), and a 40-character name in the launcher's four columns (truncation was seen only on
the atl screen's five, with names up to 15 characters).

### DINE-16

**Back and Home behave differently towards the launcher: Back leaves it as it was, Home resets it at
once.** The user, 2026-11-22: "distinguish back and home actions in their behaviour. Back from just
started app does not reset the launcher state and just closes (or in the future minimizes/stops)
the app. Home resets the launcher - e.g. scrolled to top, main launcher screen RIGHT AWAY. The
secret is to reset the launcher view even when you just start the app closing gesture (home). If
you started the gesture and decided to not continue - this is fine, yes it will be already reset
and back will send you to the main launcher screen in reset state, no contradiction or bugs -
android phones do this, at least samsungs".
- Back out of an app (Back on the screen it started with): the app closes, later minimizes or
  stops, and the launcher shows as the user left it, with its pushed screen and scroll position.
- Home: the launcher resets (its main screen, scrolled to the top) as soon as the Home gesture
  begins, before it commits. A cancelled gesture keeps the app and the reset is not undone: a later
  Back lands on the reset launcher, as meant.
- Today: Back on the task root resets as Home does (`taskMoved` calls `dismissToRoot("back")`); an
  app's exit leaves the launcher as it was (`exited`); Home resets only after the container's
  dismissal has ended and only the path, not the scroll (`dismissToRoot`). That late reset stays
  until this is built (the user: "leave A for now").
- Where: `apps/Dine/Sources/Dine/Navigation.swift`; `EdgeGestures.swift` (a gesture knows it is
  Home when the pan begins, once its axis picked the binding); `LauncherView.swift` (nothing can
  scroll it to the top). The Home accessibility action has no gesture: it resets when it runs.
- Trap: UIKit drops a path change made during the dismissal of a container with an alert over it,
  and the path then claims a root that doesn't show. Unverified: whether it takes one while the
  container covers the launcher and nothing moves, which the early reset needs, with an alert, a
  menu or the keyboard up too. Smoke `atl-dialog-late` and `atl-two-apps` show the refusal.
- Changes with it: `notes/nav-gestures.md` "Actions" ("Back on the root activity is Home"), smoke
  `atl-nav`'s "back on the task root" step (waits for `nav: launcher root`, and the next step's
  "Recent apps" works only at the launcher's root).

## TOOL

### TOOL-5

**gtk `ui back` reports only whether ATL's main loop was up,** not what Back did: it is
`atl_nav_back`'s result.

### TOOL-6

**An ATL test hook `ATL_SCREENSHOT=<file>` that saves a window to PNG after its first frame,** and
optionally its GTK render node as text: a diffable golden of what gsk draws, like the headless
display-list golden. Its timing is exact, and it needs no compositor screenshot (`grim` on the
hidden sway does that part today), but GTK still needs a display. `gtk4-rendernode-tool render`
(installed with gtk4) turns a saved render node into a PNG. ATL already renders GTK
drawings to images (the view readback test hook `gfx_test_render_view`) and encodes PNGs
(`dine-atl/src/backends/gfx/gsk/bitmap.c`); the gtk test hooks have a
window-ready point (`src/main-executable/main.c`, `src/backends/ui/gtk/dump.c`).

### TOOL-7

**Runtime-suite tests that fail for want of a tool:** `952-invoke-custom` and
`979-const-method-handle` need ASM 6, `701-easy-div-rem` has a Python 2 generator, `130-hprof`
needs `hprof-conv`, `141-class-unload` and `150-loadlibrary` need upstream's native test lib
`libarttest` (which 100 skipped tests need too). `071-dexfile-map-clean`, `677-fsi` and
`707-checker-invalid-profile` need dex2oat, which dine-art never runs: they stay expected
failures (707's `check` also calls `./default-check`, which the harness doesn't provide). Reasons per test: `dine-art/tests/runtime/expectations/linux-x86_64.json`.

### TOOL-9

**`tools/dine dbg ui ls` walks the key window only.** The walk misses a keyboard's
`inputAccessoryView` (the pads' round return button), which sits in the keyboard's window: `ls`
doesn't list it and a screenshot may not show it (`notes/dev-reference.md` "UI agent").
- Where: uidrive's walk (`../dine-uidrive`, `src/uidrive/agent/ax.mm`).

### TOOL-14

**The runtime suite on the phone is seven authored tests behind buttons.** The phone runner of
`notes/atl-port.md` "Test strategy" (a test mode in Dine, tests pushed and pulled, batches in one
VM) has no stage. Until it exists the AOSP run-tests never run on arm64, and of the authored ones
`dine-0005-embedder-tag`, `dine-0007-native-libs` (their JNI code isn't linked into
`native/dev/runtimetests`) and `dine-0009-no-dex2oat` (a `run` script) stay Linux-only: the Apple
rule that a library outside the embedder's symbol lists doesn't load has no test.

### TOOL-15

**`dbg ui` reaches only the tiles of the atl screen that are on the screen.** The grid is lazy
(`LazyVGrid`) and `dbg ui` lists only built elements with a frame on the screen, so a smoke step
can't activate a tile further down (seen 2026-11-21, overhaul A7: with a 29th tile before `config`
the `atl-keyboard-dialog` step found no `keyboard dialog`). Workaround: five columns, so the iPhone
13 shows the 36 tiles at once (seen 2026-11-22), with the tiles the scenarios use first in
`AtlView.swift`.
- Fix: a smoke `drag` step that scrolls the grid to the tile (untried: the grid fits the screen
  today), or a scroll action in the agent. A grid that builds every tile isn't enough: the walk
  skips what is off the screen.
- Where: `apps/Dine/Sources/Dine/Dev/AtlView.swift`, `tools/py/dine/dbg/smoke.py`.

### TOOL-16

**Test gaps routed to overhaul A9 and left there.** Each passes today with the rule it would guard
broken (found 2026-11-14 to 2026-11-21: the instruments audit, the A9 review, the stage claims).
- The package suite's harness: a JUnit test no longer discovered lowers the row count and the run stays
  green; unused scripted answers and missing `dialog:` lines aren't graded; refusals are graded on the
  exit status alone (`cli:provider_conflict` takes any non-zero); the fixtures dir is never emptied;
  `test_package.py` covers `grade_scenario` only; no `--gtk` mode for the gtk host's `--uninstall` and
  `--allow-fake-signature`.
- Installs: no split APK (CLI or session); no session written at an offset, with no file, with an
  invalid APK or abandoned; no second operation in one driver process; no session install of `gms` over
  its generated row; no reinstall that grants the fake signature; no equal-size fixtures that differ past
  one 64 KiB compare chunk; no Cancel to an intent install or uninstall, no dismissed dialog, no refused
  uninstall of a preinstalled package; `cli:path_run` doesn't check that the app started or which
  version ran.
- The registry: no committed blob of the current `PackageCodec` format; the codec's round trip has no
  `<instrumentation>`, `<uses-library>` or `<uses-configuration>`; `cli:reparse` passes any blob longer
  than a byte and no later process decodes it; no generated row is made stale;
  `RegistryTest#testStaleRows`' last assertion can only see null; no update changes a package's
  components, so no check reads the index tables after one.
- `PackageContextTest` loads no class or resource through a package context.
- No run reaches a commit that throws: `ATLInstaller.end`'s `landed` reads for an install and an
  uninstall are code-path proof only (no failure can be planted there without a product hook).
- `AppStateTest` (`--one-vm`) checks receivers, preferences and installer sessions per app; jobs and
  providers aren't (an authority can't be shared; graphics has no job service).
- Multidex, per-ABI native libraries ([ATL-106](#atl-106)) and broken zips have no fixture.
- The framework suites pin targetSdkVersion 27: api-impl's branches for 28 and up never run.
- The draw golden: `drawLines` runs with offset 0 and the whole array only, and nothing calls `drawOval`
  (`DrawActivity`).
- Code-path proof only (overhaul A9): the session's sync, the two-process races of an uninstall's
  put-back against an install, a second `Session.commit`.
- Where: `tests/harness/package.py`, `tests/harness/test_package.py`, `dine-atl/tests/package/`,
  `dine-atl/tests/framework/*/AndroidManifest.xml`, `dine-atl/tests/headless/` (DrawActivity).

### TOOL-17

**Test gaps of builds, tools and test mode (overhaul A10, from the stage claims).**
- Nothing fails when `<depend closure="true">` is dropped from `dine-atl/src/api-impl/build.xml`:
  the tracked generated headers turn dirty only after a from-scratch build (M5a-10). Wanted: a
  check that they are clean after a build.
- Nothing compares `src/api-impl/meson.build`'s list with the Java files in the tree: a file left
  out compiles and an edit to it rebuilds nothing (M6b3b-15).
- An expected failure of `test apps` keeps its reason when the app stops earlier
  (`tests/harness/expect.py` compares statuses only) (M6a-4).
- gtk: no check reads the GApplication id of `--package`, and gtk's `--install` and `--uninstall`
  never run (MA0-MA1-14).
- The parts of `tools/dine ios` that need no phone have no test: `sync-ios-icons.sh` with a
  missing icon, `cmd_lldb`'s arguments, `tunnel_status`'s text (app-tools-17).
- `smoke.run` (`tools/py/dine/dbg/smoke.py`): the relaunch rule, a declined activation, the
  `--network` skip and the still-alive check have no unit test (app-tools-8).
- gtk's debug target: no check attaches lldb, sets a breakpoint and reads an expression
  (app-tools-3).
- Test mode with several apps: no run has two apps answered from `ATL_DIALOG_ANSWERS` (each main
  thread reads the whole list with its own cursor), and test-runner's
  `SingleLaunchActivityTestCase` keeps VM-wide statics in a jar every app shares (MA2-10).
- Code-path proof only (overhaul A10): Home before an app's start on uikit, `LldbHost.kill` against
  a real lldb, `stop-server --kill-app` on the phone, gtk `shutdown`'s failed kill; removing the
  dismissal's IME zero alone fails nothing (the keyboard's hide notification sends it too).

### TOOL-18

**Test gaps of the instruments themselves (overhaul A0's audit, left open by A0 to A10).** None shows
a product defect; the audit's id is in brackets.
- Runtime suite: the log filter drops every line below FATAL, so a new runtime error line fails
  nothing (`corpus.toml` `log_tags`; its reason predates the runtime without boot image)
  (grading-r2-2).
- Runtime suite: two runs share `out/tests/runtime/build/` with no lock, and `ios run`'s payload
  build is one of them (grading-r1-7); a test that expects a non-zero exit can't pass, and the 14
  custom-run-script tests never run (grading-r3-1).
- Apps suite: nothing pins the third-party APKs' content, only their file names (framework-r2-6).
- `linux smoke`: `_script` and `_gd`'s verdicts and the scripts' judges have no failing control in
  `test unit` (smoke-a-r2-7); the gtk checks inherit the desktop's session bus (all but
  `windows-gtk`'s keyboard-dialog launch), portal night and GTK settings (critic 3); it and `dbg
  smoke` stop at the first failure, with no option to go on (critic 10); the looper APK never runs on glib, whose worker-thread poll only `loop_test`'s stubs
  stand in for (smoke-a-r2-6).
- `dbg smoke`: a step's `ok` lines pass in any order (critic 4); `atl-demo` and `art` don't check
  that the app still runs afterwards (phone-r2-5); Java's `nav: I size` is compared with nothing,
  only the surface with Dine's size (phone-r3-5); value lines beside the markers are unread
  (`run hello`'s `map size 2`, `views createFromPath missing`, the art probe's) (phone-r2-1); a run
  leaves no scenario, pattern or verdict in the session log (phone-r3-7).
- gtk's debug target: the unit tests stub ATL and the agent, so `dbg ui` against a real ATL
  (`insert`, `back`) runs in no check; `linux smoke input-gtk` and `text-gtk` drive the agent
  directly (phone-r2-3, app-tools-4).
- CLI: no test runs `cli.main` for `test` or `linux`, and it turns a handler's non-int result into
  exit 0 (dispatch-r1-4); `test_server.py` takes 0.5 s for "the server is busy" (phone-r1-14).
- No Linux build compiles the side without `test_hooks`; only the iOS release build does
  (critic 5).
- `DispatchCostTest#testMoveCost` asserts nothing (critic 7).
- gtk checks: only `run-draw.sh` fails on a GLib critical, and only a Gtk or Gsk one
  (smoke-a-r2-2).
- Headless scripts: `run-windows.sh` skips a stray "menu item" or "popup row" line (smoke-c-r1-4); no
  run shows a light panel alert's show line (smoke-b-r2-4); the dialog chrome's dp at another density
  has no check (smoke-b-r3-2).
- A0's fixes that no run proved: children ended on a signal, test APKs renamed into place, markers
  at the deadline, the abbreviated-flag refusal, the gd check without output (ledger A0).

### TOOL-22

**Recheck why iOS links use xtool's `ld64.lld`.** The toolchain file, `env.sh`,
`notes/dev-reference.md` "iOS builds" and `docs/first-run.md` §9 say the system `ld64.lld` rejects
the SDK's `.tbd` stubs. The system LLD 23.1.4 linked uidrive's agent dylib against UIKit and
Foundation without error, with the same load commands; executables weren't tried.
- Found 2026-11-25 (the toolchain's shared-library flag, left out in a test link).
- Where: `tools/cmake/ios.toolchain.cmake`, `env.sh`, `notes/dev-reference.md`, `docs/first-run.md`.
- Then: link Dine and artbridge with the system LLD; restate the reason, or drop the `-B` flags.

## Done

### TOOL-25

**Pin uidrive to its git source before Dine's `main` goes up.** 2026-11-25, dine
`dine: pin uidrive`, at dine-uidrive a25614a.

### TOOL-8

**Real touches and keys for phone UI checks without XCUITest: uidrive (`../dine-uidrive`),
injected into dev builds.** 2026-11-25, dine 0efd5d5, 4558682, 59bd868; dine-uidrive
af1c3de..35b68ea.

### TOOL-4

**Return can't be pressed in a field** (`dbg ui press return`). 2026-11-25, dine 154d4de,
dine-uidrive 35b68ea.

### ATL-147

**`dbg smoke atl-text` reads no field's own text.** 2026-11-21, overhaul A6: the UI agent lists a
field's text as its `accessibilityValue`, `atl-text` asserts it, and `text-gtk` does for gtk.

### ATL-18

**A CTFont cache on iOS.** 2026-11-01, dine-atl 4fd8005c.

### ATL-23

**BitmapShader and ComposeShader didn't shade.** 2026-11-03, M6b1, dine-atl cff73b6f.

### DINE-11

**An app's screen brightness on iOS.** 2026-11-04, a no-op: no public API withdraws an app's
request (findings: `~/.claude/plans/dine-brightness-restore.md`); dine-atl 73077776.
