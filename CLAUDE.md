# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A generic Android app runner for iOS, built as a translation layer ("Wine for Android") on top of
ATL + ART, distributed by sideloading. Read `notes/meta.md` for the why, the iOS constraints (no
JIT, code signing, one process, App Store rules) and the agreed layer architecture. `README.md`
has per-tool caveats; `docs/first-run.md` has the full setup. Which stage is done and which is
next: the Stages table at the top of `notes/atl-port.md`.

There's no Mac. Everything is built from Arch Linux in WSL2, and testing happens on a physical
iPhone (iPhone 13, iOS 27.0.1, free Apple ID).

## Commands

`tools/dine` is the single entry point (`tools/dine <group> --help`); it sources `env.sh` itself.
For direct tool use, `source env.sh` first: it puts the in-repo `.venv/bin` (pymobiledevice3,
meson, Python 3.12), `out/tools/bin` (xtool) and `tools/` on `PATH`, and sets `DINE_IOS_SDK`,
`DINE_LLDB` and the `PKG_CONFIG_PATH` / `LD_LIBRARY_PATH` entries for the local Linux prefix.

Setup on a new PC: `docs/first-run.md`. Tools come from pacman, paru or `uv sync`
(`pyproject.toml`, `tools` group).

**Before installing any new tool, look for a package first, in this order:**
1. `pacman -Ss <name>`
2. `paru -Ss <name>` (AUR; prebuilt `-bin` variants count)
3. PyPI, via uv: `uv add --group tools <name>` (then `uv sync`). Never `uv tool install`, pip or
   pipx.

Only if none of them ships it, download it manually, pinned, into a gitignored dir in the repo
(`out/tools/bin`, `out/downloads`). Never install to `~/.local` or other system dirs. Add every new
tool to `docs/first-run.md` under its source.

