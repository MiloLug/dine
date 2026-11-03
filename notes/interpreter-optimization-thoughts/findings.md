# Thoughts: running APK native code through an interpreter

Whether Dine could run an APK's own `.so` files on iOS without JIT by interpreting them, and how
such an interpreter could be made fast. No stage owns this and nothing schedules it. The iOS
constraints it starts from are in `notes/meta.md` ("iOS constraints that shape everything"). A
snapshot from 2026-11-03; line numbers drift. **C**: read in code. **W**: from a cited web source
(listed under Sources). **U**: unchecked (memory or inference). **E**: an estimate, unmeasured.

## qemu-user does not fit

- qemu-user (QEMU's linux-user mode) translates the guest's Linux syscalls into host Linux
  syscalls and builds only on a Linux host, so it cannot run on iOS. U
- Its TCG backend generates host code at run time (JIT), which iOS forbids unless a debugger grants
  JIT. U
- Guest and host are both arm64. What keeps APK `.so` files from loading is code signing, not the
  instruction set (`notes/meta.md`). An interpreter helps only by not executing the guest code
  natively.
- Unicorn (QEMU's CPU core as a library) runs the guest in its own address space. Whether that
  space can map 1:1 onto Dine's memory, which JNI needs (see Containment), and whether Unicorn has
  an interpreter mode: U.

## The shape that fits

An arm64 interpreter that executes the mapped ELF in Dine's own address space. A bionic linker
loads it, and the guest's calls into host libraries go out through wrappers (the box64 model).

- bionic_translation's linker resolves each guest import to a host `bionic_<symbol>` override when
  one exists, else to the host symbol itself, through `wrapper_create`
  (`third_party/bionic_translation/linker/dlfcn.c:135-162`). The interpreter would keep that and
  replace jumping into guest code with interpreting it. C
- The `native` slot that would own this is planned, not built: `dine-atl/src/slots/` holds `gfx.h`,
  `host.h`, `loop.h` and `ui.h`, and the iOS row of the build table in `notes/atl-port.md` sets
  `native` to `none`. C
- ART's hook points: `bionic_dlsym` and `bionic_dlopen` in
  `dine-art/art/runtime/jni/java_vm_ext.cc:188,1025`, `ArtMethod::RegisterNative`
  (`dine-art/art/runtime/art_method.cc:387`), and the generic JNI trampoline's `blr xIP0`
  (`dine-art/art/runtime/arch/arm64/quick_entrypoints_arm64.S:2201`). C
- Every guest function pointer the host calls (JNI natives, `JNI_OnLoad`, `RegisterNatives`
  targets, pthread start routines, `qsort` comparators, audio callbacks) needs a host entry stub
  that enters the interpreter. iOS cannot create code at run time, so the stubs come from a fixed
  pool compiled into Dine, each paired with a data slot naming its guest target. U
- Host libc, libm, libz and GLES run natively behind the wrappers, so `memcpy`, `malloc` and
  `inflate` are not interpreted; the app's own code is. U

### Android and Darwin arm64 ABI differences

Guest and host both follow AAPCS64, so a call across the boundary is mostly a register copy. Where
Darwin differs (U, from memory of Apple's arm64 ABI doc):

- variadic arguments go on the stack: `CallXMethod(...)`, `__android_log_print`, `open`, `ioctl`,
  `fcntl`;
- the caller extends arguments narrower than 32 bits;
- `long double` is 64-bit;
- `x18` is reserved;
- constants and struct layouts differ: `errno` values, `O_*` flags, `stat`, `dirent`, `sockaddr`
  (`sa_len`), `pthread_*_t` sizes.

bionic_translation passes calls through to glibc, which shares Linux's constants. A Darwin shim has
to translate all of them, and every way of running APK native code needs it: this interpreter,
on-device re-signing and JIT alike. Its size: U.

An interpreter can virtualize what native execution cannot: `x18`, `TPIDR_EL0` (the thread pointer
ELF TLS uses), and raw `svc` syscalls from statically linked code such as gomobile libraries. U

### Containment

Guest code shares Dine's address space, because JNI hands it raw pointers
(`GetPrimitiveArrayCritical`, `GetStringUTFChars`, direct ByteBuffers, `long` fields holding host
addresses). An interpreted guest can still write anywhere, so item 16 of
`notes/multi-app-support/findings-native-faults.md` applies to it as to native code. Bounds checks
would need a software MMU and cost more again. U

## Speed

- A plain interpreter: E, 10 to 50 times slower than native. Apps put code in `.so` files for their
  hot paths (codecs, crypto, sqlite, engines), which is the worst place to interpret.
- QEMU's TCI (Tiny Code Interpreter) is reported to be about 10 times slower than a good
  interpreter, and one poster's C++ interpreter reached about 1/3 of QEMU's JIT. W, anecdotal
  (UTM discussion #7694).
- UTM SE runs QEMU through a threaded interpreter that "performs better than a traditional
  interpreter but still slower than JIT". W (UTM README, Wikipedia).

## Precompiled instruction sequences

The idea: collect common guest instruction sequences and compile fused handlers for them into the
interpreter (superinstructions on top of threaded code). iOS allows it: all executable code ships
signed inside Dine, and at run time only data is created. Fusing at run time, by concatenating
handler code, writes code and is forbidden, so only fusions compiled in ahead of time work.

Where the time goes per guest instruction, and what removes each cost (U):

| Cost | Removed by |
|---|---|
| decoding arm64's bit fields | decoding each basic block once and caching it as data: handler pointer plus operands |
| one indirect branch per instruction, often mispredicted | threaded dispatch (each handler jumps to the next) and fused sequences |
| loads and stores of a register file kept in memory | keeping guest registers in host registers |
| materializing the flags | fusing `cmp`/`tst` with the following `b.cond` |

### Prior art: TCTI

QEMU's TCTI backend, used by UTM SE, pre-builds a native code fragment per TCG operation and per
register combination, in 16×16×16 tables. W (tcti-gadget-gen.py). The review of the July 2025 RFC
measured 75 MiB of generated code and 18 MiB of tables. W (RFC patch). Whether later versions
shrank it: U. Fusing k instructions multiplies the register combinations again, so fused sequences
cannot specialize registers; they read register numbers from the cached operands. U

### Same-ISA shortcut

The guest is arm64, so the fragment for `add x3, x4, x5` can be that instruction followed by a
jump to the next fragment. U, design inference:

- With guest registers kept in the matching host registers there is no register-file traffic. The
  interpreter needs 2 or 3 host registers for itself and Darwin reserves `x18`; the guest registers
  left without a host register take a slower path.
- Guest addresses are host addresses, so `ldr` and `str` run as they are.
- Branches, PC-relative instructions (`adr`, `adrp`, literal loads), `mrs tpidr_el0`, `svc` and
  `x18` stay in the interpreter. `adrp`+`add` and `adrp`+`ldr` become constants when the block is
  first decoded.

### Fusion candidates

NDK clang output repeats: prologues and epilogues (`stp x29, x30, [sp, #-N]!; mov x29, sp`),
`cmp`/`tst` + `b.cond`, runs of `ldp`/`stp`, and `bl` into a host wrapper. The set would be chosen
by profiling real APK `.so` files. U

### Expected gain

E: threaded dispatch plus fused sequences runs about 2 to 4 times faster than a switch interpreter
(memory of Ertl and Gregg's interpreter papers, U), which would put a well-built interpreter at
about 1/3 to 1/10 of native speed on app code.

## Known binaries

Runtime and engine libraries ship byte-identical across apps of one version: SDL2, Hermes,
`libflutter.so` per Flutter engine version, `libc++_shared.so` per NDK release. U. Dine could match
each `.so` by hash against a table of native builds compiled into its signed binary, either rebuilt
from source or patched copies of the ELF code (whether patched copies work: U). Per-app code
(Flutter's `libapp.so`, Unity's `libil2cpp.so`, an app's own JNI library) stays interpreted. This
extends the known-library substitution in `notes/meta.md` from matching by name to matching by
hash.

What the test APKs ship (C): in `third_party/atl_test_apks/`, 6 APKs carry arm64 libraries.

| APK | `lib/arm64-v8a/` |
|---|---|
| `gles3jni.apk` | `libgles3jni.so` |
| `glmark2.apk` | `libglmark2-android.so` |
| `ndk_sample_endless_tunnel.apk` | `libgame.so` |
| `oculus_vr_gl2hittestOXR.apk`, `oculus_vr_gl2tri3dOXR.apk` | `libopenxr_app.so`, `libopenxr_loader.so` |
| `sample_sdl2_app.apk` | `libSDL2.so`, `libSDL2_image.so`, `libSDL2_ttf.so`, `libhidapi.so`, `libmain.so` |

None of them ships `libc++_shared.so`, and the APKs in `third_party/apks/` carry no arm64
libraries. How often identical `.so` files repeat across real apps: U.

## Other routes

- **On-device re-signing**, as LiveContainer does it: without JIT it signs every guest executable
  with the user's SideStore certificate (W, LiveContainer). That runs at native speed, but it signs
  Mach-O files, so an APK's ELF `.so` would first be wrapped in a signed Mach-O. It needs segments
  aligned to iOS's 16 KB pages (Google Play requires 16 KB alignment for apps targeting Android 15
  and later from November 2025, U), Dine holding the user's certificate and key, and a re-sign per
  install tied to the free Apple ID's 7-day certificate. iOS 26.4 broke SideStore's refresh method
  (W, SideStore guide gist). On iOS 27: U.
- **JIT via StikDebug**: the design rule in `notes/meta.md`. Native speed, fragile across iOS
  updates.
- **iOS builds of known libraries** behind the same JNI names: the plan in `notes/meta.md`.

## Options, if this is built

1. Recommended: count `.so` use across real APKs first. If the count shows demand, build an
   interpreter that decodes each block once and caches it, with a small corpus-chosen set of fused
   sequences and no register specialization, which keeps the binary small. Add the hash table of
   known binaries on top.
2. TCTI-style register-specialized fragments: faster per instruction, at tens of MB of code and
   more instruction-cache pressure.
3. QEMU's TCG core with TCTI: the backend exists, but it translates twice (arm64 to TCG's
   intermediate form to fragments), and the Darwin syscall and ABI layer is still missing.

## Sources

- tcti-gadget-gen.py:
  https://github.com/tctiSH/qemu/blob/4de86e6de1f071d33ce130db1062ebac8fe90a5e/tcg/aarch64-tcti/tcti-gadget-gen.py
- TCTI RFC patch and review: https://patchew.org/QEMU/20250722174228.16205-1-j@getutm.app
- UTM discussion #7694 (TCI speed): https://github.com/utmapp/UTM/discussions/7694
- UTM README (SE edition): https://github.com/vien97/utm
- UTM (Wikipedia): https://en.wikipedia.org/wiki/UTM_(software)
- LiveContainer: https://github.com/LiveContainer/LiveContainer
- LiveContainer fork (signing below and above iOS 26): https://github.com/Maxpro131/LiveContainer
- SideStore guide gist (iOS 26.4): https://gist.github.com/sinceohsix/688637ac04695d1ff38f844acc8ba7f3
