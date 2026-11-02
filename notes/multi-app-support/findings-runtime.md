# Findings: ART and libcore for several apps in one VM

What dine-art (Android 10 ART, libcore 8.1/9) allows and blocks when several apps share one
runtime, as needed by `design.md`. A snapshot read on 2026-10-31; line numbers drift. Paths are
under `dine-art/` unless they start with `native/` or `dine-atl/`. **C**: read in code. **U**:
inference, unchecked. **M**: measured by MA0's probe (`tests/probes/multi-app/`, run with
`run.sh all`) on 2026-11-02: host ART on Linux x86_64 under WSL2 with artbridge's VM flags, not the
phone. The one-runtime rule and the second-VM options are in
`multi-head-exec-maybes.md`.

## One runtime

- `Runtime::Create` refuses while `Runtime::instance_` is set (`art/runtime/runtime.cc:733`). A
  failed `Init` resets `instance_` to null and leaks the Runtime (`:738-743`), so the comment
  "ART keeps the failed runtime" in `native/artbridge/artbridge.cpp:130` is wrong; whether a retry
  works is U. C
- `JNI_GetCreatedJavaVMs` reports at most one VM (`art/runtime/jni/java_vm_ext.cc:1239-1248`). No
  isolate or multi-runtime support exists; field-write transactions are AOT-compiler only
  (`runtime.cc:2392-2400`). C
- VM-wide app identity: target SDK, package name, data dir and `registerAppInfo`
  (`art/runtime/native/dalvik_system_VMRuntime.cc:745,767,773-774`). The target SDK changes ART
  behaviour, for example in library loading (`java_vm_ext.cc:1036-1039`). C
- The JNI global and weak-global tables hold 51,200 entries for the whole VM; overflow is a FATAL
  (`java_vm_ext.cc:60-62,671-674`). C

## VM-wide Java state

| State | Where | Effect with several apps |
|---|---|---|
| `-D` system properties | `unchangeableProps`, `libcore/ojluni/src/main/java/java/lang/System.java:1004-1008`, `:923-947` | fixed for the VM; `setProperty` on them is ignored. Covers `java.io.tmpdir` (`native/artbridge/artbridge.cpp:117`) and ATL's `java.library.path`, `java.class.path`, `atl.app.*` (`dine-atl/src/shared/startup.c:185-193`). C |
| `user.dir` | `getcwd()` once (`ojluni/src/main/native/System.c:187-191`) | one cwd; relative paths resolve against it (`UnixFileSystem.java:130`). C |
| `user.home` | `System.java:1051` | `""`, changeable, shared. C |
| default `Locale` | `Locale.java:2203`, `setDefault` `:1023`, categories `:921-937` | one default; ATL sets it (`LocaleList.java:516`). C |
| default `TimeZone` | `TimeZone.java:795`, `:704,738` | one default. C |
| default uncaught handler | `hacky_uncaught_exception_handler`, `Thread.java:1832-1839` | calls `System.exit(10)`: an uncaught exception on any thread ends the process. ATL sets no other handler. C |
| URL and socket factories | `URL.java:1122-1133,1139`; `URLConnection.java:1216-1218`; `Socket.java:1713`; `ServerSocket.java:798-800` | settable once per VM; the second app gets `Error("factory already defined")` or `SocketException`. C |
| network defaults | `CookieHandler`, `ProxySelector`, `ResponseCache`, `Authenticator`, `HttpURLConnection` followRedirects, `URLConnection` useCaches and fileNameMap, `HttpsURLConnection` default verifier and factory, `SSLContext.setDefault`, `NetworkSecurityPolicy.instance` | last writer wins for every app. C |
| okhttp pool | `external/okhttp/android/main/java/com/squareup/okhttp/ConfigAwareConnectionPool.java:34-50` | one pool for every app; `http.keepAlive` and friends are read once by the first user (`AndroidHardcodedSystemProperties.java:95-97`). C |
| Security providers | `sun/security/jca/Providers.java:49`, `Security.java:61` | one list; ATL adds AndroidKeyStore at `Context` init (`dine-atl/.../Context.java:122-127`). C |
| `CloseGuard`, `System.setIn/Out/Err` | `CloseGuard.java:113-162`, `System.java:151-198` | shared. C |

