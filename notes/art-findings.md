# ART: findings and runnability

What we know about dine-art's ART as of 2026-10-16: how it runs on Linux, what the runtime test
suite says about it, and what stands between it and the iPhone. Sources:
- runtime suite runs (`tools/dine test runtime`) and small experiments on Linux;
- dine-art's sources (paths below are relative to `dine-art/art/`);
- XNU's `bsd/kern/mach_loader.c` (apple-oss-distributions/xnu `main`, fetched 2026-10-16).

Facts marked **(unverified)** come from documentation or memory and haven't been tested here.
Open runtime items are the `ART-` codes in `notes/bug-tracker.md` and `notes/general-todo.md`.

## What we run

- **Versions:** ART is Android 10 (`android-security-10.0.0_r75`, oat v170). libcore is older
  (8.1/9), so ART 10 features whose Java side lives in libcore are partly missing (see the
  failures below).
- **Build:** art_standalone's own make build (AOSP `build/core`, adapted). It is **gcc-only, Linux
  host only**; the Makefile says the clang path was never cleaned up. Output goes in-tree
  (`dine-art/out`, ~2 GB). Installed: `lib/art` 363 MB (`libart.so` is 248 MB, of which 8.2 MB is
  text; the rest is debug info), `lib/java` 38 MB.
- **Boot classpath:** 10 dex jars: `core-oj`, `core-libart`, `okhttp`, `bouncycastle`,
  `apache-xml`, `apachehttp`, `wolfssljni`, `core-junit`, `hamcrest`, `junit-runner`.
- **Lambdas:** `LambdaMetafactory` isn't implemented, so desugaring is mandatory. dine-art's dex
  is built with d8 (`--min-api 27`), which fixed libcore's own lambdas (test 656's
  `BootstrapMethodError`). Side effect: every desugared boot jar contains R8's
  `com.android.tools.r8.annotations.LambdaMethod`, and dex2oat warns
  `Skipping class … previously found` once per jar. Harmless.
- **Shutdown abort (fixed):** libcore's `JNI_OnUnload` called `GetEnv`, but ART 10 unloads boot
  libraries with no thread attached, so every VM exit aborted (exit 134). Fixed in
  `libcore/luni/src/main/native/Register.cpp`.

## Linux status: runtime suite

842 tests (AOSP run-tests at the same tag, plus our own): **578 pass**, 20 expected failures,
244 skipped (130 need JVMTI, 100 need upstream's native test lib `libarttest`, 14 have custom run
scripts). Warm run ~78 s on 16 cores with the C++ interpreter ("Runs on the phone"); cold ~5.5
min (measured with mterp).