```sh
# iOS
tools/dine ios tunnel start|status       # iOS 17+ developer services; tunneld runs from boot; start mounts the DDI
tools/dine ios build-native [lib...]     # native/<lib> → out/ios/{lib,include} (CMake + tools/cmake/ios.toolchain.cmake)
                                         #   and native/dev/* (name one as dev/<lib>) unless DINE_RELEASE=1
                                         #   DINE_IOS_BUILD_TYPE=Debug for unoptimized C++ (default RelWithDebInfo)
tools/dine ios build-art                 # dine-art (ART + libcore natives + androidfw) + ICU/lz4/liblzma/wolfSSL → out/ios/lib/*.a,
                                         #   jni.h, boot jars → out/ios/share/art (junit ones → share/art-junit);
                                         #   Dine links them (not run by ios run)
tools/dine ios build-atl                 # dine-atl ui=uikit, meson cross → out/ios/lib/libtranslation_layer_main.a,
                                         #   its jars → out/ios/share/atl, the looper, dialog, nav, views, widgets test APKs → out/tests/apks
                                         #   (after linux build atl; not run by ios run)
tools/dine ios icons                     # Icons.xcassets from its sources.txt (copies from third_party's icon pack)
tools/dine ios run [App]                 # build-native + dev payload (test APKs and jars → out/ios/dev) + build-assets
                                         #   (accord) + xtool dev (build/sign/install) + launch
tools/dine ios launch [--suspended] [App] | ps [App] | kill <App|pid> | logs [App]
tools/dine ios lldb [--suspended] [App] [-- lldb args]   # interactive lldb: (re)launch + attach
tools/dine ios lldb-offline [App] <bp> [-- lldb args]    # same lldb setup on a synthetic core, no phone
tools/dine ios symbols                   # phone's dyld shared cache → out/ios-symbols (Swift po); per iOS build

# Debug server (one per session; explicit start/stop; bounded commands; logs in /tmp/dine-dbg/)
tools/dine dbg start-server | status | stop-server
tools/dine dbg smoke [scenario...] [--list] [--network]   # the iOS smoke checks, one line per step (~12 s)
tools/dine dbg fresh [--attach]          # syslog on, relaunch, wait for the UI (--attach: + attach, continue)
tools/dine dbg ui ls | ui tap <label|#N> | ui back | ui action <name> | ui screenshot [path]
                                         #   through Dine's debug agent, no attach; tap/back/action print the new
                                         #   screen; action: Back, Home, Recent apps; screenshot: DVT, PNG in the session
tools/dine dbg syslog start | attach | bp add <file:line> | continue | call <fn> [args]
tools/dine dbg wait --timeout S (--stop|--at LOC|--log TEXT|--log-re RE|--exit|--ui LABEL)   # never sleep/grep
                                         #   --log: loose words in order, not a regex; --log-re for a regex
tools/dine dbg bt | vars | exec [--lang swift|c|c++|objc] [--po] [--force] EXPR   # --force: worker thread in a syscall
tools/dine dbg log tail|grep|show [--app] [--text] [--from SEQ]   # listings start at the last launch

# Linux ATL/ART stack (third_party/ → out/linux/prefix, no sudo)
tools/dine linux build [bionic|art|opensles|atl|atl-headless ...]   # default: all, in that order
tools/dine linux smoke [gd|demo|demo-480|looper|dialog|dialog-gtk|nav|views|views-gtk|widgets ...] [--list]   # the Linux smoke checks, one line each
ANDROID_APP_DATA_DIR=$PWD/out/linux/appdata android-translation-layer <apk> -l <pkg/path/Activity> -X -Xint
                                         #   ATL_DUMP_VIEWTREE=1: view tree on stdout at first layout
                                         #   ATL_DIALOG_ANSWERS='Yes;Green': answers alerts in order (labels, !cancel)
dine-atl/tests/headless/run-demo.sh out/linux/build/dine-atl-headless third_party/atl_test_apks/demo_app.apk
                                         #   headless ATL, no display; [--density DPI] (golden demo_app.DPI.viewtree,
                                         #   cli host -d); [--update] rewrites the golden
tests/harness/apk.py dine-atl/tests/headless/looper out/tests/apks/looper.apk   # authored test APK
dine-atl/tests/headless/run-looper.sh out/linux/build/dine-atl-headless out/tests/apks/looper.apk
                                         #   worker loops + last activity finishing; ATL exits 0
dine-atl/tests/headless/run-dialog.sh [--headless] <build dir> out/tests/apks/dialog.apk
                                         #   alert + list with scripted answers, gtk or headless build
dine-atl/tests/headless/run-nav.sh out/linux/build/dine-atl-headless out/tests/apks/nav.apk
                                         #   back/home/front/insets on the cli host's stdin (-c); lifecycle
                                         #   order, the insets each show gets, exclusion spans (host: lines),
                                         #   Back on a shown list
dine-atl/tests/headless/run-widgets.sh out/linux/build/dine-atl-headless out/tests/apks/widgets.apk
                                         #   -c input: touch down|move|up|cancel <id> <x> <y> (window px),
                                         #   key down|up <code> [<meta> [<unicode>]]; tap, hold, Tab/Enter, a
                                         #   drag that scrolls, exclusion following scroll and translation, a
                                         #   drag to the end of the range (padding included), ESC
dine-atl/tests/headless/run-views.sh [--headless] <build dir> out/tests/apks/views.apk
                                         #   removeView, re-add, collected views freed (viewfreed: lines);
                                         #   gtk: a nine-patch and a StateListDrawable freed (drawablefreed: <type>);
                                         #   a row attached and detached, ImageView, ProgressBar, Matrix, Paint;
                                         #   headless: keep screen on 1/0, a fullscreen frame;
                                         #   MALLOC_PERTURB_ set, gtk or headless build

# Tests (tests/README.md)
tools/dine test runtime [fetch|build|run|all] [-f REGEX] [--network] [--update-expectations]   # ART run-tests, dalvikvm -Xint
tools/dine test framework [-f REGEX] [--update-expectations]                         # android.* JUnit suites, headless --instrument
tools/dine test unit                                                                 # harness + tools/py unit tests
```

**Dev and release builds:** iOS builds are dev builds unless `DINE_RELEASE=1` is set on
`ios build-atl` and then `ios run`. A release build leaves out every dev and test part:
- the dev screens in `apps/Dine/Sources/Dine/Dev/` (`#if DEBUG`; a release build passes xtool `-c release`);
- the libs in `native/dev/` (debug agent, hello, runtimetests) and artbridge's `dev.cpp`, which
  also adds ART's junit boot jars and `-Xcheck:jni` to the VM;
- ATL's test hooks (meson `test_hooks`);
- `Resources/Dev.xcassets`, and the test APKs, test jars and junit jars (`out/ios/dev`, bundled as
  `dev/`).

`ios run` stops when the ATL build's `test_hooks` doesn't match the flag. `dbg ui`, `dbg fresh`
and `dbg smoke` need a dev build. A release build can't start an app until the launcher gets APK
import (M8a).

