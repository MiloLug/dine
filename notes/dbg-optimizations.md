# Debugger optimizations

## UI through the in-app debug agent (2026-10-19)

Nine `dine-debugger` transcripts: 62% of wall time was model turns (3529 s vs 2115 s of tools).
Per fresh process the tools paid attach (14–26 s), lldb's first expression (~5.6 s), the
`dbg-actions.mm` define (~4 s), and 2–4 s per `wait --ui` poll, whose host AX inspector walk
(`developer accessibility list-items`) also highlighted every element on the phone.

`native/dev/dbgagent` (linked into Dine's dev builds, started by `DINE_DBG_AGENT_PORT` from `ios launch`) answers
`ls`/`tap`/`back`/`settle` over usbmux, so UI work needs neither lldb nor the inspector. Measured
on the phone (quickack on):
- agent `ls` 8–78 ms raw, `dbg ui ls` ~0.15 s; `ui tap`/`ui back` 0.6–1.0 s including the settle
  wait; a tap into a breakpoint returns the stop in 0.34 s.
- `dbg smoke` (hello, probe, atl demo + looper, art run hello/jni args): 12 s; with `--network`
  (run https) 15 s. Agent-driven runs of the same checks took 10–70 min.
- in-process pymobiledevice3 instead of a CLI process per call: `ios launch` 1.5–1.7 s (was
  2.5–3 s), apps list 0.29 s, OS version 0.15 s, screenshot 0.48 s.
- Attach, fresh server, three configs: default 14.9 s, `target.preload-symbols false` 14.5 s,
  `symbols.load-on-demand true` 14.5 s: no knob shipped. First Swift `po` after the attach:
  15.1 / 9.7 / 10.8 s.
- One target per server: the next process attaches in 3.3 s (a new target per pid: 3.6 s), with
  breakpoints kept, so the per-pid target and its breakpoint carry-over were dropped.

After a phone reboot with no host AX client since boot, the walk still sees every SwiftUI label: the
agent needs no accessibility switch.

## lldb `--top-level` definitions (2026-10-18)

The previous UI path compiled `tools/dbg-actions.mm` into each process with
`expression --top-level`: the first UI action per process took ~10 s (define ~4 s), later ones
0.37–0.47 s, and the first action after a reattach ~5.6 s (lldb's first expression).

lldb `--top-level` behavior (ObjC++, lldb 21 swiftlang):
- A function whose body uses `[obj msg]` compiles, but later expressions can't see it
  (`use of undeclared identifier`). Declaring it in the call's prefix
  (`SBExpressionOptions.SetPrefix`) links the call to the code already in the app.
- Later expressions do see functions without message sends, and calls re-emit their bodies. A
  `static` used in such a body fails to link (`Couldn't look up symbols: __ZL…`).
- Definitions belong to the lldb target and can't be redefined (`redefinition of …`). Their
  globals keep the first process's addresses (EXC_BAD_ACCESS after a relaunch), so attaching to
  another process creates a new target.
- `nil` resolves to a symbol named `nil` (`void *`), not to a null pointer.

## Note for the future: lldb index cache (~5 s per attach)

Not actionable now, just recorded (2026-10-18).

- `symbols.enable-lldb-index-cache` would cache the parsed symbol tables of the ~1400 system
  dylibs and save ~5 s of every attach. It's off because, with a warm cache, attach segfaults:
  `ConstString(char const*)` ← `Symbol::ResolveReExportedSymbol` ← `AppleObjCTrampolineHandler`
  (3/3 runs, swift-bin 6.4.1, lldb `21.0.0` swiftlang).
- Cause: lldb stored a re-export symbol's target name as a raw pointer into its own memory. A
  symtab loaded from the cache carries that pointer from an old session. swiftlang PR #13223
  (`swift/release/6.4.x`, 2026-06-25) made the ObjC trampoline handler resolve `objc_msgSend`
  through re-exports, which reaches the stale pointer during attach.
- Fixed upstream in `38d1460c57` (#213356, 2026-08-13: stores the name, bumps the cache format)
  and `8df22c7dc7` (#228266, 2026-10-05: also saves the target binary). swiftlang
  cherry-picked both into `stable/23.x` (PRs #13944, #14589) and `next`; no 6.4 branch has them.
- Versions on 2026-10-18: Swift 6.4.1 (newest release) is on LLVM 21; LLVM 23.1.3 is the newest
  release and `main` is 24. Swift freezes an LLVM branch per release line, so the fix arrives
  with the first Swift release built on `stable/23.x` (and its matching Xcode, see CLAUDE.md
  version coupling).
- Then: enable the cache in `ios.lldb_memory_cmds()` (path under `out/`), attach twice (fill,
  then use it) and check the second attach doesn't crash.