The 20 expected failures, each with its reason, are in
`dine-art/tests/runtime/expectations/linux-x86_64.json`: runtime bugs
[ART-14](bug-tracker.md#art-14) to [ART-16](bug-tracker.md#art-16), libcore 8.1/9 gaps
[ART-17](bug-tracker.md#art-17), missing test tools [TOOL-7](general-todo.md#tool-7). The libcore
gaps are the "newer Android" problem in miniature: ART 10 is ahead of its libcore.

## How ART starts on Linux, and why it matters for iOS

A plain `dalvikvm -Xint` run of stock art_standalone does more than interpret:

- **Boot image:** on first start the runtime fork+execs `dex2oat` to build a boot image of the 10
  boot jars. It writes the image into `$XDG_CACHE_HOME/art/<isa>/`, falling back to
  `~/.cache/art/` (an art_standalone patch, `libartbase/base/file_utils.cc:242`; `ANDROID_DATA`
  doesn't move it). The image is mapped at a fixed low address (`0x60070000`, from
  `ART_BASE_ADDRESS`).
- **App dex:** every jar or APK on the classpath gets its own fork+exec'd `dex2oat
  --compiler-filter=quicken` (quicken because of `-Xint`). The oat and vdex land in the same
  cache, named after the jar's absolute path.

Consequences:
- **iOS can't do either:** no fork/exec, and dex2oat is a separate program.
- **The Linux reference didn't match the phone:** with these defaults the suite got dex2oat's
  ahead-of-time verification and quickening, which the iPhone won't have.
- **The harness polluted the cache:** every run left about 2 files per test, named after its run
  dir (2,496 files, 106 MB by 2026-10-16), and runs shared the boot image there, so they weren't
  hermetic.

Both are fixed in the harness (2026-10-16): the suite now runs with the flags below, and each test
gets its own `XDG_CACHE_HOME`. `~/.cache/art` was deleted. dine-art now loads no boot image or
oat files and opens dex files without dex2oat ("Runs on the phone"; a side path that still can:
[ART-23](bug-tracker.md#art-23)).

**Experiment: the same thing with no boot image and no dex2oat.** Flags `-Xnoimage-dex2oat
-Xcompiler:/nonexistent/dex2oat`, with an empty `XDG_CACHE_HOME` (the suite now also passes
upstream's `-Ximage:/system/non-existent/core.art`). The runtime logs `Attempting to
fall back to imageless running`, the dex2oat exec fails, and it runs the dex files directly,
verifying at runtime. Results:

| Workload | Boot image + dex2oat (default) | Imageless, no dex2oat |
|---|---|---|
| `dine-0001-hello` | 0.71 s cold (builds the boot image), 0.03 s warm | 0.15–0.20 s, peak RSS 34 MB |
| Runtime suite (842 tests) | 43.8 s | **52–54 s, identical results** (576 pass, same 22 expected failures, exit 0) |
| Gravity Defied under ATL, launch → `onResume` | 1.85 s cold, 0.54 s warm | 0.70–0.76 s |
| Files written to the ART cache | yes | none |

So **ART runs fine without a boot image and without dex2oat**: the configuration iOS will need
works today on Linux, at a modest startup cost. Notes:
- The fallback forked; only the exec failed. dine-art's dex open path never runs dex2oat now
  (side path: [ART-23](bug-tracker.md#art-23)), and on Apple `Exec` returns an error without
  forking (`runtime/exec_utils.cc`).
- A prebuilt boot image to win the startup back: [ART-22](general-todo.md#art-22).
- ATL passes VM flags with `--extra-jvm-option=<flag>`, one per flag.

## iOS blockers and porting surface

### 1. The heap must sit below 4 GB, and iOS forbids that (blocker, solved: heap-base references)

- **ART side:** 64-bit ART stores every object reference as a 32-bit raw address.
  `PtrCompression::Compress` (`runtime/mirror/object_reference.h:36-47`) is a truncating cast
  (reference poisoning is off). `HeapReference`, `StackReference`, `CompressedReference` and
  `GcRoot` all go through it, and shadow-frame vregs hold the same 32-bit values. The heap spaces
  are mapped `low_4gb` (`runtime/gc/heap.cc:464`, `:732`), and the card table covers the whole low
  4 GB (`heap.cc:587`). Without `MAP_32BIT` (aarch64, Apple), `USE_ART_LOW_4G_ALLOCATOR`
  (`libartbase/base/mem_map.h:33`) scans for free space below 4 GB. ART on macOS hosts got that
  space by linking with a small `__PAGEZERO`.
- **iOS side:** XNU's `load_machfile` rejects any 64-bit arm64 binary whose hard page zero doesn't
  cover the whole low 4 GB: "64 bit ARM binary must have 'hard page zero' of 4GB to cover the
  lower 32 bit address space" (`LOAD_BADMACHO`). `enforce_hard_pagezero` is only ever turned off
  for 32-bit x86. So `-pagezero_size` can't work on the iPhone (the app wouldn't launch), and
  nothing can ever be mapped below 4 GB. This comes from the kernel source and hasn't been tried
  on the phone yet.
- **Way out: references relative to a heap base.** Reserve one region of up to 4 GB wherever the
  kernel puts it, and store `ptr - base` instead of `ptr`.
  - The central point is `PtrCompression`. Beyond it:
    - about 25 `reinterpret_cast32` call sites and 27 explicit pointer-to-`uint32_t` casts in
      `runtime` + `libartbase` (for example `PointerToLowMemUInt32`);
    - the lock word's forwarding address (`runtime/lock_word.h:149`: address >> 3 in 30 bits);
    - the card table range;
    - the low-4G allocator, which can be retargeted to scan the reserved region instead;
    - boot image loading, if we ever use one.
  - Offset 0 must stay null, so the region's first page stays unmapped.
  - **mterp** (the assembly interpreter) loads references and uses them as pointers directly. The
    C++ switch interpreter avoids that: `kInterpreterImplKind` is a constexpr chosen by
    `ART_USE_CXX_INTERPRETER` (`runtime/interpreter/interpreter.cc`), which dine-art defines
    (`build/Android.common_build.mk`). The mterp port: [ART-19](general-todo.md#art-19).
  - It can be developed and tested on Linux: keep the low 4 GB unavailable (reserve it
    `PROT_NONE` before the runtime starts, or force the region above 4 GB) and run the suite.
- **Address space:** the phone probe reserved 6144 MB without the `extended-virtual-addressing`
  entitlement ("Phone probe").

### 2. No fork/exec, no dex2oat

Covered above: the imageless, no-dex2oat configuration works. The remaining fork sites are
`runtime/exec_utils.cc` (dex2oat) and `runtime/native_stack_dump.cc` (addr2line for crash
dumps). On Apple neither forks: `Exec` returns an error, and the stack dump's Apple branch is
empty.

### 3. Assembly

- Interpreter-only ART still needs its arm64 entry stubs: invoke stub, generic JNI trampoline,
  to-interpreter bridge, resolution trampoline, exception delivery. They live in 4 files in
  `runtime/arch/arm64/*.S`, plus mterp's arm64 sources (`runtime/interpreter/mterp/arm64/`,
  generated into one file at build time).
- They're written for ELF: `.type`, `.size` and `.hidden` in `asm_support_arm64.S:44-55`, and 4
  `adrp`/`:lo12:` relocations. Mach-O wants underscore-prefixed symbols, `.private_extern` and
  `@PAGE`/`@PAGEOFF`. Mostly macro work.
- Good news: ART's thread register is x19, and x18 (Apple's reserved platform register) is
  already never touched (`quick_entrypoints_arm64.S` skips it explicitly).

### 4. Apple's arm64 calling convention in the generic JNI trampoline

Native methods are called through `BuildNativeCallFrameStateMachine`
(`runtime/entrypoints/quick/quick_trampoline_entrypoints.cc`). Apple's arm64 ABI packs stack
arguments at their natural size and alignment (1, 2, 4 or 8 bytes) and has the caller extend
arguments narrower than 32 bits; AAPCS64 gives each an 8-byte slot. The state machine keeps a
byte offset into the stack area: on Apple arm64 each argument takes its natural size, elsewhere a
`uintptr_t` slot, and narrow values are extended by their Java type before they are pushed.

Measured on the phone with `dine-0002-jni-args` (16 arguments of each type, plus a 28-argument
mixed-width signature, all returned back to Java): with 8-byte slots, 82 arguments arrived wrong,
every stack argument of 4 bytes or less after the first; long, double and object passed. With the
packed layout all of them pass, and the Linux suite is unchanged.

### 5. Signals

- Stock ART turns on implicit null and stack-overflow checks on arm64. dine-art keeps them off
  (`runtime/runtime.cc:1448`): the interpreter checks both explicitly, so ART installs no SIGSEGV
  handlers and never protects, touches or madvises a thread's stack.
- Under lldb, `EXC_BAD_ACCESS` stops in the debugger before the signal reaches ART. Whether an
  app can catch SIGSEGV at all needs a probe without a debugger attached, the route for
  [ART-10](bug-tracker.md#art-10).
- Stock `libsigchain` intercepts `sigaction` by symbol interposition, which a static link on iOS
  can't do against libc. The fork's Apple path exports `sigchain_*` and finds libc's `sigaction`
  with `dlsym`.

### 6. Linux-only code

- **Futexes:** `ART_USE_FUTEXES` is set only on `__linux__` (`runtime/base/mutex.h:36`); the
  pthread fallback exists.
- **TLS:** `Thread::Current` uses `pthread_getspecific` off Android
  (`runtime/thread-current-inl.h:39`).
- **macOS host remnants:** 22 files under `runtime`/`libartbase` have `__APPLE__` branches,
  including thread stack bounds in `thread.cc:1223`. AOSP built ART on Mac hosts in this era.
- **Still Linux-only:** `/proc/self` readers and `memfd_create`, `prctl`, `gettid`:
  [ART-13](bug-tracker.md#art-13).

### 7. Native dependencies to build for iOS

From the installed Linux libraries' `NEEDED` entries:

| Library | Needs |
|---|---|
| `libart` | zlib, lz4, `libdl_bio` (bionic_translation's dlopen shim), libbacktrace/libunwind, nativebridge, sigchain, artpalette, libbase, liblog |
| `libjavacore` | ICU 78 (`icuuc`, `icui18n`), expat, zlib, libziparchive, libnativehelper |
| `libopenjdk` | ICU 78, OpenSSL 3 `libcrypto`, zlib, `libopenjdkjvm` |
| `libwolfssljni` | wolfSSL |

- The iOS SDK has zlib.
- ICU must be built: iOS's `libicucore` has no public headers and unversioned symbols. Its data
  is linked in statically; trimming it: [ART-20](general-todo.md#art-20).
- libcrypto and wolfSSL: build or stub.
- The dlopen shim, nativebridge and backtrace become stubs (one process, no loading of the app's
  `.so` files).

### 8. Build (done 2026-10-17; runs on the phone since 2026-10-18)

- dine-art's own make build cross-compiles: `make ____TARGET=ios` (`HOST_OS=darwin`,
  `HOST_ARCH=arm64`, combo `build/core/combo/HOST_darwin-arm64.mk`), shared-library modules
  archived instead of linked. `tools/dine ios build-art` → `out/ios/lib/*.a` (17 ART/libcore
  archives plus ICU 78.3, lz4, liblzma built from `third_party/` clones).
- Verified by two scratch links of a `main` calling `JNI_CreateJavaVM` and the libcore
  `JNI_OnLoad_*`s: `-all_load` over every archive and `-dead_strip`, 0 undefined, 0 duplicate,
  with `-lz -lexpat -framework CoreFoundation`. ELF output of the edited arm64 `.S` files is
  byte-identical to before; their Mach-O symbols are exactly the ELF ones with `_`.
- What it took, beyond `__APPLE__` guards:
  - gcc's `-fpermissive` hid real errors (const `jvalue*` vs the 4.4-era `jni.h`, now const like
    Android 10's; `dladdr` of a function; `char*` from `malloc`); a qualified member in
    `offsetof` (`GetCalleeSaveMethodOffset`).
  - **arm64 asm:** `SYMBOL()`/`ASM_HIDDEN`/`FUNCTION_TYPE` (`arch/arm64/asm_symbols_arm64.h`),
    `@GOTPAGE` loads, comma-separated macro args. **No CFI on Apple** (`CFI(...)`): Mach-O starts
    an atom at every non-`L` label and CFI can't advance across atoms, and these files use `.L`
    labels. Effects: [ART-7](bug-tracker.md#art-7).
  - `FlushCpuCaches` uses `sys_icache_invalidate` (iOS's libSystem has no `__clear_cache`).
  - `JNI_OnLoad` of libjavacore/libopenjdk renamed to `JNI_OnLoad_javacore`/`_openjdk` (JEP 178
    names) on darwin; libnativehelper's `JniInvocation` (a second `JNI_CreateJavaVM`) left out.
  - libcore: Linux-only `Os` calls throw `ENOSYS`, netlink and packet sockets compiled out,
    missing `OsConstants` stay 0: [ART-12](bug-tracker.md#art-12).
  - ojluni: `EPoll.c`, `LinuxNativeDispatcher.c`, `LinuxWatchService.c` left out on darwin:
    [ART-11](bug-tracker.md#art-11).
  - libutils was a dead dependency of libartbase/libdexfile (0 symbols used); dropped.
- Unrelated Linux bug found on the way: fdlibm got `-D__LITTLE_ENDIAN` only for arm/x86, so on
  x86_64 `StrictMath` used big-endian word order (`fabs` cleared bit 31 of the low word). Now set
  for arm64/x86_64 too.

## Phone probe (2026-10-18, iPhone 13, iOS 27.0.1, free account)

Dine's `art` screen (`native/artbridge`, `dine_art_probe`):

| Check | Result |
|---|---|
| `getpagesize()` / `sysconf(_SC_PAGESIZE)` | 16384 / 16384 |
| largest `PROT_NONE` reservation (64 MB steps, up to 64 GB) | 6144 MB, at `0x7000000000` |
| `mmap` hint `0x10000000` | ignored: got `0x1039e4000` (nothing below 4 GB) |
| `fork()` | `EPERM` |
| `pthread_attr_setstack` 68 KB / 80 KB | `EINVAL` / ok (16 KB multiples only) |
| `mprotect` at a 4 KB offset | `EINVAL` |
| `dlopen(NULL)` + `dlsym` of `JNI_CreateJavaVM`, `JNI_OnLoad_javacore`, `JNI_OnLoad_openjdk` | found (`-force_load` + `-rdynamic`) |
| `getpwuid_r(getuid())` | uid 501, `mobile`, `/var/mobile` |

- SIGSEGV catching wasn't probed: with implicit checks off (no compiled code), ART doesn't rely on
  it; a fix for [ART-10](bug-tracker.md#art-10) would.
- The first `JNI_CreateJavaVM` died at `runtime.cc`'s page-size CHECK. `Runtime::Abort` then
  recursed until the stack overflowed: `~ScopedThreadStateChange` CHECKs a thread-less runtime is
  shutting down (fixed in dine-art; affects Linux too). The bridge's SIGABRT handler drains the
  stderr socket into `os_log`, so ART's FATAL text reaches syslog.
- An ART FATAL kills Dine: ART runs in Dine's process and `Runtime::Abort` ends in `abort()`.

## Runs on the phone (2026-10-18)

Dine's `art` screen → **run hello** runs `dine-0001-hello` through `JNI_CreateJavaVM` in Dine's
process: `Hello from dine runtime tests` / `map size 2` in syslog, ~0.28 s from tap to return
(VM creation included); a second tap reruns `main` on an attached thread. Linux suite unchanged
(578 pass, 20 expected failures, ~78 s instead of ~52 s: C++ interpreter).

What it took in dine-art (one config, Linux and iOS):
- C++ switch interpreter; no boot image, oat files or dex2oat; implicit checks off.
- `kPageSize` 16 KB; on 4 KB Linux MemMap re-places mappings on 16 KB boundaries.
- Heap references are 32-bit offsets from one heap reservation (base in
  `mirror::gHeapReferenceBase`, first page unmapped so offset 0 is null): all spaces, the card
  table and the large-object bitmaps cover it; class-table slots, lock-word forwarding, vreg and
  argument-array encodings and the quick receivers decode through it. On Linux it sits at
  ~0x7f…; a suite run with `reinterpret_cast32`/`PointerToLowMemUInt32` as CHECKs found no
  leftover truncation.
- Apple: JEP 178 `JNI_OnLoad_<lib>` from the main image; no ART crash handlers; alloc
  entrypoints built for arm64.
- App libraries: `System.loadLibrary` finds no file on iOS. On Darwin, `Runtime.loadLibrary0`
  then loads the mapped name, and ART requires `JNI_OnLoad_<lib>` in the main image. The check
  uses `uname`, because `os.name` is hardcoded to `Linux` for apps. Dine links the authored
  tests' JNI code from `native/dev/runtimetests` (dev builds).
- Bugs found on the way, Linux-visible too:
  - `Runtime::Abort` recursed until stack overflow when aborting before a thread attached.
  - `VisitClassLoaderDexFiles` copied an uninitialized out value; clang 23 deleted the "class
    found" path (FindClass of an app class failed a CHECK). gcc never exploited it.
  - liblog wrote a NUL after every line (the color-support commit), so readers splitting on
    newlines saw empty lines.

Startup noise on iOS: [ART-4](bug-tracker.md#art-4), [ART-5](bug-tracker.md#art-5),
[ART-6](bug-tracker.md#art-6).

## More hazards found (2026-10-17)

Fixed since, except where a code is named:
- **16 KB pages:** `kPageSize` is 16 KB ("Runs on the phone").
- **dex2oat exec without a switch:** the dex open path never runs dex2oat, and on Apple `Exec`
  fails without forking; `GetBestOatFile` still can: [ART-23](bug-tracker.md#art-23).
- **No futex on Apple:** `ART_USE_FUTEXES` is `__linux__`-only, so ART's mutexes, condition
  variables and RW locks use pthreads there. Park and Unpark block through
  `os_sync_wait_on_address` (`ParkWait`/`ParkWake` in `thread.cc`; iOS 17.4+, the min target),
  graded by `dine-0004-park` on Linux and from the art screen. Still on the fallback:
  [ART-1](bug-tracker.md#art-1).
- **Implicit null/stack-overflow checks are hardwired on for arm64** in stock ART;
  `-Xno-sig-chain` aborts in `Runtime::Start`. Interpreter-only needs neither: dine-art turns them
  off (`runtime.cc:1448`).
- **Static JNI loading:** ART calls `JNI_OnLoad_<lib>` from the main image ("Runs on the phone").
- **Startup paths:** `ANDROID_ROOT` (the dladdr fallback is compiled out on Apple) and
  `ANDROID_DATA` must be set; boot classpath via `-Xbootclasspath:`; ICU's data is linked in
  statically.
- sigchain is static-friendly: the fork exports `sigchain_*` and finds libc's `sigaction` with
  `dlsym`, no interposition.

## Decided

- **Decided 2026-10-17, done 2026-10-18:** heap-base references are one config for Linux and
  iOS (no build flag): C++ interpreter, heap above 4 GB, graded by the Linux suite. dex2oat
  never runs (no oat files at all), and hello runs on the phone (above).
