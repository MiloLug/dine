# CLAUDE.md

## Project

A generic Android app runner for iOS, built as a translation layer ("Wine for Android") on top of
ATL + ART, distributed by sideloading. Read `notes/meta.md` for the why, the iOS constraints (no
JIT, code signing, one process, App Store rules) and the agreed layer architecture. Which stage is
done and which is next: the Stages table at the top of `notes/atl-port.md`. Open defects:
`notes/bug-tracker.md`; other open work no stage owns: `notes/general-todo.md`. A defect found
outside a stage's own work, or work no stage owns, gets a code there (`ART-n`, `ATL-n`, `DINE-n`,
`TOOL-n`; each file's header has the rules), and other notes link the code.

There's no Mac. Everything is built from Arch Linux in WSL2, and testing happens on a physical
iPhone (iPhone 13, iOS 27.0.1, free Apple ID).

Where the rest is (read the one a task touches):
- `README.md`: layout, commands (the full list: `tools/dine <group> --help`), device connection,
  the debug server, interactive lldb.
- `docs/first-run.md`: setup on a new PC, where each tool comes from, build caveats.
- `notes/dev-reference.md`: details few tasks need (running ATL by hand, the debug agent, lldb
  internals, iOS build traps); its Contents list says when to read each section.
- `notes/atl-port.md` (ATL slots, builds, milestones), `notes/decisions.md` (fork decisions),
  `notes/art-findings.md` (ART config), `notes/nav-gestures.md`, `notes/icons.md`.

## Commands

`tools/dine` is the single entry point (`tools/dine <group> --help`); it sources `env.sh` itself.
For direct tool use, `source env.sh` first (`PATH` with `.venv/bin`, `out/tools/bin`, `tools/`;
`DINE_IOS_SDK`, `DINE_LLDB`, the Linux prefix).

**Before installing any new tool, look for a package first, in this order:**
1. `pacman -Ss <name>`
2. `paru -Ss <name>` (AUR; prebuilt `-bin` variants count)
3. PyPI, via uv: `uv add --group tools <name>` (then `uv sync`). Never `uv tool install`, pip or
   pipx.

Only if none of them ships it, download it manually, pinned, into a gitignored dir in the repo
(`out/tools/bin`, `out/downloads`). Never install to `~/.local` or other system dirs. Add every new
tool to `docs/first-run.md` under its source. The one exception is accord, our `actool`: `cargo
install` from its GitHub repo (`docs/first-run.md`).

```sh
tools/dine ios tunnel start|status       # iOS 17+ developer services; start mounts the DDI
tools/dine ios build-art | build-atl     # dine-art, dine-atl for iOS (not run by ios run); build-atl after linux build atl
tools/dine ios run [App]                 # native libs, dev payload, asset catalogs, xtool dev, launch
tools/dine ios icons                     # Icons.xcassets from its sources.txt
tools/dine linux build [bionic|art|opensles|atl|atl-headless ...]   # default: all, in that order
tools/dine linux smoke [check...] [--list]
tools/dine test runtime [fetch|build|run|all] [-f REGEX] [--network] [--update-expectations]
tools/dine test framework [-f REGEX] [--gtk] [--update-expectations]
tools/dine test unit                     # harness + tools/py unit tests
tools/dine dbg start-server [--target gtk --app <apk>] | smoke [--network] [--list] | stop-server
```

