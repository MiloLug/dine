# dine — iPhone dev environment (Arch on WSL2)

Goal: run Android apps on iPhone via ATL + ART. Most work happens on Linux (ATL/ART,
`-Xint` reproduces the no-JIT iPhone situation); only iOS-specific parts need the device.

```sh
source env.sh
```

## First-time setup (from scratch)

Tested on Arch Linux in WSL2 (Windows 11), iPhone 13 on iOS 27.0.1, Swift 6.4.1, xtool 1.22.2,
Xcode 27. Total time: about 45 minutes, mostly unattended (SDK extraction plus the ART build).

### 0. Windows + phone prerequisites

1. Install **Apple Devices** (Microsoft Store) or **iTunes**. Either one installs the
   *Apple Mobile Device Service* (AMDS), which owns the USB connection and listens on
   `127.0.0.1:27015`. Check that it's running: `Get-Service "Apple Mobile Device Service"`.
2. Plug in the iPhone via USB, unlock it, and tap **Trust This Computer**. The pairing record ends
   up in `C:\ProgramData\Apple\Lockdown\<UDID>.plist`, and WSL reuses it through AMDS.
3. Turn on **Developer Mode** on the phone: Settings → Privacy & Security → Developer Mode. This
   needs a reboot plus a confirm prompt after boot. The toggle only appears once a developer tool
   has used the phone. If it's missing, it shows up after the first install attempt in step 5;
   enable it then, reboot, and retry.
4. `%UserProfile%\.wslconfig` needs mirrored networking, so WSL can see Windows' `127.0.0.1`:
   ```ini
   [wsl2]
   networkingMode=Mirrored
   [experimental]
   hostAddressLoopback=true
   ```
   `/etc/wsl.conf` needs `[boot] systemd=true`. Then run `wsl --shutdown` and restart WSL.
   - Without mirrored networking, use the netsh portproxy + firewall-rule workaround from
     [xtool#19](https://github.com/xtool-org/xtool/issues/19#issuecomment-2898986718) and set
     `USBMUXD_SOCKET_ADDRESS=<windows-host-ip>:27015`.
   - **Don't** use usbipd to pass the iPhone into WSL. It breaks with "message was too large" /
     `AFCClient.Error.muxError`, and it takes the phone away from Windows.
5. In WSL: Arch with `sudo` and `paru`. Check the bridge target from WSL:
   `python3 -c "import socket; socket.create_connection(('127.0.0.1', 27015)); print('ok')"`.

### 1. Packages

```sh
sudo pacman -S --needed llvm fuse2 ninja meson socat libimobiledevice zsync jdk8-openjdk git \
  bubblewrap libbsd libunwind elfutils mesa expat icu libpng lz4 openssl xz zlib libcap valgrind \
  zip alsa-lib ffmpeg gtk4 gtk4-layer-shell graphene libgudev libportal libsecret sqlite \
  vulkan-icd-loader vulkan-headers wayland wayland-protocols webkitgtk-6.0 openxr glib2-devel \
  libglvnd libdrm patchelf
paru -S --needed swift-bin wolfssl-jni bsd-compat-headers
```

- `bsd-compat-headers` is AUR-only, so pacman rejects it.
- `swift-bin` installs into `/usr/lib/swift/usr` and only symlinks `swift`, `swiftc` and
  `sourcekit-lsp`, so it doesn't clash with system clang/lldb. **The Swift version must match
  the Xcode version** xtool expects (Swift 6.4 ↔ Xcode 27). Check `xtool`'s docs when either
  one changes.
- **Do NOT install `usbmuxd`** (the daemon). It would fight the bridge for `/var/run/usbmuxd`.
  If something pulls it in, run `sudo systemctl mask usbmuxd.service`.
- `fuse2` is needed to run the xtool AppImage (Arch only ships `fuse3` by default).
- `llvm` provides `llvm-ar` and `llvm-ranlib` for the iOS CMake toolchain. Arch's `clang`
  package doesn't include them.

### 2. Device bridge

```sh
sudo install -m644 tools/usbmuxd-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now usbmuxd-bridge
idevice_id -l                                                        # prints UDID
ideviceinfo -q com.apple.security.mac.amfi -k DeveloperModeStatus    # prints true
```

- If that second command prints `true`, the pairing record is being served correctly. If you get
  pairing errors instead, copy the Windows plist from step 0.2 into `/var/lib/lockdown/`.
- The bridge only works while Windows can see the phone. Replugging or reconnecting is handled by
  AMDS; nothing needs restarting on the WSL side.

### 3. xtool + Apple ID + iOS SDK

```sh
curl -fL https://github.com/xtool-org/xtool/releases/latest/download/xtool-x86_64.AppImage \
  -o ~/.local/bin/xtool && chmod +x ~/.local/bin/xtool
xtool auth login                       # interactive
```

- **Login:** pick password mode for a free Apple ID, or API key mode for a paid developer
  account. Password mode uses private Apple APIs, so **use a throwaway Apple ID**. You'll get a
  2FA prompt.
- **Free account limits:** certificates expire after **7 days** (re-run `scripts/ios-run.sh` to
  refresh), at most **3** sideloaded apps per device, and no paid-only entitlements. Bundle IDs
  get rewritten to `XTL-<TeamID>.<bundleID>`.
- **Download Xcode** (the `.xip`) in a browser from
  <https://developer.apple.com/download/all/?q=Xcode>. It needs an Apple ID and accepting the
  license; `curl` won't work. Make sure the download is complete before installing (it's about
  2 GB, and a partial file fails late).
