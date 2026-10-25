# Dev reference

Details few tasks need, kept out of `CLAUDE.md` to save context. Read only the section a task
touches. Commands and setup live in `tools/dine <group> --help`, `README.md` and
`docs/first-run.md`; ATL's slots and builds in `notes/atl-port.md`.

## Contents

- [Running ATL by hand](#running-atl-by-hand): the gtk and headless builds outside the smoke
  checks, the test-hook env vars, the cli host's `-c` commands, authored test APKs.
- [Smoke checks by eye](#smoke-checks-by-eye): what `atl-widgets` leaves on the phone to look at.
- [Debug agent](#debug-agent): how `dbg ui` walks, taps, runs actions and waits; when the agent
  listens. Read before changing `native/dev/dbgagent`, the gtk agent or a `dbg ui` command.
- [lldb and the debug server](#lldb-and-the-debug-server): SB API traps, ObjC and symbol settings,
  Swift expression internals.
  Read before changing `tools/py/dine/dbg/` or `tools/libexec/lldb`.
- [iOS builds](#ios-builds): native libs into Swift, the iOS linker, the SDK version check, asset
  catalogs, app bundle IDs. Read before changing a CMake project, `Package.swift`, `xtool.yml` or
  a build recipe in `tools/libexec/`.

## Running ATL by hand

- gtk build (after `source env.sh`):
  `ANDROID_APP_DATA_DIR=$PWD/out/linux/appdata android-translation-layer <apk> -l <pkg/path/Activity> -X -Xint`.
- The headless build isn't installed: run it from `out/linux/build/dine-atl-headless` with
  `RUN_FROM_BUILDDIR=1`.
- Test hooks (meson `test_hooks`, default on; off in the iOS release build):
  `ATL_DUMP_VIEWTREE=1` prints the view tree on stdout at first layout;
  `ATL_DUMP_DISPLAYLIST=1` prints a drawing view's display list after each of its draws (records
  backends: headless, iOS);
  `ATL_DIALOG_ANSWERS='Yes;Green'` answers alerts in order (labels, `!cancel`);
  `ATL_DBG_AGENT=<socket path>` (gtk) starts the debug agent ([Debug agent](#debug-agent)).
- `dine-atl/tests/headless/run-*.sh` drive one APK each; each script's header has its usage and
  what it checks. `tools/dine linux smoke` runs them.
- The cli host's `-c` reads commands on stdin: `back`, `home`, `front`, `insets`,
  `touch down|move|up|cancel <id> <x> <y>` (window px), `key down|up <code> [<meta> [<unicode>]]`,
  and text lines for the field that has the keyboard: `text commit|compose <text>` (`\n` a
  newline), `text delete <before> <after>`, `text select <start> <end>` (UTF-16 code units),
  `text tap <x> <y>` (the field there takes the keyboard as a toolkit's own tap gives it),
  `text action` (the return key), `text dismiss`, and `text hold` / `text release` (reports wait,
  so Java's snapshots meet a newer report). The field prints `edit:` and `keyboard:` lines.
- An authored test APK by hand:
  `tests/harness/apk.py dine-atl/tests/headless/looper out/tests/apks/looper.apk`.

## Smoke checks by eye

`dbg smoke atl-widgets` runs the widgets APK (a fullscreen frame, windowed after 5 s), then
sends Home and leaves it running for checks by eye on the phone: the status bar, the spinner, a
bar at 50%, a grey box, the screen kept on. A full `dbg smoke` run relaunches Dine after it.

## Debug agent

`native/dev/dbgagent`, linked into dev builds (`Sources/CDbgAgent`), serves `dbg ui …` in-process:
an accessibility walk of the key window, `accessibilityActivate` or escape, and a settle wait (no
transition, labels unchanged).

- Alert actions decline `accessibilityActivate`: `tap` then dismisses the topmost
  `UIAlertController` and runs the action's handler, as a touch would.
- `action <name>` runs an accessibility custom action found the way escape is: up from the walked
  elements, then from the presented controllers' views, top first.
- `type <label> <text>` makes the element the first responder if it edits text and inserts the text
  with `insertText:`, as a keyboard's committed text; no marked text. It can't press return: a
  UITextField takes an inserted newline as a space ([TOOL-4](general-todo.md#tool-4)).
- It listens on the phone's loopback only when the app gets `DINE_DBG_AGENT_PORT` in its
  environment, which `ios launch` passes; the server reaches it through a usbmux connection. A
  home-screen launch has no agent, so `dbg ui` asks for a relaunch.
- Host-side AX `perform_press` is ignored by our apps, and the host AX inspector's walk
  (`developer accessibility list-items`) highlights every element on the phone as it moves its
  focus. UI work goes through the agent.
- The agent needs no accessibility switch: after a phone reboot with no host AX client since
  boot, its walk still sees every SwiftUI label.

The gtk target runs headless sway with the pixman renderer, not Xvfb (GTK's X11 path, while WSLg
uses Wayland) or Broadway (another GDK backend, with a browser in the loop).

The gtk build's agent (`dine-atl/src/backends/ui/gtk/agent.c`, test hooks) speaks the same
protocol on the Unix socket in `ATL_DBG_AGENT`, which the gtk target sets per session. ATL starts it
when the app window first has a size. Requests come in on the agent's own thread; the walk and the
actions run on the GTK main thread, which is the Android main thread on gtk.

- The walk lists every mapped GtkLabel and GtkText with text, on screen in its own surface: the app
  window first, then the other toplevels (dialogs). A GtkText's label is its hint, then
  `hint: text` once it holds text.
- `tap` on a label inside a view sends one pointer's DOWN and UP at that view's centre through its
  window's root view (`input_tap`); Java's dispatch decides, as for a press that GTK hands on. A
  GtkText takes `gtk_widget_grab_focus`, a dialog's own GtkButton or list row `gtk_widget_activate`.
- `type` inserts at the GtkText's cursor (`gtk_editable_insert_text`), so `edit.c` reports the
  edit as it does a keyboard's.
- `back` is `atl_nav_back`; its result is only whether ATL's main loop was up
  ([TOOL-5](general-todo.md#tool-5)).
- The same hook calls `prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY)`: with Yama's `ptrace_scope` 1,
  lldb in the debug server, which is ATL's sibling, could not attach otherwise.

## lldb and the debug server

The server (`tools/py/dine/dbg/server.py`) hosts lldb through the SB API in the `.venv` Python
with `out/lldb`'s `PYTHONPATH`/`LD_LIBRARY_PATH` (`dbg/targets/lldbcmds.py`); targets are a seam
(`fake` for tests, `gtk` for ATL's gtk build). `$DINE_LLDB` borrows `libpython3.12` from the `.venv`
interpreter, which is why Python is pinned to 3.12. What makes Swift `expr`/`po` work: README
"Interactive lldb", `tools/libexec/lldb` (the relocated prefix) and the bullets below.

- In batch mode, `process connect` with no process blocks unless it's wrapped in `SetAsync(True)`.
- On Linux, `target create` needs the Mach-O inside the `.app`, not the bundle.
- SB API, local process (gtk): `AttachToProcessWithID` takes our listener, which then gets the
  process's events; the attach takes about 1 s.
- SB API: after `ConnectRemote`, `AttachToProcessWithID` needs an empty `SBListener()`; it blocks
  10 to 15 s (no deadline of its own) and its stop event never reaches our listener (read
  `GetState()`). The `process attach` command never returns in async mode.
- ObjC expressions: naming a class costs ~35 s once per process (lldb reads the runtime's class
  names; debugserver takes 5 to 8 s per `MultiMemRead` batch of them): use `objc_getClass`. Locals
  named like system symbols (`str`) fail: prefix them.
- `target.preload-symbols false` and `symbols.load-on-demand true` don't shorten the attach.
- Don't enable `symbols.enable-lldb-index-cache`: with a warm cache, attach crashes in
  `Symbol::ResolveReExportedSymbol` (from `AppleObjCTrampolineHandler`);
  [TOOL-1](bug-tracker.md#tool-1).
- `target.memory-module-load-level` `minimal` and `partial` read no nlist from device memory (only
  `complete` does, `ObjectFileMachO::ParseSymtab`), so `po`, which JITs calls into libswiftCore,
  needs the local symbols from `tools/dine ios symbols`.
- lldb finds `<App>.swiftmodule` through the CU's `DW_TAG_module` `DW_AT_LLVM_include_path` and
  loads every module through Swift Build's explicit module maps: no `-add_ast_path` or N_AST
  stabs needed.
- `ios lldb-offline` stops a synthetic core at the breakpoint: module setup and `type lookup` work,
  `expr` can't finish (a core has no OS version, so `@available(iOS 0, *)` fails to parse, and
  no JIT); the fallback `SwiftASTContext` it hits: [TOOL-2](bug-tracker.md#tool-2).
- `expression --top-level` definitions belong to the lldb target: they can't be redefined
  (`redefinition of …`), and their globals keep the first process's addresses. A body with an ObjC
  message send compiles but later expressions can't see it (`use of undeclared identifier`;
  declare it in `SBExpressionOptions.SetPrefix`). Later calls re-emit other bodies, and a `static`
  in one fails to link (`Couldn't look up symbols: __ZL…`). `nil` resolves to a symbol named
  `nil` (`void *`), not a null pointer.

## iOS builds

- `native/<lib>/` is a CMake project cross-compiled with system clang 23 and the Darwin SDK that
  xtool built from Xcode.xip (`~/.swiftpm/swift-sdks/darwin.artifactbundle`), through
  `tools/cmake/ios.toolchain.cmake`, and installed into `out/ios/`. ObjC++ libs work the same way
  (`project(<lib> OBJCXX)`).
- Swift consumes a lib through a `.systemLibrary` target whose `module.modulemap` points at the
  header and `link`s the library; `Package.swift` adds `-L out/ios/lib` via `unsafeFlags`.
  libjavacore, libopenjdk and, in dev builds, `native/dev/runtimetests` are `-force_load`ed
  because ART finds their `JNI_OnLoad_<lib>` and `Java_*` with dlsym.
- iOS links need xtool's linker: the system `ld64.lld` rejects the SDK's arm64e `.tbd` stubs
  (`malformed file … unknown target`), and plain clang falls back to GNU ld. Link with
  `clang -fuse-ld=lld -B"$DINE_IOS_TOOLSET_BIN"` (`env.sh` sets the variable;
  `ios.toolchain.cmake` passes the flags). It warns `does not support linking for platform
  iOS` on every link; ignore that.
- `apps/<App>/Package.swift` hardcodes `iosSDK = "27.0"`: the link driver can't read the SDK
  version itself, and with `sdk == minos` iOS runs the app in compatibility mode (no Liquid
  Glass). Check with `llvm-otool -l <App>.app/<App> | grep -A4 LC_BUILD_VERSION`. The Swift ↔
  Xcode coupling is in `docs/first-run.md`.
- Asset catalogs: `tools/libexec/build-ios-assets.sh` compiles
  `apps/<App>/Resources/{*.icon,*.xcassets}` with accord into `out/ios/assets/<App>`; `xtool.yml`
  lists `Assets.car` and the loose icons under `resources` and the partial plist as `infoPath`
  (shallow merge). accord's `Assets.car` matches Apple's except for the differences its README
  lists. iOS 27 SpringBoard draws `.icon` layer stacks itself; accord's pre-rendered PNGs only
  show on older iOS and in the loose icons.
- Apps are xtool SwiftPM packages (`apps/<App>/`, `xtool.yml` for the bundle ID). Free accounts
  install them as `XTL-<TeamID>.<bundleID>`; `tools/py/dine/ios.py` resolves this.