**On-device work goes through a subagent, never raw `lldb`/`pymobiledevice3` with `sleep`/`grep`
waits.** Both drive `tools/dine dbg` and leave the server up for the next task; continue them with
SendMessage. Spawn neither from plan mode: it blocks every launch, attach and tap.
- `dine-peek` (Sonnet, fast): a fully specified read, e.g. "value of `self.native` at
  `HelloView.swift:23` after tapping hello++", a log line after given taps, a smoke run, a screenshot.
- `dine-debugger`: anything that needs diagnosis, stepping or judgment (why it crashes, where a value
  goes wrong).

Test suites live in the repo that owns the code (`tests/README.md` has the map); the engine is
`tests/harness/`. The runtime suite, `dine-art/tests/runtime/`: AOSP ART run-tests harvested at the
tag dine-art's ART is rebased on, graded against its `expectations/` (exit 1 = regression). The
framework suite, `dine-atl/tests/framework/`: our JUnit 3 test APKs for `android.*`, run by the cli
host's `--instrument` (`dine-atl/tests/framework/README.md`), graded the same way. After a fix
makes tests pass, rerun with `--update-expectations`; the file changes inside the fork that owns
the suite. No linters yet.
The smoke tests are:
- **iOS** (dev build): `tools/dine dbg start-server`, then `tools/dine dbg smoke` (`--network` adds **run
  https**). It covers the app grid, **hello++**, **probe** (accord's `Assets.car`), **atl** (run
  demo: both strings on screen, its `viewtree:` lines shaped like the Linux golden (window and text
  sizes differ), then Home; run looper, Dine still running after; run views, a laid-out view
  freed, Dine still running after; run dialog, tapping the alert's "Yes" and the list's "Green"; run nav: B's insets (the side strips, the home indicator) and its exclusion span, Back,
  Back on the task root, Recent apps, back to app, Home; the list A shows while in the back appears
  on back to app, leaves with Home and comes back, then its "Odd" item is tapped; run widgets:
  fullscreen frame, windowed after 5 s, Home; it stays open for checks by eye: status bar,
  spinner, a bar at 50%, a grey box, the screen kept on) and **art** (run
  hello, run jni args, run park), relaunching where ATL needs a process without a VM.
  `dbg smoke --list` prints every step and the log line it waits for; the table is
  `tools/py/dine/dbg/smoke.py`.
- **Linux:** `tools/dine linux smoke` (after `linux build`): **gd** (the gtk build runs Gravity
  Defied to `onResume` under `-Xint`; opens a WSLg window), **demo**, **demo-480** (density 480),
  **looper**, **dialog**, **nav**, **views** and **widgets** (`dine-atl/tests/headless/run-demo.sh`,
  `run-looper.sh`, `run-dialog.sh --headless`, `run-nav.sh`, `run-views.sh --headless`,
  `run-widgets.sh`) and
  **dialog-gtk** and **views-gtk** (`run-dialog.sh`, `run-views.sh` on the gtk build; open
  windows). The table is `tools/py/dine/linux.py`.

## Architecture (current scaffolding)

