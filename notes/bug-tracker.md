# Bug tracker

Open defects in Dine, dine-art and dine-atl: misbehaviour of what is built, suspected defects nobody
has checked, startup noise of our own, and fixes that wait on upstream. Non-defect work (ideas,
checks to run) is in `notes/general-todo.md`. Work a stage of `notes/atl-port.md` owns stays in
that stage; atl-port and the other notes link an entry here by its code.

- **A new find:** a defect found outside a stage's own work gets a code here, with an Owner line
  when a stage will fix it. A stage's own leftovers stay in its section (its "Open:" lines, M6a's
  findings).
- **Codes:** `ART-` dine-art, `ATL-` dine-atl, `DINE-` the app and its native libraries (artbridge,
  wolfSSL, the bundle), `TOOL-` dev tools (lldb, builds, accord). Numbers per area are shared with
  `notes/general-todo.md` and never reused: a new entry takes the highest number of its area in
  either file, Fixed and Done included, plus one. An item that moves between the two files keeps
  its code.
- **Fixed:** the entry moves under `## Fixed`, keeps its heading, and shrinks to one line: title,
  date, commit.
- **Links:** `[ART-3](bug-tracker.md#art-3)`.

Entry lines, where they apply: State (open; unchecked: suspected, never tested; blocked: waits on
upstream), Where, Repro, Workaround, Fix, Owner (the stage that fixes it), Also in (another doc
that keeps the same fact as a rule or record).

## ART

### ART-1

**On Apple the suspend barrier spins, and `WakeupToRespondToEmptyCheckpoint` is fatal.**
- State: open, not reached today: only the CC collector calls the wakeup, and dine-art runs CMS.
  `ART_USE_FUTEXES` is Linux-only; on Apple only park and unpark use os_sync, ART's mutexes,
  condition variables and RW locks are pthreads.
- Where: `dine-art/art/runtime/thread_list.cc` `ThreadList::SuspendAllInternal` (the `#else`
  spin wait); `art/runtime/base/mutex.cc` `Mutex::WakeupToRespondToEmptyCheckpoint` and
  `ReaderWriterMutex::WakeupToRespondToEmptyCheckpoint` (`Non futex case isn't supported.`).
- Fix: the barrier on os_sync wait and wake. Moving the remaining locks onto os_sync turns
  `ConditionVariable::RequeueWaiters` (`FUTEX_REQUEUE`) into a wake-all.

### ART-2

**`Thread::GetCpuMicroTime` and `ThreadCpuNanoTime` log `unimplemented` on Apple and return -1.**
- Where: `dine-art/art/runtime/thread.cc`, `art/libartbase/base/time_utils.cc`.

### ART-3

**No tzdata on iOS: time zones fall back to GMT.**
- State: open, listed after the first phone run. Neither the build nor the bundle ships tzdata
  (`grep -ri tzdata native tools apps`: 0 hits).

### ART-4

**On iOS startup logs `AsynchronousCloseMonitor: setting blocked thread signal handler failed`.**
- Where: `dine-art/libnativehelper/AsynchronousCloseMonitor.cpp`: off Linux `__SIGRTMIN` defaults
  to 32, so `BLOCKED_THREAD_SIGNAL` (`__SIGRTMIN + 2`) is out of range on Darwin and the
  `sigaction` fails.
- Effect (unchecked): the monitor's signal wakes a thread blocked in I/O on a descriptor another
  thread closes; without it that thread stays blocked.
- Fix: a signal Darwin has that nothing else in the process uses.

### ART-5

