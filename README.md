# dine — iPhone dev environment (Arch on WSL2)

Goal: run Android apps on iPhone via ATL + ART. Most work happens on Linux (ATL/ART,
`-Xint` reproduces the no-JIT iPhone situation); only iOS-specific parts need the device.

```sh
source env.sh
```

## First-time setup

See **[docs/first-run.md](docs/first-run.md)**: Windows prerequisites, every system package
(pacman + paru), the uv-managed `.venv` (Python tooling), device bridge, xtool, iOS SDK, debugger
symbols, ATL build, and a verification checklist.

## Layout

| Path | What |
|---|---|
| `env.sh` | `PATH` (`.venv/bin`, `out/tools/bin`), `DINE_IOS_SDK`, `DINE_IOS_SWIFT_RESOURCES`, `DINE_LLDB`, Linux prefix/pkg-config paths |
| `pyproject.toml`, `uv.lock` | Python tooling for the in-repo `.venv` (`uv sync`): Python 3.12, pymobiledevice3, meson |
| `docs/first-run.md` | setup on a new PC: every package, where each tool comes from |
| `tools/usbmuxd-bridge.service` | `/var/run/usbmuxd` → Windows Apple Mobile Device Service (`127.0.0.1:27015`) |
| `tools/dine-tunneld.service` | `pymobiledevice3 remote tunneld` (iOS 17+ developer services) |
| `tools/ios.toolchain.cmake` | clang cross-compile → `arm64-apple-ios` with xtool's SDK |
| `scripts/build-ios-native.sh` | builds `native/*` → `out/ios/{lib,include}` (`DINE_IOS_BUILD_TYPE`, default `RelWithDebInfo`) |
| `scripts/ios-run.sh [App]` | native libs → `xtool dev` (build/sign/install) → launch via DVT |
| `scripts/ios-lldb.sh [--suspended] [App] [lldb args]` | launch (optionally suspended) + attach Swift lldb through the tunnel |
| `scripts/ios-lldb-offline.sh [App] <breakpoint> [lldb args]` | same lldb setup on a synthetic core (`tools/ios-core.py`), no phone |
| `scripts/ios-symbols.sh` | phone's dyld shared cache → per-dylib files in `out/ios-symbols/` (lldb `--sysroot`) |
| `tools/lldb` | Swift toolchain lldb run from `out/lldb/` with the iOS Swift resource dir (borrows libpython3.12 from the `.venv`) |
| `scripts/build-linux-stack.sh` | bionic_translation → dine-art → libopensles → ATL → `out/linux/prefix` (applies `patches/<repo>/*.patch` to `third_party/` first) |
| `scripts/test-runtime.sh` | ART run-tests on the local `dalvikvm -Xint` (`tests/android-compat/runtime`) |
| `native/hello` | C++ static lib smoke test (stand-in for ART / bionic shim) |
| `apps/Dine` | xtool SwiftUI app: launcher grid (SQLite) + hello++ screen linking `native/hello` |
| `third_party/` | editable clones of the ATL stack (gitignored, own git repos) |
| `dine-art/` | submodule: our fork of art_standalone (ART + libcore), branch `dine` |
| `patches/<repo>/` | fixes to `third_party/` clones that must survive a fresh clone (ATL: d8 dexing, framework-res opt-in) |
| `tools/bin/d8` | build-tools d8 on JDK 21 (on `PATH` via `env.sh`), used by the ART/ATL build and the tests |
| `tests/` | test worlds: `android-compat/{runtime,framework,package,apps}`, `launcher/` |

## Device connection

