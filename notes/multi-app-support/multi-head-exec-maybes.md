# Multiple apps per launch: maybes

Why Dine runs one ATL app per launch, and what running a second app after it, or two apps in
parallel, would take. The first findings for multi-app support: the roadmap is `todo.md` in this
directory, the design `design.md`, later findings the `findings-*.md` files. The one-process
constraint is in `notes/meta.md`. Outcome (2026-11-02): one VM with an app record per app; a
second VM from bundled ART copies is rejected ("too complicated").

## Why one VM per launch

- The first `dine_atl_run` creates ATL's VM; each later one starts its app in that VM. It refuses
  while the first run starts (`atl is still starting, or failed to`) and when the art screen made
  the VM (`atl needs a process without a VM: relaunch Dine`): that VM lacks ATL's class and
  library paths. A package runs once per VM: a second start of it ends with `exited` -1.
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

A second app needs no second VM: apps share one VM, each in its own class loader and app record,
with its own Android main thread and main loop (multi-app MA2b: the cli and embedded hosts, the
headless test mode). This is the model `notes/meta.md` assumes; `multi-app-support/design.md` "App
record" is the design.

Upstream ATL has groundwork:
- "api-impl: Put applications into their own class loader": `ATLLoadedApp.loadFromPath` gives
  each APK its own `PathClassLoader`, `AssetManager` and `Resources`.
- "api-impl: Implement extra package loading": `ATLLoadedAppManager` loads other installed APKs
  into the running VM, each as its own record; a record that no host started has no Application
  (a package context, a service).

What still limits apps side by side is staged in `todo.md`: one task stack per app (MA6), the
Binder stub and guests without `Application.onCreate` (MA7).

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