- **Native → iOS app path:** C/C++ under `native/<lib>/` is a CMake project. It is
  cross-compiled with system clang 23 and the Darwin SDK that xtool built from Xcode.xip
  (`~/.swiftpm/swift-sdks/darwin.artifactbundle`), and installed into `out/ios/`. Swift apps
  consume it through a `.systemLibrary` target whose `module.modulemap` points at the header and
  `link`s the library, while `Package.swift` adds `-L out/ios/lib` via `unsafeFlags`. See
  `apps/Dine`. **Native libs must be built before the app**; `ios run` does this. ART goes in
  the same way (`native/artbridge`, `Sources/CArtBridge`): libjavacore, libopenjdk and, in dev
  builds, `native/dev/runtimetests` (the authored runtime tests' JNI code) are `-force_load`ed
  because ART finds their `JNI_OnLoad_<lib>` and `Java_*` with dlsym. ObjC++ libs work the same way
  (`project(<lib> OBJCXX)`). Dev-only libs live in `native/dev/<lib>`; Swift imports them only from
  `Sources/Dine/Dev/`, so a release build links none of them.
- **Debug agent: `native/dev/dbgagent`**, linked into dev builds (`Sources/CDbgAgent`), serves `dbg ui …`
  in-process: an accessibility walk of the key window, `accessibilityActivate`/escape, and a settle
  wait (no transition, labels unchanged). Alert actions decline `accessibilityActivate`: `tap` then
  dismisses the topmost `UIAlertController` and runs the action's handler, as a touch would.
  `action <name>` runs an accessibility custom action found the way escape is: up from the walked
  elements, then from the presented controllers' views, top first.
- **Navigation: `apps/Dine/Sources/Dine/Navigation.swift`** (spec `notes/nav-gestures.md`): a
  started ATL app gets a full-screen container holding ATL's window (a UIView from below the status
  bar to the screen's bottom, handed to `dine_atl_run`); Back, Home and Recent apps come from edge swipes
  (`EdgeGestures.swift`) and accessibility actions; the running apps list is a placeholder. It listens on the phone's loopback only when the app gets
  `DINE_DBG_AGENT_PORT` in its environment, which `ios launch` passes; the server reaches it through
  a usbmux connection. A home-screen launch has no agent, so `dbg ui` asks for a relaunch.
- **Apps** are xtool SwiftPM packages (`apps/<App>/`, with `xtool.yml` for the bundle ID). Free
  accounts install them as `XTL-<TeamID>.<bundleID>`; `tools/py/dine/ios.py` resolves this.
- **Asset catalogs: accord** (sibling repo `../dine-accord`, `DINE_ACCORD`) is our near 1:1
  `actool` for Linux: it takes `actool`'s arguments, and its `Assets.car` matches Apple's except
  for the known differences its README lists (tested against catalogs compiled by Apple's
  `actool`). Anything that needs `actool` uses accord. `tools/libexec/build-ios-assets.sh`
  compiles `apps/<App>/Resources/{*.icon,*.xcassets}` with it into `out/ios/assets/<App>`;
  `xtool.yml` lists `Assets.car` and the loose icons under `resources` and
  the partial plist as `infoPath` (shallow merge). iOS 27 SpringBoard draws `.icon` layer stacks
  itself; accord's pre-rendered PNGs only show on older iOS and in the loose icons.
- **Icons** (`notes/icons.md`): where iOS has a standard icon, use the SF Symbol and ship
  nothing. The rest come from one open pack (Fluent UI, `third_party/fluentui-system-icons`) into
  `Resources/Icons.xcassets`, listed in its `sources.txt` and copied by `tools/dine ios icons`.
- **Tooling:** `tools/dine` (bash) → `tools/py/dine` (Python package: `cli.py`, `ios.py`, `dbg/`);
  build recipes in `tools/libexec/`, systemd units in `tools/systemd/`. The debug server
  (`dbg/server.py`) hosts lldb through the SB API in the `.venv` Python with `out/lldb`'s
  `PYTHONPATH`/`LD_LIBRARY_PATH` (`dbg/targets/ios.py`); targets are a seam (`fake` for tests,
  Linux later).
- **Device access:**
  - The phone stays attached to Windows. Systemd unit `usbmuxd-bridge` (socat) relays
    `/var/run/usbmuxd` to the Windows Apple Mobile Device Service on `127.0.0.1:27015`
    (mirrored networking).
  - iOS 17+ developer services (launch, debugserver, screenshots) go through the
    `dine-tunneld` unit (`pymobiledevice3 remote tunneld`, root) plus a mounted
    personalized Developer Disk Image (`tools/dine ios tunnel start` mounts it; a phone reboot
    unmounts it). `dine-tunneld` runs from boot. Pass `--tunnel ''` to `pymobiledevice3
    developer …` commands.
- **ART: `dine-art/`** is a git submodule: our fork of art_standalone
  (`git@github.com:MiloLug/dine-art.git`, branch `dine`; remote `upstream` = gitlab
  art_standalone). ART/libcore changes are made there; the superproject records the submodule
  SHA. Linux and the iOS port build from this one tree. **Don't commit or push in it without
  asking.**
- **ATL: `dine-atl/`** is a git submodule too: our fork of android_translation_layer
  (`git@github.com:MiloLug/dine-atl.git`, branch `dine`; remote `upstream` = gitlab ATL).
  Upstream isn't merged (we're too far apart): read its commits and reimplement the wanted ones
  by hand. Keeping our diff small or merge-friendly is not a goal. Toolkit, OS and native-code-loader code sits behind
  backend slots (host, loop, ui, gfx; services and native are planned), each open to any number of
  backends picked by meson options (`-Dhost= -Dloop= -Dui= -Dgfx=`). Slot interfaces are in
  `src/slots/`, shared code in `src/shared/` plus the portable files of `src/api-impl-jni/`
  (static library `atl_shared`, built without GTK or glib; graphene for Matrix comes from a meson
  wrap without GObject except on the desktop build, and Dine links `libgraphene-1.0.a`), backends in
  `src/backends/<slot>/<name>/`. Natives not yet behind a slot stay in `src/api-impl-jni/` and
  build only with ui=gtk, so a headless build throws `UnsatisfiedLinkError` on them. The iOS
  build has no glib at all. The test hooks (`ATL_DIALOG_ANSWERS`, `ATL_DUMP_VIEWTREE`) are in
  `src/shared/test_hooks.c` and the ui backends' `dump.c`, built with meson `test_hooks` (default
  on; off in the iOS release build). Slots, rules and milestones: `notes/atl-port.md`.
  **Don't commit or push in it without asking.** Our changes so far: dex with `d8` through
  `build-aux/d8-jar.sh` (adds the manifest meson's install needs), and `framework-res`
  regeneration opt-in (`-Dregenerate_framework_res`), since the `aapt` from
  android-sdk-build-tools would rewrite ATL's `R.java` in place.
  - Builds: desktop (`gtk`/`glib`/`gtk`/`gsk`, `out/linux/build/dine-atl`, installed),
    headless (`cli`/`poll`/`headless`/`record`, `out/linux/build/dine-atl-headless`, not
    installed: run it from its build dir with `RUN_FROM_BUILDDIR=1`) and iOS
    (`embedded`/`cfrunloop`/`uikit`/`record`, meson cross, `out/ios/build/dine-atl`; uikit keeps
    the headless view records, mirrors them as UIViews and measures text with UILabel, and shows
    alerts as `UIAlertController`s; ScrollView is a UIScrollView). Never build
    the two Linux ones at once: both write `src/api-impl-jni/generated_headers`. The iOS build
    compiles no Java and uses those headers and the Linux jars.
  - In Dine, artbridge owns the one VM: `dine_atl_run` creates it with ATL's options and runs the
    `embedded` host on an 8 MiB pthread with its own CFRunLoop, which stays the Android main thread.
    uikit queues UIKit changes there and sends them to UIKit's thread once per layout pass; only text
    measurement waits for UIKit's thread, so UIKit's thread must never wait for the Android one.
  - Input: backends hand a window's touches and keys to `src/shared/input.c`, and Java dispatches
    them as AOSP does (`android.view.ATLInput` stands in for ViewRootImpl); the toolkit owns scroll
    offsets and Java mirrors them. AOSP code ported into the fork is listed in `dine-atl/doc/AOSP.md`.
- **Both forks must keep building and passing on Linux** (`tools/dine linux build` +
  `tools/dine test runtime`): Linux is the fast loop and the reference for the iOS port.
- **Linux stack:** `third_party/{bionic_translation,libopensles-standalone,atl_test_apks}` are
  plain upstream clones (gitignored).
  - `d8` = `tools/bin/d8` (build-tools d8 on JDK 21; JDK 8 stays the system default).
  - Versions: ART is Android 10 (`android-security-10.0.0_r75`), libcore is 8.1/9, ATL's
    device level (`SDK_INT`) is 21, set by hand in `SystemProperties.java`
    (`ro.build.version.sdk`) and raised as `android.*` catches up; apps with a higher minSdk run
    with a warning.
  - dine-art (art_standalone) uses its own make-based build and **gcc**, in-tree (`dine-art/out`,
    ~2 GB). The same build cross-compiles for iOS with `____TARGET=ios` (clang, static archives,
    `build/core/combo/HOST_darwin-arm64.mk`, intermediates in `dine-art/out/host/darwin-x86`).
    One config on both: C++ interpreter, no boot image/oat/dex2oat, 16 KB pages, heap references
    relative to a heap reservation above 4 GB (`notes/art-findings.md`).
  - Make doesn't track flag changes: after editing cflags in an `.mk`, delete the module's
    `out/host/*/obj` **and** `out/host/*/gen` intermediates (stale generated `asm_defines.h`).
  - ATL rpaths assume system lib dirs; `env.sh` compensates with `LD_LIBRARY_PATH`.

## Gotchas when operating tools

- **Never run xtool with stdin = `/dev/null`.** It crashes with `epoll_ctl … Operation not
  permitted`. When running non-interactively, use a pty (`script -qec "xtool …" /dev/null`).
- **Ask the user before answering yes to xtool prompts.** For example,
  `The following certificates must be revoked … Continue? (yes/no)` is an Apple ID account
  change: it breaks other sideload tools' certificates.
- **Ignore `DebugserverClient.Error.unknown` from `xtool launch` / `xtool dev`.** It's expected:
  xtool uses the pre-iOS-17 debugserver. Launch with
  `pymobiledevice3 developer dvt launch --tunnel '' <bundle>` instead.
- **"Failed to launch process with bundle identifier …"** means either the phone is locked or
  the developer certificate isn't trusted on the phone. Ask the user to unlock or trust. Apps
  that are backgrounded get killed.
- **`xtool dev run` hangs after `[Installing] 100%`:** the install waits for the old app process
  to die, and one that was debugged (even detached) doesn't. `tools/dine ios run` kills running
  instances first; with plain xtool, `tools/dine ios kill Dine` and rerun.
- **Device round trips cost ~44 ms without `quickack`:** AMDS's small writes on usbmuxd-bridge's
  socat connection to Windows wait for Linux's 40 ms delayed ACK. `wsl-quickack` (sibling repo
  `../wsl-quickack`, its own systemd unit) keeps `quickack 1` on WSL's routes to Windows;
  `ios tunnel status` shows it. With it a small gdb-remote round trip takes ~1.6 ms.