## Exit path

- `Runtime.exit` sets `shuttingDown` and holds `synchronized(this)` through the shutdown hooks and
  `nativeExit` (`Runtime.java:139-172`). `Runtime.halt` reaches the same `nativeExit` and
  `JVM_Exit` (`Runtime.java:357`, `ojluni/src/main/native/Runtime.c:70-73`). C
- ART's exit hook is `void(jint)` without app context; if it returns, ART warns and calls
  `exit()` anyway (`runtime.cc:682-688`, `art/openjdkjvm/OpenjdkJvm.cc:313-317`). artbridge passes
  no hook (`artbridge.cpp:115-124`). C
- A hook that never returns leaves the `Runtime` monitor held: every app's `loadLibrary0` blocks
  on it (`Runtime.java:998,1119`) and `add/removeShutdownHook` throw (`:276,319`). Per-app exit has
  to be caught in Java before the `shuttingDown` latch. A native `exit()` call bypasses all of it.
  C
- `Process.killProcess(myPid())` calls `System.exit(0)` (`dine-atl/.../os/Process.java:680-684`).
  C

## Uncaught exceptions and daemons

- `ThreadGroup.uncaughtException` reaches the default handler only from a root group
  (`ThreadGroup.java:1061-1075`); the static pre-handler runs first (`Thread.java:1893-1906,
  1954-1961`). A per-app group that overrides `uncaughtException` catches everything its threads
  throw. C
- New threads take their creator's group (`Thread.java:405`). Native threads attached through JNI
  go to the main group unless `JavaVMAttachArgs.group` is set (`art/runtime/thread.cc:1136,1209`,
  `java_vm_ext.cc:464`). C
