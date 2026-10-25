# ATL port: backends, milestones, tests

The plan for turning dine-atl (our ATL fork) into a framework that runs on any toolkit and OS
through pluggable backends. iOS (inside Dine) is the first new target. It defers to
`notes/meta.md` for the why and the iOS constraints, to `notes/art-findings.md` for the runtime,
and to `tests/README.md` for the map of test suites.

## Stages

Every stage in order, with its state. A stage's section holds what was built (its Status block);
its row here changes when that block does.

| Stage | Scope | State |
|---|---|---|
| [M0](#m0-slots-on-linux) | slots on Linux, headless `demo_app.apk` | done |
| [M1](#m1-headless-on-the-iphone) | headless on the iPhone | done |
| [M2](#m2-a-dialog) | a dialog, Back and Home | done |
| [M3](#m3-demo_appapk-on-screen) | `demo_app.apk` on screen | done |
| [Pre-M4 batch](#pre-m4-batch-2026-10-21) | natives that layouts reach before input | done |
| [M4a](#m4a-touch-scrolling-and-keys) | touch, scrolling and keys | done |
| [M4b](#m4b-controls) | controls | done |
| [M4c](#m4c-text-input) | text input | done |
| [M5a](#m5a-renderer-and-display-list) | renderer choice, display list | done |
| [M5b](#m5b-drawing-on-the-phone) | drawing on the phone | done |
| [M5c](#m5c-text) | text | next |
| [M5d](#m5d-paths-nine-patch-layers-gravity-defied) | paths, nine-patch, layers; Gravity Defied | planned |
| [M6a](#m6a-triage-and-fixes) | triage and fixes | planned |
| [M6b](#m6b-breadth) | breadth | planned |
| [M6c](#m6c-search-ahead-of-m7) | search ahead of M7 | planned |
| [M7](#m7-services) | services, items in `notes/service-impl.md` | planned |
| [M8a](#m8a-apk-import-and-launch) | APK import and launch | planned |
| [M8b](#m8b-ios-lifecycle) | iOS lifecycle | planned |
| [M8c](#m8c-navigation-settings-store) | navigation settings store | planned |
| [M8d](#m8d-background-probes) | background probes | planned |
| [M8e](#m8e-several-apps) | several apps | planned |
| [M9](#m9-heavy) | Compose, GL, WebView | planned |

## Decisions

- api-impl stays the one Java implementation of `android.*`, shared by every build.
- Everything that touches a UI toolkit, an OS service or a native-code loader sits behind a
  backend slot. Code outside the backends, Java and C alike, depends only on JNI, ART/libcore,
  androidfw, sqlite, graphene and libc: no GTK, no glib. graphene is built without GObject (a
  meson wrap) everywhere but the desktop build, which links the system one gtk4 uses.
- Slots are designed for any number of implementations. Each slot has at least three planned:
  today's Linux desktop one, a headless one, and the iOS one.
- The iOS build contains no glib.
- The main-thread loop sits behind the loop slot; only its `glib` backend uses glib.
- The Linux GTK build keeps building and passing at every step (`tools/dine linux build`, the
  Gravity Defied smoke test, `tools/dine test runtime`).
- No pristine copy of ATL in the tree. dine-atl's `master` branch tracks upstream unchanged;
  `git diff master...dine` shows our delta.
- The first visible results come step by step: headless boot, then a dialog, then a real APK on
  screen.

**Consequence:** extracting a subsystem rewrites upstream files, and the fork has drifted too far
to merge. Upstream isn't merged any more: its commits are read and the wanted ones reimplemented
by hand.

## ATL as it is

Measured on dine-atl's C sources (99 files, 17.9k lines), by the worst dependency in each file:

| Kind | Files | Lines |
|---|---|---|
| portable: JNI, sqlite, libc | 19 | 3,757 |
| glib only | 10 | 1,495 |
| GTK, GDK, GSK, Pango | 45 | 6,508 |
| Linux desktop: Wayland, D-Bus portals, ALSA, udev, libsecret, webkitgtk, EGL | 21 | 4,372 |
| bionic linker and the app's own `.so` files | 4 | 1,779 |

- **Backend layer:** none. `util.h` includes `gtk/gtk.h`, and 60 C files include
  `util.h`. `native_window.h` pulls in EGL, X11 and GTK.
- **Views:** every View has a GTK widget pair. GTK drives measure and allocation and calls into
  Java for `measure` and layout; leaf widgets (TextView is a GtkLabel, Button a GtkButton,
  EditText a GtkText, ScrollView a GtkScrolledWindow; 16 widget files) are measured by
  GTK itself. Whether a View draws through Canvas is decided per class, by reflection: only
  classes that override `onDraw`, `draw` or `dispatchDraw` get a Canvas. Layout containers are
  AOSP's Java. Upstream supports widgets written fully in Java and suggests copying AOSP's.
- **Graphics:** Canvas operations go to GtkSnapshot, Path to GskPath, Matrix to graphene, Bitmap
  to GdkTexture, image decoding to GdkPixbuf, text to Pango. Fidelity gaps are in the shared
  Java: `Paint.measureText` is a width estimate (0.6 × text size per char), shaders are stored but
  never drawn, `saveLayer` is a plain `save`, Typeface is a stub.
- **Dialogs:** `Dialog` is a toolkit window holding a Java decor view. `AlertDialog` creates
  three Java `Button`s and hands them, with a label and a list, to the toolkit window.
  `Builder.setView` does nothing.
- **Main loop:** the Android main Looper runs from a GSource on the default glib context; worker
  threads use the NDK's ALooper (libutils' epoll Looper). glib idle, timeout and frame-clock
  callbacks schedule work in 11 files.
- **Resources:** parsed by dine-art's androidfw through a C wrapper. Already toolkit-free.
- **Startup:** the GTK executable creates the VM with `api-impl.jar` and `framework-res.apk` on
  the classpath, loads `libtranslation_layer_main` by name (it has no `JNI_OnLoad`), builds a
  window holding a stack of activities, then runs the Application and Activity lifecycle.
- **What `demo_app.apk` needs:** a Linux run with `-verbose:jni` reaches `onResume` through 50
  ATL natives: 26 for resources (AssetManager, XmlBlock), 3 for the loop and clock, 2 for log and
  data dir, 1 for display config, and 18 for UI (View 7, ViewGroup 1, Window 3, TextView 4,
  Drawable 1, Paint 2).
- **GTK in the Java code:** most of it is opaque `long` handles, which any backend can fill. The
  rest carries GTK meaning and must become neutral (see [Java](#java)).

## Backend slots

A slot is a subsystem boundary with a C interface. A backend is one implementation of a slot.
A build selects one backend per slot with a meson option.

| Slot | Owns | Backends |
|---|---|---|
| `host` | process entry, VM creation, classpath, data dirs, launching an app and an activity, the container that holds activity windows | `gtk` (today's executable), `cli` (plain C entry, no glib), `embedded` (a library API Dine calls) |
| `loop` | the Android main thread's integration with the platform loop, worker-thread loops, delayed and cross-thread posts to the main thread | `glib`, `cfrunloop`, `poll` |
| `ui` | windows (Activity, Dialog, PopupWindow, WindowManager views), view nodes (children, frame, visibility, background, padding), toolkit widgets, focus, IME, touch and key input | `gtk`, `uikit`, `headless` |
| `gfx` | Canvas, Paint, Path, Bitmap, image decoding, text measurement and layout, fonts, NinePatch, RenderNode | `gsk` (GSK, Pango, GdkPixbuf), `coregraphics` (CoreGraphics, CoreText, ImageIO), `record` (a display list), later possibly `skia` |
| `services` | one sub-slot per service, listed in `notes/service-impl.md` | `desktop-linux`, `ios`, `none`, selectable per service |
| `native` | loading the app's own `.so` files: bionic linker, libandroid (NDK), EGL and Vulkan surface shims | `bionic`, `none` |

| Build | host | loop | ui | gfx | services | native |
|---|---|---|---|---|---|---|
| Linux desktop | `gtk` | `glib` | `gtk` | `gsk` | `desktop-linux` | `bionic` |
| Linux headless (tests) | `cli` | `poll` | `headless` | `record` | `none` | `none` |
| iOS | `embedded` | `cfrunloop` | `uikit` | `coregraphics` | `ios` | `none` |

A gfx backend draws into what the ui backend hands it: `gsk` goes with `gtk` and `coregraphics`
with `uikit`, which provides the CGContext; `record` goes with `headless`. meson rejects other
combinations.

### Interface rules

- **Downcalls:** shared code calls slot functions with C types only (rects, colors, paint
  state, opaque handles). Backends contain no JNI.
- **Upcalls:** backends report back through one shared C API implemented once with JNI: measure
  and layout requests, draw requests, touch and key events, dialog results, loop dispatch.
- **Handles:** each slot defines its opaque types (view node, window, canvas, path, bitmap);
  Java stores them as `long`.
- **Shared JNI glue:** each native has one implementation in shared code that converts Java
  arguments and calls the slot. Backends never see `JNIEnv`.
- **No toolkit object assumed per View:** `gtk` and `uikit` create one per view node; `headless`
  and a future single-surface backend keep records and request pixels through the draw upcall.
- **Threads:** ui and gfx calls happen on the Android main thread; uikit's layers replay
  coregraphics' finished display lists on UIKit's side, and list and bitmap refs drop on any
  thread. `cfrunloop` binds to the run
  loop of the thread that prepares it. On iOS that is an 8 MiB pthread with its own run loop, not
  UIKit's main thread (1008 KiB stack with RLIMIT_STACK fixed at that, so ATL's Linux setrlimit
  and 6 MiB pregrow can't grow it, and whether iOS honours LC_MAIN `-stack_size` is unverified;
  secondary threads get 524 KiB; VM creation and `-Xint` Java would stall Dine's UI). `uikit`
  queues UIKit changes on it and sends them to UIKit's thread in one batch per layout or draw
  pass; text measurement waits for UIKit's thread (`dispatch_sync`), so UIKit's thread never waits
  for the Android one. Nothing on the Android thread drains an autorelease pool, so each uikit entry point
  that makes ObjC objects there wraps itself in `@autoreleasepool`. Bitmap canvases work on any
  thread.
- **Generic logic moves to shared code** when its slot is extracted: the per-class draw-mode
  decision, MotionEvent and KeyEvent construction, touch dispatch and intercept order,
  LayoutParams interpretation, dialog content.
- **Binding is at link time:** one backend per slot per build, no runtime dispatch table. No
  build needs two backends of one slot in one process.

### How the interface grows

A slot function exists only when a milestone extracts it, and it lands with an implementation in
every backend the current builds select: `gtk` and `headless` from M0, `uikit` and
`coregraphics` in the milestone that needs them. Natives not yet extracted stay in their GTK
files as gtk-backend code in legacy form, built only with `ui=gtk`. In other builds a call to one
throws `UnsatisfiedLinkError`, and that is how the next extraction list is found.

Shared code builds as its own meson static library whose dependencies exclude GTK and glib, so a
stray include fails the build.

### Loop slot

Shared MessageQueue natives call the loop slot: whether this is the main thread, schedule the
main thread's next dispatch (now, after a timeout, or never), wake it from any thread, and the
same three operations on a worker thread's loop.

- `glib`: the GSource for the main thread; workers keep ALooper, because app native code under
  `native=bionic` can attach file descriptors to a Java thread's ALooper.
- `cfrunloop`: a run-loop source on the main run loop calls `Looper.loop()`, a run-loop timer
  carries the timeout, and a wake signals the source and wakes the loop. Worker threads run their
  own CFRunLoop with a timeout.
- `poll`: a mutex and condition variable per loop, for headless builds.

glib idle and timeout callbacks outside the gtk backend become loop-slot posts to the main
thread.

### Shared C without glib

- `util.h` and `util.c` split: JNI helpers, logging and NIO buffer helpers stay shared; the
  `atl_safe_gtk_*` helpers go to the gtk backend; intent serialization to GVariant goes to the
  `desktop-linux` services (it exists for D-Bus and desktop notifications).
- `native_window.h` moves to the `native` slot.
- AssetManager: its few glib string helpers become libc.
- MemoryFile: GHashTable becomes a small map; `memfd_create` becomes a platform helper.
- SystemClock: `CLOCK_BOOTTIME` has no Darwin equivalent under that name; a platform helper picks
  the clock.
- ContentResolver's content-type lookup goes to the MIME service; ConnectivityManager's network
  monitor to the connectivity service.
- The GInputStream wrapper exists for GdkPixbuf decoding and goes to `gsk`.
- Matrix uses graphene (`src/shared/android_graphics_Matrix.c`; decided 2026-10-21); it
  cross-builds for iOS with NEON and no glib.

### Java

Opaque `long` handles stay. Names and values with GTK meaning become neutral when their subsystem
is extracted:

| GTK-ism in api-impl | Neutral form | When |
|---|---|---|
| `GskCanvas` as the Canvas implementation class | `android.atl.ATLCanvas` over a `struct gfx_canvas` (done) | M5a |
| `Window.remove_gtk_background` | `Window.clear_background`, calling `ui_window_clear_background` (done) | M1 |
| `GDK_MEMORY_*` pixel formats in Bitmap | Android `Bitmap.Config` values; the backend maps them (done) | M5b |
| `RenderNode.getGskNode` and its GskRenderNode natives | a node over a gfx display list | M9 |
| CSS class names set from TextView (bold, italic) | typeface style passed to the ui slot (done) | M3 |
| CSS classes for `setAllCaps`, `setTextAlignment`, Button's `ATL-no-border` | all caps in Java (AOSP's transformation), `ui_text_set_alignment`, the border from the view's background (done) | M4b |
| `Paint.measureText` width estimate | text measurement from the gfx slot | M5c |
| AlertDialog's three toolkit-bound Buttons | dialog content as data (see M2) | M2 |
| `GTK_FILE_CHOOSER_ACTION_*` ints in Activity | file-picker service request kinds | M7 (file picker) |
| Toast sent as a desktop notification | a ui-slot toast | M6b |
| `"xdgportal"` location provider name | provider name from the location service | M7 (location) |
| external intents sent over D-Bus from ContextImpl | the open-links-and-files service | M7 (open links and files) |

## Build

- dine-atl stays a meson project, with one option per slot. The iOS build uses a meson cross file
  with the same clang, SDK and linker flags as `tools/cmake/ios.toolchain.cmake`.
- The Java artifacts (`api-impl.jar`, `framework-res.apk`, the gstub and ghax jars) come from the
  Linux build and go into the app bundle.
- iOS output: static archives in `out/ios/lib`, Java artifacts in `out/ios/share/atl`, built by a
  `tools/dine ios build-atl` step (like `ios build-art`). The test hooks (`ATL_DIALOG_ANSWERS`,
  `ATL_DUMP_VIEWTREE`, `ATL_DUMP_DISPLAYLIST`: `src/shared/test_hooks.c`, the ui backends' `dump.c`) build with meson
  `test_hooks`, default on; `DINE_RELEASE=1 tools/dine ios build-atl` turns it off, and the test
  APKs go to `out/tests/apks`, which only dev builds of Dine bundle.
- Dine `-force_load`s the archives, and the dev link's `-rdynamic` keeps their `Java_*` symbols
  through dead stripping; the release link has no `-rdynamic` ([M8a](#m8a-apk-import-and-launch)).
  The embedded host provides `JNI_OnLoad_translation_layer_main` so ART accepts the statically
  linked library.
- dine-art builds androidfw for iOS with its dependencies: libutils, libcutils, incfs-utils.
  libutils' epoll Looper is not needed on iOS (`native=none`) and is left out there.

## Milestones

Every milestone also requires: the gtk build passes the Gravity Defied smoke test, and the
runtime suite shows no regressions.

From M5 on, a stage has one target graded on headless, plus a check on the phone where the target
shows there. A milestone too big for that splits into lettered stages (M4a, M5a) before its work
starts; a bare number means the whole milestone. M7's stages are the numbered items of
`notes/service-impl.md`.

A triage stage (M6a, M6c) is graded by its table, a design choice (M5a's renderer, M8e's design)
by the decision and its reason written into its section. The Dine-only stages M8b to M8d have no
headless target yet: how they are graded is settled when the first one starts, and their sections
list the checks known so far.

### M0: slots on Linux

- Slot headers, meson options and the shared static library without GTK or glib.
- Extract what `demo_app.apk` needs: the `host`, `loop`, `ui` and `gfx` functions behind its 18
  UI natives and the loop and display-config natives, with `gtk` and `headless` backends (the
  resources natives are already shared).
- `headless` ui keeps view-node records with fixed text metrics and can dump the view tree;
  `record` gfx keeps a display list.
- **Done when:** the headless build runs `demo_app.apk` to `onResume` on Linux with no display
  and dumps a view tree of a LinearLayout with two TextViews.

**Status: done** (committed with M1). `dine-atl/tests/headless/run-demo.sh` passes: the headless
build reaches `onResume` through the same 50 natives as GTK and dumps decor FrameLayout →
LinearLayout → two TextViews. As built:
- Tree: `src/slots/{loop,ui,gfx}.h`; `src/shared/` (startup phases, activity lifecycle, upcalls,
  JNI glue for partly extracted classes); `src/backends/<slot>/<name>/`. Natives not behind a
  slot stay in `src/api-impl-jni/` and build only with ui=gtk; whole-file portable sources stay
  there and go into the `atl_shared` static library.
- The app surface (toplevel window and activity stack) belongs to `ui`, not `host`:
  `ui_window_*`. `host` is the executable plus the shared start phases it calls; since M2 it also
  implements `src/slots/host.h` (task moves, keep screen on).
- Layout in headless mirrors GTK: the root is measured and laid out at the window size, each
  `ui_view_new` node upcalls `View.layoutInternal` for its children; Java is unchanged.
- `ATL_DUMP_VIEWTREE=1` prints the view tree when the app window first lays out, in gtk and in
  the records backends (gtk from real allocations), with `test_hooks`. Dine's dev builds set it
  (artbridge's `dev.cpp`).
- `record` holds plain paint and drawable records; the display list comes with the first
  extracted draw native (nothing on demo_app's path draws).
- gtk+record is rejected for now: legacy GTK draw code is GSK-bound.
- The GVariant intent helpers sit in legacy `gtk_util.c` until M7's open-links-and-files item moves
  them into `desktop-linux`.
- dine-art's `libandroidfw` links libpng itself; the GTK build only got it through gdk-pixbuf.

### M1: headless on the iPhone

Prerequisites in dine-art:
- Native calls with stack arguments use Apple's packed layout (`notes/art-findings.md` §4),
  guarded by the `dine-0002-jni-args` runtime test on Linux and on the phone. 7 ATL natives
  exceed 8 integer-class arguments; `View.native_setLayoutParams` (10, counting `JNIEnv*` and
  `this`) is on `demo_app.apk`'s path.
- `System.loadLibrary` resolves libraries linked into the app, which `translation_layer_main`
  needs.
- androidfw and its dependencies for iOS.

Work:
- `tools/dine ios build-atl`; the `embedded` host in a Dine native library, like `artbridge`: VM
  with the ATL classpath, the APK from the bundle, a data dir in the app container.
- `cfrunloop` loop on the Android main thread.
- A Dine screen that runs `demo_app.apk` headless.
- Probes: main-thread stack depth, time from tap to `onResume`.

**Done when:** `dbg wait --log` sees `onResume` from the phone, and the headless view-tree dump
matches the Linux one.

**Status: done.** On the iPhone 13, Dine's **atl** → **run demo** reaches `onResume`
and dumps the same five `viewtree:` lines as `dine-atl/tests/headless/demo_app.viewtree`; the art
screen's runs then work on the VM ATL created. As built:
- dine-art's iOS build adds libandroidfw, libutils and libcutils: without aapt2's PNG code (no
  libpng in the SDK) and libutils' epoll `Looper`, libcutils cut to `native_handle` and `trace`
  (all androidfw and libutils use). `androidfw_c_api.h` and `asset_manager.h` get `off64_t` (and
  C `char16_t`) on Apple. `install-ios` installs `androidfw/androidfw_c_api.h`.
- dine-atl builds for iOS as a meson cross build (`tools/dine ios build-atl`; the cross file comes
  from `tools/libexec/build-ios-atl.sh` and puts `out/ios/include` on the include path). Java
  builds only in native builds; the iOS build uses the Linux build's jars and JNI headers.
- `host=embedded` is a static archive with `JNI_OnLoad_translation_layer_main` and a small API
  (`atl_embedded.h`): ATL's VM options for the embedder's `JNI_CreateJavaVM`, then
  `atl_embedded_main` on the thread that becomes the Android main thread. The start phases split
  for it: `atl_set_app`, `atl_vm_options`, `atl_vm_init`; the Linux hosts keep `atl_prepare` and
  `atl_vm_start`.
- In Dine, artbridge stays the one VM owner (states none, creating, ready, failed). `dine_atl_run`
  creates the VM with ATL's options on an 8 MiB pthread and `ANDROID_LOG_TAGS=*:i`; it refuses
  once any VM exists, so ATL runs before the art screen in a launch. The ATL thread detaches from
  the VM when `atl_embedded_main` returns: ART aborts the process when an attached thread exits.
- TLS on iOS is wolfSSL and libwolfssljni, as on Linux (`--enable-jni`), linked into Dine.
  wolfJSSE's default trust manager, when it gets no keystore and finds no Java trust store, makes
  the context call `wolfSSL_CTX_load_system_CA_certs`: on iOS wolfSSL then validates with SecTrust
  (no hostname: `HttpsURLConnection`'s verifier checks names). libcore's provider list loads
  `WolfSSLProvider` during PackageParser's jar verification: with the jar on the boot class path
  but no native library, `Providers.<clinit>` fails and ATL aborts.
  wolfSSL builds with `--enable-armasm` (`-mcpu=apple-a12` in `CC`); on the iPhone 13
  `cpuid_get_flags()` is 0x23F (AES, PMULL, SHA256, SHA512, RDM, SHA3, ASIMD), so the ARMv8
  crypto paths run in the sandbox. The glue compiles against the library's `options.h` alone on
  both hosts.
- The bundle carries `gstub.jar` and `ghax.jar` next to `api-impl.jar`: `ATLPaths` and the
  AssetManager open them.
- `looper.apk` (`dine-atl/tests/headless/looper`, built by `tests/harness/apk.py`) covers the
  loop slot's worker paths (new, timed poll, wake, `is_idling`, free), a cross-thread main wake and
  the last activity finishing, which stops the main loop. It passes headless on Linux
  (`run-looper.sh`) and on the phone (**atl** → **run looper**: `looper done`, `atl main returned
  0`, Dine keeps running and the art screen's runs work on that VM afterwards).
- Fork deltas from this: dine-art's `add-dex-to-package` stores and aligns `classes.dex`
  (`ZIPALIGN` is build-tools' `zipalign`), and dine-atl's `build-aux/d8-jar.sh` does the same with
  the manifest last (meson's install runs `jar ufM` on every jar). ART then maps boot and ATL dex
  files from the jars instead of inflating copies. `Window.clear_background` is a rename in an
  upstream file that upstream edits often.
- Measured (iPhone 13, 2026-10-19): tap to VM created 0.24 s with stored dex (0.28 s
  deflated), then about 0.26 s to `onResume`. Stack, from page residency (`mincore`, 16 KiB
  pages; artbridge's `atl probe` lines, `dine_atl_probe` through `dbg call`): VM creation reaches
  48 KiB, demo_app's run 80 KiB. `phys_footprint`: 21-24 MiB before the VM, 42-44 MiB once it
  exists, 51-54 MiB at `onResume`, with a transient peak of about 280 MiB inside
  `JNI_CreateJavaVM`. With deflated dex it was 62 and 71 MiB. The 30 MiB of growth to `onResume`:
  - 16 MiB: ART's allocation and live stacks (2 × 8 MiB), every page dirtied because
    `MemMap::MadviseDontNeedAndZero` memsets before `madvise` off Linux (`kMadviseZeroes`);
  - 4 MiB: a mark bitmap, the same way;
  - 3.6 MiB: Java heap pages (1 MB allocated once the VM exists);
  - 2.8 MB: malloc (`malloc_zone_statistics` in use, 12.2 to 15 MB);
  - 1.7 MB: LinearAlloc (2388 classes loaded).

  The same memsets zero the heap spaces (512 MiB) once at creation. That is the peak; afterwards
  those pages show as dirty or compressed zero pages that `phys_footprint` doesn't charge. The
  earlier "67 to 105 MiB" included the 7.7 MiB stack paint, which is gone.

### M2: a dialog

- An authored APK whose Activity shows an AlertDialog with a title, a message and two buttons, and
  a second dialog with a list of items. Built by the test-APK tool (see [Tests](#tests)).
- Shared Java models the dialog as data: title, message, items, up to three labelled actions,
  cancelable. One upcall returns the chosen action or the cancel. This edits upstream's
  AlertDialog: the three Buttons go away.
- Backends the same day: `gtk` (a toolkit window), `headless` (logs the dialog, answers from a
  script), `uikit` (`UIAlertController`; items as an action sheet). The Activity window in
  `uikit` goes inside Dine's app container (`notes/nav-gestures.md`); in M2 the container is a
  placeholder and alerts present over it.
- The result looks like an iOS alert.

- Back and Home from `notes/nav-gestures.md`, so the app container has a way out: task state,
  `atl_nav_*`, the host slot's task functions, Dine's container, edge swipes and accessibility
  actions; the running apps list is a placeholder. Status and what is left: that spec's Status.

**Done when:** on the phone, `dbg ui tap` on a button produces the `onClick` log line and the
dialog closes; the same APK passes on gtk and headless.

**Status: done (2026-10-20).** `dbg smoke atl-dialog` on the iPhone 13 taps "Yes" (`dialog onClick
-1`, the list appears) and "Green" (`dialog onClick 1`, the app finishes); `linux smoke dialog`
and `dialog-gtk` pass the same APK with `ATL_DIALOG_ANSWERS='Yes;Green'`. As built:
- `ui.h`: `struct ui_alert` (title, message, items, three button labels, cancelable),
  `ui_dialog_new/show/close/set_cancel_on_touch_outside`, `UI_DIALOG_CANCEL`;
  `atl_upcall_dialog_result`. A Dialog's handle is a `struct ui_window *`, because Dialog hands it
  to its `Window`'s natives. `ui_window_get_size` serves `View.getWindowVisibleDisplayFrame`.
- Java owns the state: `showing`, `cancelable`, a canceled flag, a static set holding shown
  dialogs (the backend's ref is weak) in show order, closed and shown again with the task
  (`notes/nav-gestures.md`). `atlDialogResult` (package-private) ignores results unless drawn
  (showing, not hidden, task in front); AlertDialog runs the listener, then `dismiss()`, for items
  too. The NewPipe 10 ms delayed close is kept. `getButton`'s Button views: M4b.
  `OnCancelListener.onCancel` exists; `setCancelable` and the cancel and dismiss listeners
  are stored (Builder too).
- gtk: `src/backends/ui/gtk/dialog.c`, a GtkWindow per dialog; alerts get a label, a GtkListBox
  and GtkButtons; close-request and a tap outside are cancel results, close only hides.
  `ATLKeyboardDialog` builds on `ui_dialog_new`.
- headless: `dialog:` lines; uikit: `UIAlertController` on the topmost presented controller
  (after a running transition), items as an action sheet with Cancel when cancelable, a tap hops
  back through `loop_main_post`, close dismisses only its own controller. Both share the view
  records (`src/backends/ui/records/`); uikit is ObjC with ARC, meson adds `objc` only for it.
- `ATL_DIALOG_ANSWERS` (`src/shared/test_hooks.c`, with `test_hooks`): labels or `!cancel`, `;`-separated, one per
  shown alert; headless posts the result, gtk activates its own widget; no match exits 1.
- Debug agent: alert actions and UIKit controls decline `accessibilityActivate`; `tap` falls back
  to the alert action's handler or the control's events.
- The iOS build is `ui=uikit`; `build-ios-atl.sh` wipes the build dir when the cross file
  changes (meson keeps the compilers it found).

### M3: `demo_app.apk` on screen

- `uikit` view nodes: one UIView each. The root's layout pass runs Java measure and layout
  through the upcall; frames come back from `native_layout`.
- TextView as UILabel, measured with `sizeThatFits`; background color; padding.
- Density = 160 × screen scale, so 1 dp = 1 pt. Display config from the screen and trait
  collection.

**Done when:** `dbg ui screenshot` shows both strings in a vertical stack, and the view-tree dump
matches the headless one except for text sizes.

**Status: done (2026-10-20).** On the iPhone 13 `dbg ui screenshot` shows "hello PoC world!" above
"second one (static)", light text on the theme's dark background; `dbg smoke` passes every
scenario, atl-demo now also waiting for both strings in `ui ls` and comparing the dump's shape with
the Linux golden: `1170x2391` roots, TextViews `315x51` and `375x51` at y 0 and 51 (headless at
480 dpi: `404x51`, `479x51`). As built:
- Thread model: the Android main thread stays on artbridge's pthread (see [Interface
  rules](#interface-rules)). `uikit/view.m` queues UIKit changes and sends them in one
  `dispatch_async` at the end of each layout pass, or from a deduplicated post when no pass is
  pending; text measurement `dispatch_sync`s to a scratch `ATLLabel` and ceils to px.
- `records/` serves headless and uikit through the hooks in `records.h` (`native` per record);
  headless keeps the fixed metrics in `headless/views.c`, so its goldens are unchanged.
- One window source: hosts pass `struct atl_window_config` (px size, density, night) to
  `atl_vm_init`; `Display.density_dpi` feeds `DisplayMetrics.DENSITY_DEVICE` and
  `AssetManager_init`; `atl_display_apply` writes dp. The cli host takes `-d DPI`;
  `run-demo.sh --density 480` and `linux smoke demo-480` cover sp, dp and px on Linux.
- TextView: one px method `setRawTextSize` (package-private, a no-op in EditText);
  `setTextSize(float)` is sp, `setTextSize(unit, size)` converts. `setTypeface` style goes through
  `ui_text_set_style` (gtk: the old CSS classes; uikit: bold and italic system font).
- Dine: `Navigator.run` creates the surface (`AppSurfaceView`) and reads the window from the key
  window: below the status bar to the screen's bottom, density 160 × scale, night from traits;
  `dine_atl_run` takes them (`struct dine_atl_window`). The container pins the surface at the
  safe area's top at that fixed size.
- Frame: `Window` sets up the status bar as `PhoneWindow.generateLayout` does (theme
  `statusBarColor`, `windowDrawsSystemBarBackgrounds`, `windowLightStatusBar`; `setStatusBarColor`,
  window flags, the decor's `SYSTEM_UI_FLAG_LIGHT_STATUS_BAR`, `setSystemBarsAppearance`). The
  shown activity's goes to `ui_window_set_frame`: none without `FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS`,
  which the theme gives only from `effective_sdk_compat` 21 (min(targetSdk, SDK_INT), with SDK_INT
  ATL's fixed level `ro.build.version.sdk`: targetSdk >= 21, as on Android).
  uikit hands it to the surface (`ATLSurface`, `atl/surface.h`) in the batch of the activity
  switch; Dine paints it behind the status bar (none: `.systemBackground`) with the text style
  from the light flag. gtk colors the header bar; headless prints `window: frame` lines.
- Debug agent: `back` and `action` also climb from every presented controller's view, so screens
  whose views have no labels (empty TextViews, an alert over the container) still reach the
  container's actions.
- Freeing: `ViewGroup.removeView` and `View.finalize`'s destructor go through the ui slot
  (`ui_view_remove_child`, `ui_view_free`). The destructor runs on the FinalizerDaemon and posts
  the free to the Android main thread. uikit frees a record in a queued block, after every block
  that names it. The same way: `Dialog.finalize` → `ui_dialog_free` (uikit's `ATLDialog` outlives
  it in the alert's blocks; its ref is freed after queued answers), `Drawable.native_unref` →
  `gfx_drawable_unref`, and `ui_window_close` releases the uikit surface. Top-level posts run in
  the Android thread's base JNI frame, which never pops: their local refs must be deleted.
  The app's `ui_window` struct stays allocated (one per process).

### Pre-M4 batch (2026-10-21)

Natives that layouts and app setup reach before any input, moved behind the slots so apps get past
`onCreate` on headless and iOS. A headless triage of six `atl_test_apks` drove it.
- Matrix: `src/shared/`, graphene from `subprojects/graphene.wrap` (1.10.8, `gobject_types=false`)
  on headless and iOS, `libgraphene-1.0.a` linked by Dine. A copy keeps its source's values,
  `setRotate(deg)` replaces the matrix, `mapPoints` divides by w, and skew, sinCos, setConcat,
  setPolyToPoly (after Skia) and mapRadius have natives.
- Paint state in the gfx slot (`gfx_paint_*`); text bounds and font metrics stay gtk-only (M5c).
  Paint frees its native state in `finalize`.
- Java: `getLocationInWindow/OnScreen` (OnScreen = InWindow: the window's origin is 0),
  `getGlobalVisibleRect`, `offset*RectInto*` and `getViewTreeObserver`'s window walk the parents.
- Attach: a Java flag and `dispatchAttached/DetachedFromWindow` (ViewGroup passes them on) from
  ViewGroup add/remove, the activity's decor in the app window (attached before onStart, detached
  before onDestroy: gtk's points, not Android's), Dialog show/dismiss, WindowManager add/remove,
  PopupWindow show/dismiss and Spinner rows (gtk); gtk has no `notify::root` path. A view keeps
  its window from attach to detach.
- Window state for the shown activity, with the frame: fullscreen (`FLAG_FULLSCREEN`, theme
  `windowFullscreen`, a view's `SYSTEM_UI_FLAG_FULLSCREEN`, last writer; `LAYOUT_FULLSCREEN` isn't
  fullscreen) in `struct ui_frame`; keep screen on (`FLAG_KEEP_SCREEN_ON`, 0x80, or an attached
  view of the window) through `host_keep_screen_on`. iOS hides the status bar with the window kept
  below the notch (Android's default cutout mode); Dine disables the idle timer while the app shows.
- ui slot: visibility, background drawable (held, drawn from M5b), invalidate, children moved
  (translation), markup flag, multi-window, ViewTreeObserver observations (records: after each
  layout pass), `ui_image_*` and `ui_progress_*` nodes (an ImageView draws nothing before M5b).
- `ProgressBar.setIndeterminate` keeps its argument, `attachViewToParent` adds a view that wasn't
  detached once, and the C targets wait for javac to rewrite the JNI headers.

### M4a: touch, scrolling and keys

- Touch to MotionEvent through a shared builder; click and long press. Posted code runs in the
  Android thread's base JNI frame, so the builder pushes a local frame.
- ScrollView as UIScrollView, through a scroll node kind in the ui slot.
- Focus; Back through the key chain, dialogs included (`notes/nav-gestures.md` covers the edge
  gestures); hardware keyboard keys.
- DrawableContainer behind the gfx slot, so StateListDrawable, LevelListDrawable and
  AnimationDrawable work on headless and uikit; pressed and focused states with input; drawing the
  selection waits for M5b. On gsk, ContainerPaintable keeps the selected child's paintable, so a
  child that swaps its paintable later (`BitmapDrawable.setBitmap`) draws the old one until the
  container selects again. views-gtk proves the container's free only through the nine-patch it
  holds: the `drawablefreed: ContainerPaintable` line alone doesn't show it.
- Edge pans against Android-hosted `UIScrollView`s, exclusion rects through scrolls and
  translations, and the by-hand check of an excluded span (`notes/nav-gestures.md` Status, Risks).
- Shared Java: one floating ViewTreeObserver per view without a window; the View constructor
  reads `keepScreenOn`.
- Input for tests: the cli host's `-c` stdin takes touch and key lines next to `back`, `home` and
  `front`, and M4c's text lines. gtk and iOS have no touch injection path (the debug agent's `tap`
  is `accessibilityActivate`, and iOS has no public touch synthesis), so their touch steps are
  checks by hand.
- Target: the widgets APK, which exists for checks by eye on iOS (`dbg smoke atl-widgets`), gets
  steps graded on headless: a tap, a long press, a scroll, a key, and a selector background's
  selected child following the pressed state, read from a log line (nothing draws it before M5b).
  Paths with no test yet: `setSystemUiVisibility`'s fullscreen, attach on Dialog, PopupWindow and
  WindowManager, and the detached-child path.

**Status: done.** `linux smoke widgets` and the framework suite `input` pass on headless, `dbg
smoke` passes on the iPhone 13. Checked by hand: gtk (WSLg), and taps, hold, scroll and the Back
swipe on the phone; a hardware keyboard on the phone is unchecked. Headless
Gravity Defied stops at `NinePatchDrawable.nativeCreate` (M5d). As built:
- Dispatch is AOSP's, in Java, on every build: a backend hands window-pixel pointers for the root
  view of the window that got them to `atl_upcall_touch` (`src/shared/input.c`), which builds the
  MotionEvent in a local frame and calls `ATLInput.touch`: touch mode, then the window's callback
  (Activity, Dialog) or the root. `ViewGroup.dispatchTouchEvent` keeps touch targets from DOWN,
  asks `onInterceptTouchEvent` on the way and splits pointers; `View.onTouchEvent` gives pressed
  and prepressed state, long press and click. MotionEvent's pointer methods (`split`,
  `getPointerIdBits`, `findPointerIndex`, `offsetLocation`, `transform`) are Java.
- Keys: `atl_upcall_key` → `ATLInput.key`: the app window's keys go to its top drawn dialog, else
  the activity; Activity and Dialog run AOSP's chain with the window's `DispatcherState`. Unhandled,
  DPAD/TAB move focus through AOSP's FocusFinder, and ESCAPE falls back to BACK (ATL's: Android
  10 gives it no fallback, and a keyboard on iOS has no Back key); a navigation key in touch mode
  first leaves it. A key's character follows Generic.kcm: Enter's is `\n`, other control keys but
  Tab have none. `atl_nav_back` is BACK down and up through this chain, so a shown
  dialog cancels.
- Focus is Java's (AOSP's View and ViewGroup code); `ui_view_set_focused` moves GTK's focus into or
  out of a widget that edits text. Touch mode starts on.
- Scroll: a `NODE_SCROLL` kind (`ui_scroll_new`) for ScrollView and HorizontalScrollView, and
  `ui_view_scroll_to` for `View.scrollTo`. The toolkit's offset is the truth and comes back through
  `atl_upcall_scrolled`; `View.atlScrolled` drops an offset equal to Java's, else sets it and calls
  `onScrollChanged`, the listener, the observer and `Window.updateExclusion`. A plain `scrollTo`
  moves Java's offset at once; `smoothScrollTo` waits for the toolkit's reports.
- gtk: each GtkWindow (the app's, each dialog's) gets a capture-phase touch controller and key
  controllers; popovers' events pass their window's. The per-widget touch, click, long-press and
  key controllers are gone. Widgets that take their own presses (GtkText, GtkScale, the spinner,
  pickers, WebView, scrollbars) are marked with `input_take_native`: a gesture that starts on one
  stays with GTK. The Button family's GTK widgets take none (M4b). A text widget with GTK's focus
  gets keys first. The scroll node is GtkScrolledWindow; a request its range can't take yet waits
  for the range to grow. Hover and the wheel stay per widget.
- headless: the cli host's `-c` takes `touch down|move|up|cancel <id> <x> <y>` (window px) and
  `key down|up <code> [<meta> [<unicode>]]`. A drag that starts in a scroll node and passes the
  touch slop along its axis stands in for the toolkit's pan: Java gets CANCEL, the offset follows.
- uikit: every node view hands its touches to `input.m` (UITouch → lowest free pointer id, surface
  points → px); a MOVE waiting for the Android thread takes the newer pointers. ATLScrollView is a
  UIScrollView (no safe-area insets; `contentSize` along its axis is the child's size plus its
  padding, without margins, as AOSP 10's range; set in the layout batch) whose offsets go back coalesced; while the
  user drives it they're clamped to the range, so the bounce past an end stays UIKit's. Other views
  scroll through `bounds.origin`. The shown activity's
  root view is the first responder: hardware keys map from HID usages in `keys.m`. A freed record
  is freed on the Android thread behind the scroll reports UIKit posted before.
- DrawableContainer is behind `gfx_container_new/select`; record holds the selected child, gsk's
  ContainerPaintable shows it. `getDrawableState` has enabled, pressed, focused and window focused.
- ViewConfiguration's scaled values are dp; `getViewTreeObserver` keeps one floating observer; the
  View constructor reads `clickable`, `longClickable`, `focusableInTouchMode`, `keepScreenOn` and
  the next-focus ids. EditText gets `editTextStyle`'s `focusable` and `focusableInTouchMode`, each
  overridden by its own attribute (ATL's EditText doesn't take that style).
- Tests: framework suite `input` (dispatch, focus, keys, scroll, observer; it prints the cost of a
  MOVE through ten levels), `run-widgets.sh` (`linux smoke widgets`), and Back on a shown list in
  `run-nav.sh`.
- AOSP provenance: `dine-atl/doc/AOSP.md`.
- Open: the edge pans against an Android-hosted UIScrollView and an excluded span, by hand; touches
  on popovers on gtk; a GtkText's Tab moves GTK's focus, not Java's; lists don't scroll
  (`ViewGroup.offsetChildrenTopAndBottom`, M6b).

### M4b: controls

- Button, CheckBox, RadioButton (with RadioGroup), Switch, ToggleButton, ImageButton.
- `AlertDialog.getButton` returns Button views bound to the alert's actions, for apps that change
  a button in `onShow`: `setText`, `setEnabled` and visibility reach the backend through a ui slot
  call that changes the shown alert in place; `performClick` gives the dialog result;
  `setOnClickListener` replaces the default listener-then-dismiss.
- The GTK-isms `setAllCaps`, `setTextAlignment` and Button's `ATL-no-border` ([Java](#java)).
- Unblocks on headless: flower_finder and accelerometerdemo get past
  `ImageButton.native_constructor`.
- Target: the widgets APK's controls, graded on headless and checked by hand on gtk and iOS, and a
  dialog APK step whose `onShow` disables "Yes" and overrides a click to keep the dialog open,
  passing on headless, gtk and iOS.

**Status: done (2026-10-24).** `linux smoke controls`, `dialog` and `dialog-gtk`, and the
framework suite `controls` pass; on the iPhone 13 `dbg smoke atl-controls` and `atl-dialog-keep`
pass. Not checked by hand: the controls' look on gtk. Next stops on headless: flower_finder at
`Region.nativeConstructor` (material's FloatingActionButton), accelerometerdemo at
`SensorManager.register_accelerometer_listener_native` (M7's sensors). As built:
- Input stays Java's (M4a): a control is a passive toolkit widget showing Java's pressed and
  checked state, and its touches and keys go through AOSP's dispatch on every build.
  `ui_button_new(kind)` (push, toggle, check, radio, switch) makes a text node with a control, so
  every `ui_text_*` call applies; `Button.drawableStateChanged` sends `ui_button_set_state`.
- Java: Button takes its style's clickable and focusable by hand, as EditText does. CompoundButton's
  checked state, toggle in `performClick`, listener order, the widget listener RadioGroup uses and
  `state_checked` are AOSP 10's; RadioButton never unchecks itself; ToggleButton shows its on or off
  text from its constructor; ImageButton is an ImageView node, focusable as in AOSP. `setAllCaps`
  upper-cases the shown text in Java (markup's tags and entities kept) and `getText` keeps the
  app's; `getTextAlignment` resolves INHERIT, and `ui_text_set_alignment` gets start, center or
  end (GRAVITY is start: ATL ignores TextView gravity). `setCompoundDrawables` goes through
  `ui_text_set_drawables` (gtk draws them; the records backends keep nothing before M5b).
- Dialogs: AlertDialog's Buttons (made on demand, GONE without a label) hold the label,
  visibility and enabled state; `ui_alert.disabled` and `ui_dialog_set_button` carry them to the
  backend, and a result for a disabled or hidden button is ignored. `atl_upcall_dialog_result`
  returns whether the dialog is still drawn: uikit then presents the alert again (UIKit dismisses
  on every action tap), headless and gtk take the next scripted answer. Scripted answers match when
  delivered, after `onShow`, against the alert's current buttons; a disabled or hidden one matches
  nothing.
- gtk: a GtkButton or GtkToggleButton holding the text box, or a GtkCheckButton (a radio in a
  private group) or GtkSwitch beside it, with `can_target` and `focusable` off; push and toggle
  buttons drop GTK's border while the view has a background. Text calls find the label through
  object data and skip handles without one.
- headless: fixed control sizes (a check or radio box one line high, a switch two lines wide);
  `dialog: button` lines for in-place changes.
- uikit: `ATLButton` holds a passive UIButton (gray; filled for a toggle that is on; plain with a
  background of its own; SF Symbols `square`, `checkmark.square.fill`, `circle` and
  `largecircle.fill.circle` for check and radio) or a label and a UISwitch, measured with a scratch
  view per kind. Accessibility activation (VoiceOver, `dbg ui tap`) calls `performClick` through
  `atl_upcall_click`. `dialog.m` queues with the views (`uikit_enqueue`); `ATLDialog` keeps the
  alert as a model and builds the controller when it presents, so `onShow`'s changes are in the
  first one; `enabled` changes in place, a label or visibility change rebuilds the alert without
  animation.
- Tests: `run-controls.sh` (`linux smoke controls`, the widgets APK's `ControlsActivity`),
  `run-dialog.sh`'s `KeepActivity` runs, the framework suite `controls`, smoke `atl-controls` and
  `atl-dialog-keep` (`Step.declined`: a tap the agent must be refused).
- Open: a Switch's thumb can't be dragged on iOS (a tap toggles it); a view with INHERIT keeps its
  native alignment when its parent's changes later; Button text gravity, and with it
  `setTextAlignment` on iOS buttons (a push button's text stays centered: the slot's start can't
  tell an explicit start from none); button drawables and tints are kept, not drawn (M5b).

### M4c: text input

- EditText as UITextField with the keyboard and IME through UITextInput. UITextInput and
  accessibility queries read a text-state mirror on UIKit's thread: UIKit's thread never waits
  for the Android one ([Interface rules](#interface-rules)). gtk's EditText and
  InputMethodManager callbacks leave local refs in the Android thread's base JNI frame.
- Selectable text (EditText, a TextView with `setTextIsSelectable`) with the toolkit's own
  selection and edit menu, so Copy writes the system pasteboard and Paste reads it, on iOS and gtk.
  An app's ClipboardManager reaches the same pasteboard through M7's clipboard item.
- Text lines on the cli host's `-c` stdin.
- Target: the widgets APK's text field, graded on headless and checked by hand on gtk and iOS.

**Status: done (2026-10-25).** `linux smoke text` and the framework suite `text` pass on headless;
on the iPhone 13 `dbg smoke atl-text` passes, and `dbg ui type` into a Button is refused. Not
checked by hand: on gtk typing, Enter, the selection and Copy/Paste; on the phone the software
keyboard's own typing, a CJK keyboard's marked text, the selection handles and edit menu, a
selectable TextView's Copy, the return keys and the pads' Done bar, password dots, the number
keyboard, the keyboard after Home and front. As built:
- Truth: Java's Editable. EditText keeps one from `Editable.Factory`; `setText` makes a new one as
  AOSP does (filters against an empty Spanned, the listeners get `(0, old, new)`, the ChangeWatcher
  span moves to it), and the old one stops reporting. The toolkit's field is the IME's side: it
  applies the user's edit at once and reports `{prev, prev selection, text, selection, seq}`
  (`atl_upcall_edit_report`, positions in UTF-16 code units). `EditText.atlEdited` finds the change
  around prev's selection and replaces Java's own selection widened by the same amounts through
  `Editable.replace` (filters, watchers), so a report on a base Java moved on from lands at Java's
  cursor, as an IME's `commitText` does. A state that differs from the report's goes back as a
  snapshot (`ui_edit_set_state`, acking the seq); Java's own changes send one per message. A field
  takes a snapshot only when it acks the field's last report and no marked text is open; otherwise
  its newer report makes Java answer. Marked text stays in the field until committed, and its end
  always reports.
- Slot: `ui_edit_new` (a text node: color, size, style and alignment apply, text and markup
  don't), `ui_edit_set_config` (keyboard kind, return key, autocap, secure, multi-line,
  autocorrect, hint, resolved in Java from `inputType` and `imeOptions`), `ui_edit_set_state`,
  `ui_edit_set_keyboard`, `ui_text_set_selectable`; upcalls `atl_upcall_edit_report`, `_action`
  and `_focus`.
- Keyboard and focus: InputMethodManager holds the EditText the keyboard serves and whether it
  shows. The keyboard follows Java's focus between EditTexts and hides when focus leaves them, on
  Done, and on Back (its down and up both go to the keyboard). A tap the toolkit takes itself gives
  the field the keyboard and Java's focus (`atl_upcall_edit_focus`); on headless a tap goes through
  Java (EditText takes `clickable` from its style by hand). gtk keeps GTK's focus with Java's
  (`ui_view_set_focused`), and `ui_edit_set_keyboard` does nothing there.
- Java: `Editable`, `InputType` and `InputFilter` are AOSP's, and EditorInfo has the IME
  constants. TextView keeps the hint, the selectable state, the transformation method and the
  editor action listener, with AOSP's `onEditorAction`. EditText has AOSP's input types (a bare
  EditText is multi-line), single line, filters, `maxLength`, password and the Enter keys. A soft
  keyboard's return key on a single-line field (iOS, headless) is the IME's editor action, or an
  Enter key with `IME_FLAG_NO_ENTER_ACTION`; gtk's Enter is a hardware key.
  `Context.INPUT_METHOD_SERVICE` is `"input_method"`.
- headless: the field with the keyboard takes the `-c` text lines (`notes/dev-reference.md`) and
  prints `edit:` and `keyboard:` lines; `text hold` keeps reports back, so the drop rule runs. It
  measures the text or the hint, a multi-line field by its lines.
- gtk: a GtkText, single-line. It reports from an idle (typing over a selection is one report) and
  upcalls focus enter and leave; the config sets the placeholder, visibility, input purpose and
  hints. An EditText takes a hardware Enter before its GtkText, as Android takes a physical
  keyboard's (an open preedit's Enter stays the IM's): a single-line field moves focus down, a
  listener gets `IME_NULL` with the key, and a multi-line one takes it as a confirm key, with no
  newline. A selectable TextView's GtkLabel is selectable and takes its own presses; its Ctrl+C
  goes to GTK. A key's release goes to Java only after its press did (by hardware keycode; a
  window going inactive forgets them, without a canceled up): GTK passes on the releases of
  presses a text widget took. The IM-context callbacks of InputMethodManager push a local frame.
- uikit: a UITextField for a single-line field, a UITextView for a multi-line one (swapped in
  place, the state and the first responder carried over), `ATLSelectableText` (a UITextView that
  doesn't edit) for a selectable TextView. A report waiting for the Android thread takes the next
  change too. A field Java gave the keyboard before its root was in a window gets the first
  responder when the root shows; a field that resigns (another activity shows, Dine leaves the
  front) tells Java the keyboard is gone. Return on a single-line field is the editor action; the
  number and phone pads, which have no return key, get a bar above them with it. The hint is the
  accessibility label. A scratch UITextField or UITextView measures, an empty one as a space.
- Debug agent: `ui type <label> <text>` (`insertText:`; no marked text).
- Tests: `run-text.sh` (`linux smoke text`, the widgets APK's `TextActivity`), the framework suite
  `text`, smoke `atl-text`.
- Open: keyboard avoidance (M6b); Java's click and touch listeners on a field or a selectable
  TextView where the toolkit takes its touches (gtk; on iOS unchecked); a hardware keyboard types
  only into the field with the keyboard (no KeyListener); gtk multi-line; a Dialog's EditText
  (M6b's content-view root); ClipboardManager (M7); `onCreateInputConnection` on EditText,
  BaseInputConnection (a stub whose own `Editable` class shadows `android.text.Editable`) and
  `onKeyPreIme`; key listeners as filters (a number field takes letters; M5c); line limits and a
  fixed-height multi-line field's scrolling (M5c);
  AutoCompleteTextView's drop-down (PopupWindow, M6b); on headless a field whose activity another
  one covers keeps the keyboard (Java's next Back hides it); typing lag under `-Xint`, unmeasured.

### M5: Canvas

Four stages. Each one adds to [M6a](#m6a-triage-and-fixes)'s findings what it hits but doesn't fix
(an app's stop point, a bug outside its target, a measurement that misses), with how to reproduce
it, and updates the entries its work changes.

#### M5a: renderer and display list

- Choose CoreGraphics or Skia, with a diverger run; the choice and its reason go here. With
  CoreGraphics the iOS backend is `coregraphics`, a CALayer per drawing view node; its parts land
  in M5b to M5d.
- A draw pass on the records backends, which have none: after a layout pass and on invalidate, each
  drawing node's `onDraw` runs and records into its display list.
- `GskCanvas` becomes a backend-neutral Canvas class over a gfx handle ([Java](#java)). The
  `record` display list keeps its operations with their Paint and Matrix state; headless dumps it
  (`test_hooks`).
- Matrix: `preScale` and `preRotate` with a pivot put the pivot on the wrong side
  (`identity.preScale(2,2,10,10)` moves (10,10)); `mapRect` has no perspective divide. Canvas's
  pivot `rotate` and `scale` translate around the plain call and don't reach these.
- Paint: `Paint.set(this)` frees the paint, then clones it; `Paint(Paint)` and `set` don't copy
  align, shader, xfermode or color filter.

**Done when:** headless dumps the display list of a widgets APK view whose `onDraw` draws rects and
lines, one under `concat` with a Matrix from `preScale(2,2,10,10)` and a pivoted `preRotate`, one
with a `new Paint(p)` copy, and the dump matches a golden as `demo_app.viewtree` does; framework
suite tests for `mapRect` with perspective and `Paint.set(this)` pass on headless and gtk.

**Status: done (2026-10-25).** `linux smoke draw` matches `draw.displaylist` on headless; the
graphics suite's Matrix and Paint tests pass on headless and on gtk (`tools/dine test framework
--gtk`); `linux smoke` and the runtime suite pass, and on the iPhone 13 `dbg smoke` does. As built:
- Renderer: CoreGraphics, with CoreText and ImageIO: the `coregraphics` gfx backend, a CALayer per
  drawing view node. It is in the iOS SDK (no build from Linux, nothing added to the app), CoreText
  measures as the UIKit labels that measure TextViews, and CGBlendMode, CGGradient, CGPath and
  transparency layers cover Paint's modes, shaders, paths and `saveLayer`. Skia's gn build for iOS
  from Linux is untried and would add several MB (unmeasured); upstream ATL draws with GSK and has
  no Skia. Pixels differ from Android's (anti-aliasing, hairlines): rasterizer goldens take a
  tolerance, and `record` stays the oracle. Where a list rasterizes (UIKit's thread in the layer's
  draw, or the Android thread into a CGBitmapContext) is M5b's choice.
- Canvas: `android.atl.ATLCanvas` over a `struct gfx_canvas` (gsk: the GtkSnapshot, so gtk's
  snapshot paths pass it as before). `gfx_canvas_*`: a recording's new and free, save, restore,
  translate, rotate, scale, concat, rect, round rect (circle and oval), line, drawable.
  `drawLines` takes four floats per line from `offset`, on every build.
  Bitmaps, paths, text, clips and RenderNode stay gtk-only: on records an `onDraw` that calls one
  gets `UnsatisfiedLinkError`, printed and cleared by the upcall.
- `View.draw`'s and `ViewGroup.drawChild`'s toolkit parts go through `ui_view_draw_*`: gtk
  snapshots its widgets, records draw nothing (a background, text or child is its own node).
  `Drawable.draw` goes through `gfx_canvas_draw_drawable`; record keeps a `drawable` op for a
  container, and a Drawable with no native paintable draws nothing.
- Draw pass (records, so headless and iOS): a node whose class draws (`traits.draws`) redraws when
  new, invalidated or resized, in tree order, skipping what isn't VISIBLE. It runs at the end of a
  layout pass (after the preDraw observers, before `records_layout_done`) and from the one draw
  post per window that `invalidate()`, or a view showing again from INVISIBLE, makes (Java
  requests a layout only for a change to or from GONE). `View.atlDraw` runs `draw()` into a fresh
  list and clears the canvas after. An invalidate inside `onDraw` draws in the next pass, unpaced
  (M5b).
  Dialog windows get no layout pass on records, so their views never draw (M6b's second layout
  root).
- record: each op keeps a copy of its paint and the matrix it was drawn under (Paint and Matrix
  free their native state on the FinalizerDaemon). `ATL_DUMP_DISPLAYLIST=1` prints `displaylist:`
  lines after each draw (`test_hooks`).
- Matrix: pivoted `preScale` and `preRotate` keep the pivot; `mapRect` divides by w and returns
  `rectStaysRect`, which is false with perspective or a zero scale. Paint: `Paint(Paint)` and `set`
  copy xfermode, shader, align and color filter, `set(this)` does nothing, the default align is
  LEFT.
- Tests: `run-draw.sh` (`linux smoke draw` with golden `draw.displaylist`, `draw-gtk`) on the
  widgets APK's `DrawActivity`, which redraws after `invalidate()`, not after a same-size layout,
  and after showing again from INVISIBLE; the graphics suite's pivot, `mapRect`, `rectStaysRect`
  and Paint copy tests. `tools/dine test framework --gtk` runs every suite on the gtk build, one at
  a time, against `expectations/linux-x86_64-gtk.json`: `InputMethodTest#testShowAndHide` fails
  there, as gtk shows no soft keyboard.
- Open: a missing native's stack trace prints on every redraw of the view that calls it.

#### M5b: drawing on the phone

- The chosen backend draws each drawing view node's display list. Where the list rasterizes:
  UIKit's thread in the layer's draw, or the Android thread into a CGBitmapContext. RenderNode is
  M9's (nothing in api-impl draws one; Compose does).
- Redraws paced to the display: at most one draw pass per frame (CADisplayLink on uikit), so an
  `onDraw` that invalidates itself doesn't spin the Android thread; headless stays unpaced.
- `clipRect` and its restore behind the gfx slot (ATLCanvas's `push_history` is gtk's way).
- Background drawables, ImageView, DrawableContainer's selected child and the lists' `drawable` ops
  draw. Bitmaps get their
  own gfx handle, with Android `Bitmap.Config` values instead of `GDK_MEMORY_*` ([Java](#java)):
  ImageView hands a Bitmap's texture to `ui_image_set_drawable`, which takes a `gfx_drawable`.
- `tests/harness/apk.py` compiles a `res/` dir (`aapt2 compile`, then `link` with it): the target
  needs a PNG and a selector resource.
- A drawable resource loaded twice is one object: `ConstantState.newDrawable` returns the same
  instance (`DrawableContainerState` returns its `owner`, the base `Drawable.getConstantState`
  returns `this`), so views that share a resource share its state, alpha and filters. Gravity
  Defied's keys 1, 2, 4 and 5 all use `btn_br`: pressing one lights up all four. Fix: port AOSP
  10's `DrawableContainerState`/`StateListState` copy constructors and a `newDrawable` that makes a
  new container with its own selected child and native paintable, sharing the child drawables;
  then real constant states for the other drawables. The port goes in `dine-atl/doc/AOSP.md`.

**Done when:** `dbg ui screenshot` on the phone shows M5a's view, the widgets APK's ImageView with a
Bitmap decoded from a PNG resource, and its selector background; on headless, a press on one of
two widgets APK views that share a selector resource changes only its own selected child (a log
line).

**Status: done (2026-10-25).** On the iPhone 13 `dbg ui screenshot` shows M5a's view with two clips
and a PNG, and the widgets screen's ImageView PNG and selector rows; `dbg smoke` passes with the new
`atl-draw`. On headless `linux smoke widgets` presses one of two rows that share
`@drawable/shared_selector` and only its own background changes (`widgets shared a=ff00c000
b=ff808080`), and `linux smoke draw` matches the new `draw.displaylist`; the graphics suite's
`BitmapTest` and `DrawableStateTest` pass on headless and gtk; `linux smoke` and the runtime suite
pass. As built:
- Raster on CA's side: the `coregraphics` gfx backend is record's display list
  (`src/backends/gfx/record/`) plus `coregraphics/draw.c` (a list's replay into a CGContext) and
  `bitmap.c` (ImageIO, decoded at once on the Android thread). uikit gives a drawing node an
  `ATLDrawLayer` (`drawsAsynchronously`, under the subviews by `zPosition`, no implicit actions, at
  the bounds' origin so it scrolls with the content, `contentsScale` the window density's); an
  ATLLabel replays in `drawRect:` under its text. The Android thread only records. Lists are
  refcounted, any thread drops them, and they hold only plain ops and bitmap refs: Java draws
  backgrounds, an ImageView's drawable and a container's selected child into them. Rasterizing on
  the Android thread into a CGBitmapContext was the alternative: simpler lifetimes, but the
  Android thread would pay the raster and a full-size image copy per frame.
- Views that draw on records: a class that draws, a background drawable, an image node's drawable.
  `ui_view_draw_background` and `_content` return whether the toolkit drew (gtk does); otherwise
  Java draws AOSP's `drawBackground` (a ColorDrawable stays the toolkit's color) and ImageView's
  `configureBounds` and `onDraw`. `setImageBitmap` wraps a BitmapDrawable.
- Pacing: `records_draw_wanted` (headless posts the pass; uikit unpauses a CADisplayLink on UIKit's
  run loop whose tick posts it, skipped while a flushed batch hasn't run there), `records_view_drawn`,
  `records_draw_done` (uikit flushes). `DrawStayActivity`'s self-invalidating bar draws 121 times in
  2000 ms on the iPhone 13 (60 Hz); with the pass posted at once instead, 319612 times, and
  `atl-draw` fails.
- Bitmaps: `gfx_bitmap` (gsk: the GdkTexture; record: RGBA from libpng, PNGs only; coregraphics: a
  CGImage), with `Bitmap.Config.nativeInt` (AOSP's) as its config. BitmapFactory reads the
  stream into a byte[] for `gfx_bitmap_decode`. `drawBitmap` records `OP_BITMAP` with its paint's
  alpha; BitmapDrawable's paintable is `gfx_bitmap_drawable_new`.
- `clipRect` is `gfx_canvas_clip_rect` (INTERSECT and DIFFERENCE; Region's other ops intersect, as
  before): record keeps `clip` and `unclip` ops, gsk counts each save level's pushes on the
  snapshot (`clipPath` too), coregraphics saves a gstate per clip.
- Drawables: AOSP 10's container constant states (a copy builds its own children from theirs,
  lazily), StateListState's `newDrawable`, ColorDrawable's and BitmapDrawable's states, a null base
  `getConstantState`, LayerState sharing a child without a state (`dine-atl/doc/AOSP.md`).
- Tests: `tests/harness/apk.py` compiles an optional `res/` (`aapt2 compile`, `link --java`); the
  widgets APK's resources, shared rows (`run-widgets.sh`) and DrawActivity's clips, bitmap and
  scrolled background (`draw.displaylist`); `run-draw.sh` fails gtk on unbalanced snapshot pushes;
  smoke `atl-draw`; the graphics suite's `res/` and tests.
- RenderNode is [M9](#m9-heavy)'s.
- Open: findings in [M6a](#m6a-triage-and-fixes) (themed GradientDrawable backgrounds stop at Path,
  `level-list` and `animation-list` XML, bitmap color filters, `clipRect`'s return value); a clip
  under a perspective matrix on coregraphics; Choreographer stays timer-based (10 ms frames);
  views redraw whole, without dirty rects; `Canvas(Bitmap)` and Bitmap's pixel natives stay
  gtk-only; a background's offset while UIKit drives a scroll waits for Java's scroll report and
  redraw; the display link on the Android thread's own run loop (saves a hop, unverified on iOS
  27); a press on a selector row on the phone and gtk is unchecked by hand.

#### M5c: text

- Text measurement and drawing in the gfx slot (CoreText with CoreGraphics): a real
  `Paint.measureText` instead of the width estimate ([Java](#java)), text bounds and font metrics
  (gtk-only now), `Canvas.drawText`.
- Measure on the phone how close UIKit text metrics come to what dp-based layouts expect.
- Key listeners as input filters, AOSP's: `NumberKeyListener`, `DigitsKeyListener` for number
  fields and `DialerKeyListener` for phone fields (ATL has no `DialerKeyListener`, and the other
  two are empty stubs), with TextView's rule
  that adds the key listener to the field's filters. Until then a number field takes letters from a
  hardware keyboard or a paste, on every build.
- TextView's line limits: `maxLines`, `lines`, `minLines` and `maxHeight` (attributes and setters;
  ATL's setters are empty), in the measured height as AOSP's `getDesiredHeight` caps and pads it.
  Until then a `wrap_content` multi-line EditText grows without a cap. A multi-line field whose
  height is fixed scrolls its own text to keep the cursor visible: on iOS its UITextView doesn't
  scroll yet.
- `Layout.draw` into a records canvas: `Layout.native_draw` is gtk-only.
- Unblocks on headless: Compose after `onResume` stops at `text.Layout.native_constructor`
  (Compose itself is M9).

**Done when:** framework suite tests for `measureText`, `getTextBounds` and `getFontMetrics` pass on
headless and gtk; M5a's view gains a `drawText`, its golden is updated, and the phone's screenshot
shows the text.

#### M5d: paths, nine-patch, layers; Gravity Defied

- Path (CGPath with CoreGraphics), `drawArc`, shaders, `saveLayer`.
- Nine-patch loading, when NinePatch joins `gfx`:
  - `nativeCreate(String)` leaks its texture on every early return;
  - `ninepatch_paintable_new` returns NULL on a failed bounds check without freeing the chunk or
    the texture (both variants);
  - a file with an `npTc` chunk whose image fails to decode passes a NULL texture to
    `gdk_texture_get_width`;
  - the byte[] variant doesn't check `size >= sizeof(struct Res_png_9patch)`;
  - a failed load leaves a NinePatchDrawable with paintable 0, and `setTint` writes through NULL.
    Android returns null for a missing file and a BitmapDrawable for a PNG without `npTc`.
- Measure on the phone a real app's stack depth on the 8 MiB Android main thread (demo_app's run
  reaches 80 KiB), and Gravity Defied's frame time: its `draw()` runs in Java under `-Xint`.
- The dev payload bundles Gravity Defied, with an AtlView tile: real apps reach the phone only
  through it until [M8a](#m8a-apk-import-and-launch) imports APKs.
- Choose Android-styled or iOS-styled widgets on iOS: UIKit controls come first (M3, M4b); AOSP
  Java widgets drawn through Canvas follow upstream's direction and need M5, and so does an
  Android-styled dialog (the AOSP layout path).

**Done when:** on headless, AdaptiveIconDemo gets past `Path.native_create_builder` and Gravity
Defied past `NinePatchDrawable.nativeCreate`, and M5a's view adds a path, an arc, a shader and a
`saveLayer` to its golden; Gravity Defied runs on the phone, driven by touch. The apps suite
starts with it.

### M6a: triage and fixes

A cycle like the [pre-M4 batch](#pre-m4-batch-2026-10-21): a headless triage runs each
`atl_test_apks` APK outside M9 (Compose, GL) to its first stop. M6a fixes the stops before an
app's first input that fit the existing slots, and the findings below; every other one moves to
the stage that owns it (M6b, M7, M9) or to Not staged; a stop an M6b item names stays there. The
triage then runs again; the cycle ends when a triage finds only stops owned elsewhere.

Findings from M4b and M5 (M5's stages add and update them):
- gtk `ui_view_set_background_drawable` makes a CSS provider per call and never unrefs it.
- A triage run shows one stop only: `activity_start` (`src/shared/activity.c`) calls
  `ExceptionDescribe` after `onCreate` throws, ART's `ExceptionDescribe` leaves the exception
  pending, and the next JNI call (`_GET_BOOL_FIELD`) aborts under CheckJNI. Other spots that only
  describe may do the same.
- flower_finder stops at `Region.nativeConstructor` (material's FloatingActionButton): Region's
  natives are gtk-only.
- `new Canvas()` without a Bitmap throws a NullPointerException on every call (`synchronized` on
  its null bitmap); AdaptiveIconDrawable makes one.
- A 90° rotation leaves cos at -4.37e-8 in graphene, so `rectStaysRect` is false for quarter
  turns; Skia snaps such values to 0 (unverified for Android 10's Skia).
- uikit's `keys.m` sends a hardware keyboard's keypad Enter as `KEYCODE_NUMPAD_ENTER` (160), which
  no Java Enter reader takes (EditText's Enter keys, `isConfirmKey`, touch mode, lists); gtk sends
  it as `KEYCODE_ENTER`. Whether Android 10's readers take 160 like Enter decides the fix.
- A themed background drawn through GradientDrawable (RippleDrawable, InsetDrawable) stops at
  `Path.native_reset` on records, its stack trace printed on every redraw, and `View.draw` stops
  there: the view's own `onDraw` (an ImageButton's image) never runs. The widgets APK's ImageButton
  (`ControlsActivity`) shows it on headless and the phone. Path joins the gfx slot in M5d.
- Drawables without a constant state of their own get the base `getConstantState`'s null:
  NinePatchDrawable, InsetDrawable, ScaleDrawable, ClipDrawable (DrawableWrapper's is commented
  out), AnimatedVectorDrawable, ColorStateListDrawable, PictureDrawable. An app's
  `getConstantState().newDrawable()` on one throws, and Resources reloads them (a `.9.png` decodes
  on every load). AOSP 10 gives each a state.
- `Drawable.createFromXml` has no `level-list` case (null), and AnimationDrawable's `inflate` is
  commented out (an `animation-list` resource has no frames).
- Color filters and tints never reach a bitmap's paint: `BitmapDrawable.setColorFilter` and
  ImageView's `setColorFilter`/`setImageTintList` paths keep nothing, and coregraphics draws a
  bitmap with its paint's alpha only.
- `Canvas.clipRect` returns whether the rect itself is non-empty, not the resulting clip.

**Done when:** the last triage's table (APK, stop before, stop after) is in this section, and each
stop and finding is fixed, named in a later stage or under Not staged.

### M6b: breadth

- ListView and RecyclerView (`views_widgets_samples_flower_finder.apk`). On uikit, lists need a
  measure cache: each measured text is one hop to UIKit's thread.
- Drawables, themes and styles, AdaptiveIconDemo.
- PopupWindow and PopupMenu, Toast.
- A second layout root over the container, for Dialogs with a content view (they show nothing on
  headless and uikit) and Builder's single and multi choice, `setAdapter` and `setView` content.
  Dialog windows then need what the shown activity's window has: keep-screen-on and fullscreen,
  ViewTreeObserver observations on records (only the app window has layout passes), insets for
  Dialog and WindowManager roots, exclusion rects.
- ActionBar with Android's API as a no-op: ATL's `ActionBar` is an empty class and
  `getActionBar()` returns null, so multitouch stops at `ActionBar.setHomeButtonEnabled`, and a
  method alone would only move the failure to a NullPointerException.
- Configuration changes: no resize or trait-change relayout (portrait only).
- The UIKit pieces the uikit backend adds around Android's views match the iPhone's own in light
  and dark: the Done bar above the number and phone pads (M4c) looks off next to the keyboard.
- Keyboard avoidance: a keyboard covers a field low on the screen, since the surface has a fixed
  size and `atl_window_insets` no IME edge. The window's `softInputMode` (adjustPan, adjustResize;
  `Window.setSoftInputMode` does nothing, the manifest's is parsed) and the keyboard's frame from
  Dine.
- Immersive mode and status-bar insets for a window that covers the whole screen
  (`notes/nav-gestures.md` Status). The Dine setting that hides the home indicator for every app is
  [M8c](#m8c-navigation-settings-store)'s.
- Screen brightness (`WindowManager.LayoutParams.screenBrightness`): window state of the shown
  activity, sent through the host slot as keep-screen-on is. Linux sets it through GNOME's power
  settings over D-Bus, else `/sys/class/backlight` (`android_view_Window.c`, gtk-only); iOS through
  `UIScreen.brightness`.
- Styled text on iOS, with real Spanned support: ATL's `Html.fromHtml` keeps the HTML tags in the
  string; gtk renders them as Pango markup (`ui_text_set_markup`), uikit shows them literally.
- `SDK_INT` above 21 as `android.*` catches up: androidx reads gesture insets and exclusion rects
  only from 29, and from 33 calls `getOnBackInvokedDispatcher`, which ATL lacks; framework-res
  says 3-button navigation (`notes/nav-gestures.md` Reach, Risks).

### M6c: search ahead of M7

A search that fixes nothing: it finds what M7 and later stages will hit. The triage APKs outside
M9 run past their M6 stops on headless, with `-c` input where a stop needs it, and a dexdump read
of each APK lists the services it calls and the methods that call them. Each finding goes, with
how to reproduce it, to the stage that needs it fixed (an item of `notes/service-impl.md`, an M8
stage, M9); one that blocks nothing goes under Not staged. A service's findings also go into its
item in `notes/service-impl.md`.

Known from static reads, not run:
- accelerometerdemo registers an accelerometer listener in `onCreate` (sensors).
- multitouch references Vibrator.
- Gravity Defied calls ConnectivityManager only from its level-download paths, and sets an
  AlarmManager alarm in `GDActivity.doRestartApp` (jobs).

**Done when:** the table (APK, what it hits, owner) is in this section, and each entry is named in
a later stage or under Not staged.

### M7: services

The `services` slot, one stage per service, each with `desktop-linux`, `none` and `ios` backends
and a section in a services test APK: `notes/service-impl.md`. Its notifications, media session,
downloads and jobs items wait for parts of [M8a](#m8a-apk-import-and-launch),
[M8b](#m8b-ios-lifecycle) and [M8d](#m8d-background-probes); each item says which.

### M8: inside Dine

The launcher installs and starts APKs; iOS foreground and background drive the Activity
lifecycle (what runs once Dine is backgrounded: `notes/background-processes.md`); Back, Home and
the running apps list are in `notes/nav-gestures.md`, whose Status lists what is left of them. The
Dine-only stages M8b to M8d are left for later ([Milestones](#milestones)).

#### M8a: APK import and launch

- Import from Files, with document types through the Info.plist merge (the base item of
  `notes/service-impl.md`, if it isn't built yet). From the PC an APK reaches Files by a Safari
  download over the LAN (untried), or `pymobiledevice3 apps push --documents` puts it in Dine's
  Documents (needs `UIFileSharingEnabled`; unverified for a development-signed app on iOS 27).
- Each app gets a directory in Application Support for its APK and data. Every AtlView run shares
  Caches today, which iOS may purge (iOS knowledge).
- `AppLibrary` gains the package, the APK path, the label and the icon; it stores `id` and `name`
  today.
- Label, icon, package and whether there is a MAIN/LAUNCHER activity are read without the VM,
  since `dine_atl_run` creates the process's one VM. The reader is shared C in dine-atl over
  androidfw's C API (already linked into Dine), its header installed like `nav.h`, so the package
  suite grades on headless the code Dine runs. The API has no `AssetManager_delete` or
  `ApkAssets_delete`: each parse leaks until they exist. Adaptive icons resolve to XML, so they
  fall back to a PNG until M5d draws paths.
- Import rejects an APK without a launcher activity, and warns about native libraries
  (`lib/*/*.so`), which iOS won't load.
- At start `dine_atl_run` passes no activity and Java picks the launcher one
  (`Activity.createMainActivity`). With none it calls `System.exit(1)`, which would end Dine: the
  embedded host returns an error instead.
- One app per launch: the running apps list (`RunningApps`) and the run states that
  `notes/nav-gestures.md` Behaviour specifies for one run per process, on the launcher's tiles.
- Release builds (`DINE_RELEASE=1`, `-c release`) start no app yet: only the dev atl screen calls
  `dine_atl_run`, and such a build keeps no `Java_*` symbol (`llvm-nm` count 0). ART finds those
  with dlsym, so once the launcher starts APKs, a release build must keep them: check the count,
  and if they are stripped, link with `-export_dynamic` or an exported-symbols list. Trap: the
  release link also force-loads `libruntimetests.a` (Package.swift's
  `.when(configuration: .debug)` doesn't reach the linking executable), which dead stripping
  removes today; with `-export_dynamic` its `Java_*` would stay, so fix that condition first.
  Whether a clean release tree, which has no `libruntimetests.a`, fails to link is unverified.
- The package suite (`dine-atl/tests/package`) starts here.

**Done when:** the package suite passes on headless (the reader's fields for the test APKs, an APK
without a launcher, launcher resolution through the cli host without `-l`); on the phone a dev
screen imports from the dev payload through the same code (`dbg smoke`), and a release build
imports `demo_app.apk` and shows both strings (by hand).

#### M8b: iOS lifecycle

- Dine leaving the front calls `atl_nav_home` and coming back calls `atl_nav_front`: onPause and
  onStop, then onRestart, onStart and onResume, the paths `run-nav.sh` grades on headless. The
  container stays presented, a background task (`beginBackgroundTask`) keeps Dine running until
  the Android thread has run them, and Dine remembers whether the app was in front.
- The Dialogs and Home race (`notes/nav-gestures.md` Status).
- A pause without a stop (`willResignActive`: Control Center, the app switcher) would be new task
  state in `src/shared/activity.c`, with a cli `-c` command and a `run-nav.sh` step: decided here.
- Phone check known so far: the nav APK's lifecycle lines around an iOS background and foreground.
  pymobiledevice3 has `developer core-device hid button home` and `dvt launch --no-kill-existing`,
  neither tried on the phone; otherwise by hand.

#### M8c: navigation settings store

- `notes/nav-gestures.md` Settings, with the open settings items of that note's Status: the store,
  its model, the agent command, and the Dine setting that hides the home indicator for every app
  over M6b's immersive mode.
- Phone check known so far: the settings steps of smoke `atl-nav` (`notes/nav-gestures.md` Tests).

#### M8d: background probes

A dev screen answers the open questions in `notes/background-processes.md` on the phone. Question
3 and question 2's "exists and submits" take one log line each, question 5 one tap on the prompt;
question 1 needs days of runs, question 4 the user's hands (another app playing audio); questions
6 to 8 are code reads or the user's decisions. The task identifiers and background modes come
through the Info.plist merge. The answers go into `notes/background-processes.md` and set the
notifications, media session, downloads and jobs items of `notes/service-impl.md`.

#### M8e: several apps

Several apps in one process (`notes/meta.md`) need design first: ATL keeps one primary application,
one system configuration and one main window as globals; the options are in
`notes/multi-head-exec-maybes.md`. A diverger run chooses the design, written here with its reason;
then closing apps and a running apps list with several entries (`notes/nav-gestures.md` Behaviour).
The stages after the choice take the letters after M8e.

### M9: heavy

Compose (`compose_demo_app.apk`), SurfaceView and GLES, GL apps, and WebView: a `ViewGroup` backed
by a webkitgtk widget (`android_webkit_WebView.c`, gtk-only), a ui node kind on WKWebView for iOS.
RenderNode on the records backends: its natives build GskRenderNodes and are gtk-only;
a node would record into a display list that an op of its parent's list draws, with its
transform, alpha and clip ([Java](#java)).

## Tests

| Suite | Home | Builds | Oracle | From |
|---|---|---|---|---|
| runtime | `dine-art/tests/runtime` | Linux; the phone (by hand, from Dine's art screen) | expected output and per-platform expectations | now: `dine-0002-jni-args` runs on both |
| framework | `dine-atl/tests/framework` | headless, gtk, iOS | JUnit through `--instrument` and `test_runner.jar`; later CTS subsets at Android 10 (graphics, text, content, view) | M2 |
| package | `dine-atl/tests/package` | headless | expected parse results | M8a |
| apps | `tests/android-compat/apps` | gtk, iOS | reaches `onResume`, no crash, log markers, screenshot | M5d |

- **Expectations per build:** `linux-x86_64-gtk`, `linux-x86_64-headless`, `ios-arm64-uikit`,
  like the runtime suite's per-platform files. A test that passes on one build and fails on
  another points at a backend.
- **Headless as the deterministic oracle:** fixed text metrics make view-tree dumps exact, and
  the `record` display list shows what the Java code drew independent of any rasterizer.
  Rasterizers get their own golden images with a tolerance (anti-aliasing differs between GSK,
  CoreGraphics and Skia).
- **Test-APK tool:** builds authored APKs from a manifest, resources and Java with `aapt2`,
  `javac` and `d8`, in the harness. M2's dialog APK is its first user.
- **Ground truth:** an Android 10 x86_64 emulator on `/dev/kvm` (present in WSL; the emulator is
  not installed) for screenshots and view bounds of the same APKs.
- **Phone runner,** shaped by one VM per process, an ART FATAL killing Dine, and no fork:
  - a test mode in Dine, selected with `dvt launch --env`; the free account's 3-app limit rules
    out a separate test app;
  - tests pushed with `pymobiledevice3 apps push`, run in batches in one VM, results written to a
    file and pulled with `apps pull` (both unverified for a development-signed app on iOS 27);
    syslog markers only for progress and crash detection;
  - after a crash the harness relaunches Dine and resumes at the next test; Dine also restarts
    every N tests, because tests change VM-wide state;
  - a smoke tier for each change and a full tier run by hand.

## Not staged

- gtk startup critical: views-gtk runs print `gdk_monitor_get_geometry: assertion
  'GDK_IS_MONITOR (monitor)' failed`; cause not traced.
- TLS on iOS: app trust managers that call the default one's `checkServerTrusted` aren't
  covered, because wolfSSL's CertManager has no SecTrust path.
- Runtime work (dine-art) has its own list: `notes/art-findings.md`, Follow-ups.
- Apps that are keyboards (`InputMethodService` over the Wayland input-method protocol, gtk-only):
  after M9, if ever.
- Draw cost under `-Xint`, after M5d's frame-time measurement: a `Matrix` allocated per
  `ATLCanvas.save()` (the current matrix could live in C), Canvas ops batched into one JNI call per
  draw, JIT through StikDebug where the phone has it (`notes/meta.md`).
