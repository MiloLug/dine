# Multi-app support: roadmap

Stages for running several Android apps at once on every backend. It replaces stage M8e of
`notes/atl-port.md`. The design behind it is `design.md` (preliminary); facts are in the findings
files; how to resume the design work is `handoff.md`. Defects found on the way get codes in
`notes/bug-tracker.md`, other work in `notes/general-todo.md`, as for every stage.

The roadmap is preliminary: stages, their order and their content follow the design, which is not
approved.

Task markers:
- `[ ]` open;
- `[?]` a decision or a probe answer is needed first;
- `[!]` a blocker;
- `[x]` done.

## Stages

| Stage | Scope | Backends | State |
|---|---|---|---|
| [B1](#b1-native-fault-containment) | native fault containment (option 1) | one-VM | planned |
| [MA0](#ma0-design-and-probes) | finish the design, run the probes | all | next |
| [MA1](#ma1-registry-and-install) | registry and install | all | planned |
| [MA2](#ma2-app-records) | per-app state, several apps in one VM | one-VM, headless test mode | planned |
| [MA3](#ma3-containment) | containment of every app failure | one-VM | planned |
| [MA4](#ma4-freeze-drop-memory-ledger) | freeze, drop, memory ledger | one-VM | planned |
| [MA5](#ma5-saved-state) | saved instance state and memory callbacks | all | planned |
| [MA6](#ma6-tasks-and-windows) | several tasks and windows per app | all | planned |
| [MA7](#ma7-calls-between-apps) | Binder, `ipc` slot, calls between apps | all | planned |
| [MA8](#ma8-dine-policy-and-ui) | memory policy, running apps list | iOS | planned |
| [MA9](#ma9-scenario-apps) | scenario apps | all | planned |

Order: MA1 and MA2 can start once MA0 settles the design; MA3 and MA4 need MA2; B1 needs MA2
(threads tagged with their app) and MA4's drop; MA7 needs MA1 and MA2; MA9 needs everything before
it. M8a's APK import builds on MA1's registry.

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
  to its app (MA2's field on ART's `Thread`). It contains the fault only when the thread is an app's
  thread in `kNative` with the held-shared-locks counter at zero, and re-raises anything else with
  the default action so iOS still writes its crash report.
- `[ ]` Containment: park the thread with async-signal-safe calls on its alternate stack, write the
  app's crash log, then drop the app (MA4). Root visiting skips a parked thread, so the dropped
  app's class loader can unload (problem 8).
- `[ ]` Raw-address checks on every `Unsafe` and `Memory` address call, reads and writes, with
  their lengths (problems 2, 4): the address must lie in a region of the calling app; a per-thread
  cache of the last region hit.
- `[ ]` Region registration at every point that hands Java a raw address (problem 4).
- `[ ]` Object-plus-offset checks on `Unsafe`'s object calls: the offset inside the object and
  past its header, no primitive write over a reference field (problem 3).
- `[?]` What a failed check does: end the app or throw (problem 17).
- `[ ]` A malloc zone per app (shared with MA4's memory ledger; problem 14).
- `[ ]` A separate instance per app of each native library with global state, from the listing
  above (problem 15).
- `[ ]` Shared locks taken through a wrapper that counts the ones each thread holds; sqlite's mutex
  layer.
- `[?]` Faults inside code whose locks Dine can't see (libmalloc, Apple's frameworks, ICU's mutex):
  end Dine, or a narrower rule (problem 5).
- `[?]` Java monitors a faulting thread holds on objects other apps use (problem 6).
- `[?]` Which `abort()` paths (SIGABRT) can be contained (problem 13).
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

- `[?]` The user's review of `design.md`, the static Linux model first; then the open design points
  listed there.
- `[ ]` Builder check of the design (brainstorming), then a plan per stage (writing-plans).
- `[?]` Probe, Linux headless: two apps in one VM through artbridge-like C, an async exception into
  threads parked in `Object.wait`, `LockSupport.park`, `Thread.sleep` and a socket read; check
  `ThreadList` and monitors afterwards.
- `[?]` Probe, Linux headless: drop an app and check that its class loader and objects are
  collected (heap before and after, `CountInstances` by loader).
- `[?]` Probe, phone: does `shutdown(fd, SHUT_RDWR)` wake a thread blocked in `read` on iOS
  ([ART-24](../bug-tracker.md#art-24)).
- `[?]` Probe, phone: `malloc_create_zone` per app and `malloc_destroy_zone`, and what each does to
  `phys_footprint`; does ART's memset plus `MADV_DONTNEED` lower it.
- `[?]` Probe, phone: `os_proc_available_memory()` and memory warnings on iOS 27; Dine's jetsam
  limit on the iPhone 13.
- `[?]` Probe, phone: Mach `thread_suspend` and `thread_terminate` on Dine's own threads.
- `[?]` Fallback probe, only if the drop probes fail: two renamed libart dylib copies on the phone,
  a VM in each, drop one, boot it again.

## MA1: registry and install

- `[ ]` Registry schema (SQLite, WAL) and APK store, written in one transaction per install; uid
  per package at install.
- `[ ]` Signature spoofing through `FAKE_PACKAGE_SIGNATURE` for any app that asks, in place of the
  GMS package-name list.
- `[ ]` `PackageInstaller` sessions (`createSession`, `openWrite`, `fsync`, `commit` with a
  PendingIntent, `STATUS_PENDING_USER_ACTION`), `ACTION_INSTALL_PACKAGE` with
  `EXTRA_RETURN_RESULT`, `ACTION_UNINSTALL_PACKAGE`; the CLI's `--install` writes the same rows.
  The install confirmation UI per backend.
- `[ ]` `PackageManager` reads the registry: `getInstalledPackages` and `getInstalledApplications`
  with flags (meta-data, signatures, signing certificates, `reqFeatures`), `getPackageArchiveInfo`,
  `getPackageInfo`, intent resolution across packages, `getLaunchIntentForPackage`,
  `getPackagesForUid`, `getPackageUid`, `checkSignatures`. The microG-only visibility gate goes.
- `[ ]` `PACKAGE_ADDED/REPLACED/REMOVED` with scheme `package` to running apps.
- `[ ]` Data dirs keyed by package; the gtk app id from the package.
- `[ ]` iOS: the registry in Application Support; Dine's launcher reads its rows (labels, icons)
  instead of `AppLibrary`'s `apps` table.
- `[ ]` `DelegateLastClassLoader` (Mihon uses it on newer SDKs; the level is unchecked), or confirm
  Mihon's compat `PathClassLoader` path works at SDK 21.
- Done when: the package suite grades install, query and removal on headless, including an APK
  without a launcher activity and a `reqFeatures` query.

## MA2: app records

- `[ ]` The app record and its thread tagging (`ThreadGroup` plus a field on ART's `Thread`;
  attached threads; UIKit upcalls).
- `[ ]` ATL's process-wide state behind the record (`findings-framework.md` table): primary app,
  data dir, PackageManager, providers, receivers, preferences, `sys_config` copy, layout inflater
  cache, job scheduler, dialogs, IME, display metrics, C globals.
- `[ ]` A main thread and main Looper per app.
- `[ ]` Guests get `Application.onCreate`, their providers and their receivers.
- `[ ]` The host API takes app handles; `dine_atl_run` and ATL's `started` stop refusing a second
  app; cfrunloop's `main_loop.quit` per app.
- `[ ]` The native library table keyed by (path, loader); native lookup limited to the loader's own
  libraries on Apple.
- `[ ]` The headless test mode: several apps in one VM.
- Done when: two test APKs run side by side in one headless VM and the framework suite passes in
  each.

## MA3: containment

- `[ ]` Per-app `ThreadGroup.uncaughtException`; `hacky_uncaught_exception_handler` goes.
- `[ ]` `System.exit`, `Runtime.halt` and `Process.killProcess` end the calling app, caught before
  the `shuttingDown` latch.
- `[ ]` App-reachable ART FATALs become app kills: JNI global table overflow, the suspension
  timeout (non-fatal return), `-Xcheck:jni` errors.
- `[ ]` A finalizer thread and watchdog per app.
- `[ ]` A main-thread watchdog per app (ANR).
- `[ ]` libcore's VM-wide statics behind the app record (`findings-runtime.md` table); drop the
  `-Djava.io.tmpdir`.
- Done when: in the headless test mode each failure kind in one app leaves the other app running
  (a test per kind).

## MA4: freeze, drop, memory ledger

- `[ ]` Freeze: stop delivery, then `SuspendThreadByPeer` per thread; resume.
- `[ ]` Drop: async exception through artbridge (the JVMTI closure), interrupts, descriptor
  ledger shutdown, windows closed, park-forever fallback.
- `[ ]` The per-app descriptor ledger (a choke point in libcore's `Os` or in the bionic shim) and
  [ART-24](../bug-tracker.md#art-24).
- `[ ]` The memory ledger: heap per class loader, malloc zone per app with shared caches in a
  shared zone, stacks, descriptors, mappings.
- `[ ]` A leak report in dev builds: what still holds a dropped app's objects.
- Done when: on the phone, dropping an app returns its footprint (measured) while another app keeps
  running.

## MA5: saved state

- `[ ]` `onSaveInstanceState` at `onStop` (before it for targets below P), `View.saveHierarchyState`
  and `restoreHierarchyState`, `onRestoreInstanceState`, a Bundle to `onCreate`.
- `[ ]` Bundles held outside the app and on disk (one-VM backends); restore after a drop and after
  iOS ends Dine.
- `[?]` Linux: restore after a kill from outside the app (`design.md` "Open design points").
- `[ ]` `onTrimMemory` (`TRIM_MEMORY_UI_HIDDEN`, `TRIM_MEMORY_BACKGROUND`), `onLowMemory`,
  `registerComponentCallbacks`.
- `[ ]` Configuration changes: `onConfigurationChanged` or recreation with saved state.
- Done when: a test APK's activity state survives a drop and a reload on headless.

## MA6: tasks and windows

- `[ ]` Task records per app; `FLAG_ACTIVITY_NEW_TASK`, `NEW_DOCUMENT`, `MULTIPLE_TASK`,
  `documentLaunchMode`, `launchMode`, `taskAffinity`.
- `[ ]` A `ui_window` per task: a GtkWindow per task on gtk, a container per task on iOS.
- `[ ]` Insets, exclusion and navigation per window; `atl_nav_*` per task.
- Done when: a test APK opens a second task in a second window on gtk and headless.

## MA7: calls between apps

- `[ ]` Binder within one app: `queryLocalInterface`, `onTransact`, `transact`, `linkToDeath`.
- `[ ]` Parcels with binder handle tables; the `ipc` slot with `inproc` and `unix` backends.
- `[ ]` `inproc`: the target app's binder thread, call timeouts, `DeadObjectException` and
  `binderDied` on drop.
- `[ ]` `unix`: runtime dir, lock files, spawn lock, `SO_PEERCRED` identity, object exports with
  reference counts, loop-slot descriptor watches for poll and glib.
- `[ ]` `getCallingUid`, `getCallingPid`, `getRunningAppProcesses` from the transport.
- `[ ]` `startActivity` and `startActivityForResult` into another package; `bindService`,
  `unbindService`, `onServiceDisconnected`; providers across apps (CursorWindow over shared
  memory); broadcasts across apps (implicit ones only to running apps; an explicit one starts its
  target).
- `[?]` The gtk D-Bus intent API: kept as the desktop's entry point (proposed, `design.md`).
- Done when: a client APK binds a service APK and queries its provider in both the headless test
  mode and two headless processes, with the same results.

## MA8: Dine policy and UI

- `[ ]` Memory pressure sources and the freeze and drop policy; `-Xmx` from
  `os_proc_available_memory()`.
- `[ ]` The running apps list with several entries and their states (running, frozen, dropped,
  crashed), a close action (`notes/nav-gestures.md` Behaviour).
- `[ ]` App lifecycle around iOS background and foreground for every app (M8b's calls per app).

## MA9: scenario apps

- `[ ]` F-Droid: install an app and open it in a new window.
- `[ ]` Mihon or TachiyomiSY: install extensions from a repo and load them in-process.
- `[ ]` microG started by hand, then an app that needs it: both work (bind, calls, caller checks).
  Starting apps at login or with Dine is [ATL-30](../general-todo.md#atl-30), not a multi-app
  stage.
- `[ ]` An app that opens a second window of itself through `NEW_DOCUMENT` or `MULTIPLE_TASK`.

## Docs to update

Once the design is approved, the notes listed in `findings-hosting.md` "Notes that assume one app
per process" change; M8a's import first (registry, no launcher-activity rule, no `System.exit(1)`).