**On iOS startup logs `Could not reserve sentinel fault page`.**
- Where: `dine-art/art/runtime/runtime.cc` `Runtime::Init`: the page at `kSentinelAddr`
  (0xebad6000) is mapped with `low_4gb`, which `MemMap` refuses on Apple arm64
  (`libartbase/base/mem_map.cc`: the kernel's page zero covers the whole low 4 GB). Nothing reads
  `protected_fault_page_` beyond the map and its reset.
- Fix: skip the page on Apple arm64; no address inside the heap can be 0xebad6000.

### ART-6

**Startup logs `DexFile … is in boot class path but is not in a known location` once per boot
jar: 7 in release builds, 10 in dev builds.**
- Linux prints it too: 10 lines per framework-suite app (`out/tests/framework/runs/*/basics/stderr`,
  2026-11-09).
- Where: `dine-art/art/runtime/hidden_api.cc` `DetermineDomainFromLocation`: a location counts as
  known under `$ANDROID_ROOT/framework/` or `/usr` (a fork patch). artbridge sets `ANDROID_ROOT` to
  the resource dir and puts the jars directly in it; the Linux prefix (`out/linux/prefix`) isn't
  under `/usr`. The jars are `kBootJars` in `native/artbridge/artbridge.cpp`, plus the junit jars
  `DevVmArgs` adds in `native/artbridge/dev.cpp`. The branch returns `kPlatform` either way.

### ART-7

**The Apple arm64 asm carries no CFI: lldb can't unwind through the quick stubs, and a C++ or ObjC
exception thrown inside a native can't unwind through the trampoline and terminates the app.**
- State: open for lldb; the exception case is unchecked.
- Where: `dine-art/art/runtime/arch/arm64/asm_symbols_arm64.h`: `CFI(...)` expands to nothing on
  Apple. Mach-O starts an atom at every label without an `L` prefix, CFI can't advance across
  atoms, and these files use `.L` labels.

### ART-8

**`art_quick_invoke_stub` sizes its frame from all of `x2`, while `args_size` is a `uint32_t`.**
- State: unchecked. The upper half of `x2` is unspecified on both ABIs; clang may leave garbage
  there where gcc didn't.
- Where: `dine-art/art/runtime/arch/arm64/quick_entrypoints_arm64.S`, macro
  `INVOKE_STUB_CREATE_FRAME` (`add x10, x2, …`); its copy loop uses `w2`.
- Fix: size the frame from `w2`.

### ART-9

**The invoke stub and the generic JNI trampoline point x29 at an address that holds no frame
record.**
- State: unchecked. Apple requires one, so frame-pointer walks (`backtrace()`, crash reports)
  through native calls go wrong.
- Where: `quick_entrypoints_arm64.S`: `INVOKE_STUB_CREATE_FRAME` and
  `art_quick_generic_jni_trampoline` (`mov xFP, sp`).

### ART-10

**A deep native frame hits the stack guard page, and nothing turns that `EXC_BAD_ACCESS` into a
`StackOverflowError`.**
- State: unchecked. With implicit checks off, natives run in the explicit-check reserve
  (`ART_STACK_OVERFLOW_GAP_arm64`, 16 KB in dine-art's make build), and ART installs no signal
  handlers on Apple.
- Fix: a handler that recognises the guard page. First a probe, without a debugger attached, of
  whether an iOS app can catch SIGSEGV at all (`notes/art-findings.md` "Signals").

### ART-11

**`java.nio.file` fails on iOS: `DefaultFileSystemProvider` picks the Linux provider, whose natives
Darwin builds leave out.**
- State: open, from a code read; not run on the phone.
- Where: `dine-art/libcore/ojluni/src/main/java/sun/nio/fs/DefaultFileSystemProvider.java` picks by
  `os.name`, which is `Linux` for apps; `libcore/NativeCode.mk` leaves `EPoll.c`,
  `LinuxNativeDispatcher.c` and `LinuxWatchService.c` out on darwin, so their natives throw
  `UnsatisfiedLinkError`. Selectors use `PollSelectorProvider` and don't reach them.
- Fix: a Darwin file system provider.

### ART-12

**On iOS the Linux-only `Os` calls throw `ErrnoException(ENOSYS)`, netlink and packet sockets are
compiled out, and the 41 `OsConstants` iOS lacks keep their Java default 0.**
- The ENOSYS calls: capget, capset, prctl, sendfile, posix_fallocate, ucred.

### ART-13

**Linux-only calls and `/proc/self` readers remain in the code iOS builds.**
- State: unchecked which of them iOS reaches.
- Where: `/proc/self` in 16 non-test files of `dine-art/art/runtime` and `art/libartbase` (memory
  maps, stack dumps, `oat_file`, GC diagnostics); `memfd_create`, `prctl` or `gettid` in 9
  (`libartbase/base/memfd.cc`, `mem_map`, `utils`, `thread_pool`, `runtime`, JIT).

### ART-14

**The interpreter skips the access-check error on `instanceof` of null that compiled code throws.**
- Repro: runtime suite `536-checker-needs-access-check` (expected failure).

### ART-15

**Invisible annotation lookup returns null.**
- Repro: runtime suite `005-annotations` (expected failure); whether ART or libcore 8.1/9 is at
  fault is unknown.

### ART-16

**ICU charset lookup throws `IllegalCharsetNameException` for `x-UTF-16,version=1`.**
- Repro: runtime suite `062-character-encodings` (expected failure).

### ART-17

**libcore 8.1/9 lacks Java APIs that ART 10 expects.**
- Repro: runtime suite expected failures 710, 712, 713 (`MethodHandles` VarHandle factories), 656
  (in-memory `DexFile`), 688 (`DelegateLastClassLoader` with shared libraries, the 4-argument
  constructor; the 3-argument one exists),
  `071-dexfile-get-static-size`, 100 (`String`'s declared methods), 959 (`unreflectSetter` on a
  static final field). Reasons per test: `dine-art/tests/runtime/expectations/linux-x86_64.json`.
- Fix: libcore brought up to ART 10's level (a libcore rebase in dine-art); a later ART bump
  needs libcore to follow again.

### ART-18

**On Apple `parkUntil` becomes a timeout at entry: device sleep delays it, and a wall-clock change
after the call doesn't move it.**
- Where: `dine-art/art/runtime/thread.cc` `Thread::Park`: os_sync's only clock is mach absolute
  time.
- Also in: `notes/decisions.md` (dine-art).

### ART-23

**`OatFileAssistant::GetBestOatFile` still builds a dex2oat command and runs it through `Exec` when
an oat file isn't up to date.**
- State: unchecked whether any run reaches it. The dex open path
  (`OatFileManager::OpenDexFilesFromOat`) never runs dex2oat. `GetBestOatFile` has three callers:
  `class_loader_context.cc` (only after a context dex file failed to open),
  `DexFile_getDexFileOutputPaths` (`native/dalvik_system_DexFile.cc`) and
  `OatFileAssistant::GetOptimizationStatus` (from `DexFile_getDexFileStatus`). On Apple `Exec`
  returns an error without forking; on Linux it forks and execs dex2oat.
- Where: `dine-art/art/runtime/oat_file_assistant.cc` `OatFileAssistant::GetBestOatFile`.
- Fix: never run dex2oat there either, as the open path does. Unchecked: whether every caller takes
  a null result, and whether upstream's `GetBestInfo().ReleaseFileForUse()` would load oat files
  that earlier dex2oat runs left on Linux.

### ART-24

**On Apple, closing a socket doesn't wake a thread blocked reading it.**
- State: unchecked through libcore. On the phone (iOS 27, 2026-11-02, plain C in
  `native/artbridge/dev_multiapp.cpp`) `close()` from another thread wakes a thread blocked in
  `read()` on a TCP socket at once with `EBADF`, and `shutdown(SHUT_RDWR)` wakes it with 0, so the
  effect below is likely absent. On Linux a plain `close()` doesn't wake it.
- Where: `dine-art/libnativehelper/AsynchronousCloseMonitor.cpp` wakes blocked threads with
  `__SIGRTMIN + 2`, defined there as 34 when the platform has no `__SIGRTMIN`. Darwin's `NSIG` is
  32 (`sys/signal.h`), so signal 34 can't be installed or sent. NIO channels use SIGIO on Darwin
  and are not affected.
- Effect (unchecked): `Socket.close()` from another thread (OkHttp's `Call.cancel`, a timeout)
  leaves the reader blocked until data arrives or its socket timeout fires.
- Fix: a signal below 32 that nothing else uses, or `shutdown(fd, SHUT_RDWR)` before the close.
- Owner: `notes/multi-app-support/todo.md` MA4 (dropping an app needs it).

### ART-26

**On Apple, ART's page release doesn't lower the footprint iOS counts.** ART releases pages with a
memset to zero and `MADV_DONTNEED` (`kMadviseZeroes` is false off Linux), and on the phone that
left `phys_footprint` where it was; `MADV_FREE_REUSABLE` lowers it.
- State: open. Measured on the phone (iOS 27, 2026-11-02) on a plain 64 MB mapping, touched: 84 MB
  footprint before and after memset plus `MADV_DONTNEED`, 20 MB after `MADV_FREE_REUSABLE`. ART's
  own path is the same two calls; its effect on Dine's footprint is unmeasured.
- Where: `dine-art/art/libartbase/base/mem_map.cc:810-822` (`MadviseDontNeedAndZero`),
  `mem_map.h:42-46`.
- Effect (unchecked): heap trims and freed GC spaces stay counted against Dine's memory limit
  (2097 MB on the iPhone 13), which iOS enforces by killing Dine.
- Fix: `MADV_FREE_REUSABLE` on Apple, and `MADV_FREE_REUSE` before the pages are used again.
- Owner: `notes/multi-app-support/todo.md` MA4 (a dropped app's heap must leave the footprint).
- Also in: `notes/multi-app-support/findings-runtime.md` "Memory".

## ATL

### ATL-1

**The incremental hax.jar build doesn't recompile a class whose only link to another class is a
compile-time constant it reads from it.** The class keeps the constant's old value in its
bytecode and, if it has native methods, in its JNI header.
- State: unchecked: it follows from how the two tools work; no repro was run and no real case is
  known.
- Cause:
  - With ant installed, meson builds hax.jar through `dine-atl/src/api-impl/build.xml`. Its
    `<depend closure="true">` deletes the class files of every class that depends, directly or
    transitively, on a changed class, and javac recompiles them.
  - `<depend>` takes dependencies from the `Class` entries in each class file's constant pool
    (ant 1.10.18's `ClassFile.getClassRefs`).
  - javac inlines compile-time constants (`static final` primitives and Strings with a constant
    initializer) and records no reference to the class that declares them. A class that uses only
    `Other.Y` from `Other` has no `Class` entry for `Other`, so `<depend>` never links the two.
- Repro shape:

  ```java
  // A.java
  public class A { public static final int Y = 1; }

  // B.java: no other use of A
  public class B { static final int X = A.Y; native void f(); }
  ```

  Change `A.Y` to 2 and run an incremental build: A recompiles, B doesn't. `B.class` and `B.h`
  (`#define B_X 1L`) keep 1.
- Not affected:
  - a class that uses `A` in any other way (a method call, a field of type `A`, `extends A`): it
    has the `Class` entry. View's `LAYOUT_DIRECTION_* = LayoutDirection.*` constants are safe for
    that reason: the ant dependency cache lists `LayoutDirection` as a dependency of View;
  - a build dir with no compiled classes yet (fresh `meson setup`, a deleted `hax.jar.p`): javac
    compiles every source;
  - the meson `jar()` path, used when ant isn't installed: one javac run over all sources on every
    change.
- Workaround (untested): after changing the value of a constant other classes read, delete
  `out/linux/build/dine-atl/src/api-impl/hax.jar.p` and
  `out/linux/build/dine-atl-headless/src/api-impl/hax.jar.p`, then build.
- Fix: a full javac on every Java edit closes the gap: 5.0 s, against 1.36 s for a leaf class and
  4.06 s for View with the closure (scratch runs of the hax build), and every edit then rewrites
  all 83 headers and recompiles the C files that include them.
- Also in: `notes/decisions.md` (dine-atl), the closure rule.

### ATL-2

**gtk startup prints `gdk_monitor_get_geometry: assertion 'GDK_IS_MONITOR (monitor)' failed`.**
- State: open, seen on views-gtk runs on WSLg; cause not traced. A views-gtk run on the hidden
  sway display doesn't print it; WSLg not rechecked. The smoke's script checks (views-gtk) drop
  ATL's output on a pass, so `tools/dine linux smoke` can't show it.

### ATL-3

**Gesture exclusion rects follow a translation only at the next layout pass, and their parents
don't clip them.**
- Where: `dine-atl/src/api-impl/android/view/Window.java` `updateExclusion` runs after each layout
  pass and each scroll, and offsets each rect by `getLocationInWindow` without clipping.
- Effect: after a translation the edge recognizer uses the old rect until the next layout pass; a
  rect partly scrolled out of its parent still excludes the hidden part.

### ATL-5

**Unchecked: whether ATL keeps every view's left and top current at the end of the root's layout
on gtk.** `View.getLocationInWindow` walks the parents and adds them up, so exclusion rects
depend on it.

### ATL-8

**gtk TextViews take Java's px text size as points.** `ui_text_set_size` sets
`pango_attr_size_new`, a size in points, and Java passes px: a TextView's text is 4/3 of its size
at 96 dpi, and a Paint at the same size measures 3/4 of the label (DrawStayActivity's
`widgets metric` lines on gtk: "Hello world" at 14 sp, Paint 76 px, label 101 px).
- Where: `dine-atl/src/backends/ui/gtk/text.c`: `ui_text_set_size` and the span runs'
  `UI_RUN_SIZE` both use `pango_attr_size_new`. `ui_text_get_size` answers in the same unit, and
  without a set size it returns the label font's size in points; the TextView constructor sets
  its Paint's size from it (`native_getTextSize`).
- Fix: `pango_attr_size_new_absolute` at both sites and a px answer from `ui_text_get_size`, which
  shrinks every gtk TextView, and the Paint of a default-sized one, to its Android size.

### ATL-9

**gtk draws stroked text filled.** A paint with `Style.STROKE` or `FILL_AND_STROKE` fills its
text on gtk; the display list keeps the style and iOS strokes it.
- Where: `dine-atl/src/backends/gfx/gsk/canvas.c` `gfx_canvas_draw_text`:
  `gtk_snapshot_append_layout` only fills.
- Fix: the layout as a path through `gtk_snapshot_append_stroke` (`gsk_path_builder_add_layout`,
  GTK 4.14 and later; this system has 4.24.1).

### ATL-10

**A lone `\r`, U+2028 and U+2029 break a Layout's lines on gtk and iOS, not on headless.** Layout
splits paragraphs at `\n` and `\r\n`; Pango and CoreText break the rest inside a paragraph, record
breaks only at spaces.
- State: what Android 10's StaticLayout does with them is unchecked.
- Where: `dine-atl/src/shared/android_text_Layout.c` (the paragraph split), each backend's
  `gfx_text_break_lines`.

### ATL-11

**gtk text measured off the main thread is in Sans, on the main thread in GTK's font.** Paint calls
from a worker (async inflation, precomputed text) measure in another font than the view draws.
- Where: `dine-atl/src/backends/gfx/gsk/text.c` `context()`: another thread's context gets the
  family "Sans".
- Fix: give those contexts the window context's font description, read on the main thread.

### ATL-12

**gtk's max-lines cap lays the label out at the whole view's width.** With compound drawables or
padding the label is narrower, wraps elsewhere, and the cut can fall inside a line.
- Where: `dine-atl/src/backends/ui/gtk/text.c` `text_cap_height`.
- Fix: take the box's horizontal extra off `for_width`.

### ATL-14

**Unchecked: a drag that starts on a multi-line EditText inside a ScrollView on iOS.** The field's
UITextView scrolls (`scrollEnabled`, so a capped field follows its cursor), and its pan recognizer
may take the drag: the parent stops scrolling, or Java gets `ACTION_CANCEL`.
- State: unchecked; no test APK puts a field in a scroll view.
- Where: `dine-atl/src/backends/ui/uikit/view.m` `ATLEditView`.

### ATL-15

**A TextView ignores its typeface's family.** `setTypeface(Typeface.MONOSPACE)` or `SERIF` shows
the default font on every build, and the `fontFamily` attribute isn't read; Paint draws the family.
- Where: the ui slot takes a style only (`ui_text_set_style`); `TextView.setTypeface` passes
  `getStyle()`.

### ATL-17

**`android.text.Layout` ignores spans, line spacing, `includePad`, right-to-left text and
`StaticLayout.Builder`'s setters.** Size and style spans measure in the paint's font,
`setLineSpacing` moves no line, and Builder's `setMaxLines`, `setEllipsize` and `setAlignment` do
nothing: `obtain` builds the layout at once.
- Where: `dine-atl/src/shared/android_text_Layout.c`, `src/api-impl/android/text/StaticLayout.java`.
- Owner: M9: Compose lays out its text through `StaticLayout.Builder`.

### ATL-24

**Resource bitmaps and nine-patches ignore screen density.** `Bitmap.setDensity` does nothing and
`BitmapFactory.setDensityFromOptions` is commented out, so a resource image draws at its pixel
size: on the iPhone 13 (480 dpi) an hdpi PNG or nine-patch draws at half its dp size (Gravity
Defied's buttons and their borders).
- Where: `dine-atl/src/api-impl/android/graphics/BitmapFactory.java`, `Bitmap.java`.
- Fix: AOSP 10's scaling to `inTargetDensity` (bitmaps, and a nine-patch's chunk with them).

### ATL-25

**Text with a shader draws in the paint's color, and coregraphics shades without the paint's color
filter.** `gfx_canvas_draw_text` ignores `Paint.setShader`; coregraphics' `draw_shader` applies
only the paint's alpha over the gradient.
- Where: `dine-atl/src/backends/gfx/{coregraphics/draw.c,gsk/canvas.c}`.

### ATL-26

**Inverse fill types draw as their plain rule.** `drawPath` and `clipPath` take the even-odd bit
only (`gfx_canvas_draw_path`); `Path.op` and Region handle inverse.
- Where: `dine-atl/src/api-impl/android/atl/ATLCanvas.java`, `src/slots/gfx.h`.

### ATL-27

**`saveLayer`'s paint: gsk ignores its PorterDuff mode, and no build applies its color filter.**
`gfx_canvas_save_layer` takes alpha and mode; gsk pushes only an opacity (GSK has no layer blend
with one child).
- Where: `dine-atl/src/backends/gfx/gsk/canvas.c` `gfx_canvas_save_layer`, `src/api-impl/android/graphics/Canvas.java`.

### ATL-28

**View work off the Android main thread races the records beyond uikit's queue.** Apps build views
on their own threads (Gravity Defied's `game_thread` builds `MenuHelmetView`); uikit's queue takes
any thread since M5d, but `schedule_draw`/`schedule_layout` change the window's `draw_pending` and
`layout_pending` unlocked from any view's `drawables_changed` or `requestLayout`; a view changed
off-thread while attached (text, children) races the main thread's tree walks; and a drawable's
last unref in `hold()` can run on an app thread.
- State: unchecked: read from the code, not seen failing.
- Where: `dine-atl/src/backends/ui/records/ui.c` (`schedule_draw`, `schedule_layout`, `hold`).

### ATL-34

**Intent filters keep only the data scheme.** `PackageParser` reads only `android:scheme` of a
`<data>` element; host, port, path, mime type and scheme-specific part are dropped, and
`IntentFilter`'s setters for them do nothing. Resolution (`PackageManager`, broadcasts) matches the
action, the categories and the scheme, and ignores an intent's type: a filter that only names a
mime type takes intents of any type with no data.
- Where: `dine-atl/src/api-impl/android/content/pm/PackageParser.java` (`<data>`),
  `dine-atl/src/api-impl/android/content/IntentFilter.java`.

### ATL-35

**An APK signed only with a v2 or v3 signature block installs as unsigned.** `collectCertificates`
reads JAR (v1) signatures only, so such a package reports no signatures, every unsigned package
matches it in the install rules, and `checkSignatures` calls it not signed. APKs with a minimum SDK
of 24 or more may carry no v1 signature (apksigner's default).
- State: unchecked against a real v2-only APK.
- Where: `dine-atl/src/api-impl/android/content/pm/PackageParser.java` `collectCertificates`.

### ATL-36

**Broadcasts run on the sender's thread.** `Context.sendBroadcast` calls each receiver's `onReceive`
at once on the calling thread, registered and manifest receivers alike, instead of posting to the
main thread or the receiver's `Handler`; `sendOrderedBroadcast` only prints.
- Where: `dine-atl/src/api-impl/android/content/Context.java` `sendBroadcast`,
  `dine-atl/src/api-impl/android/atl/ATLLoadedApp.java` `receiveBroadcast`.

### ATL-38

**An installed APK is synced with `fsync` only.** On Apple `fsync` doesn't make the data durable
(`F_FULLFSYNC` does), so after a power loss the registry's row (written with SQLite's `fullfsync`)
may point at an APK whose blocks never reached the disk.
- State: unchecked.
- Where: `dine-atl/src/api-impl/android/atl/ATLInstaller.java` (`copy`, `fsyncDir`).

### ATL-39

**`Process.myUid()` may equal the desktop user's own uid.** It returns the package's registry uid
(10000 and up, never the OS uid, so that apps like WhatsApp accept their own files); a Linux user
whose uid falls in that range would make them refuse again.
- State: unchecked.
- Where: `dine-atl/src/api-impl/android/os/Process.java` `myUid`.

### ATL-41

**`Looper.myLooper() == Looper.getMainLooper()` is true on a thread of no app**: both are null.
Code that takes it as "am I on the main thread" then touches UI state from that thread.
- State: unchecked: no app code is known to run there.
- Where: `dine-atl/src/api-impl/android/os/Looper.java` `getMainLooper`. Threads of no app: ART's
  daemons (they run no app code), native threads that attach without a group on iOS and in a
  headless VM of several apps (`notes/multi-app-support/design.md` "App record").

### ATL-44

**bionic_translation's native `__system_property_get("ro.build.version.sdk")` says 21 while Java's
`SDK_INT` is 29.** A native library that asks for the level gets 21.
- State: open; no suite reaches it (native-library apps run only on the gtk build).
- Where: `third_party/bionic_translation/libc/libc.c:68`, a plain clone, not a fork
  (`notes/decisions.md`), so a fix is a local patch the build applies.
- Owner: M9 (native-library apps).

### ATL-45

**An app with no theme that targets API 24 or more gets `Theme_DeviceDefault` (dark), not AOSP
10's `Theme_DeviceDefault_Light_DarkActionBar`.** `Resources.selectDefaultTheme` has the pre-N
steps only.
- State: open; ATL's own test APKs set no theme, so the fix changes how they look. Seen
  2026-11-05: the widgets draw app (targetSdk 27) shows a `#1A1B20` background on the phone and a
  light one on Android (in dark mode too), so its translucent `saveLayerAlpha` square looks dark on
  the phone; its pixels match a 50% layer over `#1A1B20` exactly.
- Where: `dine-atl/src/api-impl/android/content/res/Resources.java` `selectSystemTheme`.

### ATL-46

**On headless a Canvas(Bitmap) draws no text, a sweep gradient as 72 wedges and a hairline 1 unit
wide.** The record backend measures text with fixed metrics and has no font; cairo
(`dine-atl/src/backends/gfx/record/painter.c`) has no conic gradient or device-space hairline.
- State: open; only bitmap pixels on headless (the display list keeps the text op).

### ATL-47

**A Canvas(Bitmap) draws no view and no Layout's text through the toolkit.** `View.onDraw`,
`dispatchDraw`, `draw`'s background, `ViewGroup.drawChild`, `Layout.draw` (its native path) and
`SurfaceView`'s post act only on an `ATLCanvas`; `Drawable.draw` takes any canvas
(`Canvas.atlHandle`). So `view.draw(new Canvas(bitmap))` (snapshots, drawing caches) gets the
view's Java drawing only.
- State: open; whether `ui_view_draw_*` can draw a view into a bitmap's canvas is unchecked per
  backend.
- Where: `dine-atl/src/api-impl/android/view/View.java`, `ViewGroup.java`, `text/Layout.java`,
  `view/SurfaceView.java`.

### ATL-48

**BitmapShader is approximate on gsk and CoreGraphics.** CLAMP draws the bitmap once without
extending its edges; MIRROR repeats; on cairo (headless) a bitmap shader tiles both axes as x.
- State: open; `graphics/BitmapShaderTest` checks what is exact (CLAMP inside the bitmap, REPEAT,
  SRC_IN).
- Where: `dine-atl/src/backends/gfx/{gsk/canvas.c,coregraphics/draw.c,record/painter.c}`.

### ATL-52

**On the phone a view draws MODULATE as multiply, and COLOR_DODGE, COLOR_BURN and SOFT_LIGHT with
CoreGraphics' own formulas (paint, layer and ComposeShader).** CoreAnimation replays a view's list
into a context whose pixels can't be read, and CoreGraphics has no blend mode for these; it differs
from Skia by up to 46 of 255 per channel. Bitmaps are exact on every backend (the painter blends
these per pixel), and gsk is exact everywhere through GSK's arithmetic node.
- State: open by choice (2026-11-05, the user: "Leave iOS views approximate"; drawing such a view
  into an image on the Android thread was the exact option).
- Where: `dine-atl/src/backends/gfx/coregraphics/draw.c` (`cg_blend_exact`, `cg_draw`,
  `cg_begin_layer`, `draw_compose`), replayed by uikit's `ATLDrawLayer`.

### ATL-53

**A Canvas(Bitmap) on headless and gtk clips DIFFERENCE with a path as even-odd against a large box,
so a path that crosses itself keeps its overlaps.** cairo has no inverted clip;
`cpainter_clip_path` adds the box and the path with the even-odd rule. gsk views clip exactly (an
inverted mask).
- State: open; found in the phase 4 plan review, 2026-11-05.
- Where: `dine-atl/src/backends/gfx/cairo/painter.c` `clip`.

### ATL-54

**`new Canvas(bitmap)` takes an immutable bitmap; AOSP 10 throws `IllegalStateException`
("Immutable bitmap passed to Canvas constructor").** `Canvas.setBitmap` already throws.
- State: open; checked against AOSP 10's `Canvas.java`, 2026-11-05. Throwing breaks apps that rely
  on ATL's leniency.
- Where: `dine-atl/src/api-impl/android/graphics/Canvas.java` `Canvas(Bitmap)`.

### ATL-55

**`Bitmap.createBitmap(src, x, y, width, height, matrix, filter)` keeps `width x height` and the
source's config.** AOSP 10 sizes the result to the matrix's mapped rect, translates by its corner,
and picks ARGB_8888 (or the source's config) by its own rules.
- State: open; checked against AOSP 10's `Bitmap.java` (`deviceR`, `newConfig`), 2026-11-05.
- Where: `dine-atl/src/api-impl/android/graphics/Bitmap.java`.

### ATL-56

**`BitmapFactory` with `inBitmap` gives the target bitmap new native pixels (`transferFrom`), so a
Canvas made over it beforehand keeps drawing into the old ones.** AOSP decodes into the same
memory.
- State: open, unchecked against an app.
- Where: `dine-atl/src/api-impl/android/graphics/Bitmap.java` `transferFrom`.

### ATL-57

**gtk may keep showing a bitmap's old pixels in a GtkPicture (ImageView, a background) after a
Canvas draws into the bitmap.** Its texture is made per change (`gsk_bitmap_texture`), but nothing
invalidates the paintable when the pixels change; only the view's own redraw makes a new one.
- State: unchecked; suspected while reviewing phase 4, 2026-11-05.
- Where: `dine-atl/src/backends/gfx/gsk/bitmap.c` (`BitmapPaintable`).

### ATL-58

**On the phone a Canvas(Bitmap) lays text out at scale 1: the text size in px as points, where
`measureText` and views use px per point.** Widths in bitmaps may differ from `measureText`.
- State: open, unchecked on the device; found 2026-11-05 (the user: "Log it as a new ATL entry").
- Where: `dine-atl/src/backends/gfx/coregraphics/painter.c` (`cg_draw(..., 1, ...)`) and
  `text.c` `cg_text_line`.

### ATL-59

**`Canvas.setMatrix` can't leave a singular matrix, and `setMatrix(null)` throws
NullPointerException; Android 10 sets the matrix (null: identity).** ATL concats the inverse of the
current matrix, then the new one; the gfx slot has no call that sets a matrix. After `scale(0, 0)`
nothing draws until the `restore`.
- State: open; found in the phase 4 review, 2026-11-05. A clip under a singular matrix follows
  Skia's rule (DIFFERENCE keeps the clip) on bitmap canvases, unobservable until this is fixed.
- Where: `dine-atl/src/api-impl/android/graphics/Canvas.java` `setMatrix`, `src/slots/gfx.h`.

### ATL-60

**`Bitmap.compress` throws the stream's IOException; Android 10 returns false.** AOSP's stream
adaptor clears the exception and fails the encode.
- State: open; found in the phase 4 review, 2026-11-05.
- Where: `dine-atl/src/api-impl/android/graphics/Bitmap.java` `compress`.

### ATL-61

**On WSLg the gtk build writes an uninitialised screen size into the config at startup.**
`update_config_for_window` asks for the window's monitor right after `gtk_window_present`; WSLg's
Weston reports it only at `enter-monitor`, so `gdk_display_get_monitor_at_surface` returns NULL
(`Gdk-CRITICAL … GDK_IS_MONITOR (monitor)`) and `monitor_size` reads a stack `GdkRectangle` GDK
never filled: `screenWidthDp`/`screenHeightDp` hold garbage until the monitor enters.
- State: open, low priority; found 2026-11-05 (Flower Finder on WSLg). The hidden sway display
  doesn't show it.
- Where: `dine-atl/src/backends/ui/gtk/display.c` `update_config_for_window`, `monitor_size`.
- Fix: skip the upcall for a NULL monitor; `enter-monitor` sets the size.

### ATL-62

**`tools/dine dbg attach` can't attach to a gtk-target ATL that hangs before its window has a
width.** The `prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY)` that lets the server's lldb attach under
Yama `ptrace_scope=1` runs in `agent_start()`, which `hacky_on_window_focus_changed_callback`
calls only once the window is non-zero wide.
- State: open, low priority; found 2026-11-05 (Flower Finder's first frame hung in Mesa d3d12).
- Where: `dine-atl/src/backends/ui/gtk/agent.c` `agent_start`,
  `dine-atl/src/main-executable/main.c` `hacky_on_window_focus_changed_callback`.
- Workaround: start ATL as a child of the debugging process, or `ptrace_scope=0` (sudo).
- Fix: the prctl at startup when `ATL_DBG_AGENT` is set.

### ATL-66

**Native-look buttons treat an app's padding differently per backend.** A Button with no app
background keeps the toolkit's look. On uikit the app's padding is space outside the gray capsule
(`ATLButton` lays the UIButton out in the padded frame, and the configuration's own content insets
stay inside it). On gtk it is space inside the button (CSS padding), and a button without app
padding gets none at all, because the View constructor always sends its padding, zeros included.
ATL's Button takes no theme style, so it has none of Android's default button padding; on uikit a
push or toggle button with an app background keeps UIKit's insets until that background (or the app)
gives it padding. Also: gtk's Spinner gets its padding on the dropdown while its background goes on
the inner toggle.
- State: open; found 2026-11-08 (ATL-64's fix, code read only).
- Where: `dine-atl/src/backends/ui/uikit/view.m` `ATLButton`, `src/backends/ui/gtk/view.c`
  `ui_view_set_padding`, `src/api-impl-jni/widgets/android_widget_Spinner.c`.

### ATL-67

**uikit's keyboard field is one per process.** `keyboard_field`, the edit view that holds the
keyboard, is a static of `view.m`, not per app: with two apps running, a window one app shows over
its activity (a dialog, a popup) can give the keys back to the other app's field.
- State: unchecked; found 2026-11-08 (M6b3b's planning, code read only).
- Where: `dine-atl/src/backends/ui/uikit/view.m` (`keyboard_field`, `root_take_responder`).

### ATL-70

**`Instrumentation.waitForIdleSync` waits for nothing.** Its body is commented out, so a test that
calls it right after `runOnMainSync` sees none of what that runnable posted (a Handler post, an
insets dispatch). M6b3c's `SystemUiTest` and `ConfigTest` use a second `runOnMainSync` as the
barrier instead.
- State: open; found 2026-11-08 (M6b3c, `SystemUiTest`'s listener case).
- Where: `dine-atl/src/api-impl/android/app/Instrumentation.java` `waitForIdleSync`.

### ATL-71

**`ScrollView.setFillViewport` does nothing, and HorizontalScrollView skips its default style.**
A form in a fill-viewport ScrollView that is shorter than the screen keeps its own height, so
content meant to sit at the bottom sits under the rest. `HorizontalScrollView(Context)` and
`(Context, AttributeSet)` pass no `horizontalScrollViewStyle` (ScrollView's pass `scrollViewStyle`).
- State: open; found 2026-11-08 (M6b3c's keyboard tests, code read only).
- Where: `dine-atl/src/api-impl/android/widget/ScrollView.java`, `HorizontalScrollView.java`.

### ATL-72

**`PackageManager.getActivityInfo` replaces an activity's `configChanges` with uiMode.** It sets
`info.configChanges = CONFIG_UI_MODE` for AppCompat's own check, which drops every flag the manifest
has; `NativeActivity` reads them from there. M6b3c's night dispatch reads the manifest's
(`PackageParser.Activity.info`) for this reason.
- State: open; found 2026-11-08 (M6b3c planning, code read only).
- Where: `dine-atl/src/api-impl/android/content/pm/PackageManager.java:1632`.

### ATL-75

**`TextView.getLineCount()` always returns 1.** It ignores the text, the width and the line caps;
`getLayout().getLineCount()` counts the lines.
- State: open; found 2026-11-09 (ATL-16's fix, code read only).
- Where: `dine-atl/src/api-impl/android/widget/TextView.java` `getLineCount`.

### ATL-76

**JobScheduler keeps a finished job pending, and a reused JobInfo can start twice.** A job whose
`onStartJob` returns false stays in `pending_jobs` until `cancel`: `getAllPendingJobs` lists it,
and a `schedule` of its id does nothing. An app that schedules, cancels and schedules one `JobInfo` object
passes both start runnables' check, so the job starts twice. An `onStartJob` that throws leaves the
job marked running.
- State: open; found 2026-11-09 (ATL-40's reviews, code read only).
- Where: `dine-atl/src/api-impl/android/app/job/JobScheduler.java` `schedule`, `JobService.java`
  `jobFinished`.

## DINE

### DINE-1

**Dialogs and Home race: Dine dismisses the app container before Java hears Home.** An alert shown
in between presents over the launcher until Java's close reaches it, and a tap whose answer
reaches Java after Home is dropped: the alert comes back on front.
- Where: `apps/Dine/Sources/Dine/Navigation.swift` `home()`: `dismissContainer` and `popToRoot`
  run before `atl_nav_home`. It handles one container; with several apps there is one per task
  (multi-app MA6).
- Owner: M8b.

### DINE-2

**A vertical scroll that starts within 20 pt of the left edge can fire Home.** The 96 pt down
commit distance and the app's exclusion rects are the only guards; a tradeoff of the default strip
width.
- Where: `apps/Dine/Sources/Dine/EdgeGestures.swift` (`stripWidth`, `commitDistance`).

### DINE-3

**Unchecked by hand: whether the edge pans win against Android-hosted `UIScrollView`s.**
- Where: `apps/Dine/Sources/Dine/EdgeGestures.swift` (`shouldBeRequiredToFailBy`).
- Fix if they lose: intercept edge touches in `UIWindow.sendEvent` before hit-testing.
- Also in: `notes/atl-port.md` M4a "Open:".

### DINE-4

**On iOS an app trust manager that calls the default one's `checkServerTrusted` fails: wolfSSL's
CertManager has no SecTrust path.** A context that loads the system CAs validates with SecTrust,
as wolfJSSE does when it finds no Java trust store (`tools/libexec/build-ios-deps.sh`).

### DINE-5

**Dine's bundle carries dine-atl's AOSP code (`api-impl.jar`) without the notices Apache 2.0
requires.** Its `licenses` folder (`out/ios/assets/Dine/licenses`) holds only the icon pack's
`Icons.txt`: no combined notice file, no `NOTICE-AOSP.txt`, no `LICENSE-APACHE-2.0.txt`.
- Fix: a combined notice file generated at build time into that folder, with dine-atl's two files;
  what goes in it and how to show it: `notes/licensing-future.md` "Notices in a packaged app".
- Also in: `dine-atl/doc/AOSP.md` ("Open:").

## TOOL

### TOOL-1

**With a warm `symbols.enable-lldb-index-cache`, attach segfaults.** The cache would save ~5 s per
attach (the symbol tables of ~1400 system dylibs), so it stays off.
- State: blocked: the upstream fix is in no Swift release yet.
- Repro: enable the cache and attach twice; the second attach crashes in
  `ConstString(char const*)` ← `Symbol::ResolveReExportedSymbol` ← `AppleObjCTrampolineHandler`
  (3/3 runs, Swift 6.4.1, lldb 21.0.0 swiftlang).
- Cause: lldb stored a re-export symbol's target name as a raw pointer into its own memory, and a
  symtab loaded from the cache carries a pointer from an old session. swiftlang PR #13223
  (`swift/release/6.4.x`) made the ObjC trampoline handler resolve `objc_msgSend` through
  re-exports, which reaches the stale pointer during attach.
- Fix upstream: LLVM `38d1460c57` (#213356: stores the name, bumps the cache format) and
  `8df22c7dc7` (#228266: also saves the target binary). swiftlang cherry-picked both into
  `stable/23.x` (PRs #13944, #14589) and `next`; no 6.4 branch has them. Swift freezes one LLVM
  branch per release line (6.4 is on LLVM 21), so they arrive with the first
  Swift release built on `stable/23.x`, and its matching Xcode (`docs/first-run.md`, Swift and
  Xcode coupling).
- Then: enable the cache in `ios.lldb_memory_cmds()` (`tools/py/dine/ios.py`, path under `out/`),
  attach twice (fill, then use it) and check that the second attach doesn't crash.
- Also in: `notes/dev-reference.md` (the "don't enable" rule).

### TOOL-2

**`tools/dine ios lldb-offline`: lldb's per-module fallback `SwiftASTContext` ignores
`target.sdk-path` and ends in a fatal state.**
- State: open, seen only offline: a core has no reflection metadata, so lldb falls back when it
  sizes a type. On the device `p` and `v` go through reflection.

### TOOL-3

**accord stores an imageset's template intent only on its raster renditions, not on the vector
one.**
- State: open; not rechecked against the current accord.
- Workaround: Dine tints in code, `.renderingMode(.template)` with `.foregroundStyle(...)`
  (`notes/icons.md` Rendering).

## Fixed

### ATL-4

**framework-res said 3-button navigation.** 2026-11-03, M6b1, dine-atl cff73b6f.

### ATL-13

**`setInputType(TYPE_CLASS_NUMBER)` after `setKeyListener(DigitsKeyListener)` kept an EditText
multi-line.** 2026-11-09, bugs step, dine-atl e7a207c6.

### ATL-16

**`TextView.getLayout()` made a new BoringLayout on every call.** 2026-11-09, bugs step,
dine-atl e7a207c6.

### ATL-33

**gsk drew some PorterDuff color filters as SRC_IN.** 2026-11-04, M6b review, dine-atl 73077776.

### ATL-37

**Two installed packages could claim one provider authority.** 2026-11-09, bugs step,
dine-atl e7a207c6.

### ATL-40

**`JobScheduler.cancel` never stopped a job.** 2026-11-09, bugs step, dine-atl e7a207c6.

### ATL-64

**A background drawable gave its view no padding.** 2026-11-08, before the M6b3a commit, uncommitted.