- **lldb:** use `$DINE_LLDB` (`tools/libexec/lldb`), the Swift toolchain lldb, which borrows
  `libpython3.12` from the `.venv` interpreter (why Python is pinned to 3.12).
  - It runs from a relocated copy in `out/lldb/` whose Swift resource dir is xtool's Darwin
    one; that, `target.sdk-path` and local system symbols (`tools/dine ios symbols`) are what
    make Swift `expr`/`po` work. Why: `notes/swift-dbg.md`.
  - In batch mode, `process connect` with no process blocks unless it's wrapped in
    `SetAsync(True)`.
  - On Linux, `target create` needs the Mach-O inside the `.app`, not the bundle.
  - A failing `-o` command skips the rest (even without `-b`), including `process detach`.
  - SB API: after `ConnectRemote`, `AttachToProcessWithID` needs an empty `SBListener()`; it
    blocks ~10–15 s (no deadline of its own) and its stop event never reaches our listener (read
    `GetState()`). The `process attach` command never returns in async mode.
  - ObjC expressions: naming a class costs ~35 s once per process (lldb reads the runtime's class
    names; debugserver takes 5–8 s per `MultiMemRead` batch of them): use `objc_getClass`.
    Locals named like system symbols (`str`) fail: prefix them.
  - Host-side AX `perform_press` is ignored by our apps, and the host AX inspector's walk
    (`developer accessibility list-items`) highlights every element on the phone as it moves its
    focus: UI goes through the debug agent.
  - The first expression after an attach takes ~8–15 s (Swift `po` included); later ones < 1 s.
    `target.preload-symbols false` and `symbols.load-on-demand true` don't shorten the attach.
  - Don't enable `symbols.enable-lldb-index-cache`: with a warm cache, attach crashes in
    `Symbol::ResolveReExportedSymbol` (from `AppleObjCTrampolineHandler`).
- **iOS links need xtool's linker:** the system `ld64.lld` rejects the SDK's arm64e `.tbd` stubs
  (`malformed file … unknown target`), and plain clang falls back to GNU ld. Link with
  `clang -fuse-ld=lld -B"$DINE_IOS_TOOLSET_BIN"` (`env.sh`; `ios.toolchain.cmake` does it). It
  warns `does not support linking for platform iOS` on every link; ignore that.
- **Free Apple ID:** certificates expire every 7 days (re-run `tools/dine ios run`), with at most 3 apps
  installed.
- **Version coupling:** Swift (AUR `swift-bin` 6.4.x) must match the Xcode version the SDK came
  from (27). `apps/<App>/Package.swift` also hardcodes `iosSDK = "27.0"`: the link driver can't
  read the SDK version itself, and with `sdk == minos` iOS runs the app in compatibility mode (no
  Liquid Glass). Check with `llvm-otool -l <App>.app/<App> | grep -A4 LC_BUILD_VERSION`.
