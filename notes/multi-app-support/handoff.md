# Multi-app support: session handoff

State of the design work on multi-app support, for the session that continues it. The design is
`design.md`, the roadmap `todo.md`, the facts the `findings-*.md` files.

## Goal

A mapped design and a staged roadmap for running several Android apps at once on every backend,
agreed with the user before any code is written. The deliverable is this directory; no code.

## Current state

Brainstorming (superpowers:brainstorming) mid-way; the last question asked, saved state on Linux
(Open questions 1), is unanswered.

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

My calls in `design.md`, not contested: freeze only under memory pressure (being asked, Pending
1), least recently used first; a headless test mode with several apps in one VM; a uid per package
at install; APKs without a launcher activity install; one VM with app records on iOS, K bundled ART
copies only as the fallback; `supervisor` as the service-management slot's name; the D-Bus intent
API kept as the gtk build's desktop entry point.

## Done

- `.` [main], uncommitted (the directory itself is in `da6a8bf`):
  - `M notes/multi-app-support/design.md`, `todo.md`, `handoff.md`, `findings-framework.md`,
    `findings-native-faults.md`, `findings-runtime.md`
  - `M notes/background-processes.md` (AlarmKit row, question 9)
  - `M notes/general-todo.md` (ATL-29, ATL-30)
  - `M notes/decisions.md` (later-SDK behaviour line in the `SDK_INT` entry)
  - `?? notes/service-management/proposal.md`
- `?? dine-atl/subprojects/graphene/.meson-subproject-wrap-hash.txt` is not this task's.

## Pending

1. Get the answer to Open questions 1 and record it in `design.md` and `todo.md` MA5. Then ask, one
   per message: freezing background apps for CPU on the phone (Android 14 freezes cached apps after
   10 s); per-app budgets for shared resources (Java heap, JNI globals, descriptors) with per-app
   `maxMemory` and `getMemoryClass`; B1's four `[?]` points; signature spoofing through
   `FAKE_PACKAGE_SIGNATURE` instead of ATL's GMS package list (stated, not answered).
2. The rest of `design.md` "Open design points": state each lean, ask only where the user's answer
   changes what gets built.
3. Brainstorming's builder check on `design.md` (a fresh subagent with the skill's
   `builder-check-prompt.md`), then the user's approval of the design and the roadmap.
4. After approval: superpowers:writing-plans per stage, with the consilium inside it
   (`~/.claude/rules/consilium.md`), MA0's probes first.
5. After approval: update the notes in `findings-hosting.md` "Notes that assume one app per
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
3. Continue the brainstorming skill's conversation: Open questions 1 is waiting for the user, then
   Pending 1. The user answers several numbered questions at once, by points.

## Open questions

1. Saved state on Linux. Asked: "If something outside the app ends a Linux app's process (not you
   closing it, and not a crash), should the app reopen where it was the next time you start it?"
   Options: yes (my lean: the iOS code writes the Bundle file; a clean end deletes it; a start that
   finds it restores) or no (always start fresh). Details in `design.md` "Open design points".
2. B1's points (`todo.md` B1): a failed check ends the app or throws; faults in code whose locks
   Dine can't see (libmalloc, Apple's frameworks; ART's own mutexes are visible) end Dine or follow
   a narrower rule; held monitors; which `abort()` paths can be contained.
3. Background apps on the phone: freeze only under memory pressure, or after a delay unless they
   play audio, run a foreground service or serve a running app.
