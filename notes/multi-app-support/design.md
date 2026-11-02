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
- Apps see SDK level 21, but the layer may follow a later Android version's behaviour where that
  is easier or saner (decided; the user: "We don't aim to fully follow sdk 21 - we could use
  features from later sdk if they are easier or more sane").
- All Android data of one install lives under one prefix, as in Wine
  ([Prefix](#prefix-decided)).

## Platform mechanisms (decided)

Each backend uses the real mechanism its OS has for a system feature (alarms, background work,
start at boot, notifications, on-demand start): an iOS alarm where iOS has one, systemd or D-Bus
where Linux has a standard one. Where the OS has none, the feature is off and nothing breaks.
A separate Linux service for what systemd and D-Bus lack is optional, planned on its own at the
lowest priority ([ATL-29](../general-todo.md#atl-29)). The per-feature mappings are
`notes/os-features.md` and `notes/background-tasks.md`.

Starting apps at login or when Dine starts, and enabling or stopping them as services, is service
management: a separate proposal, `notes/service-management/proposal.md`
([ATL-30](../general-todo.md#atl-30)). In the multi-app stages an app starts when it is opened or
called. The user: "this autostart and all will be completely separate from multi-apps changes. On
the multi-app stage "done" for services is when you can manually start microG and start an app
that requires it, and they will work".

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
| hung main thread | a watchdog per app shows Android's wait or close dialog (my call); its limits are measured under `-Xint` in MA3, not Android's fixed ones |
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
  - per-app state for the native libraries whose global state B1's listing shows to differ per
    app, kept per app in their source, not by library copies (my call); ICU and the font caches
    stay one shared instance;
  - shared locks taken through a wrapper that counts the ones each thread holds.
- A failed check ends the app (decided). The build flag `enable-oob-unsafe-recovery`, separate
  from dev and release builds (the user: "a separate flag, not dev vs release"), makes it throw into
  the app instead, to test apps. Proposed: `java.lang.InternalError` naming the address, as HotSpot
  throws for a faulting `Unsafe` access (from memory).
- Faults in code whose locks Dine can't see (decided): on libmalloc's shared zone they end Dine,
  since the shared heap may be corrupt. In Apple's frameworks or ICU on an app's thread they are
  contained; if UIKit's thread or another app's main thread then hangs, Dine ends.
- `abort()` (decided): libmalloc's abort on the app's own zone is contained (the app and its zone
  go); on the shared zone it ends Dine. `std::terminate` and assertions in sqlite or ICU follow
  the rule above. ART's `LOG(FATAL)` follows [Containment](#containment).
- A Java monitor the parked thread holds (decided; the user: "yes, for now"): it stays held; when
  a thread of another app, or of no app, blocks on it, Dine ends. The check sits in ART's contended
  lock paths, which know the owner (`Monitor::Lock`'s `owner_`, the thin-lock owner in
  `Monitor::MonitorEnter`, `monitor.cc:417-470,1100-1135`). Later: an unwind method an object can
  define, so ART releases the lock and undoes the change ([ART-25](../general-todo.md#art-25)).
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
- Background freeze (decided): an app freezes about 10 s after it leaves the screen, as Android 14
  freezes cached apps, unless it asks to run in the background. The user: "if an app explicitly
  asks for background - allow it". What counts as asking (proposed): audio playing, a started or
  foreground service, a held partial `WakeLock`, a running job, a client bound from a running app.
  A call or a delivered event (alarm, broadcast, notification action) thaws the app while it is
  handled.
- Memory pressure (decided): frozen apps drop first, least recently used first, then apps that
  asked to run; the app on screen last. No per-app heap measuring decides the order (Android
  doesn't either).

## Memory control (one-VM, proposed)

Every resource an app holds is owned by its record and counted, so Dine sees each app's footprint,
picks what to drop, and checks that a drop freed it:
- Java heap: live bytes counted per app in ART's allocation and sweep paths, so an app over its
  cap gets an `OutOfMemoryError` on its own allocation, as on Android (my call). A heap walk by
  class loader is the fallback if MA0's probe finds the counting too costly, and serves the leak
  report; per-app allocation spaces are a later option;
- native allocations on the app's threads: a malloc zone per app. Shared native caches (ICU, fonts)
  must allocate from a shared zone, or destroying the app's zone frees memory other apps use;
- threads and stacks, file descriptors, memory mappings, windows and surfaces.

Caps per app (decided; the user: "your proposal is good"): the Java heap, the JNI global table
and the descriptor table are shared, so each gets a cap per app, and the app over its cap is the
one that fails. `Runtime.maxMemory` and `getMemoryClass` report the app's heap cap, since apps size
their caches from them. When a shared total runs out with no app over its cap, Dine drops apps in
the order of [Freeze and drop](#freeze-and-drop-one-vm-proposed) before anyone fails. Needs the live
heap per app (a probe).

No fixed number of live apps (decided; the user: "I think it should be dynamic... Like allocation
dependant?"): apps stay loaded while memory allows, and the drop order frees memory when it runs
short. An app's heap cap is set when the app starts, from the memory available then, and stays
fixed for its life, since apps read `maxMemory` and `getMemoryClass` once to size their caches (my
call). The caps may add up to more than `-Xmx`, since the drop order handles a full shared heap.

Shared limits raised (proposed; the user: "can't we also increase global cap?"):
- JNI globals: `kGlobalsMax` and `kWeakGlobalsMax` (51,200, `java_vm_ext.cc:60-62`) are constants
  in our fork. The index encoding has room for more than 16 bits (`indirect_reference_table.h:
  342-348`); the ceiling is `kMaxTableSizeInBytes`, 128 MB (`indirect_reference_table.cc:39`). The
  table is mapped whole at start (`indirect_reference_table.cc:81-86`), so a larger one costs only
  the pages it touches.
- Descriptors: Dine raises the soft `RLIMIT_NOFILE` to the hard limit at start; nothing raises it
  today. The iOS values are a probe.
- Java heap: `-Xmx` sized from `os_proc_available_memory()` instead of ART's 256 MB default. The
  real ceiling is Dine's iOS memory limit: past it iOS kills all of Dine, with no
  `OutOfMemoryError`. The `com.apple.developer.kernel.increased-memory-limit` entitlement raises
  that limit (iOS knowledge); whether a free account gets it is a probe. A larger footprint also
  gets Dine killed sooner while it is in the background.

## Calls between apps (all backends, proposed)

- No Java object crosses from one app to another. A call into another app is a Parcel run on the
  target app's own binder thread, with no timeout (see "No timeout on sync calls" below); a
  dropped or dead target fails it with `DeadObjectException`. A hung or dropped target can't take
  the caller with it, and nothing outside an app keeps it alive.
- Within one app, a Binder stays a local object (`queryLocalInterface`, `onTransact`), as on
  Android.
- Binder objects inside a Parcel travel as handles; each side keeps a handle table.
- Identity: every call carries the caller's package and virtual uid; `Binder.getCallingUid` and
  `getCallingPid` return them. A package's uid is assigned at install and kept in the registry.
- No package gets special treatment; the user: "no special treatment for microG (system flags or
  whatever)". microG's clients accept a target with a Google or microG signature
  (`findings-apps.md`), so no system flag is needed. Signature spoofing (decided; the user chose
  "B"): an app that requests `android.permission.FAKE_PACKAGE_SIGNATURE` is reported with the
  signature it declares (how it declares it is unchecked here), in place of ATL's list of GMS
  package names (`ATLLoadedApp.play_services`). The install confirmation shows the request, and the
  permission is granted only if the user accepts it there.
- `ATLGStub` (decided, the user took the lean): ATL's fake `com.google.android.gms`, `gsf` and
  `vending` (`FLAG_SYSTEM`, Google's signatures, a `ProviderInstaller` and a Maps creator) become
  preinstalled packages in the registry, as a phone ships Play Services; installing microG
  replaces them. Apps that start without microG today keep starting. Caller checks get real per-call
  identity.

## Registry (all backends, proposed)

- One SQLite database plus an APK store in the prefix (WAL: many readers, one writer). A row per
  package: uid, signatures, components,
  intent filters, provider authorities, metadata, features, label, icon.
- Any app's `PackageInstaller` session, `ACTION_INSTALL_PACKAGE`, or the CLI's `--install` parses
  the APK and writes its row in one transaction. Every app's `PackageManager` reads from it:
  `getInstalledPackages` with flags, `getPackageArchiveInfo`, intent resolution across packages,
  `getLaunchIntentForPackage`, `getPackagesForUid`. The microG-only visibility gate goes.
- Data dirs are keyed by package, which aligns the three identities of an app on Linux.
- On iOS the database is in Application Support and Dine's launcher reads the same rows instead of
  its own `apps` table.
- An APK without a launcher activity installs (extensions); M8a's rule that rejects it goes.

## Prefix (decided)

The user's words: "we need a prefix for all of the android data, like wine does, so we don't
spread it all over the host and can make it simpler in iOS too". The registry, the APK store, every
app's data, caches (today `/tmp/atl_cache/<pkg>`) and shared storage live under it.
- Layout (proposed): Android's paths inside the prefix (`data/app/<pkg>/`, `data/data/<pkg>/`,
  `storage/emulated/0/`), so the paths apps hardcode (`/data/data/<pkg>`, `/sdcard`) map into it
  the way `libc_bio_path_overrides.c` already maps `/storage/emulated/0/`.
- Sockets and locks (proposed): in a runtime dir named after the prefix's device and inode, as
  wineserver names its socket dir, under `$XDG_RUNTIME_DIR`, else `/tmp`; a socket can't live on
  every filesystem a prefix may sit on.
- Linux: the prefix is today's data base (`$ANDROID_APP_DATA_DIR`, else
  `$XDG_DATA_HOME/android_translation_layer`). iOS: it can't stay in Caches, which iOS may purge
  (`findings-hosting.md`).
- Shared storage (decided): one per prefix that every app sees, as Android's `/sdcard`; today each
  app's external storage is a folder in its own data dir. On iOS only the shared storage is visible
  to the host (the Files app, other iOS apps); app data stays private. The user: "only shared seen
  to host (at least on iOS, on linux of course I can go the dine's root and list all files)".

## Linux: the static model (proposed, holes reviewed)

No Dine service runs. The fixed places are the registry above and the prefix's runtime dir:
- A running app listens on `<runtime dir>/<pkg>.sock` and holds `<pkg>.lock` for its whole
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
  that aren't running get only explicit ones, by being started (decided for every backend, as
  Android 8 and later do: "starting all apps on some event is not a good idea, especially on
  desktop").
- Desktop: a `.desktop` entry runs `android-translation-layer --package <pkg>`; a second launch
  connects to the running app instead of booting a second VM.
- Costs against a server: nothing runs while no app runs, so alarms and jobs of a closed app need
  the OS scheduler (systemd user timers) or wait; closed apps miss implicit broadcasts; every app
  exports reference-counted objects for binders passed through Parcels (the biggest unknown).

### Holes in the static model (2026-11-01)

The user answered "ok" to lifetime, start race, activities across apps and binders, and "Yes" to
saved state, which are **decided**; the rest stay proposed.
- Lifetime (decided): closing the window ends the process today (`atl_exit`), the cli build ends
  with its last activity, and an app without a launcher activity exits (`findings-hosting.md`). A
  process started for `bindService` (microG) has no activity. A process lives while it has an
  activity, a started or foreground service, or a bound client, and exits after a short idle grace
  period.
- Saved state across process death (decided): the one-VM code that writes each activity's Bundle
  to a file runs on Linux too. A clean end (the window closed, a crash, SIGTERM at logout) deletes
  the file; a start that finds it restores from it, so an app killed from outside (the OOM killer,
  systemd-oomd) reopens where it was. The gtk build runs the restore path iOS depends on.
- Start race (decided): two clients, or a client and a desktop launch, can both find X's lock free
  and exec X. X takes `X.lock` before it listens; a second X that finds the lock held forwards its
  intent to the first and exits. The spawn lock only saves the double exec. A client that finds the
  lock held but no socket yet retries until a deadline.
- Lock kind: POSIX locks drop on any close of the file; OFD locks (`F_OFD_SETLK`) don't, but
  `F_OFD_GETLK` reports no pid. Lean: an OFD lock for liveness, the holder's pid written into the
  lock file for the `SO_PEERCRED` check.
- Runtime dir: it follows the prefix ([Prefix](#prefix-decided)), so a test run with a temporary
  prefix doesn't reach the user's running apps. A unix socket path holds at most 108 bytes: a short
  hash of the package as the socket name when the path is too long.
- State that system_server keeps across process death: a PendingIntent (a notification, a callback
  held by microG) must fire after its owner exits. Lean: such records are rows in the registry
  database (owner, intent, flags, a generation); `send()` reads the row, starts the owner if needed
  and delivers; cancel deletes the row. What wakes a closed app at a time or at login follows
  [Platform mechanisms](#platform-mechanisms-decided).
- Descriptors in Parcels: `ParcelFileDescriptor` (FileProvider shares, F-Droid's install URI,
  `ContentProvider.openFile`) and `CursorWindow` need descriptors passed with `SCM_RIGHTS`;
  `CursorWindow` on a memfd.
- Binders in Parcels (decided): handles are relative to the connection, so a callback passed to
  the peer needs no new connection. Only a binder owned by a third app needs a connection to its
  owner and a transfer step that keeps a reference until the receiver claims it. The owner keeps
  an object alive while any peer holds a handle and drops a peer's handles when its connection
  closes.
- Activities across apps (decided): a task can't span processes, so an activity of B started by A
  (`startActivityForResult`, a share target) opens in B's own window, transient for A's window
  where the desktop allows it. The result goes back over the connection; it is lost if A's process
  has exited.
- A service app that dies: clients bound with `BIND_AUTO_CREATE` start it again with a backoff and
  reconnect, as Android restarts a bound service.
- An APK replaced while its app runs: the process ends, as on Android, and the new version starts
  on next use. The APK is written under a versioned name and fsynced before the registry row points
  at it; the old file goes after the commit.

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
| One VM per app from K bundled copies of ART as dylibs (own statics, heap, malloc zone; drop resets the copy) | fallback if the drop probes fail: a hard cap of about 3-4 live apps, a full VM boot and boot classes per app (no boot image), the uikit backend's Objective-C classes can't be duplicated, one address space still; the fixed count goes against the decided dynamic one |
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

My calls, stated to the user on 2026-11-02 without objection:
- Saved Bundles on one-VM backends: a system record in the VM plus a file per app in its data dir.
- The registry on iOS when no app runs: the VM starts just to install, so M8a's VM-free APK reader
  may only be needed for labels and icons, or not at all if the rows hold them.
- The cost of an Android main thread per app (8 MiB virtual stack each today): measured in MA2.
- The gtk D-Bus intent API stays. Under [Platform mechanisms](#platform-mechanisms-decided) D-Bus
  activation is how the Linux desktop starts an app from its notification or launcher entry, so it
  becomes the gtk build's entry into the same delivery the sockets use.
- A per-app okhttp pool, and which other shared caches must be split: settled in MA2.
- The running apps list on iOS: one entry per task, as Android's recents; each entry shows its
  app's state (running, frozen, dropped, crashed). An app with two tasks has two entries.
- Hangs on Linux, one process per app: no watchdog; a hung app hangs like any desktop program.
- JIT with an APK's own `.so`: native code of one app can write anywhere, and the
  [Native faults](#native-faults-one-vm-decided) bar no longer holds (`findings-native-faults.md`
  problem 16). Left to the JIT work.

Found on 2026-11-01, proposed leans:
- No timeout on sync calls between apps (decided; the user: "ok, no limit"). Calls that
  legitimately take long: some microG calls do network work before they return (a sign-in token,
  from memory), and opening a file from a cloud documents provider may block for the download
  (from memory). Tachiyomi's extensions make no calls between apps: their code runs inside
  Tachiyomi. When an app's main thread waits on another app past the hang limit, the waited-on app
  is the one marked as not responding, in the wait or close dialog; closing it fails the call and
  the waiting app goes on. A
  background thread waits as long as the target lives. Android's limits on a service's start, a
  broadcast receiver and a provider's publish stay, as hangs of the target. A call to a frozen app
  thaws it; a call to a dropped or dead app fails with `DeadObjectException`.
- Nested calls: a call back into a thread that waits for a reply runs on that thread, as binder
  does, so a callback that needs a monitor the caller holds doesn't deadlock.
- Activities across apps (one-VM): an activity of B started by A sits in A's task and window, as
  on Android; UIKit upcalls take the record of the activity's app, not the window's.
- `android:process` is ignored: every component of a package runs in its one app record or
  process, as ATL does today.
- Trust (decided): apps are trusted. Containment protects apps from each other's bugs, not from a
  malicious app (reflection reaches shared statics; one sandbox on iOS; one OS user and one prefix
  on Linux). File isolation between apps is a later item ([ATL-32](../general-todo.md#atl-32)).
- After iOS ends Dine: the apps that were running show as dropped and are restored from their
  Bundles when opened, not all at start.

Found on 2026-11-02 in `notes/background-tasks.md`, proposed leans:
- iOS background wake-ups: iOS starts Dine without UI when a background `URLSession` finishes (a
  few seconds), for a `BGProcessingTask` run (minutes) and for a notification tap after Dine was
  killed. Dine loads only the app that owns the event, without UI; the other apps stay dropped.
- PendingIntent records on every backend: the registry rows of the Linux holes (owner, intent,
  flags, a generation) hold them on iOS too, so a notification tap or an alarm still reaches its
  app after iOS ended Dine.