- **Copy the .xip to the Linux filesystem before installing.** Reading it directly from `/mnt/c`
  is slow. Then:
  ```sh
  cp /mnt/c/Users/<you>/Downloads/Xcode_27.xip ~/xcode.xip
  xtool sdk install ~/xcode.xip          # ~15 min
  swift sdk list                         # → darwin
  rm ~/xcode.xip                         # not needed after install
  ```
  The SDK lands in `~/.swiftpm/swift-sdks/darwin.artifactbundle`, and `env.sh` finds
  `iPhoneOS.sdk` there automatically (`$DINE_IOS_SDK`).
- **Always run xtool in a real terminal.** With stdin redirected from `/dev/null` it crashes with
  `epoll_ctl ... Operation not permitted`. For scripted use, wrap it with `script -qec "xtool …" /dev/null`.

### 4. Logs, launch and debug tooling

```sh
uv tool install --python 3.13 pymobiledevice3
sed "s|@HOME@|$HOME|" tools/dine-tunneld.service | sudo tee /etc/systemd/system/dine-tunneld.service >/dev/null
sudo systemctl daemon-reload && sudo systemctl start dine-tunneld   # not enabled; scripts start it
pymobiledevice3 mounter auto-mount --tunnel ''     # Developer Disk Image (needs phone unlocked)
uv python install 3.12                             # libpython3.12 for Swift's lldb (tools/lldb)
```

- `pymobiledevice3` is pinned to Python 3.13 because system Python 3.14 is too new for some wheels.
- `tunneld` runs as root because it creates a TUN interface. Check it with
  `curl -s 127.0.0.1:49151`.
- The Developer Disk Image is downloaded and personalized (signed by Apple) for the device on
  first use. Remount it after every phone reboot; the scripts do this for you.
- Swift's `lldb` needs `libpython3.12`, which Arch doesn't ship. `tools/lldb` borrows it from
  uv's CPython 3.12.

### 5. First app install

```sh
cd <repo> && source env.sh
scripts/ios-run.sh                     # from a real terminal (prompts!)
```

1. **First run, certificate prompt:** a free Apple ID has only a few development-certificate
   slots, and xtool can't reuse one it didn't create. You may see
   `The following certificates must be revoked: … Continue? (yes/no)`. Answering `yes` invalidates
   certificates made by other sideload tools (AltStore, SideStore, Sideloadly) on that Apple ID,
   and apps they installed stop refreshing.
2. **Trust the developer:** the first launch fails with `Failed to launch process with bundle
   identifier …`. On the phone go to Settings → General → VPN & Device Management → your Apple ID
   → **Trust**, then rerun or launch again.
3. **Phone state:** keep it unlocked with the app in the foreground. A locked phone fails to
   launch with the *same* error as an untrusted certificate. A backgrounded app gets suspended and
   then killed. Set Settings → Display & Brightness → Auto-Lock → **Never** while developing.
4. `xtool dev` prints `DebugserverClient.Error.unknown` at the end. That's expected:
   xtool's own launcher doesn't work on iOS 17+. `ios-run.sh` ignores this one error and launches
   the app through pymobiledevice3 instead.

### 6. Linux ATL/ART stack

```sh
mkdir -p third_party && cd third_party
for r in bionic_translation art_standalone libopensles-standalone android_translation_layer; do
  git clone https://gitlab.com/android_translation_layer/$r.git
done
git clone --depth 1 https://gitlab.com/android_translation_layer/atl_test_apks.git
cd .. && scripts/build-linux-stack.sh  # ~10 min on 16 cores; installs to out/linux/prefix (no sudo)
```

- `third_party/` is gitignored. Each clone is its own git repo, so patch them in place.
- art_standalone builds with **gcc** using its own make-based build (not clang). Its makefile links
  `-ldl_bio` without pkg-config, so the script exports `LIBRARY_PATH` and `CPATH` for the local
  prefix.
- ATL's rpaths assume the bionic_translation libraries are in a system lib dir. `env.sh` adds
  `out/linux/prefix/lib` to `LD_LIBRARY_PATH` instead (checked: no names clash with `/usr/lib`).
- GUI apps open through WSLg (Wayland). No extra setup is needed.

### 7. Verify