- One FinalizerDaemon runs every app's finalizers (`libcore/libart/src/main/java/java/lang/
  Daemons.java:195`). Its watchdog sends SIGQUIT and then exits the process with status 2 when a
  `finalize()` runs longer than 10 s (`:40,398-419`). C. A frozen app's finalizer blocked on a lock
  of one of its suspended threads would trip it: U.

## Native libraries per class loader

- The library table is keyed by path. A load from a second class loader fails with `Shared
  library "<path>" already opened by ClassLoader ...` (`java_vm_ext.cc:900-981`). On iOS the path
  is the bare `libfoo.so`, so two apps clash on the name alone. C
- On Apple the handle is `dlopen(NULL)`, the main image, and `JNI_OnLoad_<lib>` must exist
  (`java_vm_ext.cc:1014-1021`). Native method lookup searches the libraries of the declaring
  loader (`:316-330`); since every handle is the main image, once a loader has loaded any library
  `dlsym` finds every `Java_*` symbol linked into Dine for that loader's classes. C (code reading)
- With a per-loader key, `JNI_OnLoad_<lib>` would run again over the one copy of the library's C
  statics. C; effect per library U.
- After a GC, `UnloadNativeLibraries` drops the entries of collected loaders and calls
  `JNI_OnUnload_<lib>` (`java_vm_ext.cc:342-375`). There is no `dlclose` (`:100-105`), and boot
  libraries are never unloaded (`:354-356`). C
- artbridge's `gLoaders` (`native/artbridge/dev.cpp:124-139`) is dev-only, on the art screen's
  path, and holds its loaders for the VM's lifetime. C

## Stopping one app's threads

- `ThreadList::SuspendThreadByPeer` and `Resume` (`art/runtime/thread_list.h:68,85`,
  `thread_list.cc:831-990`) suspend any set of threads, one per call, with nesting counts per
  reason (`thread.cc:1503-1512`). Only C++ reaches them; artbridge links libart statically and can
  call them. C
- A suspension that does not complete in 10 s is `LOG(FATAL)` "Thread suspension timed out"
  (`thread_list.h:50`, `thread_list.cc:974-976`). C
- A thread in native code, a syscall, a wait or a sleep counts as suspended at once
  (`thread.h:257-262`); its native code keeps running until it re-enters Java. C. On the phone
  Mach `thread_suspend` and `thread_resume` stop and restart one of Dine's own pthreads;
  `thread_terminate` on a pthread fails with `MACH_SEND_INVALID_DEST` (0x10000003) and the thread
  keeps running, also when it is blocked in `read()`. M (phone)
- A suspended thread keeps its monitors. If it holds a lock other apps take (`Runtime`, `Locale`,
  `TimeZone`, ATL statics), they block: U. A thread of another app waiting on a frozen thread's
  monitor stays blocked until the frozen thread resumes and unwinds: M.
- `Thread.stop`, `suspend`, `resume` and `destroy` throw `UnsupportedOperationException`
  (`Thread.java:877,991,1031,1056`); the `ThreadGroup` versions call them (`ThreadGroup.java:
  622-760`). Only `interrupt` works. C
- Async exceptions exist: `Thread::SetAsyncException` (`thread.cc:4244-4255`) is checked at
  monitor enter and exit, throws, branches (`art/runtime/interpreter/interpreter_switch_impl-inl.h:
  758-951`), before invokes (`interpreter_common.h:146`), in `Object.wait` (`monitor.cc:1262`) and
  on JNI return (`entrypoints/quick/quick_trampoline_entrypoints.cc:1197`). C
- Its only caller is JVMTI `StopThread` (`art/openjdkjvmti/ti_thread.cc:1075-1122`), and
  libopenjdkjvmti is not built (`Makefile:49,61`). The checkpoint closure (`ti_thread.cc:
  1099-1118`) can be copied into artbridge; its `Notify` wakes a monitor wait, not a park
  (`thread.cc:2683-2693`). C. App code can catch it: a `catch (Throwable)` loop kept running
  through 5 injections. M
- A thread that exits while still attached is a FATAL (`thread.cc:2247-2261`). C
- The probe's closure (`SetAsyncException`, `Notify`, then Java `Thread.interrupt()`) stops a thread
  in `Object.wait`, `Thread.sleep`, a busy loop, and `LockSupport.park` while the interrupt flag is
  clear, at once; the exception reaches the app group's `uncaughtException`. M
- A park whose thread's interrupt flag is already set is not woken: `Thread::Interrupt` returns
  early when the flag is set (`thread.cc:2671-2679`) and `Park` ignores the flag (`thread.cc:
  415-445`), AOSP 10's code (dine-art `f9aedbf5`). The closure must also call `Unpark()`; with it
  the park ends.
  M, C
- A socket read is woken by neither the injection nor an interrupt; `Os.shutdown(SHUT_RDWR)` and
  `Socket.close()` (signal 34 on Linux) wake it, a raw `close()` doesn't. M (Linux)
- A thread blocked entering a monitor another app holds stays blocked; once the monitor is free it
  enters and runs the block's body before the exception lands. M
- A frozen thread (`SuspendThreadByPeer`) accepts the injection (the checkpoint runs on the
  caller), unwinds after `Resume` and releases its monitors. M
- An injection inside a `<clinit>` leaves the class erroneous for everyone: waiters and later
  users get `NoClassDefFoundError`. In 34 complete runs that initialize 5296 boot classes in a loop
  under 208 to 656 injections each, 66 to 98 classes per run (15 to 34% of the injections) had
  their `<clinit>` hit, and each stayed erroneous VM-wide (`javax.crypto.JceSecurity`,
  `libcore.icu.LocaleData`, ICU classes). M (`out/probes/multi-app/results/case-storm-*.log`; the
  3 runs that hit the deadline below are excluded, their injection counts are inflated)
- In 3 of those 37 runs the loop's thread blocked for good on the monitor of
  `System.getProperties()`, a VM-wide object, so every later `System.getProperty` blocks, in any
  app. M. The monitor names an owner id no thread had: two reads gave 23305 and 30574, while ids
  are allocated first-free (`thread_list.cc:1545-1555`) and stay below 20 here (thread dump in
  `case-storm-37.log`). That fits a fat monitor whose owner thread exited and was freed
  (`Monitor::GetOwnerThreadId` reads `owner_->GetThreadId()`, `monitor.cc:1552-1560`): U. One more
  run hung with the injected thread at 100% CPU (cause unknown, log lost). Finalizers of shared
  objects the injection left half built fail on the shared FinalizerDaemon (`Inflater.finalize`
  NullPointerException, 7 of 37 runs; logged, not fatal). M
- The exception lands at invokes, gotos, monitor enter and exit and throws
  (`interpreter_switch_impl-inl.h:758-951`, `interpreter_common.h:146`), also on the cleanup call
  of a `finally`, which then doesn't run: a read stopped by shutdown skips `SocketInputStream`'s
  `releaseFD()`, so `Socket.close()` defers the close forever and the descriptor leaks. M, C
  (`AbstractPlainSocketImpl.java:628-654`). An injection into a loop of lock, try, finally-unlock
  on a shared `ReentrantLock` left the lock held by the dead thread in 43 to 46 of 50 trials (5
  runs); where in lock or unlock it landed is unmeasured. M
- A thread attached from C (`JavaVMAttachArgs.group`) returns from the call with the exception
  pending. C that clears it and detaches ends cleanly; C that makes another JNI call first aborts
  the process under `-Xcheck:jni` ("JNI DETECTED ERROR ... called with pending exception"). M
- libcore's wakeup signal for a socket closed under a blocked reader can't exist on Apple
  ([ART-24](../bug-tracker.md#art-24)); NIO uses SIGIO on Darwin and is not affected
  (`ojluni/src/main/native/NativeThread.c:50-54`). C. On the phone the kernel wakes the reader
  anyway: `close()` from another thread ends its `read()` at once with `EBADF`, `shutdown(SHUT_RDWR)`
  with 0. M (phone); through libcore U.

## Freeing one app

- ART unloads classes. Class loaders are weak roots (`art/runtime/class_linker.cc:5785-5799`);
  `CleanupClassLoaders` frees the ClassTable and LinearAlloc of collected ones (`:9606-9630`) on
  GC reclaim (`gc/collector/mark_sweep.cc:350`; the GC is CMS, `art/build/Android.common_build.mk:
  85`). Dex caches are weak (`class_linker.h:722-736`). C
- A dropped app's dex files stay. Their finalizer fails ("Failed to close dex file in finalizer",
  every cycle) because `closeDexFile` keeps a dex whose dex cache is still registered
  (`art/runtime/native/dalvik_system_DexFile.cc:396-405`), and nothing frees it after
  `CleanupClassLoaders`. With 500 classes defined from a 3.1 MB dex on the app's path (ATL's
  `api-impl.jar` dex, deflated as in most APKs so ART extracts it to memory;
  `api-impl-deflated.jar` from `build.sh`, passed as `DINE_PROBE_EXTRA_JAR`), RSS and VmSize grow
  by about 3.1 MB per drop cycle (`drop-plain-extra.log`); a dex with no class defined from it is
  freed (2 runs, logs not kept). M, C
- Drop and reload of a test app (about 46 MB of small objects, 200 classes, 4 blocked threads) 10
  times, with app A running throughout: the loader is collected at the first `Runtime.gc()` plus
  `runFinalization()` every cycle; heap back to baseline plus 0.1 MB; loaded classes back to
  baseline plus 96 (boot classes the first load initialized). RSS: 36.7 MB baseline, 85.5 MB
  loaded, 39.2 MB after the first drop, then about 60 KB more per cycle on average, which
  includes one leaked socket descriptor and the test app's own small dex per cycle. A control app
  that sets `Thread.setDefaultUncaughtExceptionHandler` to its own object keeps its loader and its
  46 MB. M
  (Linux RSS, not iOS `phys_footprint`)
- What keeps a loader alive (C): any live object of its classes; its live threads, and
  `contextClassLoader`, which new threads inherit (`Thread.java:177,549`); ThreadLocal values on
  shared threads (`ThreadLocal.java:308-310`); any VM-wide static above that holds an app object;
  Security providers and shutdown hooks the app added; JNI global refs from native code (circular:
  `JNI_OnUnload` runs only after the loader is gone, `java_vm_ext.cc:354`).
- What does not (C): `SharedLibrary` (weak, `java_vm_ext.cc:92`); the ResourceBundle cache
  (`ResourceBundle.java:304,718,736`); the proxy cache, per loader (`ClassLoader.java:195`).
- String literals and dex locations are interned strongly and never freed (`class_linker.cc:1600,
  1658,2537,8405`), so memory grows with each drop and restart of an app. C; size: within the
  60 KB per cycle above. M
- A dropped app's pending finalizers still run its code on the shared FinalizerDaemon. U

## Memory

- No `-Xmx` is passed (`artbridge.cpp:115-118`, `dine-atl/src/shared/startup.c:179-196`): the VM
  gets ART's defaults, 2 MB initial and 256 MB maximum for all apps together
  (`art/runtime/gc/heap.h:131-132`), growth limit equal to the maximum. C
- `Runtime.maxMemory()` is `JVM_MaxMemory()`, the VM's limit (`libcore/ojluni/src/main/native/
  Runtime.c:59-61`). An allocation that fails after the GCs throws `OutOfMemoryError` on the
  allocating thread (`art/runtime/gc/heap.cc:1783-1785`), whichever app filled the heap. C
- No per-app accounting. Per-thread cumulative allocation counts exist only with allocation stats
  on (`heap-inl.h:173-179`). Live heap per app needs a stop-the-world walk with `VisitObjects` or
  `CountInstances` (`heap.h:272,370`), grouped by class loader. C (the API exists). Grouping by
  the loader of each object's class misses what an app holds in boot-class instances: the walk
  found 206 objects, 2 KB, of the test app's 46 MB (`byte[]`, `ArrayList`). The walk, under a
  shared mutator lock with no thread suspended, took 3 to 5 ms over a 47 MB heap. M
- Java thread stacks: 1 MB plus a 16 KiB guard by default (`thread.cc:726-763`); artbridge's own
  threads are 8 MiB (`artbridge.cpp:98,147`). Only touched pages are resident. C
- Trim hooks are push-only: `Heap::Trim`, `VMRuntime.trimHeap`, `requestConcurrentGC`,
  `clampGrowthLimit`, `-XX:LowMemoryMode` (`dalvik_system_VMRuntime.cc:729-760`,
  `runtime_options.def:73`). ART gets no OS memory-pressure signal. C
- On Apple `kMadviseZeroes` is false, so ART releases memory with a memset then `MADV_DONTNEED`
  (`libartbase/base/mem_map.h:42-46`, `mem_map.cc:810-822`). C. On the phone those two calls left
  a touched 64 MB mapping's `phys_footprint` at 84 MB; `MADV_FREE_REUSABLE` brought it to 20 MB
  ([ART-26](../bug-tracker.md#art-26)). M (phone)
- Dine's memory limit on the iPhone 13 is 2097 MB: `phys_footprint` plus `limit_bytes_remaining`
  (`TASK_VM_INFO`) gives it at every step, and `os_proc_available_memory()` equals
  `limit_bytes_remaining` within 3 MB. Touching 32 MB steps, the one memory-pressure event (critical)
  and UIKit's memory warning came at 1679 MB (418 MB left); iOS killed Dine after the step that
  reached 2072 MB (25 MB left), with no JetsamEvent or crash report. With
  `com.apple.developer.kernel.increased-memory-limit` in an `entitlementsPath` file (xtool 1.22.2,
  free account) Dine installed without a prompt and the limit stayed 2097 MB. M (phone)
- Descriptors: soft `RLIMIT_NOFILE` 2560, hard unlimited, `kern.maxfilesperproc` 10240; raising
  the soft limit to 10240 works, and 10234 descriptors then opened before `EMFILE`. M (phone)

## Abort path

- `Runtime::Abort` takes `abort_lock_`, logs, then calls the abort hook if one is set, then
  `abort()` (`runtime.cc:620-668`). The hook option is `HookAbort`, next to `HookExit`
  (`art/runtime/runtime_options.def:151-155`). A hook that contains an abort to one app must not
  return and must release `abort_lock_`. C
