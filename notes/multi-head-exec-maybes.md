# Multiple apps per launch: maybes

Why Dine runs one ATL app per launch, and what running a second app after it, or two apps in
parallel, would take. Several apps in one process is stage M8e in `notes/atl-port.md`, which
needs design first; this note holds the findings for that design. The one-process constraint is
in `notes/meta.md`.

## Why ATL runs once per launch

- `dine_atl_run` refuses in two cases:
  - ATL already ran: `atl already ran in this process: relaunch Dine`;
  - any VM exists, for example after the art screen ran: `atl needs a process without a VM:
    relaunch Dine`.
- ATL binds the app to the VM through statics. `ATLLoadedApp.getPrimaryApplication()` reads
  `atl.app.class.path` once and caches the app in `primary_application`, and `Context`'s static
  initializer configures that app. Both last as long as the VM, so a different app needs a
  different VM while ATL keeps them (see the table below).
- ART allows one runtime per process: `Runtime::Create` fails while `Runtime::instance_` is set,
  whichever thread calls it. There is no VM per thread.
- On Linux each ATL launch is its own process, so the limit never shows. iOS apps can't spawn
  processes (`notes/meta.md`); the phone probe's `fork()` returns `EPERM`.
- The art screen's runs have no such limit: a second run reuses the one VM on an attached thread.

## A second VM

- **Destroy and recreate.** `DestroyJavaVM` deletes the runtime, and `~Runtime` clears `instance_`
  and `WellKnownClasses` so another runtime can start; ART's gtests create and destroy runtimes in
  one process. No test recreates through `JNI_CreateJavaVM` with the `JNI_OnLoad_*` libraries
  loaded and an app running. Untested here. Risks:
  - `DestroyJavaVM` waits for every non-daemon thread to exit (`WaitForOtherNonDaemonThreadsToExit`),
    so one ATL or app thread still running hangs it;
  - libjavacore and libopenjdk are linked into Dine statically and may keep caches from the old
    VM (unverified);
  - ATL's native globals survive;
  - a failure is an ART FATAL, which kills Dine.

  artbridge needs changes too: `gAtlStarted` never resets, `dine_atl_run` refuses once any VM
  state is set, and `CreateVm` pauses forever when creation fails.
- **Two VMs at once.** This needs a second copy of ART's code and statics, for example ART built
  as a renamed dynamic library instead of the static `libart.a`. The copy also needs its own
  libjavacore, libopenjdk and ATL native code, which hold per-VM statics. Untested. Both copies
  would install signal handlers through sigchain, each needs its own heap reservation out of the
  6144 MB the phone probe found (`notes/art-findings.md`), and memory use roughly doubles
  (estimate: two heaps and two copies of the runtime).

## Several apps in one VM

A second app needs no second VM: apps can share one VM, each in its own class loader. This is
the model `notes/meta.md` assumes. iOS doesn't block it; ATL's single primary app and one ART
rule do.

Upstream ATL has groundwork:
- "api-impl: Put applications into their own class loader": `ATLLoadedApp.loadFromPath` gives
  each APK its own `PathClassLoader`, `AssetManager` and `Resources`.
- "api-impl: Implement extra package loading": `ATLLoadedAppManager` loads other installed APKs
  into the running VM as guests of the primary app (MicroG, packages the primary app calls into),
  not as independent apps.

What blocks independent apps side by side:

| Blocker | Where | Needs |
|---|---|---|
| One primary app, read once from `atl.app.class.path`; package visibility and paths key on it | `ATLLoadedApp.primary_application`, `ATLLoadedAppManager` | several primary apps, each with its own paths and visibility |
| App state in statics shared by every app | `Context.this_application` (deprecated; native code reads it in `android_content_Context.c`, `gtk_util.c`, `actions.c`), `Context.package_manager`, `Context.receiverMap` (broadcast receivers) | per-app context |
| One main thread | `Looper.sMainLooper` | a main thread per app, or accepting that a slow app freezes the other |
| One main window (M8e's list) | ATL globals | a window per app |
| One app per host run | `atl_embedded_main` runs one app until its last activity finishes; `dine_atl_run` refuses a second call | an artbridge call that loads another app into the running VM |
| ART opens a native library from one class loader only: `Shared library "<path>" already opened by ClassLoader …; can't open in ClassLoader …` | ART's per-VM library table | two apps can't both load a library of the same name; artbridge's `gLoaders` works around this for its own reruns |

Risks no ATL change removes:
- Crash isolation is as `notes/meta.md` describes; `System.exit` in any app also ends Dine and
  every app.
- No access control between apps. They share one iOS sandbox, so one app's Java code can open
  another app's data folder, and reflection reaches the statics in ATL's shared classes. With JIT,
  where an APK's own `.so` can load, its native code can also read the whole process's memory.
  Fine for trusted apps, wrong for untrusted ones.

## Options

1. One app per launch; relaunch Dine for the next (`tools/dine dbg fresh` in development). No
   work.
2. Destroy and recreate the VM between apps. Sequential only; needs the artbridge changes above,
   every non-daemon thread gone before `DestroyJavaVM`, and the static-state risks to hold up.
3. Several apps in one VM, per the blocker table. The only route to apps in parallel, the largest
   job, and apps get no access control between them.
