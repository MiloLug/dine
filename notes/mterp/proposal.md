# mterp: proposal

Port mterp, ART's assembly interpreter, to dine-art's heap-base references, so dine-art can drop
the C++ switch interpreter on Linux and on the phone; plus the other ways found to speed up
interpreted code. State: proposed, nothing built, nothing decided by the user. The facts it rests
on are `findings.md`; the backlog item is [ART-19](../general-todo.md#art-19).

## Goal

mterp runs on Linux x86_64 and on the phone with heap-base references, and the runtime suite
passes on both with its expectations unchanged. The Linux suite took ~52 s with mterp and ~78 s
with the switch interpreter; the gain on the phone is unmeasured.

## The change

- Every handler that uses a reference as an address adds the heap base first (on arm64 an `add`
  of the base and the zero-extended 32-bit value). One macro per architecture, used at every
  dereference, so a grep finds a dereference that skips it.
- Null checks, and copies of references between vregs, fields and array slots, keep the encoded
  32-bit value (`findings.md` "What blocks mterp").
- Where the base comes from, open:
  1. A register pinned for mterp's lifetime: on arm64 one `add` per decode, and x19 and x28 are
     unused by mterp; on x86_64 a free register is unchecked.
  2. A load from `Thread` per decode: one more memory load each time.
  3. A load of the global `gHeapReferenceBase`: an `adrp` and a load each time.
- `ART_USE_CXX_INTERPRETER` comes out of the build flags once both architectures pass. Whether the
  switch interpreter stays selectable (for comparisons or debugging) is open.

## Test order

1. x86_64 mterp on the dev machine: `tools/dine linux build art`, then `tools/dine test runtime`.
   A test mode reserves the low 4 GB `PROT_NONE` before the runtime starts, so every missed decode
   faults instead of reading whatever is mapped there.
2. arm64 under qemu user mode: a Linux arm64 cross build with arm64 dependencies, the suite
   filtered with `-f` (speed under qemu is unchecked). Native arm64 hardware runs the same build at
   full speed.
3. The phone: the iOS build, the runtime tests from Dine's art screen. Covers what Linux arm64
   can't: Apple's ABI and code signing.

## Related levers

- **Interpreter intrinsics in the switch interpreter.** dine-art already builds 87 C++ intrinsics
  that only mterp calls (`findings.md` "Interpreter intrinsics"). Letting the switch interpreter
  call them is a smaller change that helps before mterp lands; mterp uses them anyway. Unchecked
  whether they work there unchanged; the gain is unmeasured.
- **Hot ATL code rewritten in C**, with its data moved to C and calls batched:
  [ATL-6](../general-todo.md#atl-6). Methods apps
  override (`onMeasure`, `onDraw`) and the framework code that calls them stay Java. A normal JNI
  call changes the thread state on every call, so a small method moved alone can get slower.
  `@FastNative` cuts that cost but keeps the thread `kRunnable`, so a fault there ends Dine instead
  of the app (`notes/multi-app-support/findings-native-faults.md` "Thread states").
- **The boot classpath compiled at build time** (libcore and ATL's api-impl jars), linked into
  Dine and signed with it; no backlog item. App code stays interpreted, since APKs arrive after
  Dine is built. Blockers (`findings.md` "Compiled code (AOT)"): the code generator, its intrinsics
  and the entrypoint stubs use references as addresses; the oat code has to become a signed Mach-O
  ART can load; references to boot objects have to go through tables patched at load time, which
  ties in with the prebuilt boot image of [ART-22](../general-todo.md#art-22). `-Xint` would go.
  Before any of it, measure the share of time spent in boot-classloader methods under `-Xint` on
  Linux.

## Open questions

- The base register or load (above).
- Whether the switch interpreter stays as a build option.
- The phone's gain from mterp, measured after step 3.
