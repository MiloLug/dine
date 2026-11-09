# ATL port: backends, milestones, tests

The plan for turning dine-atl (our ATL fork) into a framework that runs on any toolkit and OS
through pluggable backends. iOS (inside Dine) is the first new target. It defers to
`notes/meta.md` for the why and the iOS constraints, to `notes/art-findings.md` for the runtime,
and to `tests/README.md` for the map of test suites. Defects found outside a stage's own work
are coded in `notes/bug-tracker.md`, other work no stage owns in `notes/general-todo.md`; a stage
links them by code.

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
| [M5c](#m5c-text) | text | done |
| [M5d](#m5d-paths-nine-patch-layers-gravity-defied) | paths, nine-patch, layers; Gravity Defied | done |
| [M6a](#m6a-triage-and-fixes) | triage and fixes | done |
| [M6b1](#m6b1-content) | breadth: content | done |
| [M6b2](#m6b2-windows) | breadth: windows | done |
| [M6b3](#m6b3-windows-continued) | breadth: windows, continued | done |
| [M6b3a](#m6b3a-dialogs-on-the-phone) | dialogs on the phone | done |
| [M6b3b](#m6b3b-window-state-and-popups) | window state and popups | done |
| [M6b3c](#m6b3c-keyboard-screen-edges-config) | keyboard, screen edges, config | done |
| [M6c](#m6c-search-ahead-of-m7) | search ahead of M7 | planned |
| [M7](#m7-os-features) | OS features, items in `notes/os-features.md` | planned |
| [M8a](#m8a-apk-import-and-launch) | APK import and launch | planned |
| [M8b](#m8b-ios-lifecycle) | iOS lifecycle | planned |
| [M8c](#m8c-navigation-settings-store) | navigation settings store | planned |
| [M8d](#m8d-background-probes) | background probes | planned |
| [M8e](#m8e-several-apps) | several apps | replaced by the multi-app stages |
| [M9](#m9-heavy) | Compose, GL, WebView | planned |

## Decisions

- api-impl stays the one Java implementation of `android.*`, shared by every build.
- Everything that touches a UI toolkit, an OS feature or a native-code loader sits behind a
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
| `host` | process entry, VM creation, classpath, data dirs, launching an app and an activity, the container that holds activity windows (an app handle in every call and event; several apps per VM on cli and embedded; a container per task, multi-app MA6) | `gtk` (today's executable), `cli` (plain C entry, no glib), `embedded` (a library API Dine calls) |
| `loop` | the Android main thread's integration with the platform loop, worker-thread loops, delayed and cross-thread posts to the main thread | `glib`, `cfrunloop`, `poll` |
| `ui` | windows (Activity, Dialog, PopupWindow, WindowManager views), view nodes (children, frame, visibility, background, padding), toolkit widgets, focus, IME, touch and key input | `gtk`, `uikit`, `headless` |
| `gfx` | Canvas, Paint, Path, Bitmap, image decoding, text measurement and layout, fonts, NinePatch, RenderNode | `gsk` (GSK, Pango, GdkPixbuf), `coregraphics` (CoreGraphics, CoreText, ImageIO), `record` (a display list), later possibly `skia` |
| `os` | one sub-slot per OS feature, listed in `notes/os-features.md` | `desktop-linux`, `ios`, `none`, selectable per feature |
| `native` | loading the app's own `.so` files: bionic linker, libandroid (NDK), EGL and Vulkan surface shims | `bionic`, `none` |

| Build | host | loop | ui | gfx | os | native |
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
- **Threads:** ui and gfx calls happen on the app's Android main thread, but gfx's text calls take any
  thread (gsk gives each thread but the main one a Pango context of its own); uikit's layers replay
  coregraphics' finished display lists on UIKit's side, and list and bitmap refs drop on any thread.
  A `cfrunloop` instance binds to the run loop of the thread that prepares it. On iOS that is an 8 MiB pthread per app
  with its own run loop, not UIKit's main thread (1008 KiB stack with RLIMIT_STACK fixed at that, so
  ATL's Linux setrlimit and 6 MiB pregrow can't grow it, and whether iOS honours LC_MAIN
  `-stack_size` is unverified; secondary threads get 524 KiB; VM creation and `-Xint` Java would
  stall Dine's UI). `uikit` queues UIKit changes on it and sends them to UIKit's thread in one batch
  per layout or draw pass; a TextView's measurement waits for UIKit's thread (`dispatch_sync`), so
  UIKit's thread never waits for the Android one, while Paint measures with CoreText on the calling
  thread. Nothing on the Android thread drains an autorelease pool, so each uikit entry point that
  makes ObjC objects there wraps itself in `@autoreleasepool`. Bitmap canvases work on any thread.
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

Shared MessageQueue natives call the loop slot: the calling thread's main loop if it is an app's
Android main thread, schedule that loop's next dispatch (now, after a timeout, or never), wake it
from any thread, and the same three operations on a worker thread's loop. Each app's main thread
has its own main loop instance; the glib backend has one per process (gtk runs one app).

- `glib`: the GSource for the main thread; workers keep ALooper, because app native code under
  `native=bionic` can attach file descriptors to a Java thread's ALooper.
- `cfrunloop`: a run-loop source on the app's main thread runs the posts and, when a dispatch is
  pending, `Looper.loop()`; a run-loop timer carries the timeout, and a wake signals the source and
  wakes the loop. Worker threads run their own CFRunLoop with a timeout.
- `poll`: a mutex and condition variable per loop, for headless builds.

glib idle and timeout callbacks outside the gtk backend become loop-slot posts to the main
thread.

### Shared C without glib

- `util.h` and `util.c` split: JNI helpers, logging and NIO buffer helpers stay shared; the
  `atl_safe_gtk_*` helpers go to the gtk backend; intent serialization to GVariant goes to the
  `os` slot's `desktop-linux` backend (it exists for D-Bus and desktop notifications).
- `native_window.h` moves to the `native` slot.
- AssetManager: its few glib string helpers become libc.
- MemoryFile: GHashTable becomes a small map; `memfd_create` becomes a platform helper.
- SystemClock: `CLOCK_BOOTTIME` has no Darwin equivalent under that name; a platform helper picks
  the clock.
- ContentResolver's content-type lookup and ConnectivityManager's network monitor go to the `os`
  slot (MIME lookup, connectivity).
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
| `Paint.measureText` width estimate | text measurement from the gfx slot (done) | M5c |
| AlertDialog's three toolkit-bound Buttons | dialog content as data (see M2) | M2 |
| `GTK_FILE_CHOOSER_ACTION_*` ints in Activity | file-picker request kinds of the `os` slot | M7 (file picker) |
| Toast sent as a desktop notification | a ui-slot toast (done) | M6b3b |
| `"xdgportal"` location provider name | provider name from the `os` slot's location | M7 (location) |
| external intents sent over D-Bus from ContextImpl | the `os` slot's open links and files | M7 (open links and files) |

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
`notes/os-features.md`.

A triage stage (M6a, M6c) is graded by its table, a design choice (M5a's renderer, multi-app's design)
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
  (`atl_embedded.h`): ATL's VM options for the embedder's `JNI_CreateJavaVM`, `atl_embedded_vm_init`
  once, then per app `atl_embedded_main` on the thread that becomes that app's Android main thread.
  The start phases split for it: `atl_open_prefix`, `atl_vm_options`, `atl_vm_init`, per app
  `atl_app_prepare`; the Linux hosts keep `atl_prepare` and `atl_vm_start`.
- In Dine, artbridge stays the one VM owner (states none, creating, ready, failed). `dine_atl_run`
  creates the VM with ATL's options on an 8 MiB pthread and `ANDROID_LOG_TAGS=*:i`, and each later
  call starts its app on a new 8 MiB thread attached to that VM. It refuses while the first run
  starts and when the art screen made the VM, so ATL runs before the art screen in a launch: the
  art screen's VM lacks ATL's class and library paths, which are fixed at VM creation. An app's
  thread detaches from the VM when `atl_embedded_main` returns: ART aborts the process when an
  attached thread exits.
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
  `atl_vm_init` (a `ui_window` per task with several apps: multi-app MA6); `Display.density_dpi` feeds `DisplayMetrics.DENSITY_DEVICE` and
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
  (`ui_view_remove_child`, `ui_view_free`). The destructor runs on its app's cleanup thread and
  posts the free to the app's main thread. uikit frees a record in a queued block, after every
  block that names it. The same way: `Dialog.finalize` → `ui_dialog_free` (uikit's `ATLDialog`
  outlives it in the alert's blocks; its ref is freed after queued answers), and
  `ui_window_close` releases the uikit surface. `Drawable.native_unref` drops its ref on the
  finalizing thread (gsk hops to the main loop). Top-level posts run in the Android thread's base
  JNI frame, which never pops: their local refs must be deleted. An app's `ui_window` struct stays
  allocated (one per app).

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
- Open: the edge pans against an Android-hosted UIScrollView ([DINE-3](bug-tracker.md#dine-3))
  and an excluded span, by hand; touches on popovers on gtk; a GtkText's Tab moves GTK's focus,
  not Java's. Lists scroll since M6b1 (rows move without a relayout).

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
  end (GRAVITY is start: ATL ignores TextView gravity, [ATL-79](bug-tracker.md#atl-79)).
  `setCompoundDrawables` goes through `ui_text_set_drawables` (gtk draws them; the records backends
  keep nothing before M5b).
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
- Keyboard and focus: InputMethodManager holds the EditText the keyboard serves, the app's show
  request (AOSP's `mInputShown`: `hideSoftInputFromWindow` answers it, on gtk too) and whether the
  toolkit's keyboard shows. The keyboard follows Java's focus between EditTexts and hides when
  focus leaves them, on Done, and on Back (its down and up both go to a shown keyboard; gtk shows
  none, so Back reaches the app). A tap the toolkit takes itself gives
  the field the keyboard and Java's focus (`atl_upcall_edit_focus`); on headless a tap goes through
  Java (EditText takes `clickable` from its style by hand). gtk keeps GTK's focus with Java's
  (`ui_view_set_focused`), and `ui_edit_set_keyboard` does nothing there. Configuration says which:
  `ui_display.keys` gives gtk a hard QWERTY keyboard (QWERTY, keyboardHidden NO, hardKeyboardHidden
  NO) and records a soft one (NOKEYS, NO, YES); AssetManager matches `-qwerty`, `-nokeys` and the
  `-keys*` qualifiers by them.
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
- Open: Java's click and touch listeners on a field or a selectable
  TextView where the toolkit takes its touches (gtk; on iOS unchecked); a hardware keyboard types
  only into the field with the keyboard (no KeyListener); gtk multi-line; ClipboardManager (M7); `onCreateInputConnection` on EditText,
  BaseInputConnection (a stub whose own `Editable` class shadows `android.text.Editable`) and
  `onKeyPreIme`;
  AutoCompleteTextView's drop-down (PopupWindow, M6b3); on headless a field whose activity another
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
  Dialog windows lay out and draw in the app window's pass on records (M6b2), on uikit in an
  overlay container over the activity roots (M6b3a).
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
  a time, against `expectations/linux-x86_64-gtk.json`.
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
- Open: a clip under a perspective matrix on coregraphics; Choreographer stays timer-based (10 ms
  frames); views redraw whole, without dirty rects; `Canvas(Bitmap)` and Bitmap's pixel natives
  stay gtk-only; a background's offset while UIKit drives a scroll waits for Java's scroll report and
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

**Done when:** framework suite tests for `measureText`, `getTextBounds`, `getFontMetrics`, key
listeners and line limits pass on headless and gtk; M5a's view gains a `drawText` and a Layout's
`draw`, its golden is updated, and the phone's screenshot shows the text; on headless a letter typed
into the widgets APK's number field is dropped, a `maxLines` 2 field keeps two lines' height, and
Compose gets past `Layout.native_constructor`; on the phone a capped multi-line field shows the
cursor's line.

**Status: done (2026-10-25).** On headless `linux smoke draw` matches `draw.displaylist` with the
text and Layout ops, `linux smoke text` drops the letter typed into the number field and keeps the
capped field at two lines, and Compose passes `Layout.native_constructor` (its next stop is in
M6a); the framework suite's `TextTest`, `KeyListenerTest` and `LineLimitTest` pass on headless and
gtk, `InkBoundsTest` on gtk; `linux smoke` and the runtime suite pass. On the iPhone 13 `dbg smoke`
passes, `dbg ui screenshot` shows the draw screen's bold, serif italic, centered monospace and
stroked text and a two-line Layout, and the capped field grows to two lines (51 to 101 px) and
shows its last lines with the cursor. As built:
- Slot: `gfx_paint_set_typeface` (sans, serif or monospace; bold, italic), `gfx_text_font_metrics`,
  `gfx_text_measure`, `gfx_text_carets`, `gfx_text_bounds` (ink), `gfx_text_break_lines` (a
  paragraph's line ends), `gfx_canvas_draw_text`; positions in UTF-16 units, any thread.
- record: fixed metrics, the one home of headless text sizes (advance 0.6·size, ascent 0.95·size,
  descent 0.25·size), greedy breaks after the last space, else between code points. Headless
  TextViews measure through it: UTF-16 units, word breaks, and a `\n` breaks a plain TextView's
  line. `OP_TEXT` keeps a copy of the text; the dump prints `text "…" x,y` with the paint, `size`,
  `serif` or `mono`, `bold`, `italic` and `align`.
- gsk: Pango; each thread's context from its own default font map, with GTK's text settings as a
  label gets them (font, glyph rounding, font options), copied on GTK's thread at start and on each
  GtkSettings change; tabular digits, as the labels; ink bounds; default size 12; `Serif` and
  `Monospace` families, sans GTK's font. A fill draws the glyphs, a stroke their outline.
- coregraphics: CoreText on the calling thread at the paint's size in points (px over the screen
  scale), measured back in px. `cg_font` is the one font source, uikit's labels included: the
  system font, Times New Roman for serif (CoreText has no public call for the system's serif
  design), `kCTFontUIFontUserFixedPitch` for monospace. The replay draws a CTLine with the paint's
  color, fill or stroke, and align.
- Layout: one shared implementation (`src/shared/android_text_Layout.c`), a line array: paragraphs
  at `\n`, the backend breaks each, every line one `FontMetricsInt` height, horizontal positions
  from the carets, `draw` one text op per line. Ellipsize (start, middle, end) keeps each paragraph
  on one line, as Pango's does.
- Paint: `measureText`, `getTextWidths`, `getTextBounds` (rounded outward), `getFontMetrics`,
  `getFontMetricsInt` (Skia's rounding), `ascent`, `descent`, `breakText`. Typeface keeps a family
  and a style, Paint keeps its Typeface. TextView's TextPaint starts at the toolkit's size
  (`ui_text_get_size`) and follows `setTextSize` and `setTypeface`; `getTextSize` and
  `getLineHeight` read it.
- Key listeners: AOSP's `NumberKeyListener` (its filter), `DigitsKeyListener` and
  `DialerKeyListener` (`dine-atl/doc/AOSP.md`). EditText makes one from a number or phone input
  type or from `digits`, and puts it after the app's filters on the Editable only: a typed letter
  is dropped and `setText` keeps it, as on Android. In AOSP's order the pin field's `1a2345` passes
  LengthFilter(4) as `1a23`, then the digits filter: `123`. Text fields get no key listener (no
  TextKeyListener).
- Line limits: TextView's `maxLines`, `lines`, `minLines`, `maxHeight`, `minHeight`, `height` and
  `singleLine`, one maximum and one minimum mode as in AOSP. Line counts go to the toolkit
  (`ui_text_set_lines`), pixels clamp in `TextView.onMeasure`. headless caps and pads its line
  count; gtk caps the label's measured height at the line's Pango position, at the width GTK gives
  the label (a layout manager on it; GtkLabel's own line limit counts per paragraph), clips the box
  and pads through the label's height request; uikit sets the ATLLabel's `numberOfLines` with word
  wrapping (no ellipsis, as Android clips) and caps the measure; a multi-line UITextView scrolls, so a capped or fixed-height field follows the cursor.
- Metrics on the iPhone 13 (480 dpi) from DrawStayActivity's `widgets metric` lines: Paint's
  `ceil(measureText)` and line spacing beside a one-line TextView's measured size, and Roboto
  3.016's advances (no kerning) and hhea line spacing, px:

  | Text | Size | Roboto | Paint (CoreText) | TextView (UILabel) |
  |---|---|---|---|---|
  | Hello world | 14 sp | 211, 49.2 | 218, 50.1 | 218 × 51 |
  | The quick brown fox | 14 sp | 379 | 392 | 392 |
  | 0123456789 | 14 sp | 237 | 250 | 250 |
  | WWWWW iiiii | 14 sp | 248 | 262 | 262 |
  | Hello world | 18 sp | 271, 63.3 | 270, 64.4 | 270 × 65 |
  | The quick brown fox | 18 sp | 487 | 487 | 487 |
  | 0123456789 | 18 sp | 304 | 313 | 313 |
  | WWWWW iiiii | 18 sp | 319 | 328 | 328 |

  Paint and the labels agree to the pixel. Against Roboto, iOS text is 3 to 6 % wider at 14 sp and
  0 to 3 % at 18 sp, and its lines 2 % taller: a layout sized in dp around Roboto text can wrap or
  cut a word on the phone.
- Tests: the framework suite's `graphics` `TextTest` (relations only: each build has its own fonts),
  `InkBoundsTest` (expected to fail on headless) and `BlendModeTest#testStrokedText`, `text`
  `KeyListenerTest`, `LineLimitTest` and `TextViewTest` (a label's width against a Paint's on the
  main thread and another one, line counts); DrawActivity's text and Layout ops in
  `draw.displaylist`; `run-text.sh`'s pin letter and capped field.
- Open: line separators besides `\n` ([ATL-10](bug-tracker.md#atl-10)); a capped field in a scroll
  view on iOS ([ATL-14](bug-tracker.md#atl-14)); TextView's font family
  ([ATL-15](bug-tracker.md#atl-15)); Layout's spans and Builder (M9,
  [ATL-17](bug-tracker.md#atl-17)); iOS serif ([ATL-19](general-todo.md#atl-19)); Roboto widths on
  iOS ([ATL-20](general-todo.md#atl-20)); TextKeyListener ([ATL-21](general-todo.md#atl-21));
  CoreText off UIKit's thread ([ATL-22](general-todo.md#atl-22)).

#### M5d: paths, nine-patch, layers; Gravity Defied

- First: the CTFont cache on iOS ([ATL-18](general-todo.md#atl-18)).
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

**Status: done (2026-11-01).** On the iPhone 13 Gravity Defied runs from the AtlView tile and a
level plays by touch on its keypad; `dbg smoke` passes with `atl-gd`; the draw screen shows the
path in its clip, the arcs (the 360° one without a radius line), the gradients (the sweep clockwise
from 3 o'clock, as on Android), the layer group and the nine-patches. During play the records draw
passes run at about 60 per second, 2.2 ms each on average (`atl frames`), the Android main thread's
stack reaches 80 KiB of 8 MiB and `phys_footprint` 126-130 MiB (`dine_atl_probe`). On headless Gravity
Defied reaches `onResume` and its GameView keeps drawing, and AdaptiveIconDemo gets past
`Path.native_create_builder` to `Region.nativeConstructor` (M6a's Region finding); `linux smoke
draw` matches `draw.displaylist` with a path under a path clip, three arcs, a mirrored linear
gradient (then with a local matrix set after `setShader`), a sweep gradient, a `saveLayerAlpha`
group and a nine-patch stretched and shrunk; the graphics suite's
`PathTest`, `ShaderTest` and `NinePatchTest` pass on headless and gtk; `tools/dine test apps`
passes on headless (AdaptiveIconDemo expected to fail) and gtk; `linux smoke`, the framework
suites and the runtime suite pass. As built:
- CTFont cache ([ATL-18](general-todo.md#atl-18)): `cg_font` keeps 64 fonts by point size, family
  and style under a mutex, made outside it on a miss. DrawStayActivity's 1000 `measureText` calls
  took 49-51 ms without it and 7-8 ms with it (three runs each).
- Sans text on iOS uses San Francisco's tabular digits, as Roboto's are: Gravity Defied's keypad
  cells are `wrap_content` with a weight, so proportional digits shifted each row's dividers.
- Path: `src/shared/path.c`, verbs and points shared by every backend. Arcs, ovals, circles and
  round rects are cubics of at most 90°, with Skia's arcTo joins and round rect radius scaling;
  bounds are the control points' (as Android's), `contains` counts windings or crossings over 16
  lines a curve. Java edits a path only it holds (`path_edit` copies a shared one); lists hold refs.
  Path.java is one handle; FillType keeps `even_odd` and inverse. `gfx_canvas_draw_path` and
  `gfx_canvas_clip_path` (INTERSECT, DIFFERENCE): record's `path` and `clip_path` ops print
  SVG-like verbs, coregraphics builds a CGPath at replay, gsk a GskPath (`gsk_path_from_gfx`).
  Inverse fills: [ATL-26](bug-tracker.md#atl-26).
- `drawArc`: `gfx_canvas_draw_arc`, an `arc` op; each backend builds its shape with the shared
  path code: a sweep of 360° or more is the whole oval, any style (Android 10's hwui; Gravity
  Defied strokes its wheels so), else Skia's `CreateDrawArcPath` (`useCenter` adds the center and
  closes).
- Shaders: linear, radial and sweep gradients (`src/shared/shader.c`: stops normalized to 0..1,
  tile mode, local matrix), made on first use from the Java fields (`Shader.getNativeInstance`, a
  new one per local matrix) and synced into the paint before a draw (`Paint.getNativeInstance`);
  a list's paint copies hold a ref. coregraphics clips to the shape (a stroke's outline through
  `CGContextReplacePathWithStrokedPath`) and draws a CGGradient (conic for sweep), gsk pushes a fill
  or stroke and appends GSK's gradient. REPEAT and MIRROR are the stops repeated over the periods
  the shape covers (`shader_stops`). `Shader.TileMode` takes AOSP's order. BitmapShader and
  ComposeShader: [ATL-23](general-todo.md#atl-23); text with a shader:
  [ATL-25](bug-tracker.md#atl-25).
- `saveLayer` and `saveLayerAlpha` (every overload, through `Canvas.atlSaveLayer`): a save level
  whose first push is the layer. record's `layer` and `unlayer` ops; coregraphics a transparency
  layer at the paint's alpha and PorterDuff mode, its clips and layers ended last first, at a
  list's end too; gsk an opacity push ([ATL-27](bug-tracker.md#atl-27)).
- Nine-patch: `src/shared/ninepatch.c` reads a PNG's `npTc` as AOSP's NinePatchPeeker does
  (deserialized, then network to native order) into `Bitmap.getNinePatchChunk`; BitmapFactory fills
  `outPadding`. `Drawable.createFromResourceStream` and `createFromPath` decode the stream: a valid
  chunk makes a NinePatchDrawable, else a BitmapDrawable, no image null (the copy to external
  storage and the String constructor are gone, and with them the five defects listed above). The
  shared slicing (fixed parts shrink when the drawable is smaller) feeds record's bitmap and rect
  ops, which coregraphics draws, and gsk's NinePatchPaintable (`src/backends/gfx/gsk/ninepatch.c`).
  NinePatchDrawable has its padding, intrinsic size, a constant state sharing bitmap and chunk, and
  a tint as a SRC_IN color filter (`gfx_drawable_set_color_filter`); an invalid chunk throws, as
  AOSP's short one does.
- Gravity Defied: its GameView is a plain View that invalidates itself; it draws rects, arcs,
  lines, text and bitmaps, its buttons have nine-patch backgrounds, it keeps scores in SQLite; no
  Path, shader, `saveLayer` or SurfaceView, and its one `new Canvas(Bitmap)` is in `loadSprites`,
  which nothing calls. The dev payload bundles it (`build-ios-dev.sh`, dev builds only; the
  atl_test_apks README says its APKs allow redistribution, the upstream license is unchecked),
  AtlView has a "gravity" tile, `dbg smoke atl-gd` waits for `onResume` and an `atl frames` line.
  Headless (unpaced) frame counts and times vary run to run and say nothing about the phone.
- Frame stats (`test_hooks`): records' draw passes that drew a view print `atl frames <n> in <ms>
  ms, draw avg <x> max <y> ms` every 5 s while they come at most 500 ms apart.
- Widgets on iOS: iOS-styled. UIKit controls stay (M3, M4b; M6b fits them to the iPhone).
  Android-styled widgets (AOSP's Java widgets drawn through Canvas, the AOSP dialog layout path)
  stay a later option: their drawing runs in Java under `-Xint`, and they would undo M6b's UIKit
  matching.
- Apps suite: `tools/dine test apps [--gtk]` (`tests/harness/apps.py`, the table
  `tests/android-compat/apps/apps.toml`, per-build expectations): an app passes when its markers
  show, no fatal line does, and it keeps running 3 s past the last; `linux smoke gd` is its `gd`
  entry on gtk.
- M6a's themed backgrounds that stopped at `Path.native_reset` draw: the widgets ImageButton
  records its round-rect background and its image on headless.
- Gravity Defied builds a View on its own `game_thread`: uikit's queue (`uikit_enqueue`) takes any
  thread under a lock; the rest of the records off the main thread is
  [ATL-28](bug-tracker.md#atl-28).
- Its keypad's touch listener calls `View.performHapticFeedback`, which makes a Vibrator: the
  headless and iOS builds have no-op Vibrator natives (`src/shared/android_os_Vibrator.c`) until
  M7's Vibrator item.
- Open: resource density ([ATL-24](bug-tracker.md#atl-24)); the black bar across the top of
  Gravity Defied's screen on the phone, not looked into.

### M6a: triage and fixes

A cycle like the [pre-M4 batch](#pre-m4-batch-2026-10-21): a headless triage runs each
`atl_test_apks` APK outside M9 (Compose, GL) to its first stop. M6a fixes the stops before an
app's first input that fit the existing slots, and the findings below; every other one moves to
the stage that owns it (M6b, M7, M9) or, owned by none, to a code in `notes/bug-tracker.md` (a
defect) or `notes/general-todo.md`; a stop an M6b item names stays there. The
triage then runs again; the cycle ends when a triage finds only stops owned elsewhere.

Ran beside multi-app MA0 (`notes/steps.md`; MA0 done 2026-11-02, probes only, no product code).

**Done when:** the last triage's table (APK, stop before, stop after) is in this section, and each
stop and finding is fixed, named in a later stage or coded in `notes/bug-tracker.md` or
`notes/general-todo.md`.

**Status: done (2026-11-02).** The triage is `tools/dine test apps`: flower_finder, multitouch and
accelerometerdemo are rows beside Gravity Defied and AdaptiveIconDemo (demo_app is `linux smoke
demo`), and a failing row's expected-failure reason names its stop and its owner. The other
`atl_test_apks` are M9's: Compose, and the GL or native-library apps (gles3jni, glmark2, both
oculus apps, endless_tunnel, sdl2, unity). `linux smoke` (with `crash`), the framework suites on
headless and gtk, the apps suite on both, the runtime suite, `ios build-atl` (dev and release) and
`dbg smoke` pass. Headless triage:

| APK | Stop before | Stop after (owner) |
|---|---|---|
| demo_app | none | none |
| Gravity Defied | none | none |
| AdaptiveIconDemo | `Region.nativeConstructor` in AdaptiveIconDrawable's constructor | none |
| flower_finder | `Region.nativeConstructor` (material's FloatingActionButton) | `Resources$NotFoundException` for `drawable/rose`, which only `drawable-v24` has ([M6b1](#m6b1-content) `SDK_INT`); gtk stops there too |
| multitouch | `NoSuchMethodError` for `ActionBar.setHomeButtonEnabled` in `onCreate`, then a CheckJNI abort | the same error, through the uncaught handler (M6b1 ActionBar) |
| accelerometerdemo | `SensorManager.register_accelerometer_listener_native` | the same (M7 sensors); gtk reaches `onResume` |

As built:
- App exceptions in C: where Android's main loop would see one (lifecycle calls, app startup, the
  main looper, the layout upcall, insets, gtk's signal callbacks and host actions),
  `exit_on_exception` (`src/api-impl-jni/util.c`) gives it to the thread's uncaught handler, whose
  default prints it and exits 10 (libcore's `hacky_uncaught_exception_handler`); it ends the process
  when an app's handler returns. It runs in place inside the natives that start, finish or resume
  an activity too: Android runs those lifecycle calls after the Java caller returns. A native whose
  Java caller should see its exception returns it pending. `linux smoke crash` throws in
  `onCreate`, `onResume`, a posted Runnable and a started activity's `onCreate`; the apps harness
  counts the handler's line as fatal and reports the exception under it.
- Region: `src/shared/region.c` on every build, y-bands of x-spans; `setPath` takes the pixels
  whose centres the fill covers, as Skia's non-antialiased fill, over the path's bounds when no clip
  is given (`Path.op`). The graphics suite's `RegionTest`.
- Canvas: `new Canvas()` draws nowhere and locks no bitmap. ATLCanvas keeps each save level's clip
  bounds in device space: `clipRect` and `clipPath` return whether any clip is left,
  `getClipBounds` maps the bounds back and rounds them as Android does. A view's draw starts at the
  view's size (gtk's one canvas per widget is reset before each draw), every other canvas at its
  target's size (`new Canvas()` at 0x0); `setBitmap` resets the stack. A DIFFERENCE keeps the bounds, and clears them only when its shape is a rect
  under a rect-keeping matrix that covers them.
- Rotations from degrees (Matrix's rotate calls, record's canvas rotate) snap a sin or cos within
  1/4096 of 0 to 0, as Skia's `SkScalarSinCos` (`src/shared/matrix.h`); `setSinCos` keeps its values.
- Keys: `KeyEvent.isConfirmKey` takes SPACE and NUMPAD_ENTER (Android 10); a NUMPAD_ENTER no view
  takes goes again as ENTER with `FLAG_FALLBACK` (Android 10's `Generic.kcm`), beside ATL's ESCAPE
  as BACK; gtk sends keypad Enter as NUMPAD_ENTER, as uikit does. Android 10's TextView reads only
  ENTER, so an EditText gets keypad Enter through its key listener and the keymap; unchecked, and
  not on the phone (no hardware keyboard).
- Drawables: DrawableWrapper's constant state (InsetDrawable, ClipDrawable, whose `mutate` takes a
  state of its own); AnimatedVectorDrawable, ColorStateListDrawable, PictureDrawable and
  ScaleDrawable copy through a state that makes a new one. `createFromXml` inflates `level-list`,
  `animation-list` (frames, durations, oneshot) and `<nine-patch>` (its `src`'s chunk; AOSP's
  XmlPullParserException without one).
- Color filters and tints on bitmaps: BitmapDrawable and NinePatchDrawable keep a color filter, a
  tint list and a tint mode on their native drawable (a filter wins over the tint, as AOSP's draws;
  a blend mode and color, or a color matrix). ImageView keeps its color filter (`setColorFilter(int)`
  is SRC_ATOP) and image tint and puts them on its drawable as AOSP's `applyColorMod` and
  `applyImageTint`. Every backend applies a filter in Skia's order and formulas (`notes/decisions.md`,
  blend modes). `linux smoke draw` has a filtered BitmapDrawable and a tinted ImageView; the phone
  shows both tinted.
- gtk frees a view's padding, background and text color CSS providers when it replaces them (no
  check counts them).
- Open: the callbacks that print an exception and go on stay so (measure, draw, input, click,
  dialog result; the layout upcall exits): multi-app's per-app handler takes them up, and uikit's
  input prints where gtk's signal callbacks exit. Region's `setPath` rasterizes every row of the
  path's bounds when no clip limits them.

### M6b: breadth

Comes after multi-app MA1 and MA2a (`notes/steps.md`): app state that M6b adds goes into the app
record (`notes/multi-app-support/design.md` "App record"), not into process-wide statics. Split
into M6b1 (what draws inside an app's window) and M6b2 (windows and window state), built one
after the other in one session; the user moved M6b2's later steps into M6b3.

#### M6b1: content

- ActionBar with Android's API as a no-op: ATL's `ActionBar` was an empty class and
  `getActionBar()` returned null, so multitouch stopped at `ActionBar.setHomeButtonEnabled`, and a
  method alone would only move the failure to a NullPointerException. A bar on screen (title, Up,
  tabs, options menus) is [ATL-42](general-todo.md#atl-42).
- `SDK_INT` and `RESOURCES_SDK_INT` 29: androidx reads gesture insets and exclusion rects only
  from 29 (`notes/nav-gestures.md` Reach); flower_finder stops at its images, which only its
  `drawable-v24` has; runtime permissions (23) get a result; [ATL-4](bug-tracker.md#atl-4)'s
  navigation values. From 33 androidx calls `getOnBackInvokedDispatcher`, which ATL lacks:
  [ATL-43](general-todo.md#atl-43), with the next raise.
- `Canvas(Bitmap)` and Bitmap's pixel natives on headless and iOS (VectorDrawable, which always
  draws through a bitmap, AdaptiveIconDrawable's mask, `Bitmap.createBitmap` from a source
  bitmap, Compose's VectorPainter).
- Drawables, themes and styles, AdaptiveIconDemo; BitmapShader and ComposeShader
  ([ATL-23](general-todo.md#atl-23)); `RegionIterator`; `createFromXml`'s `scale`, `clip`,
  `rotate`, `color`, `animated-selector` and `animated-rotate`; InsetDrawable's insets;
  ScaleDrawable's draw; color filters other than PorterDuff on bitmaps; `BitmapDrawable.getPaint`,
  a new Paint per call.
- ListView and RecyclerView (`views_widgets_samples_flower_finder.apk`). On uikit, lists need a
  measure cache: each measured text is one hop to UIKit's thread.
- Styled text on iOS, with real Spanned support: ATL's `Html.fromHtml` kept the HTML tags in the
  string; gtk rendered them as Pango markup (`ui_text_set_markup`), uikit showed them literally.

**Done when:** at `SDK_INT` 29 the framework suites (headless, gtk, one VM), `linux smoke`, the
package suite and the runtime suite pass; multitouch and flower_finder reach `onResume` on
headless and gtk, or their reason names a later stage's stop (M6a's rule); the graphics suite
reads back pixels drawn through `Canvas(Bitmap)`, VectorDrawable, the new XML drawables and color
matrix filters on headless and gtk; `linux smoke draw` shows the adaptive icon masked; a ListView
and a GridView scroll with no row laid out again; the controls dump shows `Html.fromHtml`'s spans
as text runs; on the phone `dbg smoke` passes with a bitmap pixel line, a list and styled text,
and the release build builds.

**Status: done (2026-11-03).** At `SDK_INT` 29 the framework suites (headless, gtk, one VM: 235 of
236, the one an expected failure), `linux smoke` (17 checks, with `lists`), the package suite, the
runtime suite, `test unit`, `ios build-atl` (dev and release) and `dbg smoke` (15 scenarios, with
`atl-lists`) pass. On the iPhone 13 flower_finder lists its 11 flowers with their images, the
controls screen shows `BOLD & CAPS` with "BOLD" bold (the build before showed
`<b>BOLD</b> &amp; CAPS`), and the draw screen the masked adaptive icon. API 29 triage (headless):

| APK | Stop before | Stop after (owner) |
|---|---|---|
| demo_app | none | none |
| Gravity Defied | none | none |
| AdaptiveIconDemo | none | none; the icon is masked |
| flower_finder | `Resources$NotFoundException` for `drawable/rose` (only `drawable-v24`) | none; on the phone its LiveData list was empty until the lifecycle callbacks below |
| multitouch | `NoSuchMethodError` for `ActionBar.setHomeButtonEnabled` | none |
| accelerometerdemo | `SensorManager.register_accelerometer_listener_native` | the same (M7 sensors); gtk reaches `onResume` |

The level raise cost 5 fixes of the 15 the plan allowed: the installed `framework-res.apk` was
stale (meson's target had no input), `ContextImpl.getTheme` picks Android's default theme for the
target level ([ATL-45](bug-tracker.md#atl-45): API 24's step is missing), `WindowInsets.inset`,
gtk's min-lines height after the theme change, and the activity lifecycle callbacks.

As built:
- ActionBar: AOSP 10's abstract API; `getActionBar()` is a per-activity `ATLActionBar` that
  keeps its values and draws nothing ([ATL-42](general-todo.md#atl-42)), null when the theme's
  window features have no action bar (`windowNoTitle`, `windowActionBar`, as PhoneWindow).
- Level: `ro.build.version.sdk` 29 in `SystemProperties.java`; bionic still says 21
  ([ATL-44](bug-tracker.md#atl-44)). `requestPermissions` answers through
  `onRequestPermissionsResult` from `checkSelfPermission`; `Context.getColor` and
  `getColorStateList` take the theme. framework-res is regenerated with gestural navigation and a
  20dp back inset ([ATL-4](bug-tracker.md#atl-4) fixed).
- Lifecycle callbacks: native lifecycle calls go through `Activity.atlPerform*`, which call the
  application's and the activity's API 29 pre and post callbacks around the app's method; the base
  `on*` methods call the plain ones (androidx's lifecycle needs both).
- Text after the M6b review: `TextView.setText` keeps AOSP's buffer types and ChangeWatcher, `Html`
  is AOSP 10's over TagSoup, and `View.layout` takes `setFrame`'s rule (any changed coordinate).
- Blend modes are SkBlendMode's on every draw, layer, ComposeShader and color filter
  (`notes/decisions.md`); phone views approximate four of them ([ATL-52](bug-tracker.md#atl-52)).
- Bitmaps: a `gfx_bitmap` is shared premultiplied words on
  every backend (`src/shared/bitmap.c`), stored per config as Android 10 does; display images are
  copies per change. A Canvas(Bitmap) draws into the words at once through its own context: record
  and gsk with cairo, CoreGraphics a CGBitmapContext with per-pixel blends where CG has none. A
  Picture records the Canvas calls and replays them. Headless bitmaps draw no text
  ([ATL-46](bug-tracker.md#atl-46)); a Canvas(Bitmap) draws no views or Layout text
  ([ATL-47](bug-tracker.md#atl-47)).
- Shaders and drawables: BitmapShader and ComposeShader on record, gsk and coregraphics (their
  approximations: [ATL-48](bug-tracker.md#atl-48)); AOSP's AdaptiveIconDrawable draw; Scale,
  Inset, Clip, Rotate, AnimatedRotate, AnimatedStateList and Transition drawables from XML; color
  filters are `struct gfx_color_filter` (PorterDuff or a 4x5 matrix); RegionIterator.
- Lists: AOSP's layout-required flag; `ui_view_layout` takes `relayout`; offsets move and
  invalidate without a layout; uikit pushes frames moved outside a layout pass. Records cache text
  measures (512 slots under a mutex, keyed on every input and the text runs; the frame stats line counts
  the cached ones).
- Styled text: AOSP 10's `Html` with its TagSoup parser; TextView sends its CharacterStyles as runs
  (`ui_text_set_styled`), drawn as Pango attributes on gtk and attributed strings on uikit;
  headless prints `textruns:`. allCaps keeps the runs when the length stays. Links take no taps
  ([ATL-49](general-todo.md#atl-49)); string resources stay plain ([ATL-50](general-todo.md#atl-50)).
- Tests: framework `ActionBarTest`, `PermissionTest`, `SystemResTest`, `LifecycleCallbacksTest`,
  `ThemedColorTest`, `BitmapTest`, `VectorDrawableTest`, `BitmapShaderTest`, `PictureTest`,
  `XmlDrawableTest`, `ColorFilterTest`, `RegionTest`, `ListScrollTest`, `HtmlTest`, `SpanTest`;
  `run-lists.sh` (`linux smoke lists`, `dbg smoke atl-lists`); `run-controls.sh` checks the bold run;
  `draw.displaylist` has the masked icon and a greyscale bitmap; `atl-draw` reads a bitmap pixel and
  redraws an ImageView's bitmap 50 times.
- AOSP provenance: `dine-atl/doc/AOSP.md`.
- Open: flower_finder's list scrolled by hand on the phone (the debug agent has no drag).

#### M6b2: windows

- Window attributes and screen brightness on every build: `Window.setAttributes`, `setLayout` and
  `setGravity` through the ui slot (with the dim amount); brightness
  (`LayoutParams.screenBrightness`) as window state of the shown activity, sent through the host
  slot as keep-screen-on is. The gtk host sets the desktop's through GNOME's power settings over
  D-Bus, else `/sys/class/backlight`; on iOS it's a no-op ([DINE-11](general-todo.md#dine-11)): no
  public API withdraws an app's request, so the user's level wouldn't come back.
- A second layout root over the container on records, for Dialogs with a content view (they show
  nothing on headless and uikit): laid out, drawn and touched over the activity in the app
  window's pass. [M6b3a](#m6b3a-dialogs-on-the-phone) shows it on uikit.

**Done when:** `linux smoke dialog windows` pass, the dialog check with its content run
(`dialog-content.viewtree`); the framework `windows` suite passes on headless, gtk and one VM;
every earlier suite passes against expectations that weren't loosened; on the phone `dbg smoke`
passes; both builds build.

**Status: done (2026-11-03).** Built: AOSP 10's `WindowManager.LayoutParams` (constants, fields,
constructors), `ui_window_set_layout`, `host_screen_brightness` on every host (the gtk host saves
and restores the desktop's level; the embedded host's is a no-op, DINE-11); records lay out a shown
Dialog's content view over the activity (Gravity.apply, a floating window's least width, the
window's frame to Java, touch routing with outside touches to a touch-modal dialog, the dump's
`window dialog` line), the cli's `dump` and `tap <text>`, AOSP's dialog and alert dialog themes,
the floating window layout and `Window.shouldCloseOnTouch`; uikit draws content dialogs from
M6b3a on. Checks: the framework suites (headless and one
VM 245/246, gtk with `DialogTest`'s centering and least-width cases as expected failures: gtk
places and sizes a dialog's window itself), the apps and package suites, `linux smoke` (18, with
`windows` and the dialog content run), `test unit`; on the iPhone 13 `dbg smoke` (16, with
`atl-windows`) and the dev and release builds. Open: in a dialog's content `getRawX`/`getRawY`
are window-local while `getLocationOnScreen` adds the window's origin (`struct atl_pointer` has no
raw coordinates).

After the M6b review, dialogs are windows in each app's registry (`notes/decisions.md`): AOSP's
token rule (BadTokenException, WindowLeaked at the activity's destroy), shown with their activity
and task; gtk draws them inside the app's window, so `DialogTest`'s centering and least-width cases
pass there. Checks after the review fixes: framework headless, gtk and one VM 312 of 313 (1
expected), apps 4/5 (1 expected) and 5/5 on gtk, package 48/48, `linux smoke` 18, `test unit`; on
the iPhone 13 `dbg smoke` 16 with `widgets pixels ok`, `widgets blend ok`, `widgets layers ok`.

#### M6b3: windows, continued

- Showing a Dialog's content view on uikit: an overlay container over the app surface, the dim,
  touches, the first responder for its fields, Dine's status-bar strip dimmed.
- Builder's single and multi choice, `setAdapter` and `setView` content, with native chrome per
  backend (UIKit, GTK, fixed metrics on headless).
- Dialog windows get what the shown activity's window has: keep-screen-on and fullscreen,
  ViewTreeObserver observations, insets for Dialog and WindowManager roots, exclusion rects.
- PopupWindow, `WindowManager.addView` (as entries of the window registry), ListPopupWindow,
  AutoCompleteTextView's drop-down; PopupMenu (a native menu), Toast.
- Configuration changes: no resize or trait-change relayout (portrait only).
- The UIKit pieces the uikit backend adds around Android's views match the iPhone's own in light
  and dark: the Done bar above the number and phone pads (M4c) looks off next to the keyboard
  (probably should match iOS style, for example glass). The user's reference: a number pad in
  another app shows a round glass X button floating above the pad's top-right corner, with no
  bar ("The approve should look similar too"), so the Done bar becomes a round glass checkmark.
- Keyboard avoidance: a keyboard covers a field low on the screen, since the surface has a fixed
  size and `atl_window_insets` no IME edge. The window's `softInputMode` (adjustPan, adjustResize;
  `Window.setSoftInputMode` does nothing, the manifest's is parsed) and the keyboard's frame from
  Dine.
- Immersive mode and status-bar insets for a window that covers the whole screen
  (`notes/nav-gestures.md` Immersive mode). The Dine setting that hides the home indicator for
  every app is [M8c](#m8c-navigation-settings-store)'s.

**Done when:** `linux smoke dialog windows keyboard nav config` pass with their new goldens; the
framework `windows` suite passes on headless, gtk and one VM; `dialog-gtk`, `windows-gtk` and `gd`
pass; every earlier suite passes against expectations that weren't loosened; on the phone
`dbg smoke` passes with a content dialog, a choice dialog, a popup, a menu, a toast, window state
and the immersive steps, and both builds build; the hand checks are listed in the Status block.

Split into three sub-stages built in order (the user's choice, 2026-11-07); the Done-when above is
their union. Plan: `~/.claude/plans/glowing-singing-raccoon.md`.

**Status: done (2026-11-08):** M6b3a, M6b3b and M6b3c below.

##### M6b3a: dialogs on the phone

- uikit shows the registry's roots: an overlay container over the app surface, a dim, touches,
  the first responder for a dialog's fields, Dine's status-bar strip dimmed.
- AlertDialog's `setView`, single and multi choice, `setAdapter`, `setCustomTitle` and
  ProgressDialog, with native chrome per backend. The user: "try your best to make the dialogs
  native-looking for the modern ios (glass etc)". Plain alerts stay `UIAlertController`; the
  others get a glass panel that mirrors it, with native rows and checkmarks for string choice
  lists and native progress views.
- Gravity Defied calls `Builder.setSingleChoiceItems`, `setView`, ProgressDialog and Toast
  (dexdump, 2026-11-07); `gd` passes because its smoke reaches none of them.

**Done when:** `linux smoke dialog dialog-gtk` pass with the view, choice and progress runs; the
framework `windows` suite passes on headless, gtk and one VM; `gd` and every earlier suite pass
against expectations that weren't loosened; on the phone `dbg smoke` passes with
`atl-dialog-content` and `atl-dialog-choice`, `atl-dialog` and `atl-dialog-keep` unchanged; both
builds build and the release build has none of the new test lines; the hand checks are listed in
the Status block.

**Status: done (2026-11-07).** Built:
- uikit draws the registry's roots: an overlay container is the surface's top subview, activity
  roots go below it; one container per window holds its dim, an alert's panel and the root at
  its records frame. Touches on the dim are the window's outside touches; its accessibility element
  "Dismiss" taps outside the window. VoiceOver stays in the topmost touch-modal window. A root
  takes the keys while it is the topmost focusable window; Dine dims its status-bar strip by the
  dims' amount (`ATLSurface atlDimChanged:`).
- AlertDialog: AOSP 10's Builder and AlertDialog API; plain or panel at the first show (the
  `notes/decisions.md` registry entry). Panels: glass, iOS 27's alert metrics measured on the phone
  (320 pt, 34 pt corners, left-aligned Headline title and Subheadline message, 48 pt capsule
  buttons in the tertiary fill, side by side when two fit, the system dim), rows with the system
  checkmark for string choice lists, `UIActivityIndicatorView` / `UIProgressView` for ProgressDialog;
  `setView`, `setAdapter` and `setCustomTitle` content is Android's, 16 pt in from the panel's sides.
  Rows past the screen scroll; Android content keeps half the height. gtk draws a panel box in the
  app window's overlay, headless fixed metrics with `dialog:` lines and the cli's `answer <label>`.
  The panel's light or dark look follows the Android theme (`isLightTheme`), so its content stays
  readable. ProgressDialog: AOSP's API; progress from any thread.
- Dialog runs `onCreate` once, as AOSP's `dispatchOnCreate`.
- Backgrounds pad and size their views as Android 10's
  ([ATL-64](bug-tracker.md#atl-64), 2026-11-08): `setBackgroundDrawable` takes the drawable's
  padding and an XML padding attribute wins edge by edge; a view is at least its background's
  least size, toolkit-measured text views and images included (`minWidth` applies to them);
  padding changes lay out again. Layer-lists nest or stack (ripples stack), selectors report
  padding; a window's padding is its background's and the theme's background goes on once, so a
  plain `Dialog` shows its card behind the whole content. On the iPhone a Button with a background
  and Android padding drops UIKit's own insets; one without padding keeps them
  ([ATL-66](bug-tracker.md#atl-66)). Tests: `graphics` `DrawablePaddingTest` and
  `BackgroundPaddingTest`, three `DialogTest` cases, `run-controls.sh`'s "framed" button and
  `dialog-content.viewtree`, each failed under its mutation.
- Checks (2026-11-08, with the background fix): framework 349/350 on headless, gtk and one VM
  (the `windows` suite 27/27, with `AlertContentTest`), apps 4/5 and 5/5, package 48/48,
  `linux smoke` 18 (`dialog` with the choice, progress and view runs, `-c` panel runs and
  `dialog-view.viewtree`; `dialog-gtk`),
  runtime and `test unit` as before; on the iPhone 13 `dbg smoke` 21 with `atl-dialog-content`,
  `atl-dialog-view`, `atl-dialog-choice`, `atl-dialog-progress`, `atl-dialog-stack`; dev and
  release builds, the release library without the `dialog: chrome measured` line.
- The chrome check (`dialog: chrome measured … ok`) catches drift between records' measure and the
  shown panel's layout, not UIKit's own fitting.
- Hand checks: screenshots in dark mode of a content dialog, a `setView` panel, an adapter list and
  a progress bar. Not done: light mode, VoiceOver, Dynamic Type, a long list on the phone.
- Open: "Dismiss" shows also when the dialog doesn't cancel on an outside touch; an app's own
  `getListView().setItemChecked` after the show doesn't reach the native rows; a panel ignores
  `Window.setLayout`'s width; AppCompat and Material dialogs draw Android's own layouts;
  `Dialog.create`, `onStart` and `onStop` are missing ([ATL-65](general-todo.md#atl-65)); a
  panel's field pans above the keyboard by the dialog theme's adjustPan (M6b3c), unchecked on
  the phone.

##### M6b3b: window state and popups

- Dialog windows get the shown activity's window state: keep-screen-on, fullscreen, brightness,
  ViewTreeObserver observations, insets clipped by their frame, exclusion rects.
- `WindowManager.addView` roots, PopupWindow, ListPopupWindow and AutoCompleteTextView's
  drop-down as registry entries on every backend; PopupMenu as a native menu; Toast.
  PopupWindow puts its background straight on the app's content view today, so a padded popup
  background replaces the content's padding; AOSP's background wrapper view fixes that.

**Done when:** `linux smoke windows windows-gtk views-gtk gd` pass with the state, popup, menu
and toast steps; the framework `windows` suite passes on headless, gtk and one VM; on the phone
`dbg smoke` passes with `atl-popup` and the extended `atl-windows`; both builds build.

**Status: done (2026-11-08).** Plan: `~/.claude/plans/humble-knitting-firefly.md`. Built:
- Window state per window: a dialog's keep-screen-on, fullscreen, brightness and exclusion rects
  are kept from its `onCreate` on; the drawn windows' together reach the host (any keeps the
  screen on, the topmost brightness, every rect offset by its window's frame). A dialog's
  ViewTreeObservers fire in the app window's pass while it shows. Insets reach each drawn window,
  clipped by its frame (none before its first placement).
- `WindowManager.addView`: the view is the root of a registry window (`Window.atlAddView`) with
  AOSP's token rules; tokens are per Window (`View.getWindowToken`, `getApplicationWindowToken`,
  `WindowManagerGlobal.getWindowView`). A sub-panel lays out in its parent's frame, layers above
  it, hides with it and goes when it is removed; one on the activity stays under the windows over
  it; toasts and overlays layer above application windows. Watching windows get `ACTION_OUTSIDE` (records, gtk, and on uikit also from native
  controls). On uikit a touch-modal window without a dim catches the touches outside it, and a
  `NOT_TOUCHABLE` one lets them through.
- PopupWindow is AOSP 10's (no transitions); ListPopupWindow and AutoCompleteTextView have their
  stubbed lines back; `dispatchKeyEventPreIme` runs before the IME takes Back, so Back closes a
  drop-down first.
- PopupMenu is native per backend: a UIMenu at the anchor (Experiment B's first candidate:
  a clear button with `performPrimaryAction`), a GtkPopoverMenu, `menu:` lines on headless
  answered from `ATL_DIALOG_ANSWERS`. Disabled, checkable and submenu items; an open menu takes
  Back.
- Toast: AOSP 10's API; each app's queue shows one at a time for 2 or 3.5 s; text toasts are a
  glass capsule in a window of their own above the alerts on iOS, an OSD label on gtk, `toast:`
  lines on headless; `setView` toasts are TYPE_TOAST windows. A toast made while its app is in the
  back never shows, and one up goes when its app goes to the back or its window closes.
- Upstream's gtk-only WindowManagerImpl, PopupWindow and PopupMenu natives are gone.
- `src/api-impl/meson.build` lists every api-impl Java source: one it misses compiles only through
  javac's source path, and an edit to it rebuilds nothing.
- Tests: framework `WindowStateTest`, `WindowManagerTest`, `PopupWindowTest`, `PopupMenuTest`,
  `ToastTest`; windows APK `StateActivity`, `OverlayActivity`, `PopupActivity`, `MenuActivity`,
  `ToastActivity`, `SelfActivity` (`run-windows.sh`, new `linux smoke windows-gtk`); `dbg smoke`
  `atl-windows` runs StateActivity, new `atl-popup`. Each new check failed under its mutation.
- Checks (2026-11-08): framework 373/374 on headless, gtk and one VM (the `windows` suite 51/51),
  apps 4/5 and 5/5, package 48/48, `linux smoke` 19, runtime as before, `test unit`; on the iPhone
  13 `dbg smoke` 22 with `atl-popup` (a toast that goes with its app's window included) and
  `atl-windows`; dev and release builds, the release library without the `menu:` and `toast:`
  test lines.
- Hand checks (iPhone 13, dark mode): the menu (Paste greyed, Bold checked, More with its
  chevron); Copy picked by hand: UIKit runs the item's action at the tap, 1.2 s before the end
  animation completes, so Java gets the item, then the dismissal (the debug agent can't pick
  UIMenu items); the toast capsule bottom-centre with Dine's status-bar strip unchanged. Not done:
  light mode, a toast over a plain alert, VoiceOver.
- Open: a `setView` toast draws under a presented plain alert; popups and drop-downs follow their
  anchor in a panned or resized window (M6b3c), unchecked on the phone; on iOS the agent's
  accessibility taps still reach Android views under an open menu (real touches close it); a text
  toast whose app comes back to the front mid-toast stays hidden; on gtk the toast's label goes
  above an application overlay (AOSP keeps toasts under them); a popup that goes with its removed
  dialog keeps its tree observers on the app window; [ATL-67](bug-tracker.md#atl-67).

##### M6b3c: keyboard, screen edges, config

- The Done bar becomes a round glass button.
- `atl_window_insets` gets IME and status-bar edges; the window size is per app.
- Keyboard avoidance (`softInputMode`), immersive mode and status-bar insets, night changes
  delivered to running apps (with a dev agent verb that switches the appearance).

**Done when:** `linux smoke keyboard nav config` pass with their new goldens; the framework
`windows` suite passes on headless, gtk and one VM; on the phone `dbg smoke` passes with
`atl-keyboard` (or its hand check), `atl-config`, the extended `atl-nav`, and `atl-text`
unchanged; both builds build; the hand checks are listed in the Status block.

**Status: done (2026-11-08).** Plan: `~/.claude/plans/sequential-growing-pancake.md`. Built:
- The pads' return key is a round glass button (`glassButtonConfiguration`) above the pad's
  top-right corner, in a clear accessory, with a symbol per action (Done `checkmark`, Next
  `arrow.down`, Go `arrow.right`, Search `magnifyingglass`, Send `arrow.up`, else `return`); its
  accessibility label is the action's title.
- `atl_window_insets` has status-bar and IME edges. Each app has its window size and night
  (`struct atl_app`): every app's embedded config sets them, `atl_nav_set_window_size` and
  `atl_nav_set_night` change them. records, the inset clip, exclusion and the uikit panel cap read
  the app's size; `getWindowVisibleDisplayFrame` leaves out the bars and the keyboard.
- Keyboard avoidance: Dine sends the keyboard's overlap as the IME inset of the app in front.
  `softInputMode` comes from the manifest, the theme (dialogs) and `Window.setSoftInputMode`;
  unspecified resizes while a scroll container shows (AOSP's flag; ScrollView takes
  `scrollViewStyle`, as AOSP's). adjustResize lays the window out above the keyboard and clips its insets
  there, and ScrollView scrolls a focused child that showed into the smaller room (AOSP's
  `onSizeChanged`). adjustPan moves the root by a per-window offset (`windows.c`: draw, touch,
  `getLocationInWindow`), from a port of `scrollToRectOrFocus` for the focused view.
- Immersive: `setSystemUiVisibility`'s flags, `setDecorFitsSystemWindows` and `InsetsController`'s
  `hide`, `show` and behavior reach Dine in `struct ui_frame` (fullscreen, `cover_top`, hide
  navigation, immersive). With `cover_top` Dine pins the window to the screen's top and sends its
  size and the status-bar inset (`notes/nav-gestures.md` Immersive mode); the home indicator hides
  with hide navigation, and immersive defers the hidden bars' edges instead (on iOS 27 a hidden
  indicator lets the first swipe through the deferral). A hidden bar's visible inset is 0.
  `getWindowSystemUiVisibility` and `OnSystemUiVisibilityChangeListener` are real.
- Behind the window uikit paints the shown activity's background color (its ColorDrawable, else
  the theme's `colorBackground`, in `struct ui_frame`), so a keyboard's rounded corners show the
  app's color, not Dine's.
- Night reaches running apps. "Night" is Android's name for dark mode: the night bits of
  `Configuration.uiMode`, `UI_MODE_NIGHT_YES` (0x20, 32) dark and `UI_MODE_NIGHT_NO` (0x10, 16)
  light, which `values-night` resources and AppCompat's DayNight follow; ATL's API and the test
  lines keep Android's name and values. Dine's key window trait change goes to every running app, gtk's
  portal to its app, the cli's `night 0|1` to its app. The app's configuration and every Resources
  it made take it, then Application and its registered `ComponentCallbacks`, and the activities
  whose manifest covers uiMode with their view tree; the others log that they keep their
  configuration. The Resources caches get Java change bits and drop a drawable on any change
  (`CONFIG_NATIVE_BITS` is empty, so native bits would be 0). Dev agent:
  `ui appearance light|dark|system`.
- Tests: framework `windows` `SoftInputTest`, `SystemUiTest` (also the frame's background),
  `ConfigTest`; windows APK
  `PanActivity`, `ResizeActivity`, `UnspecifiedActivity`, `ConfigActivity`, `PlainConfigActivity`
  (`run-keyboard.sh` with `keyboard-pan.viewtree` and `keyboard-resize.viewtree`, `run-config.sh`;
  `linux smoke keyboard config`); nav APK `ImmersiveActivity` (orange and teal bands at its top
  and bottom) and `run-nav.sh`'s edges, size and immersive steps; `dbg smoke` `atl-keyboard`, `atl-config` and `atl-immersive` (the extended
  `atl-nav`: a second nav tile would only bring the running nav app to the front); `atl-keyboard`
  and `atl-nav` also fail when a container's show resizes a window below the status bar. Each new
  check failed under its mutation, on the phone a Dine build without the keyboard observer, the
  night sends or the size send; the glass button has no automated check.
- Checks (2026-11-08): framework 384/385 on headless, gtk and one VM (the `windows` suite 62/62),
  apps 4/5 and 5/5, package 48/48, `linux smoke` 21, runtime as before, `test unit` 79; on the
  iPhone 13 `dbg smoke` 25 with `atl-keyboard`, `atl-config`, `atl-immersive`, `atl-nav` and
  `atl-text` unchanged; dev and release builds, the release library without the new test hooks.
- Hand checks (iPhone 13): from the agent's screenshots, the round button in light and dark, no
  bar; a panned field above the keyboard (2340 to 1356 px under a 984 px keyboard); a resized
  window (2391 to 1407 px) with the field above the keyboard. By the user: content under the notch
  (the orange band to the screen's top, the clock over it); with the indicator's auto-hide turned
  off by the debugger, the indicator stays away, the first swipe up only reveals it and the second
  goes home; the keyboard
  animation; a real touch on a panned field; VoiceOver on the round button; a dark/light flip in
  Control Center. One switch reached three running apps (windows, widgets and nav) in the phone's
  log. Not done: the swipe and the keyboard corners on the build with their fixes; the top edge's
  deferral with the status bar hidden.
- Open: theme attributes keep their values after a night change
  ([ATL-73](general-todo.md#atl-73)), and an activity without uiMode keeps its look until
  recreation (multi-app MA5); an app's Resources share one AssetManager, so a configuration
  context that overrides night resolves at the app's;
  non-sticky immersive never clears (iOS reports no revealed indicator); a text cursor's
  `requestRectangleOnScreen` doesn't pan; no cutout shape ([ATL-69](general-todo.md#atl-69));
  a popup's own soft input mode is unchecked; the IME inset includes a pad's return button;
  `waitForIdleSync` waits for nothing ([ATL-70](bug-tracker.md#atl-70)); [ATL-71](bug-tracker.md#atl-71),
  [ATL-72](bug-tracker.md#atl-72).

### M6c: search ahead of M7

A search that fixes nothing: it finds what M7 and later stages will hit. The triage APKs outside
M9 run past their M6 stops on headless, with `-c` input where a stop needs it, and a dexdump read
of each APK lists the OS features it calls and the methods that call them. Each finding goes, with
how to reproduce it, to the stage that needs it fixed (an item of `notes/os-features.md`, an M8
stage, M9); one that blocks nothing gets a code in `notes/bug-tracker.md` (a defect) or
`notes/general-todo.md`. An OS feature's findings also go into its item in
`notes/os-features.md`.

Known from static reads, not run:
- accelerometerdemo registers an accelerometer listener in `onCreate` (sensors).
- multitouch references Vibrator.
- Gravity Defied calls ConnectivityManager only from its level-download paths, and sets an
  AlarmManager alarm in `GDActivity.doRestartApp` (jobs).

**Done when:** the table (APK, what it hits, owner) is in this section, and each entry is named in
a later stage or coded in `notes/bug-tracker.md` or `notes/general-todo.md`.

### M7: OS features

The `os` slot, one stage per OS feature, each with `desktop-linux`, `none` and `ios` backends
and a section in the OS features test APK: `notes/os-features.md`. Its notifications, media session,
downloads and jobs items wait for parts of [M8a](#m8a-apk-import-and-launch),
[M8b](#m8b-ios-lifecycle) and [M8d](#m8d-background-probes); each item says which.

### M8: inside Dine

The launcher installs and starts APKs; iOS foreground and background drive the Activity
lifecycle (what runs once Dine is backgrounded: `notes/background-tasks.md`); Back, Home and
the running apps list are in `notes/nav-gestures.md`; what is left of them is in the stages
below. The Dine-only stages M8b to M8d are left for later ([Milestones](#milestones)).

#### M8a: APK import and launch

Runs after multi-app MA1 and builds on its registry: an import installs the package (its registry
row, its APK in `apps/<pkg>/`), and the launcher reads the registry's rows (`notes/multi-app-support/design.md` "Registry",
`notes/filesystem/proposal.md` "Layout").

- Import from Files, with document types through the Info.plist merge (the base item of
  `notes/os-features.md`, if it isn't built yet). From the PC an APK reaches Files by a Safari
  download over the LAN (untried), or `pymobiledevice3 apps push --documents` puts it in Dine's
  Documents (needs `UIFileSharingEnabled`; unverified for a development-signed app on iOS 27).
- The APK goes to `apps/<pkg>/` and the app's data to `data/<pkg>/`, both in the prefix
  `Application Support/dine` that MA1's dev-screen runs already use (`dine_atl_run`'s
  `prefix_dir`).
- The launcher reads the registry's rows (package, label, icon, launcher activity) in place of
  `AppLibrary`'s `apps` table, which stores `id` and `name`. The registry has no label or icon
  column yet: this stage adds them (a schema version 2), its launcher being their only reader.
- Install parses the APK and writes its row in one transaction (`ATLInstaller`, MA1). On iOS the
  VM starts to install, so a VM-free reader is needed only if the rows can't hold labels and icons
  (`notes/multi-app-support/design.md` "Further points"). Such a reader would be shared C in
  dine-atl over androidfw's C API (already linked into Dine), so the package suite grades on
  headless the code Dine runs; the API has no `AssetManager_delete` or `ApkAssets_delete`: each
  parse leaks until they exist. Adaptive icons resolve to XML, so they fall back to a PNG until
  M5d draws paths.
- An APK without a launcher activity installs (an extension) and gets no tile; import warns about
  native libraries (`lib/*/*.so`), which iOS won't load.
- At start `dine_atl_run` passes no activity and Java picks the launcher one
  (`Activity.createMainActivity`). With none it calls `System.exit(1)`, which would end Dine: the
  embedded host returns an error instead, until multi-app MA3 makes `System.exit` end only the
  calling app.
- The running apps list (`RunningApps`) and the run states that `notes/nav-gestures.md` Behaviour
  specifies, on the launcher's tiles. Several apps' list (an entry per task, each app's state, a
  close action) is MA8.
- Release builds (`DINE_RELEASE=1`, `-c release`) start no app yet: only the dev atl screen calls
  `dine_atl_run`, and such a build keeps no `Java_*` symbol (`llvm-nm` count 0). ART finds those
  with dlsym, so once the launcher starts APKs, a release build must keep them: check the count,
  and if they are stripped, link with `-export_dynamic` or an exported-symbols list. Trap: the
  release link also force-loads `libruntimetests.a` (Package.swift's
  `.when(configuration: .debug)` doesn't reach the linking executable), which dead stripping
  removes today; with `-export_dynamic` its `Java_*` would stay, so fix that condition first.
  Whether a clean release tree, which has no `libruntimetests.a`, fails to link is unverified.
- The package suite (`dine-atl/tests/package`, from MA1) grades the label and icon columns.

**Done when:** the package suite passes on headless (the label and icon columns of the test APKs,
launcher resolution through the cli host without `-l`); on the phone a dev
screen imports from the dev payload through the same code (`dbg smoke`), and a release build
imports `demo_app.apk` and shows both strings (by hand).

#### M8b: iOS lifecycle

- Dine leaving the front calls `atl_nav_home` and coming back calls `atl_nav_front` (for every
  running app with several apps: multi-app MA8): onPause and onStop, then onRestart, onStart and
  onResume, the paths `run-nav.sh` grades on headless. The
  container stays presented, a background task (`beginBackgroundTask`) keeps Dine running until
  the Android thread has run them, and Dine remembers whether the app was in front.
- The Dialogs and Home race: [DINE-1](bug-tracker.md#dine-1).
- A pause without a stop (`willResignActive`: Control Center, the app switcher) would be new task
  state in `src/shared/activity.c`, with a cli `-c` command and a `run-nav.sh` step: decided here.
- Phone check known so far: the nav APK's lifecycle lines around an iOS background and foreground.
  pymobiledevice3 has `developer core-device hid button home` and `dvt launch --no-kill-existing`,
  neither tried on the phone; otherwise by hand.

#### M8c: navigation settings store

- `notes/nav-gestures.md` Settings: the `navigation` store, the observable `NavigationSettings`
  model, agent `ui defaults`, smoke `atl-nav` steps 1, 5 and 6, and the Dine setting that hides
  the home indicator for every app over M6b3's immersive mode.
- Phone check known so far: the settings steps of smoke `atl-nav` (`notes/nav-gestures.md` Tests).

#### M8d: background probes

A dev screen answers the open questions in `notes/background-tasks.md` on the phone. Question
3 and question 2's "exists and submits" take one log line each, question 5 one tap on the prompt;
question 1 needs days of runs, question 4 the user's hands (another app playing audio); questions
6 to 8 are code reads or the user's decisions. The task identifiers and background modes come
through the Info.plist merge. The answers go into `notes/background-tasks.md` and set the
notifications, media session, downloads and jobs items of `notes/os-features.md`.

#### M8e: several apps

Several apps at once on every backend: the roadmap is `notes/multi-app-support/todo.md`, its
design (approved 2026-11-02) and findings sit next to it, and `notes/steps.md` orders its stages
against this file's. Its stages replace this one; M8a's import builds on its registry (stage
MA1).

### M9: heavy

Compose (`compose_demo_app.apk`), SurfaceView and GLES, GL apps, and WebView: a `ViewGroup` backed
by a webkitgtk widget (`android_webkit_WebView.c`, gtk-only), a ui node kind on WKWebView for iOS.
RenderNode on the records backends: its natives build GskRenderNodes and are gtk-only;
a node would record into a display list that an op of its parent's list draws, with its
transform, alpha and clip ([Java](#java)). Layout's spans, line spacing and `StaticLayout.Builder`
setters, which Compose's text needs: [ATL-17](bug-tracker.md#atl-17). The cli host (headless)
doesn't unpack an APK's `lib/<arch>/`; only the gtk host does, so a native-library app's headless
stop is that gap.

## Tests

| Suite | Home | Builds | Oracle | From |
|---|---|---|---|---|
| runtime | `dine-art/tests/runtime` | Linux; the phone (by hand, from Dine's art screen) | expected output and per-platform expectations | now: `dine-0002-jni-args` runs on both |
| framework | `dine-atl/tests/framework` | headless, gtk; iOS waits for the phone runner below | JUnit through `--instrument` and `test_runner.jar`; later CTS subsets at Android 10 (graphics, text, content, view) | M2 |
| package | `dine-atl/tests/package` | headless | expected parse results | MA1 |
| apps | `tests/android-compat/apps` | headless, gtk; on the phone only Gravity Defied (`dbg smoke atl-gd`) | reaches `onResume`, no crash, log markers | M5d |

- **Expectations per build:** `linux-x86_64-gtk`, `linux-x86_64-headless` (an `ios-arm64-uikit`
  file comes with the phone runner), like the runtime suite's per-platform files. A test that
  passes on one build and fails on another points at a backend.
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
