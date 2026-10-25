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
- Where: `dine-art/art/runtime/runtime.cc` `Runtime::Init`: the page at `kSentinelAddr` is mapped
  with `low_4gb`, which iOS refuses.
- Fix: drop the page, or map it inside the heap reservation.

### ART-6

**Startup logs `DexFile … is in boot class path but is not in a known location` once per boot
jar: 7 in release builds, 10 in dev builds.**
- Where: `dine-art/art/runtime/hidden_api.cc`; the jars are `kBootJars` in
  `native/artbridge/artbridge.cpp`, plus the junit jars `DevVmArgs` adds in
  `native/artbridge/dev.cpp`.

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
  (in-memory `DexFile`), 688 (`DelegateLastClassLoader(String, String, ClassLoader)`),
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
  (`OatFileManager::OpenDexFilesFromOat`) never runs dex2oat; `GetBestOatFile` is called from
  `class_loader_context.cc`, `native/dalvik_system_DexFile.cc` and `oat_file_assistant.cc`. On
  Apple `Exec` returns an error without forking; on Linux it forks and execs dex2oat.
- Where: `dine-art/art/runtime/oat_file_assistant.cc` `OatFileAssistant::GetBestOatFile`.
- Fix: never run dex2oat there either, as the open path does.

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

### ATL-4

**framework-res says 3-button navigation: `config_navBarInteractionMode` 0,
`config_backGestureInset` 0dp.** Apps that detect gesture navigation from these resources assume
buttons.
- Where: `dine-atl/res/framework-res/res/values/config.xml`; a change needs
  `-Dregenerate_framework_res`.
- Owner: M6b, with `SDK_INT` above 21.

### ATL-5

**Unchecked: whether ATL keeps every view's left and top current at the end of the root's layout
on gtk.** `View.getLocationInWindow` walks the parents and adds them up, so exclusion rects
depend on it.

### ATL-8

**gtk TextViews take Java's px text size as points.** `ui_text_set_size` sets
`pango_attr_size_new`, a size in points, and Java passes px: a TextView's text is 4/3 of its size
at 96 dpi, and a Paint at the same size measures 3/4 of the label (DrawStayActivity's
`widgets metric` lines on gtk: "Hello world" at 14 sp, Paint 76 px, label 101 px).
- Where: `dine-atl/src/backends/ui/gtk/text.c` `ui_text_set_size`; `ui_text_get_size` answers in
  the same unit.
- Fix: `pango_attr_size_new_absolute`, which shrinks every gtk TextView to its Android size.

### ATL-9

**gtk draws stroked text filled.** A paint with `Style.STROKE` or `FILL_AND_STROKE` fills its
text on gtk; the display list keeps the style and iOS strokes it.
- Where: `dine-atl/src/backends/gfx/gsk/canvas.c` `gfx_canvas_draw_text`:
  `gtk_snapshot_append_layout` only fills.
- Fix: the layout as a path through `gtk_snapshot_append_stroke` (`gsk_path_builder_add_layout`;
  that GTK 4.24 has it is unchecked).

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

### ATL-13

**After `setKeyListener(DigitsKeyListener)` on a multi-line EditText,
`setInputType(TYPE_CLASS_NUMBER)` keeps it multi-line.** EditText compares the multi-line state with the old input type, which
`setKeyListener` already made NUMBER; AOSP compares with `mSingleLine`.
- Where: `dine-atl/src/api-impl/android/widget/EditText.java` `setInputType`.
- Fix: a single-line flag, as AOSP's TextView keeps.

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

### ATL-16

**`TextView.getLayout()` makes a new BoringLayout on every call.** An app that calls it in
`onDraw` allocates a native line array per frame, freed only by the finalizer, and its lines come
from Paint, not from the toolkit's label.
- Where: `dine-atl/src/api-impl/android/widget/TextView.java` `getLayout`.

### ATL-17

**`android.text.Layout` ignores spans, line spacing, `includePad`, right-to-left text and
`StaticLayout.Builder`'s setters.** Size and style spans measure in the paint's font,
`setLineSpacing` moves no line, and Builder's `setMaxLines`, `setEllipsize` and `setAlignment` do
nothing: `obtain` builds the layout at once.
- Where: `dine-atl/src/shared/android_text_Layout.c`, `src/api-impl/android/text/StaticLayout.java`.
- Owner: M9: Compose lays out its text through `StaticLayout.Builder`.

## DINE

### DINE-1

**Dialogs and Home race: Dine dismisses the app container before Java hears Home.** An alert shown
in between presents over the launcher until Java's close reaches it, and a tap whose answer
reaches Java after Home is dropped: the alert comes back on front.
- Where: `apps/Dine/Sources/Dine/Navigation.swift` `home()`: `dismissContainer` and `popToRoot`
  run before `atl_nav_home`.
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
