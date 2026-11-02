# Multiple apps per launch: maybes

Why Dine runs one ATL app per launch, and what running a second app after it, or two apps in
parallel, would take. The first findings for multi-app support: the roadmap is `todo.md` in this
directory, the design `design.md`, later findings the `findings-*.md` files. The one-process
constraint is in `notes/meta.md`. Outcome (2026-11-02): one VM with an app record per app; a
second VM from bundled ART copies is rejected ("too complicated").

## Why ATL runs once per launch

- `dine_atl_run` refuses in two cases:
  - ATL already ran: `atl already ran in this process: relaunch Dine`;
  - any VM exists, for example after the art screen ran: `atl needs a process without a VM:
    relaunch Dine`.
- ATL refuses a second start on its own too (`started` in the embedded host's
  `atl_embedded_vm_options`), and the cfrunloop main loop's quit flag is never cleared.
- ATL keeps each app's state in its app record (`notes/multi-app-support/design.md` "App
  record"); what still makes one VM run one app is the table below.
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

A second app needs no second VM: apps can share one VM, each in its own class loader and app
record. This is the model `notes/meta.md` assumes. iOS doesn't block it; ATL's one main loop and
ART's one runtime per process shape how (multi-app MA2b).

Upstream ATL has groundwork:
- "api-impl: Put applications into their own class loader": `ATLLoadedApp.loadFromPath` gives
  each APK its own `PathClassLoader`, `AssetManager` and `Resources`.
- "api-impl: Implement extra package loading": `ATLLoadedAppManager` loads other installed APKs
  into the running VM, each as its own record; a record that no host started has no Application
  (a package context, a service).

What blocks independent apps side by side:

| Blocker | Where | Needs |
|---|---|---|
| One main loop per process | the loop slot's `loop_main_*` | a main thread and loop per app (MA2b) |
| A second start refused | `started` in the embedded host, `dine_atl_run` | starts per app handle (MA2b) |
| One app per host run | `atl_embedded_main` runs one app until its last activity finishes; `dine_atl_run` refuses a second call | an artbridge call that loads another app into the running VM |
| ART opens a native library from one class loader only: `Shared library "<path>" already opened by ClassLoader …; can't open in ClassLoader …` | ART's per-VM library table | two apps can't both load a library of the same name; artbridge's `gLoaders` works around this for its own reruns |

More blockers (the layout inflater cache, preferences, the shared data dir and `Configuration`,
the Binder stub, guests without `Application.onCreate`, one task stack) are in
`findings-framework.md`.

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
