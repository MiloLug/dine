# Multi-app support: roadmap

Stages for running several Android apps at once on every backend. It replaces stage M8e of
`notes/atl-port.md`. The design behind it is `design.md`; facts are in the findings files; the
design work's record is `handoff.md`. Defects found on the way get codes in `notes/bug-tracker.md`,
other work in `notes/general-todo.md`, as for every stage. The user approved the design and this
roadmap on 2026-11-02. Each stage starts with its plan (superpowers:writing-plans with the
consilium).

Task markers:
- `[ ]` open;
- `[?]` a decision or a probe answer is needed first;
- `[!]` a blocker;
- `[x]` done.

## Stages

| Stage | Scope | Backends | State |
|---|---|---|---|
| [B1](#b1-native-fault-containment) | native fault containment (option 1) | one-VM | planned |
| [MA0](#ma0-design-and-probes) | finish the design, run the probes | all | done 2026-11-02 |
| [MA1](#ma1-registry-and-install) | registry and install | all | done 2026-11-02 |
| [MA2a](#ma2a-app-records) | app records, no primary app; one app per VM | all | done 2026-11-02 |
| [MA2b](#ma2b-several-apps-in-one-vm) | several apps in one VM | one-VM, headless test mode | done 2026-11-03 |
| [MA3](#ma3-containment) | containment of every app failure | one-VM | planned |
| [MA4](#ma4-freeze-drop-memory-ledger) | freeze, drop, memory ledger | one-VM | planned |
| [MA5](#ma5-saved-state) | saved instance state and memory callbacks | all | planned |
| [MA6](#ma6-tasks-and-windows) | several tasks and windows per app | all | planned |
| [MA7](#ma7-calls-between-apps) | Binder, `ipc` slot, calls between apps | all | planned |
| [MA8](#ma8-dine-policy-and-ui) | memory policy, running apps list | iOS | planned |
| [MA9](#ma9-scenario-apps) | scenario apps | all | planned |

Order: MA1 and MA2a follow MA0, MA2b follows MA2a; MA3 and MA4 need MA2b; B1 needs MA2a
(threads tagged with their app) and MA4's drop; MA7 needs MA1 and MA2b; MA9 needs everything before
it. M8a's APK import builds on MA1's registry. The order against `notes/atl-port.md`'s stages is
`notes/steps.md`.

## B1: native fault containment

A native fault (SIGSEGV, SIGBUS) in code all apps share ends all of Dine on one-VM backends. The
user made it a plan blocker ("SO it is a plan blocker until said otherwise") and lifted it with
option 1: "I think yes, we can lift it with option 1, so let's go with option 1". What stays
Dine-ending under option 1: bugs in Dine's own native code or in ART that fault in `kRunnable` or
corrupt shared memory. The design is `design.md` "Native faults"; facts, costs and the problems
found are in `findings-native-faults.md`.

- `[ ]` List the native code an app thread can reach (JNI natives, libraries behind them), with
  their global state and the locks they take.
- `[ ]` A sigchain handler for SIGSEGV and SIGBUS on one-VM backends. It maps the faulting thread
  to its app (MA2a's member on ART's `Thread`, `art_thread_embedder_tag`). It contains the fault
  only when the thread is an app's thread in `kNative` with the held-shared-locks counter at zero,
  and re-raises anything else with the default action so iOS still writes its crash report.
- `[ ]` Containment: park the thread with async-signal-safe calls on its alternate stack, write the
  app's crash log, then drop the app (MA4). Root visiting skips a parked thread, so the dropped
  app's class loader can unload (problem 8).
- `[ ]` Raw-address checks on every `Unsafe` and `Memory` address call, reads and writes, with
  their lengths (problems 2, 4): the address must lie in a region of the calling app; a per-thread
  cache of the last region hit.
- `[ ]` Region registration at every point that hands Java a raw address (problem 4).
- `[ ]` Object-plus-offset checks on `Unsafe`'s object calls: the offset inside the object and
  past its header, no primitive write over a reference field (problem 3).
- `[ ]` A failed check ends the app; the build flag `enable-oob-unsafe-recovery` makes it throw
  into the app instead (problem 17, `design.md` "Native faults").
- `[ ]` A malloc zone per app (shared with MA4's memory ledger; problem 14).
- `[ ]` Per-app state, kept per app in the library's source, for each native library whose global
  state the listing above shows to differ per app; ICU and the font caches stay shared (problem
  15).
- `[ ]` Shared locks taken through a wrapper that counts the ones each thread holds; sqlite's mutex
  layer.
- `[ ]` Faults inside code whose locks Dine can't see: libmalloc's shared zone ends Dine; Apple's
  frameworks and ICU are contained, and a hang of UIKit's thread or another app's main thread
  afterwards ends Dine (problem 5).
- `[ ]` A monitor a parked thread holds: Dine ends when a thread of another app blocks on it,
  checked in ART's contended lock paths (problem 6).
- `[ ]` `abort()` paths: libmalloc's on the app's own zone contained, on the shared zone ends Dine;
  `std::terminate` and assertions follow the rule for unknown locks (problem 13).
- `[ ]` Linux fault-injection tests in the headless test mode: a fault in `kNative` on one app's
  thread inside a JNI call leaves the other app running; a fault with a shared lock held ends the
  process; a wild `Unsafe` access is rejected.
- `[?]` Probe, phone: the handler gets SIGSEGV and SIGBUS on the faulting thread, parks it, and the
  other app keeps running; how lldb passes the signal on (problem 12); whether a re-raise keeps the
  iOS crash report (problem 11).
- `[?]` Probe, phone: the cost of the checks on the iPhone 13 (Linux numbers in
  `findings-native-faults.md`).
- Done when: on the phone and in the headless test mode, a fault injected into one app's JNI call
  ends that app only, and a wild `Unsafe` access from one app doesn't reach another.

## MA0: design and probes

Runs beside M6a of `notes/atl-port.md` (`notes/steps.md`): the design and probes, no product code.

- `[x]` The user's review of `design.md` with the probe results: approved 2026-11-02 ("Approve
  all"). `notes/filesystem/proposal.md`'s layout replaces `design.md` "Prefix"; several ART copies
  are rejected ("too complicated").
- `[x]` For the review: where the drop may inject. Decided 2026-11-02: in app code only, in shared
  code only as the throw of a blocking call, never in a class initializer (`design.md` "Freeze and
  drop"). On host ART an injection inside a boot class's
  `<clinit>` left that class erroneous VM-wide (15 to 34% of injections into a loop over boot
  classes), one into a lock, try, finally-unlock loop left a shared `ReentrantLock` held (43 to 46
  of 50), and in 3 of 37 such loops the VM-wide `System.getProperties()` monitor stayed held, its
  owner an id no thread had (`findings-runtime.md` "Stopping one app's threads").
- `[x]` Builder check of the design (brainstorming), 2026-11-02.
- `[x]` Probe, Linux headless: two apps in one VM through artbridge-like C, an async exception into
  threads parked in `Object.wait`, `LockSupport.park`, `Thread.sleep` and a socket read; check
  `ThreadList` and monitors afterwards. 2026-11-02, `tests/probes/multi-app/`: all stop, with
  `Unpark` in the closure and the socket shut down; `ThreadList` back to its count, monitors
  released, the other app running; a `catch (Throwable)` loop never stops; C attached threads must
  check the exception (`findings-runtime.md` "Stopping one app's threads").
- `[x]` Probe, Linux headless: drop an app and check that its class loader and objects are
  collected (heap before and after, `CountInstances` by loader). 2026-11-02: collected at the first
  GC in each of 10 cycles; RSS back to 2.5 MB over baseline, then about 60 KB per cycle; a leak
  control keeps its loader. The app's dex stays: about 3.1 MB per cycle with a used 3 MB dex
  (`findings-runtime.md` "Freeing one app").
- `[x]` Probe, phone: does `shutdown(fd, SHUT_RDWR)` wake a thread blocked in `read` on iOS
  ([ART-24](../bug-tracker.md#art-24)). 2026-11-02: yes, and so does `close()` (with `EBADF`).
- `[x]` Probe, phone: `malloc_create_zone` per app and `malloc_destroy_zone`, and what each does to
  `phys_footprint`; does ART's memset plus `MADV_DONTNEED` lower it. 2026-11-02: freeing a zone's
  blocks lowers it at once; memset plus `MADV_DONTNEED` doesn't, `MADV_FREE_REUSABLE` does
  ([ART-26](../bug-tracker.md#art-26)); the default zone's struct is writable
  (`findings-native-faults.md` problem 14).
- `[x]` Probe, phone: `os_proc_available_memory()` and memory warnings on iOS 27; Dine's jetsam
  limit on the iPhone 13, with and without the `increased-memory-limit` entitlement (does a free
  account get it); `RLIMIT_NOFILE`'s soft and hard limits and raising the soft one. 2026-11-02:
  2097 MB with or without the entitlement (it didn't take effect), one critical pressure event at
  418 MB left, no jetsam report; descriptors 2560 soft, raised to 10240 (`findings-runtime.md`
  "Memory").
- `[x]` Probe, phone: Mach `thread_suspend` and `thread_terminate` on Dine's own threads.
  2026-11-02: suspend and resume work; terminate on a pthread fails (`MACH_SEND_INVALID_DEST`).
- The drop probes pass (my call) when a drop and reload of a test app returns its measured
  footprint except a few MB of what is never freed (interned strings, dex locations), and no
  thread of an idle app stays parked for good once ART-24 is fixed. Linux (2026-11-02): the
  threads part holds; the footprint part fails for any app with a real dex until MA4 frees dropped
  dex files. Phone: the kernel wakes a blocked read on close or shutdown; the in-VM drop on the
  phone is MA4's (below); on Apple the footprint part also needs
  [ART-26](../bug-tracker.md#art-26).
- Phone probes: the `ma` buttons on the Dev art screen (`dine_ma_probe`,
  `native/artbridge/dev_multiapp.cpp`), logged as `ma probe <name> ...`.

## MA1: registry and install

After MA0 and M6a, before MA2 (`notes/steps.md`). Built 2026-11-02 on Linux (gtk and headless) and
run on the phone. The registry's shape is `design.md` "Registry"; the
suite is `dine-atl/tests/package/` (`tools/dine test package`).

- `[x]` Registry schema (SQLite, WAL, `synchronous=FULL`), a row per package keyed by its package
  name, written in one transaction per install; uid per package at install, from 10000, never
  reused. Each package's APKs in `apps/<pkg>/<versionCode>-<serial>/`, byte for byte as installed.
- `[x]` Signature spoofing through `FAKE_PACKAGE_SIGNATURE` plus `<application>` meta-data
  `fake-signature` (hex), in place of the GMS package-name list: the install confirmation asks,
  the CLI grants it with `--allow-fake-signature`. Whether current GmsCore declares the meta-data:
  unchecked (MA9).
- `[x]` `PackageInstaller` sessions (`createSession`, `openWrite`, `fsync`, `commit` with an
  `IntentSender`, `STATUS_PENDING_USER_ACTION`), `ACTION_INSTALL_PACKAGE` with
  `EXTRA_RETURN_RESULT`, `ACTION_UNINSTALL_PACKAGE` and `ACTION_DELETE`; the CLI's `--install` and
  `--uninstall` write the same rows. The confirmation is an `AlertDialog` through the `ui` slot;
  an app-started install keeps Android's rules (same signer, no downgrade). A session takes split
  APKs as one package.
- `[x]` `PackageManager` reads the registry: `getInstalledPackages` and `getInstalledApplications`
  with flags (meta-data, signatures, signing certificates, `reqFeatures`), `getPackageArchiveInfo`,
  `getPackageInfo`, intent resolution across packages (action, categories, data scheme),
  `getLaunchIntentForPackage`, `getPackagesForUid`, `getPackageUid`, `checkSignatures`. The
  microG-only visibility gate is gone.
- `[x]` `PACKAGE_ADDED/REPLACED/REMOVED` with scheme `package` to the installing app's own receivers;
  other running apps get them in MA7.
- `[x]` `ATLGStub` as preinstalled rows (`com.google.android.gms`, `gsf`, `vending`, with
  `FLAG_SYSTEM` and Google's signatures); an installed package of the same name replaces its row
  and keeps its uid, and its uninstall restores the row.
- `[x]` An APK replaced while its app runs: the new version is written and fsynced before the row
  points at it, the old one is deleted after the commit, and an app that replaced or removed itself
  ends. Ending the app in another process is MA7.
- `[x]` Data dirs keyed by package (`data/<pkg>/`) under the prefix `DINE_PREFIX` (default
  `~/.dine`); a run by APK path installs the APK unless the registry holds those exact bytes; a run
  by `--package` starts an installed package; gtk takes the app id from `--package`.
- `[x]` iOS: the prefix, with the registry, is `Application Support/dine`; dev-screen runs install
  into it. On the phone (2026-11-02, through `dine-peek` and the syslog): a first demo_app run installs it, a second start installs
  nothing; the `installer` tile's session install shows the confirmation from the Application
  context and installs.
- `[x]` `DelegateLastClassLoader(String, String, ClassLoader)` and a child-first `PathClassLoader`
  (Mihon's compat order) both load an installed extension's class from its `sourceDir`. Mihon's SDK
  threshold for the platform class: unchecked.
- Done when: the package suite grades install, query and removal on headless, including an APK
  without a launcher activity and a `reqFeatures` query. Met 2026-11-02.

## MA2a: app records

MA2 split in two (the user, 2026-11-02): MA2a gives every app its record and deletes the primary app
while each VM still runs one app; MA2b runs several apps in one VM. The record model is `design.md`
"App record".

- `[x]` The app record and its thread tagging: `ATLLoadedApp` plus the C `struct atl_app`
  (`src/shared/app.h`); a `ThreadGroup` per app whose `embedderTag` ART copies to a member of each
  thread that starts or attaches in it (`art_embedder.h`); the host thread that runs the app joins
  its group; threads attached without a group take the host's app on gtk and headless (the user:
  "Host's app on PC"), none on iOS.
- `[x]` ATL's process-wide state into the record: data dir, PackageManager, providers, dynamic
  receivers, preferences, a `Configuration` copy, the LayoutInflater constructors (by full class
  name), job scheduler, shown dialogs, the keyboard and input state, location listeners, the MPRIS
  id; an AsyncTask's handler is on the main Looper of the app that made it; C: the window,
  activity stack, insets and exclusion, APK class path, data dir, listener.
- `[x]` No primary app: the fields `design.md` lists are deleted; code reaches its app through its
  Context, its object or a handle; Android's static APIs read the calling thread's record.
  `getApplicationContext()` of a package whose app isn't running is null, as Android (the user's
  answer); `createPackageContext` of an unknown package throws.
- `[x]` One start path per record (`ATLLoadedApp.start`): Application, providers, UnifiedPush,
  `onCreate`.
- `[x]` The host API takes app handles (`nav.h`, `host.h`, the embedded listener); the embedder
  makes the handle before the start (`dine_atl_app_new`), so insets still go in before it.
- `[x]` The notes follow the code: no note but a findings file describes a primary app.
- Not in MA2a: the gtk host keeps its one window and app handle, and gtk's C IME context and
  MediaSession stay per process (one app per gtk process); the screen's density stays VM-wide,
  the window size is per app (M6b3c) and per task with MA6; the headless and uikit input state (touch, scroll, edit
  target) stays per process (MA2b).
- Done when: today's suites pass at baseline on headless and gtk, both iOS builds build, `dine-atl/src`
  keeps none of the primary app's fields. Met 2026-11-02, and `dbg smoke` passes on the phone.

## MA2b: several apps in one VM

- `[x]` A main thread and main loop per app: the loop slot has an instance per Android main thread
  (glib keeps its one: gtk runs one app per process); the cli host runs each app on its own 8 MiB
  thread, artbridge each later `dine_atl_run`; uikit's queue to UIKit, its windows and the frame
  link's passes per app; the headless input, edit and test-hook state per app main thread.
- `[x]` Every app in the VM gets `Application.onCreate`, its providers and its receivers through
  `ATLLoadedApp.start` (MA2a's path), several per VM. A package starts once per VM: a second start
  of it is refused until MA4's drop.
- `[x]` The embedded host and `dine_atl_run` start a second app; cfrunloop's quit per app; the dev
  screen starts a second APK over the first, and a running app's tile brings it to front (phone,
  2026-11-03: demo_app and widgets side by side).
- `[x]` The native library table keyed by (path, loader); on Apple a library resolves only the
  `Java_*` names of its own archive (`art_register_jni_symbols`, lists from
  `tools/libexec/jni-symbols.sh`).
- `[x]` The headless test mode: each `--instrument CLASS` or `-l ACTIVITY` opens an app with the
  APKs after it; a finished instrumentation ends only its app (`host_app_end`) and the VM exits
  after the last; each Instrumentation line carries `[<package>] ` (the user's answer); test hooks
  per app; `tools/dine test framework --one-vm`.
- `[x]` ART's daemons keep no app and run no app code; each app's finalizers and `Cleaner`s run on
  one cleanup thread per app in its group (`CleanupDomain`), on every backend, started on the
  first object and exiting when idle (the user, 2026-11-03: "retagging really doesn't make sense,
  we need to run all app-related threads with that app's tag, do as you recommend"). On a thread of
  no app `Looper.myLooper() == Looper.getMainLooper()` stays true:
  [ATL-41](../bug-tracker.md#atl-41).
- `[x]` Per-app AsyncTask executors behind the static `THREAD_POOL_EXECUTOR` (still a
  `ThreadPoolExecutor`) and `SERIAL_EXECUTOR`. Shared lazily created threads need no code: each
  worker of a shared pool takes the group of the thread that creates it (`design.md` "App record").
- `[x]` The cost of an Android main thread per app: `findings-runtime.md` "Memory" (Linux RSS per
  idle app, the phone's `phys_footprint` at each start).
- Moved to MA7: a service of another package runs in its caller's app, but its `getApplication()`
  is that package's Application, which no host started (the user: decide in MA7).
- Moved to MA3: target SDK and package name per app in ART (one VM-wide value each, unset today).
- Done when: two framework suite APKs instrumented side by side in one headless VM each pass. Met
  2026-11-03: `tools/dine test framework --one-vm` runs all five suites in one VM at their
  expectations.

## MA3: containment

- `[ ]` Per-app `ThreadGroup.uncaughtException`; `hacky_uncaught_exception_handler` goes.
- `[ ]` `System.exit`, `Runtime.halt` and `Process.killProcess` end the calling app, caught before
  the `shuttingDown` latch.
- `[ ]` App-reachable ART FATALs become app kills: JNI global table overflow, the suspension
  timeout (non-fatal return), `-Xcheck:jni` errors.
- `[ ]` The finalizer watchdog per app (MA2b's cleanup thread per app, which ART's watchdog doesn't
  watch): a finalizer over its limit ends that app.
- `[ ]` A main-thread watchdog per app on one-VM backends, with Android's wait or close dialog;
  its limits measured under `-Xint` on the phone.
- `[ ]` Native code that calls into an app (ATL's C, uikit's upcalls) checks and clears a pending
  exception after each call: under `-Xcheck:jni` the next JNI call with one pending aborts the
  process (MA0 probe).
- `[ ]` libcore's VM-wide statics behind the app record (`findings-runtime.md` table); drop the
  `-Djava.io.tmpdir`. ART's target SDK and process package name per app (`Runtime`,
  `VMRuntime`).
- Done when: in the headless test mode each failure kind in one app leaves the other app running
  (a test per kind).

## MA4: freeze, drop, memory ledger

- `[ ]` Freeze: stop delivery, then `SuspendThreadByPeer` per thread; resume.
- `[ ]` Drop: async exception through artbridge (the JVMTI closure plus `Unpark`, since an
  interrupt doesn't wake a park whose thread is already interrupted), frozen threads resumed after
  the injection, interrupts, descriptor ledger shutdown, windows closed. MA0's Linux results:
  `findings-runtime.md`.
- `[ ]` The drop's delivery rule in ART's `Thread::ObserveAsyncException`: the drop's exception
  lands only in a frame of the app's own code, or in shared code only as the throw of a blocking
  call (wait, park, sleep), never inside a class initializer. Done when MA0's probes
  (`tests/probes/multi-app/run.sh`: storm, juclock, the `System.getProperties()` hang) show no
  erroneous shared class and no held shared lock with it.
- `[ ]` A thread still running after a deadline (a `catch (Throwable)` loop) is suspended for good
  and its GC roots skipped (shared with B1's parked threads).
- `[ ]` [ART-26](../bug-tracker.md#art-26): release pages with `MADV_FREE_REUSABLE` on Apple, so a
  dropped app's heap leaves the footprint iOS counts.
- `[ ]` The per-app descriptor ledger (a choke point in libcore's `Os` or in the bionic shim) and
  [ART-24](../bug-tracker.md#art-24). The ledger closes descriptors itself: after a drop
  `Socket.close()` can defer the close forever (MA0).
- `[ ]` The memory ledger: heap per class loader, malloc zone per app with shared caches in a
  shared zone, stacks, descriptors, mappings.
- `[ ]` Caps per app on the Java heap, JNI globals and descriptors; the heap cap is set at the
  app's start from the memory available then; `maxMemory` and `getMemoryClass` report it; the app
  over its cap fails. Shared limits raised:
  `kGlobalsMax` and `kWeakGlobalsMax`, the soft `RLIMIT_NOFILE` (`design.md` "Memory control").
- `[ ]` A leak report in dev builds: what still holds a dropped app's objects.
- `[ ]` Free a dropped app's dex files: today `closeDexFile` keeps any dex whose dex cache is still
  registered, so every drop keeps the app's dex (MA0).
- `[ ]` Measure the cost of per-app live-byte counting (`design.md` "Memory control"; a walk by
  class loader sees only instances of the app's own classes, MA0) and a frozen app's footprint
  (`design.md` "Options considered").
- `[ ]` On the phone: probe 1's cases through `dine_art_run`, since blocked threads behave
  differently on Apple (ART-24, os_sync park).
- Done when: on the phone, dropping an app returns its footprint (measured) while another app keeps
  running.

## MA5: saved state

- `[ ]` `onSaveInstanceState` at `onStop` (before it for targets below P), `View.saveHierarchyState`
  and `restoreHierarchyState`, `onRestoreInstanceState`, a Bundle to `onCreate`.
- `[ ]` Bundles held outside the app and on disk (one-VM backends); restore after a drop and after
  iOS ends Dine.
- `[ ]` Linux: the same Bundle files; a clean end (window closed, crash, SIGTERM at logout)
  deletes them, a start that finds them restores (`design.md` "Holes in the static model").
- `[ ]` `onTrimMemory` (`TRIM_MEMORY_UI_HIDDEN`, `TRIM_MEMORY_BACKGROUND`), `onLowMemory`.
  `registerComponentCallbacks` is real (the Application keeps them, M6b3c).
- `[ ]` Configuration changes: recreation with saved state. A night change reaches
  `onConfigurationChanged` of the activities that cover uiMode (M6b3c); the others keep their
  configuration.
- Done when: a test APK's activity state survives a drop and a reload in the headless test mode,
  and a `kill -9` of its headless process and a restart.

## MA6: tasks and windows

- `[ ]` Task records per app; `FLAG_ACTIVITY_NEW_TASK`, `NEW_DOCUMENT`, `MULTIPLE_TASK`,
  `documentLaunchMode`, `launchMode`, `taskAffinity`.
- `[ ]` A `ui_window` per task: a GtkWindow per task on gtk, a container per task on iOS.
- `[ ]` Insets, exclusion and navigation per window; `atl_nav_*` per task.
- Done when: a test APK opens a second task in a second window on gtk and headless.

## MA7: calls between apps

- `[ ]` Binder within one app: `queryLocalInterface`, `onTransact`, `transact`, `linkToDeath`.
- `[ ]` Parcels with binder handle tables; the `ipc` slot with `inproc` and `unix` backends.
- `[ ]` `inproc`: the target app's binder thread, no call timeout, `DeadObjectException` and
  `binderDied` on drop.
- `[ ]` `unix`: runtime dir, lock files, spawn lock, `SO_PEERCRED` identity, object exports with
  reference counts, loop-slot descriptor watches for poll and glib.
- `[ ]` `getCallingUid`, `getCallingPid`, `getRunningAppProcesses` from the transport.
- `[ ]` `startActivity` and `startActivityForResult` into another package; `bindService`,
  `unbindService`, `onServiceDisconnected`; providers across apps (CursorWindow over shared
  memory); broadcasts across apps (implicit ones only to running apps; an explicit one starts its
  target).
- `[ ]` `ParcelFileDescriptor` in Parcels: descriptors passed with `SCM_RIGHTS` on `unix`.
- `[?]` A service of another package runs in its caller's app, but its `getApplication()` is that
  package's Application, which no host started (no `onCreate`, no main Looper; its
  `getApplicationContext()` is null). Options: that never-started object (today), null, or that
  package's start path (Application, providers, `onCreate`) run once on the caller's main thread
  before the service's `onCreate`, as Android starts a package's Application before its services.
- `[ ]` A bound service app that dies is started again with a backoff for `BIND_AUTO_CREATE`
  clients, which reconnect.
- `[ ]` `unix`: a second launch of a running app forwards its intent to it and exits.
- `[ ]` PendingIntent records as registry rows (owner, intent, flags, a generation) on every
  backend, from MA1; they need `Intent` in Parcels, which ATL lacks.
- `[ ]` `PendingIntent.send` from the registry rows: starts the owner if needed and delivers.
- `[ ]` `PACKAGE_ADDED/REPLACED/REMOVED` to apps in other processes, from MA1; what to watch:
  `design.md` "Linux: the static model".
- `[ ]` An app whose APK another process replaced or removed ends, from MA1.
- `[ ]` The gtk D-Bus intent API kept as the desktop's entry point into the same delivery
  (`design.md`).
- Done when: a client APK binds a service APK and queries its provider in both the headless test
  mode and two headless processes, with the same results.

## MA8: Dine policy and UI

- `[ ]` Background freeze about 10 s after an app leaves the screen, unless it asks to run (audio, a
  started or foreground service, a partial `WakeLock`, a running job, a bound client); a thaw for
  calls and delivered events (`design.md` "Freeze and drop").
- `[ ]` Memory pressure sources and the drop order; `-Xmx` from `os_proc_available_memory()`.
- `[ ]` The running apps list with one entry per task, each with its app's state (running, frozen,
  dropped, crashed), and a close action (`notes/nav-gestures.md` Behaviour).
- `[ ]` iOS background wake-ups (a finished background `URLSession`, a `BGProcessingTask`, a
  notification tap after Dine was killed) load only the owning app's record, without UI; the
  wake-ups themselves are M8d and the downloads, notifications and jobs items of
  `notes/os-features.md`.
- `[ ]` App lifecycle around iOS background and foreground for every app (M8b's calls per app).

## MA9: scenario apps

- `[ ]` F-Droid: install an app and open it in a new window.
- `[ ]` Mihon or TachiyomiSY: install extensions from a repo and load them in-process.
- `[ ]` microG started by hand, then an app that needs it: both work (bind, calls, caller checks).
  Starting apps at login or with Dine is [ATL-30](../general-todo.md#atl-30), not a multi-app
  stage.
- `[ ]` An app that opens a second window of itself through `NEW_DOCUMENT` or `MULTIPLE_TASK`.

## Docs to update

Done 2026-11-02: the notes listed in `findings-hosting.md` "Notes that assume one app per
process" name the multi-app stage that changes each place; M8a now builds on MA1's registry.
