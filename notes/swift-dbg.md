# Issue: Swift expressions (`expr`/`po`) don't work in lldb (Linux → iOS)

**Status:** fixed 2026-10-16. At a Swift breakpoint, `expr -l swift -- 1 + 1` → `2`,
`po self` → `▿ HelloView …`, `po 42`, `type lookup DineApp` all work, nothing hangs.

**Environment:** lldb 21.0.0 swiftlang (Swift 6.4.1), iPhoneOS 27.0 SDK from xtool, iPhone 13 on
iOS 27.0.1 (24A446), attached through `scripts/ios-lldb.sh` (now `tools/dine ios lldb`).

## Root causes (each confirmed)

1. **No SDK path.** lldb maps `DW_AT_APPLE_sdk` to a path through `HostInfo::GetSDKRoot`, which
   is unimplemented on Linux (`HostInfoError`). With no SDK the Swift ClangImporter can't find
   Darwin → `cannot load underlying module for 'Darwin'`.
   **Fix:** `settings set target.sdk-path $DINE_IOS_SDK` (honored by the expression context:
   log line `Using target SDK override`). In `lldb_setup_cmds` (`tools/py/dine/ios.py`).
2. **Wrong Swift resource dir.** lldb hardwires it to `<realpath of liblldb's dir>/swift`
   (`HostInfoPosixSwift.cpp`), i.e. Linux's `/usr/lib/swift/usr/lib/swift`, with no setting or
   env var to override it. Two problems there:
   - its `CoreFoundation/Modules/module.modulemap` (swift-corelibs) clashes with the SDK pcms:
     `could not find file '/usr/lib/swift/usr/lib/swift/CoreFoundation/Modules/module.modulemap'
     referenced by AST file …/SDKExplicitPrecompiledModules/CoreFoundation-….pcm`;
   - no `iphoneos/prebuilt-modules/27.0`, and the 6.4.1 compiler can't rebuild the SDK's stdlib
     from `.swiftinterface` (`this SDK is not supported by the compiler (the SDK is built with
     'Apple Swift version 6.4 … swiftlang-6.4.0.31.4' …)`), so prebuilt modules are mandatory.

   **Fix:** `tools/libexec/lldb` runs lldb from a relocated prefix `out/lldb/` (real copies of `lldb` and
   `liblldb.so`, the rest symlinked) whose `lib/swift` is xtool's Darwin toolchain resource dir
   (`$DINE_IOS_SWIFT_RESOURCES`), except `host`, `linux`, `shims`.
3. **No symbols for system dylibs.** `target.memory-module-load-level minimal` (needed for a
   bearable attach) reads no nlist from device memory; `partial` doesn't either (only
   `complete` does, see `ObjectFileMachO::ParseSymtab`). `expr 1 + 1` needs no stdlib symbols, but
   `po` JITs calls into libswiftCore: `Couldn't look up symbols:
   $ss16_DebuggerSupportO20stringForPrintObjectySSypFZ`, then `po` falls back to `p`.
   `complete` works but costs ~30 s of memory reads per session.
   **Fix:** `tools/dine ios symbols` downloads the phone's dyld shared cache
   (`pymobiledevice3 developer fetch-symbols download`, 7.2 GB, ~5 min) and splits it with
   `ipsw dyld extract --all` (Linux build; keeps install paths and UUIDs) into
   `out/ios-symbols/<version> (<build>)/Symbols/`; `ios-lldb.sh` passes that dir to
   `platform select remote-ios --sysroot`. Bonus: system frames are symbolicated
   (`SwiftUI\`ToolbarItem<>.init(placement:content:)`), and attach → first breakpoint dropped from
   ~75 s to ~4 s.
4. **Slow memory reads** (not a correctness bug): lldb read device memory in 512-byte
   `memory-cache-line-size` chunks, one round trip each. Now 16 KiB (the device page size).
5. **~44 ms per round trip** (found 2026-10-17): not the tunnel (ping 2.5 ms) but TCP ACK timing
   on usbmuxd-bridge's socat connection to Windows AMDS (`127.0.0.1:27015`, mirrored-mode route
   in `table 127`). AMDS's small writes wait for Linux's ACK, which Linux delays 40 ms
   (`TcpExtDelayedACKs` +1 per round trip); replies of a full segment weren't affected (~6 ms).
   **Fix:** `quickack 1` on that route (`../wsl-quickack` keeps it there; existing
   connections pick it up at once): `qHostInfo` 44 ms → 1.6 ms.

Tried and rejected (2026-10-17): `symbols.enable-lldb-index-cache` would save ~5 s of each attach
(symtab parsing of ~1400 system dylibs), but with a warm cache attach segfaults in
`Symbol::ResolveReExportedSymbol` ← `AppleObjCTrampolineHandler` (3/3 runs).
`target.preload-symbols false` didn't help (attach 18.5 s).

The 2026-10-15 "hang" was most likely just this: lldb reading dyld and Swift reflection metadata
from memory 512 bytes at a time (gdb-remote log at ~0% CPU, all `x` packets), on top of the
failing expression context. Not seen since the fixes.

Not needed after all: `-add_ast_path` / N_AST stabs. lldb finds `Dine.swiftmodule` through the
CU's `DW_TAG_module` `DW_AT_LLVM_include_path` (`Discovered main module …`) and loads every
module through its serialized explicit module maps (Swift Build's prebuilt `.swiftmodule` paths
and `SDKExplicitPrecompiledModules/*.pcm`).

## Tools

- `DINE_LLDB_LOG=<dir> tools/dine ios lldb …` writes `lldb types expr`, `swift health` and
  `gdb-remote packets` logs (with timestamps) that survive a killed session.
- `tools/dine ios lldb-offline [App] <breakpoint> [-- lldb args]`: same lldb setup against a
  synthetic Mach-O core (`tools/libexec/ios-core.py`) stopped at the breakpoint. No phone, seconds per
  run. Good for the module setup (`type lookup`, `Imported module …` in the log); `expr` can't
  finish there (a core has no OS version → `@available(iOS 0, *)` parse errors, no JIT).
- `DINE_LLDB_LOAD_LEVEL=complete` if the local symbols are missing for the phone's iOS version.

## Remaining limits

- `Error while searching for SDK: HostInfoError` is still printed (per-module contexts ask the
  host before reading `target.sdk-path`); harmless.
- The per-module fallback `SwiftASTContext` (used when reflection metadata can't size a type)
  ignores `target.sdk-path` and ends in a fatal state. Seen only offline (a core has no
  reflection metadata); `p`/`v` on device go through reflection.
- Local symbols are per iOS build: rerun `tools/dine ios symbols` after an iOS update.
