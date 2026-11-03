# Findings: native faults in a shared process

What a native fault (SIGSEGV, SIGBUS) does on one-VM backends, what option 1 of
[B1](todo.md#b1-native-fault-containment) can contain, what its checks cost, and the problems found
along the way. The decision and its tasks are in `todo.md` B1; the design is in `design.md`
"Native faults". A snapshot read and measured on 2026-11-01; line numbers drift. Paths are under
`dine-art/` unless they start with `dine-atl/` or `notes/`. **C**: read in code. **M**: measured
(the method is under "Cost of the checks"). **U**: inference, unchecked.

## Today

- ART's fault manager starts only with implicit null, stack-overflow or suspend checks, and all
  three are off (`art/runtime/runtime.cc:1448-1454`). C
- `Runtime::InitPlatformSignalHandlers` installs nothing on Apple (`art/runtime/runtime_linux.cc:66-70`),
  so a SIGSEGV goes to the iOS crash report and ends Dine with every app. C
- On iOS no APK `.so` loads (`notes/meta.md`). The native code an app reaches is Dine's (ART,
  libcore's natives, ATL's natives, sqlite, ICU, wolfSSL), Apple's frameworks under the backends,
  and raw memory access from Java ([below](#raw-memory-access-from-java)). C

## Thread states

- A normal JNI native moves its thread to `kNative`, which releases the mutator lock that GC and
  suspend-all wait on (`art/runtime/entrypoints/quick/quick_jni_entrypoints.cc:75-77`). C
- `@FastNative` and `@CriticalNative` natives stay `kRunnable` and keep the mutator lock
  (`art/runtime/entrypoints/quick/quick_trampoline_entrypoints.cc:2377-2379`). C
- ART doesn't wait on a thread that isn't runnable: for a checkpoint, the requester raises that
  thread's suspend count and runs the checkpoint for it (`art/runtime/thread_list.cc:339-391`). C
- Suspend-all waits for every runnable thread. On Linux it logs an error after 10 s in release
  builds (FATAL after 50 s in debug builds) and goes on waiting (`thread_list.cc:747-763`,
  `thread_list.h:50`). On Apple there are no futexes (`art/runtime/base/mutex.h:36-40`), so it spins
  with no timeout. C
- ATL's Java declares no `@FastNative` or `@CriticalNative` (grep of `dine-atl/src`, 0 files):
  every ATL native runs in `kNative`. C
- Every thread attached to ART gets a 32 KB alternate signal stack (`art/runtime/thread.cc:984`,
  `thread_linux.cc:36-37`, which the make build lists for every host in
  `art/runtime/Android.mk:217-221`). The iOS build compiles it too: its `thread_linux.o` is a Mach-O
  arm64 object that references `_sigaltstack` (checked 2026-11-03). Threads not attached to ART get
  none from ART. C

## What a fault leaves behind

Threads give each fault to the thread that caused it; they don't isolate memory. Only a separate
address space does, and iOS gives Dine one (`fork` returns `EPERM`, `multi-head-exec-maybes.md`).

| State of the faulting thread | It also | Outcome |
|---|---|---|
| `kNative`, on an app's thread | holds no shared lock, wrote only its app's memory | containable: park the thread, drop the app; GC and the other apps go on (freeing the app's memory needs problem 8 solved) |
| `kNative` | holds a shared lock | the lock stays held; every app that needs it hangs |
| `kNative` | wrote shared memory before the fault | the corruption shows up later, in another app or in GC |
| `kRunnable` (ART's code, `@FastNative`) | holds the mutator lock | the next GC or suspend-all waits on it forever: every app hangs |

Row 1 and row 4 follow from the thread-state facts above (C); rows 2 and 3 are U.

## Raw memory access from Java

- libcore's raw-address methods are `@FastNative`, so a bad address faults in `kRunnable`:
  - `sun.misc.Unsafe`'s address variants (`getByte(long)`, `putByte(long, byte)`, `getLong(long)`,
    `putLong(long, long)` and the rest, `art/runtime/native/sun_misc_Unsafe.cc:598,602`), `setMemory`,
    `copyMemory`, `copyMemoryToPrimitiveArray`, `copyMemoryFromPrimitiveArray` (`:569-572`);
  - `libcore.io.Memory`'s single-value peeks and pokes (`pokeByte`, `pokeLongNative`,
    `libcore/luni/src/main/native/libcore_io_Memory.cpp:305,312`). Its array variants
    (`pokeByteArray`, `pokeLongArray`) are normal natives (`:306,313`). C
- A bad read faults like a bad write, so reads need the check too. U
- The object-plus-offset variants (`putLong(Object, long, long)`, `putByte(Object, long, byte)`,
  `compareAndSwapInt`) are `@FastNative` too (`sun_misc_Unsafe.cc:551,558,581`) and write at the
  object's address plus any offset. C. A primitive write over a reference field leaves a garbage
  pointer in the heap, which GC follows later on its own thread. U
- ART keeps a bitmap of each class's reference field offsets, `reference_instance_offsets_`, set to
  `kClassWalkSuper` when it doesn't fit and the super chain has to be walked
  (`art/runtime/mirror/class.h:77-81,1417`). An offset check can test it. C; the cost of the walk
  case is U.
- `java.util.concurrent` uses the object-plus-offset calls on hot paths: `AtomicInteger`
  (`libcore/ojluni/src/main/java/java/util/concurrent/atomic/AtomicInteger.java:111-168`),
  `ConcurrentHashMap` (23 call sites). C
- `DirectByteBuffer` keeps its memory in a non-movable `byte[]` inside the Java heap
  (`VMRuntime.newNonMovableArray` and `addressOf`,
  `libcore/ojluni/src/main/java/java/nio/DirectByteBuffer.java:71-72`) and calls `Memory.peek*` or
  `Memory.poke*` once per element (`:209,248`). C
- The hidden-API policy defaults to disabled (`art/runtime/runtime.cc:296`), and artbridge and
  ATL's startup code pass no hidden-API flag (grep, 0 hits): app code reaches `Unsafe`, `Memory`
  and `VMRuntime.addressOf` through reflection. C

## Cost of the checks

Measured 2026-11-01 on Linux x86_64 under WSL2. Java: a loop of 3 M iterations under
`dalvikvm -Xint -Xusejit:false`, three runs, the 22 ns empty loop with a field store subtracted. C:
200 M iterations at `gcc -O2`, each call in a non-inlined function; the raw-address check is a
per-thread cache of the last region hit plus a binary search over 64 regions on a miss. M

| Path | Without the check | Added by the check |
|---|---|---|
| `Unsafe.putLong(address, value)`, interpreted | ~60 ns | |
| `Unsafe.compareAndSwapInt(object, offset, …)`, interpreted | ~85 ns | |
| `DirectByteBuffer.put(index, byte)`, `AtomicInteger.incrementAndGet()`, interpreted | ~270 ns each | |
| raw-address check, cache hit | | +0.05 ns |
| raw-address check, cache miss | | +4 ns (~7% of a `putLong` call) |
| object-plus-offset bounds check | | 0 to 0.3 ns (noise) |
| mutex lock and unlock with a held-shared-locks counter | 3.4 ns | 0 to 0.2 ns |
| `malloc` and `free` through a per-app zone table (thread-local app id, indirect call) | 4.4 ns | 0.1 to 0.3 ns |

Estimate from these numbers: under 1% for a whole app. Not measured: the iPhone 13 (Apple's malloc;
each `__thread` read on Darwin goes through a TLV thunk, estimated at 1 to 2 ns, which JNI natives
avoid by taking ART's `Thread` from `JNIEnv`), the reference-field check, miss rates in real apps,
lookups over thousands of regions, and keeping the region list current at each allocation and free.

## Problems found

Each stays open until a task in `todo.md` B1 settles it.

1. Faults in `kRunnable` can't be contained: ART's own code, every `@FastNative` native, the
   interpreter on a corrupt heap, GC threads. Under option 1 they end Dine; the checks close the
   ones app code can cause.
2. Reads need the raw-address check as well as writes.
3. Object-plus-offset calls need an offset check (inside the object and past its header; the header
   size is U), and primitive writes need a reference-field check.
4. Every place that hands Java a raw address must register a region: `Unsafe.allocateMemory`,
   `reallocateMemory` and `freeMemory`; `VMRuntime.newNonMovableArray` with `addressOf` (used by
   `DirectByteBuffer`, and by any app through reflection); `FileChannel.map`; JNI
   `NewDirectByteBuffer` in Dine's natives. A missed point rejects a correct access and ends an app
   that did nothing wrong. A freed region leaves the list, so a stale address is rejected. The list
   may be incomplete. U
5. Locks the handler can't see: a held-shared-locks counter only covers locks taken through Dine's
   wrapper. Not wrapped: libmalloc's internal locks; Apple's frameworks (CoreGraphics and CoreText
   under the gfx backend, CoreFoundation, libdispatch); ICU's own mutex. sqlite takes its mutexes
   through a replaceable layer (`SQLITE_CONFIG_MUTEX`, U). For a fault inside code whose locks are
   unknown, the only safe outcome is ending Dine, so a framework fault on bad app input (a font, an
   image) ends Dine; decided instead: contained, with a hang rule (`design.md` "Native faults").
   ART's own mutexes are visible: release builds record each one a thread holds, one slot per lock
   level, readable with `Thread::GetHeldMutex(level)` (`SetHeldMutex` outside
   the `kDebugLocking` block, `art/runtime/base/mutex-inl.h:101-165`; `thread.h:1075,1747`).
   Monitors are not recorded there (`mutex-inl.h:160-163`). C
6. Java monitors: a thread that entered `synchronized` on an object other apps also use, then
   faulted in a native, keeps that monitor. `Monitor::VisitLocks` lists the monitors one Java frame
   holds (`art/runtime/monitor.cc:1423`), but it runs from a stack walk, so not inside the handler.
   C. Walking a parked thread's Java frames from a normal Dine thread afterwards: U. No record says
   which objects are shared.
7. Misattribution: memory corrupted earlier through app A can fault later on app B's thread. B is
   dropped and A keeps running. The handler can't tell the two apart. Corruption that never faults
   isn't caught at all.
8. A parked thread keeps its GC roots: `Thread::VisitRoots` walks its stack and JNI local refs
   (`art/runtime/thread.cc:4014-4071`), so the dropped app's objects and class loader stay
   reachable until root visiting skips that thread. Its stack and `Thread` record stay too. C for
   root visiting; U that nothing else releases them.
9. Threads that belong to no app: UIKit's main thread (the uikit backend applies queued changes
   there), Dine's Swift threads, ART's daemons (heap task, reference queue, signal catcher, the
   shared finalizer until MA3 gives each app its own), GC threads. A fault there ends Dine even
   when app data caused it. The daemon list is U.
10. The handler itself: async-signal-safe calls only (no malloc, no locks, no Java), on the thread's
    alternate stack. A native stack overflow faults on the guard page and needs that stack. A fault
    inside the handler or during the drop ends Dine.
11. iOS writes no crash report for a contained fault, so Dine writes its own (a backtrace into the
    app's log). An uncontained fault must be re-raised with the default action so iOS still writes
    its report; that report is why `InitPlatformSignalHandlers` installs nothing on Apple today
    (`runtime_linux.cc:68-69`). C for the reason; U that a re-raise from the handler keeps the
    report.
12. Darwin reports some bad accesses as SIGBUS, so both signals need the handler. With lldb attached
    the debugger gets the Mach exception first and the handler runs only if lldb passes the signal
    on; phone tests of containment need that. U
13. `abort()` paths raise SIGABRT: libmalloc's corruption check, C++ `std::terminate`, assertions in
    sqlite or ICU. ART's `LOG(FATAL)` goes through `Runtime::Abort` and `HookAbort`
    (`findings-runtime.md`). Which of them can be contained is open: libmalloc's abort on a per-app
    zone may be, on the shared zone it isn't. U Decided in `design.md` "Native faults".
14. Per-app malloc zones on iOS: system libraries call plain `malloc`, so routing their allocations
    to a zone means replacing the default zone's functions. U. On the phone (iOS 27, 2026-11-02)
    the default zone's struct (`DefaultMallocZone`, version 10) sits in a read-write region, among 5
    registered zones. `malloc_create_zone` gave a zone of its own; 64 MB in 4 KB blocks raised
    `phys_footprint` by 64 MB and freeing them lowered it at once, before `malloc_destroy_zone`.
    Filling the zone again, then 64 MB from the default zone, left `phys_footprint` unchanged at
    21 MB; why freed and reused pages don't count again: U. M
15. Per-app instances of stateful native libraries (ICU's caches, wolfSSL's init and RNG, sqlite's
    global config) cost memory per app. Unmeasured. U
16. APK native code: option 1's bar holds only while no APK `.so` loads into a shared process. With
    JIT on iOS, or any other way app native code gets in, that code can write anywhere and the bar
    no longer holds. On Linux each app has its own process; an in-process guest with native code
    takes its host app down, as on Android.
17. What a failed check does: end the app (on Android the bad access faults the app's process) or
    throw an exception into it. Decided in `design.md` "Native faults".