**Dev and release builds:** iOS builds are dev builds unless `DINE_RELEASE=1` is set on
`ios build-atl` and then `ios run`; `ios run` stops when the ATL build's `test_hooks` doesn't
match the flag. A release build leaves out every dev and test part: the dev screens in
`apps/Dine/Sources/Dine/Dev/` (`#if DEBUG`; xtool `-c release`), the libs in `native/dev/` (debug
agent, hello, runtimetests; Swift imports them only from `Sources/Dine/Dev/`), artbridge's
`dev.cpp` (ART's junit boot jars, `-Xcheck:jni`), ATL's test hooks (meson `test_hooks`),
`Resources/Dev.xcassets`, and the test APKs, test jars and junit jars (`out/ios/dev`, bundled as
`dev/`). `dbg ui`, `dbg fresh` and `dbg smoke` need a dev build. A release build can't start an
app until the launcher gets APK import (M8a).

**On-device and gtk-build debugging go through a subagent, never raw `lldb`/`pymobiledevice3` with
`sleep`/`grep` waits.** Both drive `tools/dine dbg` (target `ios`, or `gtk`: ATL's gtk build on a
hidden display; the task names which) and leave the server up for the next task; continue them with
SendMessage. Spawn neither from plan mode: it blocks every launch, attach and tap.
- `dine-peek` (Sonnet, fast): a fully specified read, e.g. "value of `self.native` at
  `HelloView.swift:23` after tapping hello++", a log line after given taps, a smoke run, a screenshot.
- `dine-debugger`: anything that needs diagnosis, stepping or judgment (why it crashes, where a value
  goes wrong).

## Tests

Test suites live in the repo that owns the code (`tests/README.md` has the map); the engine is
`tests/harness/`. The runtime suite (`dine-art/tests/runtime/`, AOSP ART run-tests) and the
framework suite (`dine-atl/tests/framework/`, JUnit 3 APKs for `android.*`) are graded against
their `expectations/` (exit 1 = regression). After a fix makes tests pass, rerun with
`--update-expectations`; the file changes inside the fork that owns the suite. No linters yet.

Smoke tests: iOS `tools/dine dbg smoke` (dev build, after `dbg start-server`; `--network` adds
**run https**), Linux `tools/dine linux smoke` (after `linux build`; gd runs the gtk build,
the rest `dine-atl/tests/headless/run-*.sh`; the gtk checks run on a hidden display, README
"Linux ATL / ART"). `--list` prints every check; the tables are `tools/py/dine/dbg/smoke.py` and
`tools/py/dine/linux.py`.

## Forks and builds

- `dine-art/` and `dine-atl/` are git submodules: our forks of art_standalone and
  android_translation_layer (`git@github.com:MiloLug/dine-{art,atl}.git`, branch `dine`; remote
  `upstream` = gitlab). ART/libcore and ATL changes are made there; the superproject records the
  SHAs. **Don't commit or push in them without asking.**
- **Both forks must keep building and passing on Linux** (`tools/dine linux build` +
  `tools/dine test runtime`): Linux is the fast loop and the reference for the iOS port.
- dine-atl: upstream isn't merged (we're too far apart): read its commits and reimplement the
  wanted ones by hand. Keeping our diff small or merge-friendly is not a goal. Toolkit, OS and
  native-code-loader code sits behind backend slots (`src/slots/`, backends in
  `src/backends/<slot>/<name>/`, shared code in `src/shared/`); natives not yet behind a slot build
  only with ui=gtk, so a headless build throws `UnsatisfiedLinkError` on them. AOSP code ported
  into the fork is listed in `dine-atl/doc/AOSP.md`.
- dine-atl builds: desktop (gtk, `out/linux/build/dine-atl`, installed), headless (cli, not
  installed, `out/linux/build/dine-atl-headless`) and iOS (uikit, meson cross,
  `out/ios/build/dine-atl`; it compiles no Java and uses the Linux build's jars and headers).
  **Never build the two Linux ones at once:** both write `src/api-impl-jni/generated_headers`.
- In Dine, artbridge owns the one VM; the Android main thread is an 8 MiB pthread with its own
  CFRunLoop. uikit queues UIKit changes on it and sends them to UIKit's thread once per layout
  or draw pass; UIKit's thread must never wait for the Android one.
- dine-art builds with its own make build and gcc, in-tree (`dine-art/out`, ~2 GB);
  `____TARGET=ios` cross-compiles. Make doesn't track flag changes: after editing cflags in an
  `.mk`, delete the module's `out/host/*/obj` **and** `out/host/*/gen` intermediates (stale
  generated `asm_defines.h`).
- ART is Android 10, libcore 8.1/9, ATL's device level (`SDK_INT`) is 21 (`notes/decisions.md`).
- accord is this repo's `actool`: anything that needs `actool` runs the `accord` command, never
  Xcode's (there is none) or the `../dine-accord` checkout. Icons: the SF Symbol where iOS has one,
  else the Fluent pack (`notes/icons.md`).

## Gotchas when operating tools

- **Never run xtool with stdin = `/dev/null`.** It crashes with `epoll_ctl … Operation not
  permitted`. When running non-interactively, use a pty (`script -qec "xtool …" /dev/null`).
- **Ask the user before answering yes to xtool prompts.** For example,
  `The following certificates must be revoked … Continue? (yes/no)` is an Apple ID account
  change: it breaks other sideload tools' certificates.
- **Ignore `DebugserverClient.Error.unknown` from `xtool launch` / `xtool dev`** (pre-iOS-17
  debugserver). Launch with `pymobiledevice3 developer dvt launch --tunnel '' <bundle>` instead.
  Every `pymobiledevice3 developer …` command takes `--tunnel ''`.
- **"Failed to launch process with bundle identifier …"** means the phone is locked or the
  developer certificate isn't trusted on the phone. Ask the user to unlock or trust. Apps that are
  backgrounded get killed.
- **`xtool dev run` hangs after `[Installing] 100%`** while an old, once-debugged app process
  lives: `tools/dine ios kill Dine` and rerun (`ios run` kills it first).
- lldb: always `$DINE_LLDB` (`tools/libexec/lldb`), never a system lldb; its setup and traps are in
  README "Interactive lldb" and `notes/dev-reference.md`.
