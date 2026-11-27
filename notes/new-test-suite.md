# New test suite: interpreter tests, Dine-app tests, tests with no UI

Stages that split Dine's tests three ways:
- the interpreter suite: Android apps on ATL and ART, one scenario format on headless, gtk and the phone;
- the Dine-app smoke: Dine's own UI on the phone;
- tests started with no UI at all.

They also give headless a `tools/dine dbg` target. The order against the other stages is
`notes/steps.md`. The suite map is `tests/README.md`, the grading rules are `tests/harness/README.md`
"Baselines", and the phone runner's design is `notes/atl-port.md` "Tests". Defects found on the way
get codes in `notes/bug-tracker.md`, other work in `notes/general-todo.md`. Each stage starts with
its plan (superpowers:writing-plans with the consilium).

Task markers:
- `[ ]` open;
- `[?]` a decision is needed first;
- `[x]` done.

## Stages

| Stage | Scope | Targets | State |
|---|---|---|---|
| [TS1](#ts1-format-runner-split) | the scenario format, the runner, the split | headless | planned |
| [TS2](#ts2-headless-and-gtk) | headless and gtk targets, headless `dbg` target; the `run-*.sh` scripts and `linux smoke`'s gtk checks ported | headless, gtk | planned |
| [TS3](#ts3-dines-control-and-the-ios-target) | Dine's compiled-in control, the iOS target; `dbg smoke`'s `atl-*` scenarios ported | iOS | planned |
| [TS4](#ts4-the-dine-app-smoke) | the Dine-app smoke | iOS | planned |
| [TS5](#ts5-tests-with-no-ui) | tests started with no UI: hello, the probe, ART | iOS | planned |

Order: by number; TS4 and TS5 need TS3's control. They come before M7a: item 1 of
`notes/os-features.md` plans M7's runners as `run-os-features.sh`, `linux smoke os-features` and
`dbg smoke atl-os-features`, and they are written in this suite instead.

## Why

- Headless's `-c` drives scripts and agents, not people. There is no screen, positions come from
  a `dump`, and a drag is touch lines with coordinates read off the dump. Each event is
  timestamped when ATL delivers it, so the script's speed sets a fling's or a long press's timing.
  `tap <text>` matches a text node's exact text whether it is inside the window or not
  ([ATL-186](bug-tracker.md#atl-186)). `tools/dine dbg` has no headless target.
- An interpreter check is written four ways:
  - the `run-*.sh` scripts: bash, each output line checked in order;
  - `linux smoke`'s gtk checks: Python sessions over the gtk agent;
  - `dbg smoke`'s scenario tables, on the phone;
  - the graded suites: framework, apps, package.

  Only the graded suites have `expectations/`.
- `dbg smoke`'s `atl-*` scenarios reach an APK through Dine's launcher UI (the `atl` tile,
  `Recent apps`, `back to app`) and check the launcher (`Add App`, `nav: launcher root`). A
  launcher change fails an interpreter check, and a tile off the screen can't be started
  ([TOOL-15](general-todo.md#tool-15)).

## Decided

- Two smokes, almost fully apart:
  - Dine as an app: the launcher, edge gestures, the apps list, Dine's own screens, driven
    through its UI on the phone;
  - Dine as the interpreter: Android apps on ATL and ART.
- An interpreter test starts its APK directly and triggers the system actions directly: back,
  minimize, and the return from minimize. UI automation stays inside the app's own views: no
  launcher walk, no Home button.
- Home is the outside system minimizing the app. The verb is minimize on every target, headless
  included (its `home` today).
- On the phone the system Android sees is Dine. Start, back, minimize and the return run Dine's
  own path: the code the atl tile, the gestures and the apps list call. The Dine-to-ATL glue stays
  under test.
- The phone's triggers are compiled into the dev build and answer over usbmux, as the uidrive
  agent does. Nothing is sent through `dbg` or lldb at run time: that is too slow.
- Tests that need no UI (ART's, the probe, hello's natives) are started directly, and their results
  are read from the log.
- The `run-*.sh` scripts become scenarios of the graded suite, and headless gets a `dbg` target.
- The interpreter suite is graded like the Linux suites on every target, the phone included. Each
  build has its own `expectations/` file, and a regression or a listed test that didn't run fails
  the run.

## Proposed, not confirmed

- One scenario format and one runner for every target.
  - A scenario is shared across targets when the APK is its subject.
  - A scenario about the host names its one target: exact insets, size, 480 dpi, `-b`, Dine's
    containers.
  - A verb its target lacks fails the scenario when it loads; it is never skipped.
- A check for "these lines, in this order, with no other line of those kinds between". The
  `run-*.sh` checks need it: `run-nav.sh` checks its lifecycle, frame and insets lines that way.
- The verbs are named `back`, `minimize` and `restore`. Headless's `front` becomes `restore`.
- Values the phone can't fix are patterns there: insets in px at 3x, a window size. Headless checks
  the exact values it sent.

## Today's checks by kind

| Kind | Today | Targets |
|---|---|---|
| interpreter | `linux smoke` demo, demo-480, looper, dialog, nav, crash, views, widgets, lists, controls, text, pan, draw, frames, windows, keyboard, config (the `run-*.sh` scripts in `dine-atl/tests/headless/`) | headless |
| interpreter | `linux smoke` gd, gd-package, dialog-gtk, views-gtk, draw-gtk, windows-gtk, input-gtk, back-gtk, text-gtk | gtk |
| interpreter | `dbg smoke`'s 30 `atl-*` scenarios; `touch`'s `lists` tap and scroll | iOS |
| Dine app | `dbg smoke` `touch` (a finger tap on `hello++`, the back swipe), `lldb` (the debug server on Dine); no launcher test ([DINE-15](general-todo.md#dine-15)) | iOS |
| no UI | `dbg smoke` `hello`, `probe`, `art` (seven authored runtime tests, [TOOL-14](general-todo.md#tool-14)) | iOS |
| no UI | `linux smoke loop` (meson tests of the loop slot) | Linux |

## The verbs today

| Verb | headless (`-c`) | gtk (gtk agent) | iOS |
|---|---|---|---|
| start an APK | the process with `-l <activity>` | the process with `-l <activity>` | the `atl` screen's tile |
| back | `back` | `back` | the `Back` accessibility action (`navigator.back()`) |
| minimize | `home` | none | the `Home` accessibility action (`navigator.home()`) |
| restore | `front` | none | `Recent apps`, then `back to app`; or the app's tile again |
| find a view | `dump`, `tap <text>` | `ls`, `at`, `activate` | `ls`, `activate` |
| touch | `touch down\|move\|up\|cancel` | `touch`; `dbg ui` on gtk doesn't offer it ([TOOL-28](general-todo.md#tool-28)) | `touch`, `gesture` |
| keys, text | `key`, `text …` | `key`, `insert` | `key`, `insert` |
| host state | `insets`, `size`, `night`, `-d`, `-b`, `answer` | scripted dialog answers (`ATL_DIALOG_ANSWERS`) | `appearance` |
| output | stdout | stdout | the syslog, through the debug server |

## TS1: format, runner, split

- `[ ]` The scenario format: a start, the system verbs, input, waits, the ordered-lines check,
  view-tree and display-list compares against goldens, and the scenario's targets.
  - `[?]` Python data like `dbg smoke`'s tables, or files of their own.
- `[ ]` The runner in `tests/harness`, driving headless through today's `-c`. It is graded by
  `expect.settle` with an expectations file per build: `linux-x86_64-headless`,
  `linux-x86_64-gtk` and `ios-arm64-uikit`, the names `notes/atl-port.md` "Tests" sets. It gets a
  `tools/dine test` command.
  - `[?]` The suite's name, and the repo its scenarios live in. A suite lives in the repo that owns
    the code it tests, and the test APKs are dine-atl's (`dine-atl/tests/headless/` `crash/`,
    `dialog/`, `looper/`, `nav/`, `views/`, `widgets/`, `windows/`).
- `[ ]` Each row of [Today's checks by kind](#todays-checks-by-kind) gets its destination: a suite
  and its targets, or its removal.
  - `[?]` Whether the apps suite (`tests/android-compat/apps/`) joins the interpreter suite.
- Done when: one `run-*.sh` check runs as a graded scenario on headless, and it fails with the
  line it guards reverted.

## TS2: headless and gtk

- `[ ]` The headless target: every verb of [The verbs today](#the-verbs-today) over `-c`. The cli
  host's `home` becomes `minimize`.
  - `[?]` `-c` stays the wire, or a socket like the gtk agent's.
- `[ ]` A `dbg` target `headless`: `dbg start-server --target headless --app <apk>` and `dbg ui`
  on it, for triage like M6c's through dine-peek and dine-debugger. It shares one driver with the
  suite's headless target.
  - `[?]` Whether [ATL-186](bug-tracker.md#atl-186) is fixed here.
- `[ ]` The gtk target, from `tools/py/dine/gtkdrive.py`.
  - `[?]` Whether [TOOL-28](general-todo.md#tool-28) is fixed here.
- `[ ]` Port the `run-*.sh` checks and `linux smoke`'s gtk checks. A ported check counts only
  after a run where it fails with the line it guards reverted or mutated. Then the scripts,
  `common.sh` and their `linux smoke` entries are removed.
  - `[?]` What `linux smoke` keeps (`loop`).
- Done when:
  - every check the scripts and the gtk smoke make runs as a graded scenario;
  - `dbg ui` drives a real APK on headless.

## TS3: Dine's control and the iOS target

- `[ ]` The control in Dine's dev build (`apps/Dine/Sources/Dine/Dev/`, `#if DEBUG`). It starts an
  APK, at an activity when one is given, through the code the atl screen's tile runs. Back,
  minimize and restore go through the navigator entry points that the gestures and the apps list
  call. A release build leaves it out, so it gets a `DEV_MARKERS` entry in `tools/py/dine/ios.py`.
  - `[?]` Verbs an app adds to uidrive's port, or a port of Dine's own.
- `[ ]` The iOS target: the control, uidrive for input, and the syslog through the debug server for
  output.
- `[ ]` Port `dbg smoke`'s `atl-*` scenarios and `touch`'s lists part. They stop walking the atl
  screen and stop checking the launcher.
  - `[?]` `atl-two-apps` switches apps through Home and the tiles. With start, minimize and restore
    as verbs it fits the interpreter suite.
- `[ ]` The `ios-arm64-uikit` expectations.
- Done when: the ported scenarios run graded on the phone, each started with no UI step in Dine.

## TS4: the Dine-app smoke

- `[ ]` `dbg smoke` keeps Dine's own checks: `touch`'s tap and back swipe, and `lldb`. Then it gains
  the edge gestures of `notes/nav-gestures.md`, the apps list and the launcher
  ([DINE-15](general-todo.md#dine-15), [DINE-16](general-todo.md#dine-16)).
- `[?]` Graded with expectations, or pass/fail.
- Done when: `dbg smoke` holds no `atl-*` scenario, and none that starts a test needing no UI.

## TS5: tests with no UI

- `[ ]` `hello`, `probe` and `art`'s seven runtime tests start through TS3's control, and their
  results are read from the log.
- `[?]` Whether this stage is [TOOL-14](general-todo.md#tool-14)'s phone runner
  (`notes/atl-port.md` "Tests": a test mode selected with `dvt launch --env`, tests pushed and
  pulled, batches in one VM). Also whether the framework, package and apps suites run on the phone
  through it.
- Done when: hello, the probe and the seven runtime tests run on the phone with no UI step.

## Docs

Each stage updates every doc that names a runner it replaces
(`grep -rlE 'linux smoke|dbg smoke|run-[a-z]+\.sh' --include=*.md`), including `CLAUDE.md`'s
Commands and Smoke tests, and the dine-peek and dine-debugger agents in `.claude/agents/`.
