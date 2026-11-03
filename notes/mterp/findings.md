# Findings: mterp and the interpreter

This file covers dine-art's two interpreters, why it runs the slower one, what porting mterp (ART's
assembly interpreter) to heap-base references touches, and what can test the port on other
architectures. It also records the facts behind the related ways to speed up interpreted code.
A snapshot read on 2026-11-03; line numbers drift. Paths are under `dine-art/art/` unless they
start with `native/` or `notes/`. **C**: read in code. **M**: measured. **U**: unchecked. The plan
is `proposal.md`; the backlog item is [ART-19](../general-todo.md#art-19).

## Which interpreter runs

- `-Xint` sets the runtime's `Interpret` option (`runtime/parsed_options.cc:260-262`), which calls
  `Instrumentation::ForceInterpretOnly()` (`runtime/runtime.cc:1299-1301`): every method runs in the
  interpreter and compiled code (oat files, JIT) is not used. artbridge passes `-Xint
  -Xusejit:false` (`native/artbridge/artbridge.cpp:116`). C
- The interpreter is a compile-time constant: `kInterpreterImplKind` is `kSwitchImplKind` when
  `ART_USE_CXX_INTERPRETER` is set, else `kMterpImplKind` (`runtime/interpreter/interpreter.cc:241-245`).
  dine-art sets it for every build (`build/Android.common_build.mk:200`). C
- mterp is still generated and assembled: `gen_mterp.py` joins `runtime/interpreter/mterp/<arch>/*.S`
  into one file (`runtime/Android.mk:58-64`). The iOS build has `mterp_arm64.o`, the Linux build
  `mterp_x86_64.o` (under `out/host/*/obj/SHARED_LIBRARIES/libart_intermediates/`). C

## Switch interpreter and mterp

- The switch interpreter is C++: a loop around one `switch` on the opcode. mterp is one assembly
  handler per opcode, each in a fixed-size slot of a table; a handler ends with its own jump to the
  next one: arm64 `GOTO_OPCODE` is `add reg, xIBASE, reg, lsl #handler_size_bits; br reg`
  (`runtime/interpreter/mterp/arm64/main.S:240-243`), x86_64 `GOTO_NEXT` is `shll`, `addq rIBASE`,
  `jmp *%rax` (`mterp/x86_64/main.S:233-239`). C
- mterp keeps its state in registers; arm64: `xPC` x20, `xFP` x21, `xSELF` x22, `xINST` x23,
  `xIBASE` x24, `xREFS` x25, `xPROFILE` x26 (`mterp/arm64/main.S:99-109`). C
- arm64 has 259 handler templates (`%def op_` in `mterp/arm64/*.S`). C
- The Linux runtime suite takes ~78 s with the switch interpreter, ~52 s with mterp (ART-19). M
- Why mterp is faster (per-handler jumps predict better than the switch's one shared jump; state in
  registers instead of memory): U, general knowledge, not profiled here.

## What blocks mterp

- Heap references are 32-bit offsets from `mirror::gHeapReferenceBase`, and offset 0 is null
  (`runtime/mirror/object_reference.h:38,47,57`), because iOS maps nothing below 4 GB
  (`notes/art-findings.md` "iOS blockers" 1). C++ decodes through it; shadow-frame vregs go through
  `GetVRegReference`, then `AsMirrorPtr` (`runtime/interpreter/shadow_frame.h:189-193`). C
- mterp's handlers use a vreg's 32-bit value directly as an address. arm64 `op_array_length`:
  `GET_VREG w0, w1`, `cbz w0, common_errNullObject`, `ldr w3, [x0, #MIRROR_ARRAY_LENGTH_OFFSET]`
  (`mterp/arm64/array.S:172-175`); `op_iget`'s cached fast path: `ldr w0, [x2, x1]`
  (`mterp/arm64/object.S:42-51`). C
- Null checks test the 32-bit value before the dereference (`cbz w0` above), and offset 0 is null,
  so they keep working. C
- Copying a reference between vregs, fields and array slots moves the encoded 32-bit value and
  needs no decode. U
- The C++ helpers mterp calls (`runtime/interpreter/mterp/mterp.cc`) decode like the switch
  interpreter: C for `GetVRegReference`, U for every helper.
- On Linux the heap reservation sits at ~0x7f… (`notes/art-findings.md` "What it took"), so an
  undecoded offset used as an address points below 4 GB. Whether something is mapped there in a
  given run: U.

## Interpreter intrinsics

- 87 intrinsics have C++ implementations for the interpreter
  (`runtime/interpreter/interpreter_intrinsics.cc`, built by `runtime/Android.mk:290`): `String`
  (`charAt`, `compareTo`, `equals`, `getCharsNoCheck`, `indexOf` and its offset variant, `isEmpty`,
  `length`), 17 `Math` functions, 22 `Integer`/`Long` bit operations, `Short.reverseBytes`, 36
  `VarHandle` accessors and fences, `MethodHandle.invoke` and `invokeExact`,
  `Reference.reachabilityFence`. C
- Methods are marked at startup (`InitializeIntrinsics`, `runtime/runtime.cc:877`), but only mterp
  uses them: `if (is_mterp && !is_range && called_method->IsIntrinsic())`
  (`runtime/interpreter/interpreter_common.h:208`). The switch interpreter runs the Java or native
  method instead. C
- `MterpHandleIntrinsic` takes the shadow frame (`interpreter_intrinsics.h:32`); whether it works
  from the switch interpreter unchanged: U.

## Compiled code (AOT)

- The optimizing compiler also uses a reference as an address: `HeapOperand` turns the W register
  holding a reference into an `[Xn, #off]` operand (`compiler/optimizing/common_arm64.h:175-178`).
  Compiled code has the same decode problem as mterp, spread over the code generator, intrinsics and
  entrypoint stubs. C
- ART loads oat files with its own ELF loader or with `DlOpenOatFile`: `dlopen`, then the
  `oatdata`, `oatexec` and `oatbss` symbols (`runtime/oat_file.cc:322-352,879,990-1025`). iOS runs
  only signed Mach-O code, so build-time compiled code would ship as a Mach-O in the bundle; whether
  `DlOpenOatFile` works on Darwin: U.
- A boot-image compile reaches image objects PC-relatively (`kBootImageLinkTimePcRelative`,
  `compiler/optimizing/nodes.h:6253`), which needs the image at a fixed distance from the code. The
  table-based load kinds are `kBootImageRelRo` and `kBssEntry` (`nodes.h:6257,6261`). C

## Testing on other architectures

- x86_64: `mterp/x86_64/` has the same 8 files as `mterp/arm64/` and runs natively on the dev
  machine. C
- arm64 Linux: dine-art's make build has `build/core/combo/HOST_linux-arm64.mk`. A cross build from
  x86_64: U.
- qemu user mode runs one Linux arm64 program on x86_64 and translates its syscalls; no VM, no
  kernel. Arch `extra` has `qemu-user` 11.1.2, `qemu-user-static`, `qemu-user-binfmt`,
  `aarch64-linux-gnu-gcc` 16.2.0 and `aarch64-linux-gnu-glibc` 2.44 (`pacman -Ss`). C. Still U:
  arm64 builds of dine-art's dependencies (ICU, lz4, expat, zlib, libcrypto: an Arch Linux ARM
  rootfs as sysroot, or built from `third_party/` as for iOS), speed under qemu, binfmt under
  WSL2, where qemu places the heap reservation.
- Unicorn emulates a CPU with no loader and no syscalls, too low for mterp, which needs the whole
  runtime. U
- Native arm64 hardware (Raspberry Pi 5, a cloud ARM VM, GitHub's arm64 Linux runners) runs the
  same build at full speed; the runners' terms: U.
- Linux arm64 doesn't check Apple's ABI or code signing; the iOS build checks the Mach-O assembly.
  x18, Apple's platform register, appears nowhere in `mterp/arm64/*.S`, and ART's arm64 stubs skip
  it (`arch/arm64/quick_entrypoints_arm64.S:1122,2518`). C
- x19 and x28 appear nowhere in `mterp/arm64/*.S`; x27 only in mterp's entry save and restore
  (`mterp/arm64/main.S:411,760,778`). C