The iPhone stays attached to **Windows** (Apple Devices / iTunes driver, AMDS service).
WSL uses mirrored networking, so `127.0.0.1:27015` is Windows' usbmuxd; the
`usbmuxd-bridge` unit (socat) exposes it as `/var/run/usbmuxd`. Pair records are
served by AMDS. Do **not** install Arch's `usbmuxd` daemon or use usbipd
(xtool#19: usbipd → "message was too large" / `muxError`).

```sh
idevice_id -l                       # UDID
ideviceinfo -k ProductVersion
pymobiledevice3 usbmux list
```

Fallback if the unit is down: `export USBMUXD_SOCKET_ADDRESS=127.0.0.1:27015`.

## iOS app build / install / launch

```sh
scripts/ios-run.sh                   # = build-ios-native.sh + xtool dev + DVT launch
```

- `xtool launch` / the launch step of `xtool dev` fail with `DebugserverClient.Error.unknown`
  (pre-iOS-17 debugserver). Launch with
  `pymobiledevice3 developer dvt launch --tunnel '' XTL-<TeamID>.<bundleID>` (what the script does).
- Free accounts install as `XTL-<TeamID>.<bundleID>` (e.g. `XTL-97U7V3FX2D.dev.dine.Dine`).
- Run xtool from a real terminal: with stdin = `/dev/null` it crashes (`epoll_ctl ... Operation not permitted`).
- **Keep the phone unlocked, app in foreground.** Locked → launch fails (same error as untrusted
  cert). Backgrounded → app suspended then killed. After reboot unlock once. Tip: Auto-Lock → Never.
- Free Apple ID: certs last **7 days** (re-run `xtool dev`), max 3 sideloaded apps.
- First install: iPhone → Settings → General → VPN & Device Management → trust the developer.
- `xtool auth status`, `xtool sdk status`.
- Native libs: link prebuilt `.a` via a `.systemLibrary` module map + `-L` unsafeFlags
  (see `apps/Dine/Package.swift`, `Sources/CDineHello/module.modulemap`).

## Logs / crashes

```sh
pymobiledevice3 syslog live -m Dine
idevicesyslog -p Dine
pymobiledevice3 crash pull out/crashes
```

Use `os.Logger` (`log.notice(...)`, `privacy: .public` for dynamic strings) — `print()` goes to
stdout and never reaches syslog.

## Debugging (lldb remote attach)

```sh
scripts/ios-lldb.sh                                  # interactive
scripts/ios-lldb.sh Dine -b -o bt -o "process detach"   # scripted
# Break in startup code: the app waits for the debugger, so set breakpoints, then continue.
scripts/ios-lldb.sh --suspended Dine -b -o "b hello.cpp:12" -o c -o "frame variable" -o "process detach"
scripts/ios-lldb.sh --suspended Dine -b -o "b HelloView.swift:8" -o c -o "po self" -o "process detach"
# Unoptimized native libs (C++ locals not "optimized out"); plain ios-run.sh switches back.
DINE_IOS_BUILD_TYPE=Debug scripts/ios-run.sh
# Logs that survive a killed/hung session: lldb types+expr, swift health, gdb-remote packets.
DINE_LLDB_LOG=out/lldb-log scripts/ios-lldb.sh …
# No phone: same setup on a synthetic core stopped at a breakpoint (module setup, type lookup).
scripts/ios-lldb-offline.sh HelloView.swift:8 -b -o "type lookup DineApp"
```

What it does: ensure `dine-tunneld` (RemoteXPC tunnel, root for TUN) + personalized DDI
(`mounter auto-mount`), DVT-launch the app, get the debugserver address from
`developer debugserver start-server`, then in `tools/lldb`:
`platform select remote-ios --sysroot out/ios-symbols/<ver>` → `target create
apps/<App>/xtool/<App>.app/<App>` (local Mach-O + debug info) → `target.sdk-path` → async
`process connect` (sync mode blocks with no process) → `process attach -p`.

- **Swift expressions** (`expr`, `po`, `type lookup`) need three things, all automatic once set up
  (details: `notes/swift-dbg.md`):
  - `target.sdk-path` = `$DINE_IOS_SDK`: lldb can't map the DWARF SDK name to a path on Linux.
  - `tools/lldb` runs lldb from a relocated copy in `out/lldb/` (rebuilt when swift-bin changes)
    because lldb's Swift resource dir is fixed to `<liblldb dir>/swift`; there it is xtool's
    Darwin one (prebuilt iOS modules). The Linux one can't load the iOS stdlib. Don't use this
    lldb for Linux Swift.
  - Local system symbols (`scripts/ios-symbols.sh`): without them `expr 1 + 1` works but `po`
    fails with `Couldn't look up symbols: $ss16_DebuggerSupport…` and falls back to `p`.
    Stopgap: `DINE_LLDB_LOAD_LEVEL=complete` reads symbols from device memory (~30 s extra).
- Attach → first breakpoint ≈ 5 s with local symbols. Memory is read in 16 KiB lines
  (`target.process.memory-cache-line-size`); every read is a ~50 ms tunnel round trip. The
  first Swift expression in a session takes ~15 s (it loads every module's reflection metadata).
- System frames are symbolicated from the local symbols (`SwiftUI\`View.toolbar(content:)`).
- `ios-lldb.sh` always (re)launches the app via DVT, then attaches; it doesn't attach to an
  already-running instance. Without `--suspended`, startup code has already run by then.
- `Error while searching for Xcode SDK: HostInfoError` during `expr` is harmless noise.
- C++ exceptions thrown inside an expression stop it (`internal c++ exception breakpoint`), as in
  Xcode. Example: calling `dine_hello()` before its static init ran (it throws and catches).
- A failing `-o` command (with or without `-b`) skips the rest, including `process detach`, so put
  speculative `expr`s last. In a C++ frame, Swift needs `-l swift` (`expr -O -l swift -- …` for
  po); plain `po` parses as C++. Inside one `script …HandleCommand(…)` call, `frame select` and stops
  from `expr -i false` don't update the frame later commands see; use real breakpoint hits.
- Verified: C++ breakpoints at startup, libc++ formatters (`std::vector<std::string>`,
  `std::string`), backtraces across C++ → Swift → SwiftUI with names, Swift `frame variable`,
  `expr -l swift`, `po`, `type lookup`, C `expr (const char *)dine_hello()`.
- If you kill a hung lldb, kill the app too. `xtool dev run` hanging after `[Installing] 100%`
  (no `[Verifying]`) means a previous install is still waiting for the old app process to
  terminate, e.g. one left stopped by a killed lldb (installcoordinationd logs
  `operation was already pending`). Kill the app:
  `pymobiledevice3 developer dvt proclist --tunnel ''` → `pymobiledevice3 developer dvt kill --tunnel '' <pid>`.

## Linux ATL / ART

```sh
scripts/build-linux-stack.sh            # all stages; or: bionic art opensles atl
source env.sh                           # PATH + LD_LIBRARY_PATH for out/linux/prefix
ANDROID_APP_DATA_DIR=$PWD/out/linux/appdata \
  android-translation-layer third_party/atl_test_apks/org.happysanta.gd_29.apk \
  -l org/happysanta/gd/GDActivity -X -Xint     # -X passes straight to ART; -Xint = interpreter only
```

Test APKs: `third_party/atl_test_apks` (gitlab.com/android_translation_layer/atl_test_apks).
Verified: Gravity Defied reaches `onResume` under `-Xint` in WSLg.

Runs under WSLg (Wayland). ART here builds with gcc for x86_64; the iOS port will need
a clang/arm64-apple-ios build of the same sources.

## Tests

`tests/README.md` describes the test worlds. Working today: ART run-tests on the local
`dalvikvm -Xint`, `scripts/test-runtime.sh` (exit 1 = regression against
`tests/android-compat/runtime/expectations/`). Details: `tests/android-compat/runtime/README.md`.

## Gotchas

- No JIT by default for sideloaded apps → ART must work interpreter-only on device (test with
  `-Xint` on Linux). StikDebug can enable JIT for dev-signed apps on iOS 17.4+, but it's fragile
  and untested on this phone / iOS 27; treat it as an optional speed-up.
- Simulator doesn't exist here and wouldn't enforce code signing anyway; test on device.
- xtool: no asset catalogs, no Interface Builder, no app extensions, no debugger launch.
- Update xtool: download the newer `xtool-x86_64.AppImage` over `out/tools/bin/xtool`
  (docs/first-run.md step 4), and check the Swift ↔ Xcode coupling.
