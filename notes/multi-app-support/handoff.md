# Multi-app support: session handoff

State of the design work on multi-app support, for the session that continues it. The design is
`design.md`, the roadmap `todo.md`, the facts the `findings-*.md` files.

## Goal

A mapped design and a staged roadmap for running several Android apps at once on every backend,
agreed with the user before any code is written. The deliverable is this directory; no code.

## Current state

Brainstorming (superpowers:brainstorming) is mid-way. Recon and two option comparisons are done,
the preliminary design is written, B1 is decided (option 1, no longer a blocker), and the user has
not yet reviewed the static Linux model or the roadmap.

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
- Restarting all of Dine as the last resort is rejected: "no, apps must not crash other apps under
  any circumstances. So if it means remodeling how we handle exceptions and system exits - let's do
  this. We must do something that would allow us to drop the whole app's state as the last resort"
- "e.g. we must ensure graceful crashes and suspensions of apps, independent of other apps. And
  this will of course differ for pc - on pc the process will just die"
- Confirmed the crash and suspension playback: "for now correct, yes, on pc if a service dies - get
  disconnected, all other too."
- "On ios (and in GENERAL on backends without separate processes) - yes, need to make sure we have
  parking and full app memory control in hand to drop them on demand"
- Linux model: "I think we must avoid turning this into a client-server thing unless other variants
  are worse. What I want is to have a "registry" of apps, for example, native sockets for apps to
  connect to service apps, like micro g. Of if not sockets - maybe some other mechanisms to call
  those and access running services etc. E.g. I want you to try and imagine how this thing could
  work, while being "static". By static I mean, for example, a registy of apks or some central
  utility that makes all apps access it in some particular way. E.g. avoiding a running active
  system service. ONLY if this makes sense on linux"
- "let's record the sigsegv thing as something to resolve, not just a "known limitation". SO it is
  a plan blocker until said otherwise."
- B1 lifted with option 1, tiered containment plus hardening (`design.md` "Native faults"), after
  the user asked whether threads could protect from SIGSEGV and what the checks cost: "I think yes,
  we can lift it with option 1, so let's go with option 1". The bar: only bugs in Dine's own native
  code or in ART may still end Dine.
- Repo rules that apply: don't commit or push in dine-art or dine-atl without asking; both forks
  keep building and passing on Linux; Linux is the fast loop and the reference for the iOS port.

My calls in `design.md`, stated to the user and not contested so far: freeze only under memory
pressure, least recently used first, no per-app heap measuring for the order; a headless test mode
with several apps in one VM; a uid per package assigned at install; APKs without a launcher
activity install; one VM with app records on iOS, K bundled ART copies only as the fallback.

## Done

- `.` [main], nothing committed:
  - `M notes/atl-port.md` (M8e points here)
  - `M notes/bug-tracker.md` (ART-24, socket close wake on Apple)
  - `D notes/multi-head-exec-maybes.md`, moved to `notes/multi-app-support/` with corrections
  - `?? notes/multi-app-support/` (`design.md`, `todo.md`, `handoff.md`, five `findings-*.md`,
    `multi-head-exec-maybes.md`)
- Other sessions have uncommitted work in `.` and `dine-atl`; this task's files are only the ones
  listed above.

## Pending

1. The user reviews the static Linux model in `design.md` (the last question asked was "What's
   wrong or missing?" about it).
2. Go through `design.md` "Open design points" and B1's `[?]` items in `todo.md` with the user,
   one at a time.
3. Brainstorming's builder check on `design.md` (a fresh subagent with the skill's
   `builder-check-prompt.md`), then the user's approval of the design.
4. After approval: superpowers:writing-plans per stage, with the consilium run inside it
   (`~/.claude/rules/consilium.md`), MA0's probes first.
5. After approval: update the notes listed in `findings-hosting.md` "Notes that assume one app per
   process", M8a first.

## Traps and facts found

- `Runtime::Create` refuses a second runtime; one VM per process is fixed (`findings-runtime.md`).
- The default uncaught handler calls `System.exit(10)`: today any uncaught exception ends Dine.
- `Thread.stop` throws; ART's async exception exists but only JVMTI, which isn't built, calls it.
- A suspension that doesn't complete in 10 s is a FATAL, and so is a finalizer over 10 s (exit 2).
- On Apple a thread blocked in a socket read can't be woken by closing it ([ART-24](../bug-tracker.md#art-24)).
- `-D` properties can't change after VM start; `java.io.tmpdir` is one.
- On Apple every native library handle is the main image, so `dlsym` finds every linked `Java_*`.
- The uikit backend's Objective-C classes can exist once per process (bars the dylib-copy fallback
  from duplicating it).
- ATL's guest loading works only for the microG family (visibility gate); Binder is a stub, so AIDL
  calls do nothing even in-process.
- Linux: one app has three unaligned identities (GApplication id, package, APK-file-named data dir).
- `artbridge.cpp:130`'s comment "ART keeps the failed runtime" is wrong: `instance_` is reset.
- `notes/nav-gestures.md` cites `artbridge.cpp:379-452`; the file has 244 lines.
- On Apple, Dine installs no SIGSEGV handler today, and suspend-all spins with no timeout (no
  futexes), so one thread stuck in `kRunnable` hangs every app (`findings-native-faults.md`).
- The cost numbers in `findings-native-faults.md` are from Linux x86_64 under WSL2, not the phone.

## How to resume

1. Read `CLAUDE.md`, `notes/meta.md`, then this file, `design.md`, `todo.md`.
2. The findings files when a question needs a fact; they carry file:line and checked/unchecked tags.
3. Continue the brainstorming skill's conversation from Pending 1: one question per message, play
   back each part before moving on.

## Open questions

- Is the static Linux model acceptable, or is a central `dine-server` needed after all?
- B1's open points (`todo.md`): a failed check ends the app or throws; faults in code whose locks
  Dine can't see (libmalloc, Apple's frameworks) end Dine or follow a narrower rule; held monitors;
  which `abort()` paths can be contained.
- Saved state on Linux across process death: not kept (my proposal) or kept?
- The gtk D-Bus intent API: keep as an adapter or remove?
- Implicit broadcasts to apps that aren't running: deliver (start them) or not?
