# Dev reference

Details few tasks need, kept out of `CLAUDE.md` to save context. Read only the section a task
touches. Commands and setup live in `tools/dine <group> --help`, `README.md` and
`docs/first-run.md`; ATL's slots and builds in `notes/atl-port.md`.

## Contents

- [Running ATL by hand](#running-atl-by-hand): the gtk and headless builds outside the smoke
  checks, the test-hook env vars, the cli host's `-c` commands, authored test APKs.
- [Smoke checks by eye](#smoke-checks-by-eye): what `atl-widgets` leaves on the phone to look at.
- [UI agent](#ui-agent): how `dbg ui` reaches uidrive's agent in the app, what its walk sees, real
  touches and keys, where `.venv` gets uidrive, the gtk agent. Read before changing a `dbg ui`
  command, how Dine builds or launches the agent, uidrive itself, or the gtk agent.
- [lldb and the debug server](#lldb-and-the-debug-server): SB API traps, ObjC and symbol settings,
  Swift expression internals.
  Read before changing `tools/py/dine/dbg/` or `tools/libexec/lldb`.
- [iOS builds](#ios-builds): native libs into Swift, the iOS linker, the SDK version check, asset
  catalogs, app bundle IDs. Read before changing a CMake project, `Package.swift`, `xtool.yml` or
  a build recipe in `tools/libexec/`.

## Running ATL by hand

- gtk build (after `source env.sh`):
  `DINE_PREFIX=$PWD/out/linux/appdata android-translation-layer <apk> -l <pkg/path/Activity> -X -Xint`.
- The headless build isn't installed: run it from `out/linux/build/dine-atl-headless` with
  `RUN_FROM_BUILDDIR=1`. It runs several apps in one VM, each on its own main thread: each
  `-l <Activity>` or `--instrument <Class>` starts the next app, whose APKs follow it
  (`-l a/Main a.apk -l b/Main b.apk`; APKs before the first one belong to the first app); the
  process exits after the last app ends. Groupless JNI
  attaches have no app then, and `-c` (commands on stdin) takes one app only.
- Test hooks (meson `test_hooks`, default on; off in the iOS release build):
  `ATL_DUMP_VIEWTREE=1` prints the view tree on stdout at first layout;
  `ATL_DUMP_DISPLAYLIST=1` prints a drawing view's display list after each of its draws (records
  backends: headless, iOS);
  `ATL_DIALOG_ANSWERS='Yes;Green'` answers alerts in order (labels, `!cancel`);
  `ATL_DBG_AGENT=<socket path>` (gtk) starts the gtk agent ([UI agent](#ui-agent)).
- `dine-atl/tests/headless/run-*.sh` drive one APK each; each script's header has its usage and
  what it checks, and `common.sh` beside them holds what they share. `tools/dine linux smoke` runs
  them.
- The cli host's `-b` sends Home before the apps start: each starts with its task in the back.
- The cli host's `-d DPI` sets the screen's density (default 160, where a dp is a px).
- The cli host's `-c` reads commands on stdin: `back`, `home`, `front`, `insets` (12 or 20 dp
  values), `size <width> <height>` (dp), `night 0|1`, `dump` (the
  view tree of the window and its shown dialogs, test hooks only), `tap <text>` (a down and an up
  at the middle of the shown text view with that text, a dialog's first; prints `tap: <text> <x>,<y>`
  or `tap: no <text>`), `answer <label>` (a tap on that button or row of the last shown alert;
  prints `answer: <label>` or `answer: no <label>`), `touch down|move|up|cancel <id> <x> <y>` (window px), `key down|up|cancel <code> [<meta> [<unicode>]]` (cancel: an UP with `FLAG_CANCELED`),
  and text lines for the field that has the keyboard: `text commit|compose <text>` (`\n` a
  newline), `text delete <before> <after>`, `text select <start> <end>` (UTF-16 code units),
  `text tap <x> <y>` (the field there takes the keyboard as a toolkit's own tap gives it),
  `text action` (the return key), `text dismiss`, and `text hold` / `text release` (reports wait,
  so Java's snapshots meet a newer report). The field prints `edit:` and `keyboard:` lines; the
  `keyboard:` line carries the field's `ui_edit_config` (`kind=`, `return=`, `autocap=`, `secure=`,
  `hidden=`, `multiline=`, `autocorrect=`, `tap_focus=`, `tap_keyboard=`, `editable=`), and a field
  with no `editable` answers an edit with `edit: refused`.
- An authored test APK by hand:
  `tests/harness/apk.py dine-atl/tests/headless/looper out/tests/apks/looper.apk`.

## Smoke checks by eye

`dbg smoke atl-widgets` runs the widgets APK (a fullscreen frame, windowed after 5 s), then
sends Home and leaves it running for checks by eye on the phone: the status bar, the spinner, a
bar at 50%, a grey box, the screen kept on. A full `dbg smoke` run relaunches Dine after it.

## UI agent

`dbg ui` on iOS talks to uidrive's agent (`github.com/MiloLug/dine-uidrive`), a dylib that runs
inside the app; its wire format is that repo's `PROTOCOL.md`. `tools/libexec/build-ios-dev.sh`
builds it with Dine's toolchain from the agent sources of the installed `uidrive` package
(`python -m uidrive agent-src`) into `out/ios/dev`, so only dev builds bundle it, as
`dev/libuidrive.dylib`.
`tools/dine ios launch` (and `dbg fresh`, `ios run`, `ios lldb`) starts the app through DVT with
`DYLD_INSERT_LIBRARIES` naming that file and `UIDRIVE_PORT=47802`, except under `DINE_RELEASE=1`.
The agent's constructor turns app accessibility on and serves that port on the phone's loopback;
the server reaches it through usbmux.

- A home-screen launch has no agent, so `dbg ui` asks for a relaunch. A launch that names a dylib
  the bundle lacks starts the app without the agent, and dyld logs nothing at the default syslog
  level.
- `ls`, `activate`, `insert`, `back`, `action` and `appearance` are the agent's accessibility
  verbs, which act without a touch. `tap` is a 60 ms one-finger `gesture` at the element's frame
  centre or at `@X,Y`, `drag` a one-finger `gesture` between two such points over `--ms`, `press`
  a `key down` and `key up` of the usage `uidrive.client.KEYS` names, and `windows` the agent's
  window list. After each action the server waits on the agent's `settle`. An element with no frame
  on the screen (zero size, or its centre off the screen) is refused.
- A touch goes to the topmost window whose hit test takes the point (`--window N` from `ui windows`
  overrides it); a key goes to the keyboard's window while the first responder takes text, else to
  the key window (`PROTOCOL.md` "Window routing").
- An element that declines `accessibilityActivate` (alert actions, UIKit controls) still acts:
  `activate` sends an enabled control the actions a tap sends, else dismisses the topmost
  `UIAlertController` and runs its action with that title, as a touch would.
- `action <name>` runs an accessibility custom action found the way escape is: up from the walked
  elements, then from the presented controllers' views, top first.
- `insert <label> <text>` makes the element the first responder if it edits text and inserts the
  text with `insertText:`, as a keyboard's committed text: no marked text and no key events. A
  UITextField takes an inserted newline as a space; Return in a field is `press return`.
- `appearance light|dark|system` sets the key window's `overrideUserInterfaceStyle`, which Dine
  hears as a trait change and sends to every running app as its night (`atl_nav_set_night`).
- The walk sees the key window only: a keyboard's `inputAccessoryView` (the pads' round return
  button) sits in the keyboard's window, so `ls` doesn't list it and a screenshot may not show it
  ([TOOL-9](general-todo.md#tool-9)).
- Host-side AX `perform_press` is ignored by our apps, and the host AX inspector's walk
  (`developer accessibility list-items`) highlights every element on the phone as it moves its
  focus. UI work goes through the agent.
- SwiftUI builds the tree the walk reads only while app accessibility is on, and iOS can leave it
  off for new launches (seen after a VoiceOver session: no labels). The agent turns it on for its
  own process when it loads (`_AXSApplicationAccessibilitySetEnabled`).
- The agent logs under the os_log subsystem `uidrive` (`dbg log grep uidrive`: `uidrive: injected
  into Dine`, `uidrive: listening on 127.0.0.1:47802`). A raw request:
  `.venv/bin/python -m uidrive ask --port 47802 '<line>'`.
- `.venv` installs uidrive from its git repo at the commit `[tool.uv.sources]` names
  ([`docs/first-run.md`](../docs/first-run.md)). A change to uidrive and Dine together points the
  `tools` group at a sibling checkout, so `.venv` imports its files with no reinstall:
  `uv add --group tools --editable ../dine-uidrive`. Once uidrive's `main` is pushed, the pin goes
  back to the pushed commit:
  `uv add --group tools "uidrive @ git+https://github.com/MiloLug/dine-uidrive.git" --rev <sha>`.
  Dine's `main` goes up only with the git source: `uv sync` in a clone without the checkout next to
  it fails on the path source.
- The install stamp of `ios run` covers the agent's sources and the server's code check uidrive's
  Python files, both by path. After an edit to the agent's sources, or a switch of source,
  `dbg smoke` refuses until `ios run`; after an edit to the Python files, or a switch, every reply
  starts with the stale-code warning until the server restarts.

The gtk target runs headless sway with the pixman renderer, not Xvfb (GTK's X11 path, while WSLg
uses Wayland) or Broadway (another GDK backend, with a browser in the loop).

The gtk agent (`dine-atl/src/backends/ui/gtk/agent.c`, test hooks) speaks uidrive's protocol, with
the differences `PROTOCOL.md` lists, on the Unix socket in `ATL_DBG_AGENT`, which the gtk target
sets per session. ATL starts it when the app window first has a size. Requests come in on the
agent's own thread; the walk and the actions run on the GTK main thread, which is the Android main
thread on gtk.

- The walk lists every mapped GtkLabel and GtkText with text, on screen in its own surface: the app
  window first, then the other toplevels (dialogs). A GtkText's label is its hint, then
  `hint: text` once it holds text.
- `activate` on a label inside a view sends one pointer's DOWN and UP at that view's centre through
  its window's root view (`input_tap`); Java's dispatch decides, as for a press that GTK hands on. A
  GtkText takes `gtk_widget_grab_focus`, a dialog's own GtkButton or list row `gtk_widget_activate`.
- `insert` puts the text at the GtkText's cursor (`gtk_editable_insert_text`), so `edit.c` reports
  the edit as it does a keyboard's.
- `back` runs Back at once (`activity_back`, what `atl_nav_back` posts) and replies what it
  closed, from the state just before and after: `"menu"` (the open PopupMenu), `"dialog"` or
  `"window"` (a shown window over the activity hides: a Dialog's, or another's such as a
  drop-down's), `"activity"` (the current one finishes), else null. gtk shows no keyboard, so
  there's no word for one. Back on the root activity ends ATL on gtk, so the `settle` after it may get no reply.
  `linux smoke back-gtk` drives it (`tools/py/dine/gtkback.py`).
- `at N "LABEL"` replies the centre of element N in the app window (px). `touch down|move|up|cancel SEQ
  X Y` feeds one pointer's event at X, Y through `input_pointer`, the function GTK's own pointer
  events reach after `on_pointer_event` read them; SEQ is a made-up handle for the pointer (0: the
  mouse's NULL handle; two handles are two fingers). `key down|up KEYVAL KEYCODE [STATE]` feeds a key
  through the capture and then the bubble phase of the key controllers (`input_key`). Both run before
  the reply and reply whether Java took the event. `insert N ["LABEL", "TEXT", KEYVAL, KEYCODE]`
  also presses and releases that key in the same main-loop call as the text. `state N "LABEL"` replies
  element N's `sensitive` (`gtk_widget_is_sensitive`) and `focused` (its window's focus widget;
  `gtk_widget_has_focus` needs an active window, which the hidden display's isn't). `linux smoke input-gtk` and `text-gtk` drive them
  (`tools/py/dine/gtkinput.py`); the tools' own `dbg ui` has no verb for them. GTK 4 has no public
  `GdkEvent` constructor, so the events can't be real ones.
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
  libjavacore, libopenjdk, libwolfssljni, libtranslation_layer_main and, in dev builds,
  `native/dev/runtimetests` are `-force_load`ed (`Package.swift`, whose lines
  `tools/libexec/jni-symbols.sh` reads) because ART finds their `JNI_OnLoad_<lib>` and `Java_*`
  by name.
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
