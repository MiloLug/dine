# Findings: ART and libcore for several apps in one VM

What dine-art (Android 10 ART, libcore 8.1/9) allows and blocks when several apps share one
runtime, as needed by `design.md`. A snapshot read on 2026-10-31; line numbers drift. Paths are
under `dine-art/` unless they start with `native/` or `dine-atl/`. **C**: read in code. **U**:
inference, unchecked. The one-runtime rule and the second-VM options are in
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
  (`thread.h:257-262`); its native code keeps running until it re-enters Java. C. Stopping the OS
  thread needs Mach `thread_suspend`: U.
- A suspended thread keeps its monitors. If it holds a lock other apps take (`Runtime`, `Locale`,
  `TimeZone`, ATL statics), they block: U.
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
  (`thread.cc:2683-2693`). C. Whether app code can catch the exception: U.
- A thread that exits while still attached is a FATAL (`thread.cc:2247-2261`). C
- Closing a socket does not wake a thread blocked reading it on Apple:
  [ART-24](../bug-tracker.md#art-24). NIO uses SIGIO on Darwin and is not affected
  (`ojluni/src/main/native/NativeThread.c:50-54`). C (code and SDK); on the phone U.

## Freeing one app

- ART unloads classes. Class loaders are weak roots (`art/runtime/class_linker.cc:5785-5799`);
  `CleanupClassLoaders` frees the ClassTable and LinearAlloc of collected ones (`:9606-9630`) on
  GC reclaim (`gc/collector/mark_sweep.cc:350`; the GC is CMS, `art/build/Android.common_build.mk:
  85`). Dex caches are weak (`class_linker.h:722-736`). C. When DexFile memory goes: U.
- What keeps a loader alive (C): any live object of its classes; its live threads, and
  `contextClassLoader`, which new threads inherit (`Thread.java:177,549`); ThreadLocal values on
  shared threads (`ThreadLocal.java:308-310`); any VM-wide static above that holds an app object;
  Security providers and shutdown hooks the app added; JNI global refs from native code (circular:
  `JNI_OnUnload` runs only after the loader is gone, `java_vm_ext.cc:354`).
- What does not (C): `SharedLibrary` (weak, `java_vm_ext.cc:92`); the ResourceBundle cache
  (`ResourceBundle.java:304,718,736`); the proxy cache, per loader (`ClassLoader.java:195`).
- String literals and dex locations are interned strongly and never freed (`class_linker.cc:1600,
  1658,2537,8405`), so memory grows with each drop and restart of an app. C; size U.
- A dropped app's pending finalizers still run its code on the shared FinalizerDaemon. U

## Memory

- No `-Xmx` is passed (`artbridge.cpp:115-118`, `dine-atl/src/shared/startup.c:179-196`): the VM
  gets ART's defaults, 2 MB initial and 256 MB maximum for all apps together
  (`art/runtime/gc/heap.h:131-132`), growth limit equal to the maximum. C
- No per-app accounting. Per-thread cumulative allocation counts exist only with allocation stats
  on (`heap-inl.h:173-179`). Live heap per app needs a stop-the-world walk with `VisitObjects` or
  `CountInstances` (`heap.h:272,370`), grouped by class loader. C (the API exists)
- Java thread stacks: 1 MB plus a 16 KiB guard by default (`thread.cc:726-763`); artbridge's own
  threads are 8 MiB (`artbridge.cpp:98,147`). Only touched pages are resident. C
- Trim hooks are push-only: `Heap::Trim`, `VMRuntime.trimHeap`, `requestConcurrentGC`,
  `clampGrowthLimit`, `-XX:LowMemoryMode` (`dalvik_system_VMRuntime.cc:729-760`,
  `runtime_options.def:73`). ART gets no OS memory-pressure signal. C
- On Apple `kMadviseZeroes` is false, so ART releases memory with a memset then `MADV_DONTNEED`
  (`libartbase/base/mem_map.h:42-46`, `mem_map.cc:810-822`). Whether that lowers iOS
  `phys_footprint`: U.

## Abort path

- `Runtime::Abort` takes `abort_lock_`, logs, then calls the abort hook if one is set, then
  `abort()` (`runtime.cc:620-668`). The hook option is `HookAbort`, next to `HookExit`
  (`art/runtime/runtime_options.def:151-155`). A hook that contains an abort to one app must not
  return and must release `abort_lock_`. C
