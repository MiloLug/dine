# Multi-app support: session handoff

State of the design work on multi-app support, for the session that continues it. The design is
`design.md`, the roadmap `todo.md`, the facts the `findings-*.md` files.

## Goal

A mapped design and a staged roadmap for running several Android apps at once on every backend,
agreed with the user before any code is written. The deliverable is this directory; no code.

## Current state

Brainstorming (superpowers:brainstorming): the builder check ran on 2026-11-02 and its questions
are answered; the user's approval of the design and the roadmap is asked, not given.

## Decisions and rules (the user's words)

- "I want it to be really multi app, and the VM must use threads IF possible in runtime."
- "It should work for all platforms (backends)."
- iOS: "it will be able to run many apps in parallel in one ios app."
- PC: "Apps still run per process, but some apps can load/create/run other apps in their process or
  have access to other processes, to be able to use single microg for example. Also there are apps
  like Tachiyomi (https://github.com/jobobby04/tachiyomisy) that install a lot of small apps-libs to
  use inside for functionality extention."
- Scenarios: "1: I open a market (like the foss or whatever), install an app. Then I click on the
  app and it opens in a new window." "2: I download tachiyomi and install internal apps from the
  repo. Nothing opens new windows, they are "inside job" for this app." "3: Chrome for android wants
  to open a new window (on android it can). It opens fine..."
- Low memory: "I owuld expect for some apps to get "frozen" - like nothing happens there and they
  try their best to reinitiate the last state switching to them, like on android when low mem"
- No Dine restart as last resort: "no, apps must not crash other apps under any circumstances. So
  if it means remodeling how we handle exceptions and system exits - let's do this. We must do
  something that would allow us to drop the whole app's state as the last resort"; "on pc the
  process will just die"; "on pc if a service dies - get disconnected, all other too."
- "On ios (and in GENERAL on backends without separate processes) - yes, need to make sure we have
  parking and full app memory control in hand to drop them on demand"
- Linux: "I think we must avoid turning this into a client-server thing unless other variants are
  worse." A "static" model: "a registy of apks or some central utility that makes all apps access
  it in some particular way. E.g. avoiding a running active system service. ONLY if this makes
  sense on linux". Its holes (`design.md`): "ok" to lifetime, activities across apps, start race,
  binders inside Parcels.
- Prefix: "yep, we need a prefix for all of the android data, like wine does, so we don't spread it
  all over the host and can make it simpler in iOS too (especially if we were to access android
  files from ios apps)". Shared storage: "yes, only shared seen to host (at least on iOS, on linux
  of course I can go the dine's root and list all files)".
- Platform mechanisms: "So on each system we must exercise it to its fullest. If iOS allows
  "standard" alarms - we do them for real." A Linux alarm service "should be OPTIONAL. E.g. if it
  isn't run - nothing breaks, alarms just go off" (read as: those alarms don't fire); "if linux
  allows for alarms, for example, with some systemd or dbus or whatever "standard" alarm service -
  we must use it." A separate Linux server goes "as super-low priority to the general todo"
  (ATL-29).
- Saved state on Linux: "Yes" to "If something outside the app ends a Linux app's process (not you
  closing it, and not a crash), should the app reopen where it was the next time you start it?"
  (the Bundle files of the one-VM backends; a clean end deletes them).
- Call timeouts: "ok, no limit" (after: "i'd not go the android way and add some timeout").
- Start at boot: "no special treatment for microG (system flags or whatever)"; service management
  (a slot: systemd `--user` on Linux, an internal manager on iOS, a UI) "goes TOO FAR. For now just
  write it down as a proposal in notes/service-management/proposal.md and link to it", "completely
  separate from multi-apps changes. On the multi-app stage "done" for services is when you can
  manually start microG and start an app that requires it, and they will work" (ATL-30).
- "We don't aim to fully follow sdk 21 - we could use features from later sdk if they are easier
  or more sane. So yes, starting all apps on some event is not a good idea, especially on desktop":
  implicit broadcasts reach running apps only.
- B1 (native faults) was a blocker ("SO it is a plan blocker until said otherwise"), lifted with
  option 1: "I think yes, we can lift it with option 1, so let's go with option 1". The bar: only
  bugs in Dine's own native code or in ART may still end Dine.
- Repo rules: don't commit or push in dine-art or dine-atl without asking; both forks keep building
  and passing on Linux; Linux is the fast loop and the reference for the iOS port.
- Background apps on the phone: "B. Of course, if an app explicitly asks for background - allow
  it" (B: freeze about 10 s after leaving the screen unless the app plays audio, runs a service or
  is bound by a running app).
- Memory: "your proposal is good" (a cap per app on the Java heap, JNI globals and descriptors;
  the drop order of `design.md` "Freeze and drop"), then "can't we also increase global cap?"
  (answered in `design.md` "Memory control", recorded as proposed).
- Signature spoofing: "B" (`FAKE_PACKAGE_SIGNATURE` granted only after the user accepts it in the
  install confirmation).
- B1's points: "1 - let's add a comptime switch for this, so we could build dev builds with error
  handling instead of crash - to test apps. But I mean a separate flag, not dev vs release.
  something like enable-oob-unsafe-recovery"; "2 - agree" (unknown locks); "4 - agree"
  (`abort()`). On monitors (3), after the explanation and a changed lean (Dine ends only when
  another app blocks on the held monitor): "yes, for now", plus "to the general todo add: think
  about extending java for "standard" unwind method for shared objects after a thread crash"
  (ART-25, low priority).
