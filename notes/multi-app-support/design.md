# Multi-app support: preliminary design

The design for running several Android apps at once on every backend. It is preliminary: the
brainstorming that produces it is not finished and nothing here is approved for building.
Requirements are the user's (their words are quoted in `handoff.md`); everything marked
**proposed** is a recommendation awaiting their review, **decided** marks the user's choices.
Facts come from the findings files (`findings-runtime.md`, `findings-framework.md`,
`findings-hosting.md`, `findings-apps.md`, `findings-native-faults.md`) and the earlier
`multi-head-exec-maybes.md`; iOS constraints are in `notes/meta.md`; stages are in `todo.md`.

## What it is for

- iOS: many Android apps running in parallel inside the one Dine app.
- PC: each app is its own process, but an app can load other apps' code into its process
  (Tachiyomi's extensions) or reach other running apps (one microG serving every app).
- Scenarios:
  1. A market (F-Droid) installs an app; "Open" starts it in a new window.
  2. Tachiyomi installs extensions from its repo and loads them inside itself; no new window.
  3. An app opens a second window of itself (Chrome-style "New window"; Chrome itself can't run,
     `findings-apps.md`).

## Requirements

- No app crashes, hangs or stops another, on any backend.
- Crashes and suspensions are graceful and per app. On PC the app's process dies.
- Under low memory, background apps are frozen and restore their last state when the user returns
  to them, as on Android.
- On backends without separate processes: parking and full control of each app's memory, so any
  app can be dropped on demand as the last resort. Restarting all of Dine is not a last resort.
- On PC, when a service app dies, its clients get disconnected.
- On PC, no running system service unless the alternatives are worse.
- The VM uses threads wherever the platform allows.
- Works on all backends: iOS uikit, Linux gtk, Linux headless.

## Two platform shapes

| | One-VM backends | Process-per-app backends |
|---|---|---|
| Backends | iOS (uikit); headless in a test mode (**proposed**) | Linux gtk and headless |
| An app is | an app record inside the shared VM | an OS process with its own VM |
| An app fails | the layer contains it ([Containment](#containment)) | its process dies |
| Low memory | freeze, then drop | the desktop's job, no freezing (**proposed**) |
| Reaching another app | `ipc` slot, `inproc` backend | `ipc` slot, `unix` backend |
| Starting another app | load it into the VM | exec `android-translation-layer` |

The headless test mode runs several apps in one VM on Linux, so the iOS model is graded in the
fast loop (CLAUDE.md: Linux is the reference for the iOS port).

## App record (one-VM, proposed)

Every app has a record that all its threads carry: a `ThreadGroup` of its own plus a field on ART's
`Thread`. Threads inherit it from their creator; native threads attached through JNI get it from
`JavaVMAttachArgs.group` or from the window or callback they serve. UIKit-thread upcalls attach
with the record of the window's app.

Everything that holds app state today moves into or behind the record:
- ATL: the primary app and its Application, data dir, PackageManager view, providers, receivers,
  shared preferences, main Looper (each app gets its own Android main thread), task stack, window,
  `sys_config` (a copy per app), `LayoutInflater`'s constructor cache (keyed by class, not name),
  the C globals in `findings-framework.md`.
- libcore: default `Locale` and `TimeZone`, the uncaught handler, `CookieHandler`, `ProxySelector`,
  `ResponseCache`, `Authenticator`, the SSL and HttpURLConnection defaults, `NetworkSecurityPolicy`,
  Security providers, the URL and socket factories, tmpdir (the `-Djava.io.tmpdir` goes), `user.dir`
  for relative paths.
- ART: the native library table keyed by (path, loader), which also closes the Apple trap where
  `dlsym` on the main image finds every `Java_*` symbol; target SDK and package name per app.

Shared state that stays shared: interned strings, class metadata of boot classes, the okhttp
connection pool (a per-app pool is open).

## Containment

One-VM backends (**proposed**); on process-per-app backends each row ends the process.

| Failure | Handling |
|---|---|
| uncaught exception | the app's `ThreadGroup.uncaughtException`; replaces `hacky_uncaught_exception_handler`'s `System.exit(10)` |
| `System.exit`, `Runtime.halt`, `Process.killProcess` | caught in Java before `Runtime`'s `shuttingDown` latch; ends the calling app |
| ART FATAL an app reaches through Java: JNI global table full, suspension timeout, `-Xcheck:jni` | turned into an app kill; the suspension timeout becomes a non-fatal return |
| finalizer running over 10 s | a finalizer thread and watchdog per app; the timeout ends that app |
| hung main thread | a watchdog per app (Android's ANR) ends or freezes it |
| SIGSEGV or SIGBUS in native code | ends the app when it is containable, else Dine ([Native faults](#native-faults-one-vm-decided)) |
| ART invariant FATAL that app code can't reach (an ART bug) | ends Dine |

An ended app shows as crashed in Dine's running apps list; the other apps keep running.

## Native faults (one-VM, decided)

The user's choice is option 1 of [B1](todo.md#b1-native-fault-containment), tiered containment.
Threads don't isolate memory, so only some faults can be contained; the facts and the problems are
in `findings-native-faults.md`.
- A handler for SIGSEGV and SIGBUS, registered through sigchain, maps the faulting thread to its
  app. It contains the fault when the thread is an app's thread in `kNative` (a normal JNI native,
  which has released the mutator lock) and holds no shared lock. The thread is parked for good and
  the app is dropped; GC and the other apps go on.
- Every other fault ends Dine: a thread in `kRunnable` (ART's code, `@FastNative` natives), a
  thread that holds a shared lock, a thread that belongs to no app.
- Hardening, so app code can't cause the faults that end Dine:
  - checks on every `Unsafe` and `Memory` raw-address call, reads and writes: the address must lie
    in a region of the calling app;
  - checks on `Unsafe`'s object-plus-offset calls: the offset stays inside the object, and no
    primitive write lands on a reference field;
  - a malloc zone per app;
  - a separate instance per app of each native library with global state;
  - shared locks taken through a wrapper that counts the ones each thread holds.
- What stays Dine-ending: bugs in Dine's own native code or in ART that fault in `kRunnable` or
  corrupt shared memory. The user accepted this as the bar for lifting B1.
- Measured on Linux, the checks add under 0.1% to an interpreted `Unsafe` call when the address
  hits the per-thread region cache and about 7% on a miss; under 1% for a whole app (estimate).

## Freeze and drop (one-VM, proposed)

- Freeze: Dine stops delivering input, messages and callbacks to the app, lets its threads go idle,
  then suspends them with `SuspendThreadByPeer`. Memory stays.
- Drop: the app's activities have saved their state; then an async exception goes into every
  app thread (the JVMTI StopThread closure copied into artbridge), threads are interrupted, every
  socket and file in the app's descriptor ledger is shut down, windows close, and the GC unloads the
  class loader. A thread that still does not stop is parked for good: no CPU, its memory leaks.
- The descriptor ledger and [ART-24](../bug-tracker.md#art-24) are on drop's critical path: idle
  apps wait in blocking socket reads (OkHttp), which closing the socket does not wake on Apple.
- Later escalation: discard a parked thread without unwinding (siglongjmp to its entry
  trampoline, detach), or Mach `thread_suspend`/`thread_terminate`.
- Restore: a frozen app resumes its threads, then `onRestart`/`onResume`. A dropped app is loaded
  again and its activities recreated from their saved Bundles.
- Saved state: `onSaveInstanceState` at `onStop`; the Bundle is held outside the app (as
  system_server holds it) and written to disk, so it also survives iOS ending Dine.
- Policy: freeze only under memory pressure, least recently used first; drop when freezing is not
  enough. No per-app heap measuring decides the order (Android doesn't either).

## Memory control (one-VM, proposed)

Every resource an app holds is owned by its record and counted, so Dine sees each app's footprint,
picks what to drop, and checks that a drop freed it:
- Java heap: attributed by class loader (a heap walk under memory pressure; per-app allocation
  spaces are a later option);
- native allocations on the app's threads: a malloc zone per app. Shared native caches (ICU, fonts)
  must allocate from a shared zone, or destroying the app's zone frees memory other apps use;
- threads and stacks, file descriptors, memory mappings, windows and surfaces.
- `-Xmx` sized from `os_proc_available_memory()` instead of ART's 256 MB default.

## Calls between apps (all backends, proposed)

- No Java object crosses from one app to another. A call into another app is a Parcel run on the
  target app's own binder thread, with a timeout that ends in `DeadObjectException`. A hung or
  dropped target can't take the caller with it, and nothing outside an app keeps it alive.
- Within one app, a Binder stays a local object (`queryLocalInterface`, `onTransact`), as on
  Android.
- Binder objects inside a Parcel travel as handles; each side keeps a handle table.
- Identity: every call carries the caller's package and virtual uid; `Binder.getCallingUid` and
  `getCallingPid` return them. A package's uid is assigned at install and kept in the registry.
- microG: `FLAG_SYSTEM` and a spoofed signature for GmsCore come from the registry; its caller
  checks get real per-call identity.

## Registry (all backends, proposed)

- One SQLite database plus an APK store: `<data>/dine/registry.db` (WAL: many readers, one
  writer) and `<data>/dine/apks/<pkg>/base.apk`. A row per package: uid, signatures, components,
  intent filters, provider authorities, metadata, features, label, icon, a system flag.
- Any app's `PackageInstaller` session, `ACTION_INSTALL_PACKAGE`, or the CLI's `--install` parses
  the APK and writes its row in one transaction. Every app's `PackageManager` reads from it:
  `getInstalledPackages` with flags, `getPackageArchiveInfo`, intent resolution across packages,
  `getLaunchIntentForPackage`, `getPackagesForUid`. The microG-only visibility gate goes.
- Data dirs are keyed by package, which aligns the three identities of an app on Linux.
- On iOS the database is in Application Support and Dine's launcher reads the same rows instead of
  its own `apps` table.
- An APK without a launcher activity installs (extensions); M8a's rule that rejects it goes.

## Linux: the static model (proposed, awaiting review)

No Dine service runs. The fixed places are the registry above and a runtime dir:
- A running app listens on `$XDG_RUNTIME_DIR/dine/<pkg>.sock` and holds `<pkg>.lock` for its whole
  life. The kernel releases the lock when the process dies, so a dead app leaves no stale entry.
- To reach app X: connect to `X.sock`; if X's lock is free, exec `android-translation-layer
  --package X` under a spawn lock, then connect. `startActivity` (and its result), `bindService`,
  provider calls and explicit broadcasts go over that connection as Parcels. A binder passed inside
  a Parcel travels as (owner package, object id); the receiver connects to the owner directly. The
  socket closing is `onServiceDisconnected` and `binderDied`.
- Identity: the peer pid from `SO_PEERCRED`, checked against the holder of `<pkg>.lock` (`F_GETLK`
  reports the holder's pid). All apps run as one OS user, so this guards against bugs, not a
  malicious app. POSIX locks drop when the process closes any descriptor of the lock file: one owner
  per lock file in each process.
- Package events: each running app watches the registry with inotify and delivers
  `PACKAGE_ADDED/REMOVED` to its own receivers. Implicit broadcasts go to every live socket; apps
  that aren't running get only explicit ones, by being started.
- Desktop: a `.desktop` entry runs `android-translation-layer --package <pkg>`; a second launch
  connects to the running app instead of booting a second VM.
- Costs against a server: nothing runs while no app runs, so alarms and jobs of a closed app need
  the OS scheduler (systemd user timers) or wait; closed apps miss implicit broadcasts; every app
  exports reference-counted objects for binders passed through Parcels (the biggest unknown).

## Slots (proposed)

- New `ipc` slot: `inproc` (one VM: a queue to the target app's thread; "start" loads the app) and
  `unix` (the runtime dir; "start" is exec).
- `host`: an app handle in every call and event (`atl_nav_*`, `task_moved`, `exited`), several
  apps per run, starting and ending one app.
- `ui`: a window per task; the uikit backend's Objective-C classes stay one copy in Dine.
- `loop`: descriptor watches for the `unix` backend under both the poll loop (cli) and glib (gtk).

## Options considered

Isolation on iOS:

| Option | Outcome |
|---|---|
| One VM, app records, async-exception drop | **proposed** |
| One VM per app from K bundled copies of ART as dylibs (own statics, heap, malloc zone; drop resets the copy) | fallback if the drop probes fail: a hard cap of about 3-4 live apps, a full VM boot and boot classes per app (no boot image), the uikit backend's Objective-C classes can't be duplicated, one address space still |
| Framework jars loaded per app class loader | rejected: ATL's cached class and method ids become per app, its C globals still need keying, libcore's statics stay shared |
| Discard threads without unwinding (siglongjmp) | kept as the later escalation of drop |
| File-backed per-app arenas, frozen apps hibernated to clean pages | rejected for now: a large ART heap change; the frozen-footprint question stays a probe |
| ART isolates with per-app static storage (MVM style) | rejected: very large and hard to reverse |

Native faults on one-VM backends:

| Option | Outcome |
|---|---|
| Tiered containment plus hardening | **decided** ([Native faults](#native-faults-one-vm-decided)) |
| The same handler without the hardening | rejected: wild `Unsafe` accesses and faults under a shared lock still end Dine |
| A separate ART copy per app (the fallback above) | rejected for faults: still one address space, so stray writes still cross apps |

Reaching other apps on Linux:

| Option | Outcome |
|---|---|
| Static: registry plus runtime dir, peer sockets | **proposed**, per the user's preference |
| Central `dine-server` owning registry, tasks, saved state, broadcast delivery | fallback if the static model fails |
| Per-backend rendezvous (D-Bus on gtk, sockets on cli) | rejected: gtk and cli drift, and headless tests only the cli path |
| Master process that boots the VM once and forks a child per app | rejected for now: forking a booted ART is untested and the master's death ends every app; its start-up saving under `-Xint` may come back |
| Lookup daemon plus peer sockets | its peer sockets are in the static model; lock files replace the daemon |
| Marshal every call, even inside one VM | its rule is the one in [Calls between apps](#calls-between-apps-all-backends-proposed) |

## Open design points

- Where saved Bundles live on one-VM backends: a system record in the VM plus a file per app in its
  data dir (my lean).
- Whether Linux keeps saved state across process death (proposed: no; the desktop doesn't kill apps
  for memory).
- Who writes the registry on iOS when no app runs: the VM can start just to install, so M8a's
  VM-free APK reader may only be needed for labels and icons, or not at all if the rows hold them.
- Cost of an Android main thread per app (8 MiB virtual stack each today).
- Implicit broadcasts to apps that aren't running: SDK 21 apps may expect manifest receivers to
  fire.
- The gtk D-Bus intent API: keep it as an adapter for desktop callers or remove it.
- A per-app okhttp pool, and which other shared caches must be split.
- JIT with an APK's own `.so`: native code of one app can write anywhere, and the
  [Native faults](#native-faults-one-vm-decided) bar no longer holds (`findings-native-faults.md`
  problem 16).