```sh
source env.sh
pymobiledevice3 usbmux list                          # phone visible
scripts/ios-run.sh                                   # Dine shows the app grid
pymobiledevice3 syslog live -m Dine                  # "loaded N apps"; tap hello++ → "Dine native: Hello from C++ …"
scripts/ios-lldb.sh Dine -b -o "expr -l c -- (const char *)dine_hello()" -o "process detach"
ANDROID_APP_DATA_DIR=$PWD/out/linux/appdata android-translation-layer \
  third_party/atl_test_apks/org.happysanta.gd_29.apk -l org/happysanta/gd/GDActivity -X -Xint
```

## Layout

| Path | What |
|---|---|
| `env.sh` | `DINE_IOS_SDK`, `DINE_LLDB`, Linux prefix/pkg-config paths |
| `tools/usbmuxd-bridge.service` | `/var/run/usbmuxd` → Windows Apple Mobile Device Service (`127.0.0.1:27015`) |
| `tools/dine-tunneld.service` | `pymobiledevice3 remote tunneld` (iOS 17+ developer services) |
| `tools/ios.toolchain.cmake` | clang cross-compile → `arm64-apple-ios` with xtool's SDK |
| `scripts/build-ios-native.sh` | builds `native/*` → `out/ios/{lib,include}` (`DINE_IOS_BUILD_TYPE`, default `RelWithDebInfo`) |
| `scripts/ios-run.sh [App]` | native libs → `xtool dev` (build/sign/install) → launch via DVT |
| `scripts/ios-lldb.sh [--suspended] [App] [lldb args]` | launch (optionally suspended) + attach Swift lldb through the tunnel |
| `tools/lldb` | Swift toolchain lldb wrapper (borrows libpython3.12 from uv) |
| `scripts/build-linux-stack.sh` | bionic_translation → art_standalone → libopensles → ATL → `out/linux/prefix` |
| `native/hello` | C++ static lib smoke test (stand-in for ART / bionic shim) |
| `apps/Dine` | xtool SwiftUI app: launcher grid (SQLite) + hello++ screen linking `native/hello` |
| `third_party/` | editable clones of the ATL stack (gitignored, own git repos) |

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
# Unoptimized native libs (C++ locals not "optimized out"); plain ios-run.sh switches back.
DINE_IOS_BUILD_TYPE=Debug scripts/ios-run.sh
```

What it does: ensure `dine-tunneld` (RemoteXPC tunnel, root for TUN) + personalized DDI
(`mounter auto-mount`), DVT-launch the app, get the debugserver address from
`developer debugserver start-server`, then in `tools/lldb`:
`platform select remote-ios` → `target create apps/<App>/xtool/<App>.app/<App>` (local Mach-O +
debug info) → async `process connect` (sync mode blocks with no process) → `process attach -p`.

- Attach ≈ 1–2 min: system dylibs are read from device memory
  (`target.memory-module-load-level minimal` keeps it bearable). lldb on Linux can't use the raw
  dyld shared cache; it would need it split into per-dylib files (Xcode's extractor is macOS-only).
  Raw cache (7.2 GB): `pymobiledevice3 developer fetch-symbols download --tunnel '' <dir>`.
- Consequence: frames inside system frameworks (`libsystem_kernel`, `CoreFoundation`, …) show
  no symbol names. Your own code is fully symbolicated. Fix later = split the DSC with a
  cross-platform extractor.
- `ios-lldb.sh` always (re)launches the app via DVT, then attaches; it doesn't attach to an
  already-running instance. Without `--suspended`, startup code has already run by then.
- `Error while searching for Xcode SDK: HostInfoError` during `expr` is harmless noise.
- `-b` stops at the first failing command, skipping the rest (including `process detach`), so put
  speculative `expr`s last. Inside one `script …HandleCommand(…)` call, `frame select` and stops
  from `expr -i false` don't update the frame later commands see; use real breakpoint hits.
- Verified: attach, `image lookup -n dine_hello` → `hello.cpp:8`, `expr (const char *)dine_hello()`;
  with `--suspended`, C++ breakpoints hit at startup, libc++ formatters (`std::vector<std::string>`,
  `std::string`), and backtraces across C++ → Swift with file:line. Swift `frame variable` works.
- Swift `expr`/`po` don't work (`failed to get module "Swift"`) and can hang lldb: see
  `notes/swift-dbg.md`. If you kill a hung lldb, kill the app too (next item).
- `xtool dev run` hanging after `[Installing] 100%` (no `[Verifying]`): a previous install is still
  waiting for the old app process to terminate, e.g. one left stopped by a killed lldb
  (installcoordinationd logs `operation was already pending`). Kill the app:
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

## Gotchas

- No JIT by default for sideloaded apps → ART must work interpreter-only on device (test with
  `-Xint` on Linux). StikDebug can enable JIT for dev-signed apps on iOS 17.4+, but it's fragile
  and untested on this phone / iOS 27; treat it as an optional speed-up.
- Simulator doesn't exist here and wouldn't enforce code signing anyway; test on device.
- xtool: no asset catalogs, no Interface Builder, no app extensions, no debugger launch.
- Update xtool: download the newer `xtool-x86_64.AppImage` to `~/.local/bin/xtool`.