- Trust: "let's add think about file isolation in general todo for much later" (apps are trusted;
  ATL-32).
- `notes/background-tasks.md` edits: "yes, and rename background-processes to background-tasks, to
  not confuse with processes and services" (renamed; references updated).
- Builder check answers: stage order "I will go with MA0 + M6a, then MA1, MA2, M6b. I already
  spelled out notes/steps.md, so you now just have to add LITTLE updates to those tasks so they
  know about each other (don't change steps)" (one-line cross-links in M6a, M6b, MA0-MA2; the
  user's `notes/steps.md` is untouched and untracked); live apps "I think it should be dynamic...
  Like allocation dependant?" (no fixed count); `ATLGStub` "your lean" (preinstalled registry
  rows); "on others agree" (the builder-check calls below).

My calls in `design.md`, not contested: what counts as asking to run in the background (the list
adds a partial `WakeLock` and a running job); a thaw for calls and delivered events;
`InternalError` as the exception under `enable-oob-unsafe-recovery`; a headless test mode with
several apps in one VM; a uid per package at install; APKs without a launcher activity install;
one VM with app records on iOS, K bundled ART copies only as the fallback; `supervisor` as the
service-management slot's name; the D-Bus intent API kept as the gtk build's desktop entry point;
the rest of "Open design points" (stated to the user 2026-11-02, no objection). From the builder
check (2026-11-02, the user: "on others agree"): the heap cap set at an app's start from the memory
available then; the wait or close dialog for a hung app on one-VM backends, its limits measured
under `-Xint`, no watchdog on Linux; `OutOfMemoryError` on the app's own allocation through per-app
live-byte counting (heap walk as the fallback); the heap caps may add up to more than `-Xmx`;
per-app state only for native libraries whose state differs per app, in their source, ICU and font
caches shared; one running apps list entry per task; the drop probes' pass rule (`todo.md` MA0); the
uncovered design items as tasks in MA1, MA7 and MA8.

## Done

- `.` [main], uncommitted (the directory itself is in `da6a8bf`):
  - `M notes/multi-app-support/design.md`, `todo.md`, `handoff.md`, `findings-framework.md`,
    `findings-native-faults.md`, `findings-runtime.md`
  - `notes/background-processes.md` renamed to `notes/background-tasks.md` (plain `mv`, not
    staged), questions 7 and 8; references in 6 notes
  - `M notes/general-todo.md` (ART-25, ATL-32)
  - `M notes/decisions.md` (later-SDK behaviour line in the `SDK_INT` entry)
  - `?? notes/service-management/proposal.md`
- `?? dine-atl/subprojects/graphene/.meson-subproject-wrap-hash.txt` is not this task's.

## Pending

1. The user's approval of `design.md` and `todo.md` (a plain yes), asked 2026-11-02.
2. After approval: superpowers:writing-plans per stage, with the consilium inside it
   (`~/.claude/rules/consilium.md`), MA0's probes first.
3. After approval: update the notes in `findings-hosting.md` "Notes that assume one app per
   process", M8a first.

## Traps and facts found

- `Runtime::Create` refuses a second runtime; one VM per process is fixed (`findings-runtime.md`).
- The default uncaught handler calls `System.exit(10)`: today any uncaught exception ends Dine.
- `Thread.stop` throws; ART's async exception exists but only JVMTI, which isn't built, calls it.
- A suspension that doesn't complete in 10 s is a FATAL, and so is a finalizer over 10 s (exit 2).
- On Apple a thread blocked in a socket read can't be woken by closing it
  ([ART-24](../bug-tracker.md#art-24)).
- On Apple every native library handle is the main image, so `dlsym` finds every linked `Java_*`.
- Release ART records each mutex a thread holds (`Thread::GetHeldMutex`), monitors excepted.
- OOME lands on the allocating thread, whichever app filled the heap; `Runtime.maxMemory` is
  VM-wide; ATL's `getMemoryClass` is a fixed 20.
- ATL fakes the Google signature by package name (`ATLLoadedApp.play_services`), and its
  `getLaunchIntentForPackage` sets no `FLAG_ACTIVITY_NEW_TASK`.
- iOS keeps Dine's ATL data in Caches, which iOS may purge.
- Linux: one app has three unaligned identities (GApplication id, package, APK-file-named data dir).
- `artbridge.cpp:130`'s comment "ART keeps the failed runtime" is wrong: `instance_` is reset;
  `notes/nav-gestures.md` cites `artbridge.cpp:379-452`, the file has 244 lines.
- The cost numbers in `findings-native-faults.md` are from Linux x86_64 under WSL2, not the phone.
- The systemd facts in `notes/service-management/proposal.md` come from the man pages of systemd
  262; nothing was run.

## How to resume

1. Read `CLAUDE.md`, `notes/meta.md`, then this file, `design.md`, `todo.md`.
2. The findings files when a question needs a fact; they carry file:line and checked/unchecked tags.
3. Continue with Pending 1. The user answers several numbered questions at once, by points.

## Open questions

None open; approval pending (Pending 1).
