# System navigation gestures: Back, Home, running apps

The spec for Android's system navigation in Dine: edge swipes that send Back, Home and open the
running apps list for the Android app in front, the gesture areas apps see through `WindowInsets`,
and the exclusion rects apps use to opt parts of an edge out. Slots, milestones and test layout are
in `notes/atl-port.md`; tool commands and gotchas are in `README.md` and `CLAUDE.md`.

System navigation is system UI, so the host owns it. Dine recognizes the gestures and owns their
settings. ATL shared code owns the Android semantics (Back, task to back and front, insets,
exclusion) and reports state changes to the host. Linux tests drive the same shared entry points
through the cli host.

## Status (2026-10-20)

Back and Home are implemented with M2 (`notes/atl-port.md`); the running apps list is an orange
"under construction" sheet with a "back to app" button. Linux `linux smoke nav` and iOS
`dbg smoke atl-nav` pass.

**Built:** stage 1 without insets and exclusion: `loop_main_post` returning bool, task state,
`nav.h` (`atl_nav_back`, `atl_nav_home`, `atl_nav_front`), `host.h` in the three hosts, the Java
Back and `moveTaskToBack`, cli `-c` (`back`, `home`, `front`), the nav APK (lifecycle only) and
`run-nav.sh` (Linux steps 3 to 7). Stage 2 without settings, insets and process management: the
listener (`task_moved`, `exited`), artbridge, `AppContainerController`, the edge recognizers with
the default bindings, the launcher's `NavigationStack(path:)`, the placeholder list, the
accessibility actions, agent `ui action`, smoke `atl-nav` (steps 2-4 and 7-9, step 8 taps
"back to app"), `atl-demo` ending with Home and `atl-looper` waiting for the exit dismissal.
Dialogs follow the task: `task_move` calls `Dialog.atlTaskMoved` before the lifecycle, which closes
shown dialogs on back and shows them again on front; a dialog shown in the back waits for the front,
and backend results count only while it is drawn. The nav APK's A shows a list on its third
`onStop`; `run-nav.sh` and smoke `atl-nav` check it across front, Home and front.

**Insets and exclusion: built 2026-10-21** ([Insets and exclusion](#insets-and-exclusion), as
amended there): the window stays full height with no padding; apps get the side strips and the
home indicator as insets and decide. Linux `linux smoke nav` checks the insets on every show and
the exclusion spans; `framework` has `WindowInsetsTest`; iOS `atl-nav` checks B's insets and its
exclusion span. Left: status-bar insets for a window that covers the whole screen; insets for
Dialog and WindowManager roots; exclusion from dialog windows; exclusion rects follow a
translation only at the next layout pass and aren't clipped by parents; a check on the phone that
the recognizer ignores an excluded span (smoke checks the log line).

**Left to do** (stages in `notes/atl-port.md`):
- Settings (M8c): the `navigation` UserDefaults store, the observable `NavigationSettings` (today a
  constant value with the defaults, `apps/Dine/Sources/Dine/EdgeGestures.swift`), agent
  `ui defaults`, smoke `atl-nav` steps 1, 5 and 6.
- Process management (one app per process: M8a, with the launcher's tiles; several apps: M8e):
  the `RunningApps` model and the real running apps list, the AtlView run buttons' states and
  footer, an AtlView button bringing a running app to the front.
- Immersive mode (M6b; the Dine-wide setting: M8c): `SYSTEM_UI_FLAG_HIDE_NAVIGATION` and the
  immersive flags map to the container's `prefersHomeIndicatorAutoHidden` and
  `preferredScreenEdgesDeferringSystemGestures` (a first swipe at a deferred edge only reveals).
  A Dine setting forces `prefersHomeIndicatorAutoHidden` on for every app, so the indicator
  doesn't cover apps on iPhones that keep it shown (newer iOS hides it by default); it lives in
  the settings store below, next to the bindings. Fullscreen (`FLAG_FULLSCREEN`) only hides the
  status bar, with the window kept below the notch (Android's default cutout mode).
- [By hand on the phone](#by-hand-on-the-phone): the default bindings fire their actions
  (2026-10-20); the scroll, Notification Center corner and settings checks (M8c) are still open.
- Dialogs and Home (M8b): Dine dismisses the container before Java hears Home, so an alert shown in
  between presents over the launcher until Java's close reaches it, and a tap whose answer reaches
  Java after Home is dropped: the alert comes back on front.

**Corrections from building it:**
- The container's escape is on its view (`EscapeView`), not on the view controller: escape and
  the agent's `action` climb accessibility containers, which skip view controllers.
- UIKit controls and `UIAlertController` actions decline `accessibilityActivate` (VoiceOver
  touches them). Agent `tap` falls back to a control's tap events, then to running the topmost
  alert's action with that title.
- The host slot's functions are linked into ATL (`src/backends/host/{gtk,cli}/host.c`, the
  embedded host's `embedded.c`): the headless `.so` links with `--no-undefined`, so the cli
  executable can't provide them.
- An activity's `stopped` flag (Java field set by `activity.c`) gives `onRestart` to every activity
  focused after `onStop`, also one uncovered by a finish, as on Android.
- The listener struct has `task_moved` and `exited` only; `exclusion_changed` comes with the
  exclusion work. `atl_embedded.h` includes `nav.h`, installed next to it.
- Verified on the phone: the agent's walk reaches the presented container, and the custom action
  on the launcher's hosting view works.
- Recognition: the pan's own start threshold (about 10 pt of total movement) is the decision
  distance. A second 10 pt check along one axis failed most diagonal swipes. Scroll views wait for
  a pan from a strip to fail. Each swipe logs `nav: swipe <edge> <axis> commits|cancels: <pt>,
  <pt/s>`. By hand on the phone (2026-10-20): the default strip and commit values feel right.

## Starting points

| What | Where |
|---|---|
| Back today: calls `onBackPressed` only when `back_has_target`; not NULL-safe | `dine-atl/src/shared/activity.c:101`, `:146` |
| its only caller, the gtk header button | `dine-atl/src/main-executable/back_button.c:11` |
| activity stack, `activity_focus` / `activity_unfocus` (guards only `onPause`), `activity_start` | `dine-atl/src/shared/activity.c:16`, `:53`, `:70`, `:190` |
| `Activity.onBackPressed` = `finish()`; `moveTaskToBack` package-private stub; `onRestart` never called | `dine-atl/src/api-impl/android/app/Activity.java:492`, `:623`, `:173` |
| `View.layoutInternal`, reached from both ui backends through `atl_upcall_view_layout` | `View.java:1663`, `dine-atl/src/shared/upcall.c:71` |
| `getFitsSystemWindows()` always true; `getRootWindowInsets`, `onApplyWindowInsets` stubs | `View.java:2029`, `:2424`, `:2629` |
| `getLocationInWindow` ends in a gtk-only native | `View.java:1520`, `:2250` |
| `WindowInsets` (getters zero, `Type` complete, Builder no-ops) | `dine-atl/src/api-impl/android/view/WindowInsets.java` |
| `loop_main_post` signals with no check (crashes before prepare) | `dine-atl/src/backends/loop/cfrunloop/loop.c:60` |
| embedded host API, installed header | `dine-atl/src/backends/host/embedded/atl_embedded.h`, `dine-atl/meson.build:270` |
| ATL config, one run per process, `atl main returned` | `native/artbridge/artbridge.cpp:379`, `:386`, `:401`, `:452` |
| Swift module for artbridge | `apps/Dine/Sources/CArtBridge/module.modulemap` |
| launcher `NavigationStack` with destination links | `apps/Dine/Sources/Dine/LauncherView.swift:12`, `:31` |
| debug agent: walk, escape, settle | `native/dbgagent/agent.mm:51`, `:92`, `:158` |
| smoke tables | `tools/py/dine/dbg/smoke.py`, `tools/py/dine/linux.py` |

## Behaviour

| Gesture | Default action |
|---|---|
| from the right edge, inward | Back |
| from the left edge, inward | running apps list |
| from the left edge, downward along it | Home |
| from the right edge, downward | none |

Every binding is a setting (see [Settings](#settings)).

- **Edges** are the physical left and right of the screen; Dine is portrait-only. Each strip spans
  only the safe-area vertical range, clear of Notification Center, Control Center and the home
  indicator.
- **Recognition:** a touch starts a gesture when it goes down inside an edge strip (default 20 pt
  wide) and outside that edge's exclusion spans. After 10 pt of movement the dominant axis picks the
  binding: inward or down. An unbound binding or any other direction fails the gesture and the
  touch stays with the content.
- **Commit:** on release, when the travel along the axis reaches the commit distance (48 pt inward,
  96 pt down) or the velocity along it reaches 600 pt/s. Otherwise the gesture cancels. The longer
  down distance guards against an accidental Home while scrolling near the left edge.
- **Feedback:** an indicator for the action follows the finger, so a cancel is visible.
- **Where:** the app container takes every binding. The launcher root takes only the bindings whose
  action is the running apps list, since Back and Home have no target there. Dine's pushed dev
  screens (hello++, probe, art, atl) keep iOS's own left-edge pop, and the launcher's recognizer is
  off while one of them is pushed.

### Actions

- **Back** is the BACK key, down and up, through the key chain: a shown dialog cancels, else the
  focused views and the current activity, whose `onKeyUp` calls `onBackPressed()`. androidx's
  `ComponentActivity` overrides it and forwards to its `OnBackPressedDispatcher`, so app callbacks
  see it. The default `Activity.onBackPressed` follows Android 12+: the task root moves to the back
  instead of finishing.

  ```java
  public void onBackPressed() {
      if (!isTaskRoot() || !moveTaskToBack(false))
          finish();
  }
  ```

  On iOS the host accepts the move, so Back on the root activity is Home. On gtk the host refuses
  it and the activity finishes, which keeps the desktop behaviour. Back while the task is in the
  back does nothing.
- **Home:** Dine dismisses the app container at once, pops the launcher to its root, then tells
  ATL, which runs `onPause` and `onStop`. Home never waits for the Android main thread, so a hung
  app can't trap the user.
- **Running apps list:** a Dine screen over the launcher, newest first, one entry per running app
  labelled with its name. Opening it from an app moves the app to the back. Tapping an entry brings
  that app to the front and presents its container. Dismissing the running apps list returns to the
  app that was in front, else to the launcher. It has no close action: ATL runs once per Dine
  process, so a closed app couldn't start again (several apps: M8e in `notes/atl-port.md`).
- **One run per process:** while an app runs, its AtlView button brings it to the front, and the
  other run buttons are disabled with the footer "ATL runs once per process: relaunch Dine". After
  the app exits, every run button is disabled with the same footer.
- **App exit:** when the last activity finishes, ATL exits. Dine removes the app from the running
  apps list and dismisses its container, leaving the screen below it.

## Settings

Changes apply while Dine runs. A settings screen comes later and binds to the same model.

- **Store:** UserDefaults key `navigation`, a String holding JSON. A missing key, field or map
  entry takes its default; a value that fails to decode means all defaults and logs
  `nav: settings invalid <error>`. The full default value:

  ```json
  {
    "bindings": {"left.inward": "appsList", "left.down": "home",
                 "right.inward": "back", "right.down": "none"},
    "stripWidth": {"left": 20, "right": 20},
    "commitDistance": {"inward": 48, "down": 96}
  }
  ```

  Actions: `back`, `home`, `appsList`, `none`. Widths and distances are pt. Planned with
  immersive mode: `"homeIndicatorAutoHidden": "app"` (follow the app's flags) or `"always"`.
- **Model:** one `@MainActor` observable `NavigationSettings`, owned by `DineMain`. It reads the
  key, writes through it, and reloads on `UserDefaults.didChangeNotification`, so a write from the
  debug agent shows up like a write from a settings screen.
- **Use:** recognizers read the model at touch-down, so a change applies to the next touch without
  rebuilding anything. Every change recomputes the gesture insets and sends them to ATL.

## Insets and exclusion

### Host to ATL

`void atl_nav_set_insets(const struct atl_window_insets *insets)` (`nav.h`) takes `float` dp for
three edge sets (`struct atl_edges`): system gestures, mandatory system gestures and navigation bars.
The navigation bars are also the system window insets apps read before API 30, the only ones that
reach androidx at ATL's level. It works from any thread and also before ATL starts: shared C
(`src/shared/insets.c`) stores the values under a mutex and posts a dispatch to the shown
activity; every show dispatches the stored values (`Window.dispatchInsets`, from `activity_focus`).
The decor doesn't fit system windows: only views with `fitsSystemWindows` pad (AppCompat's subdecor
does), as on Android with edge-to-edge.

Dine sends (`Navigator.sendInsets`, before the start and on the container's safe-area change):

| Edge | System gestures | Mandatory | Navigation bars |
|---|---|---|---|
| left, right | the strip width when the edge has a binding, else 0 | 0: apps may exclude parts of both side edges | 0 |
| top | 0: the window starts below the status bar | 0 | 0 |
| bottom | the safe area's bottom (the home indicator) | same | same |

Dine treats 1 pt as 1 dp. Since M3 the ATL window on iOS runs from below the status bar to the
screen's bottom at density 160 × screen scale (1 dp = 1 pt): its side and bottom edges are the
screen's, its top is the safe area's, so the top insets it gets are 0 until it covers the status
bar too.

### Java

- `WindowInsets` stores insets per type (the Builder's `setInsets`); the system window insets are
  the status, navigation and caption bars', as AOSP 11 maps them (`replaceSystemWindowInsets`).
  It has the API 29 gesture getters, `getInsetsIgnoringVisibility` and the consume calls; stable
  insets are the system window's (the bars never hide).
- View and ViewGroup: `dispatchApplyWindowInsets` with the dispatch before API 30 (ATL's level):
  the children get the insets until one consumes all. `onApplyWindowInsets` pads through
  `fitSystemWindows` only with `fitsSystemWindows` (default false, the XML attribute, the setter).
  `requestApplyInsets` posts the window's dispatch; `getRootWindowInsets` is the window's last
  insets while attached.
- `Window.dispatchInsets` reads the stored insets in px (`get_insets`), dispatches them to the decor
  and requests layout.

### Exclusion rects

- Add `View.setSystemGestureExclusionRects(List<Rect>)` and `getSystemGestureExclusionRects()`.
  The view keeps a copy in its own coordinates.
- The Window tracks its attached views that have rects and recomputes their window-space rects
  (`getLocationInWindow`, a parent walk) at the end of the root's `View.layoutInternal`, at a scroll
  and when a view's rects change. It sends a changed list to shared C as px (`set_exclusion_rects`), and every
  show sends it with the frame; only the shown activity's window counts.
- Shared C keeps the last rects and rebuilds the spans when they change and after every
  `atl_nav_set_insets`. Per side edge, the strip is the window rect from the edge to its side
  system gesture inset, between the top and bottom system gesture insets. Shared C intersects the
  rects with the strip, merges their vertical extents, keeps the bottom-most 200 dp per edge (AOSP
  10's `MIN_GESTURE_EXCLUSION_LIMIT_DP`, granted from the bottom up, verified), converts to dp, and
  calls `host_gesture_exclusion_changed` when the spans differ from the last ones sent.
- Dine keeps the spans on the main queue; the container's recognizer ignores a touch in an
  excluded span of its edge (pt from the window's top, the safe area's top).

### Reach

androidx reads gesture insets and sets exclusion rects only at SDK 29 and above, and ATL's
`SDK_INT` is its fixed level (`ro.build.version.sdk` in `SystemProperties.java`), so no app sees
them through androidx until the level reaches 29. At 33 or more androidx calls
`getOnBackInvokedDispatcher`, which ATL lacks.

## Interfaces

### Task state

Shared C keeps `task_front`, true at start. It gates `activity_focus` and `activity_unfocus`.

- While the task is in the back, an activity that is started runs `onCreate` and `onPostCreate`,
  joins the stack and the window, and gets `onStart` only when the task comes to the front. An
  activity uncovered by a finish is not focused until then either.
- A second unfocus sends no second `onStop`.
- Coming to the front calls `onRestart` before `onStart`, only for an activity that got `onStop`.

### Shared entry points: `src/shared/nav.h`

`nav.h` includes no JNI header. Meson installs it as `atl/nav.h` next to `atl_embedded.h`; the
`CArtBridge` module map lists it (`header "../../../../out/ios/include/atl/nav.h"`), so Swift calls
`atl_nav_*` directly with no artbridge wrappers.

| Function | Effect |
|---|---|
| `bool atl_nav_back(void)` | posts Back: the BACK key through the key chain (a shown dialog, the focused views, the current activity); no-op while in the back |
| `bool atl_nav_home(void)` | posts task to back; no-op while in the back |
| `bool atl_nav_front(void)` | posts task to front; no-op while in the front |
| `void atl_nav_set_insets(...)` | stores insets, posts their dispatch ([Host to ATL](#host-to-atl)) |

The `bool` functions work from any thread and return false when the post failed because ATL isn't
running. `atl_nav_back` replaces `current_activity_back_pressed`. The gtk header button calls it;
`back_has_target` stays only to set the button's sensitivity.

`nav.h` also defines the types the host sees:

```c
struct atl_gesture_insets { float left, top, right, bottom; };          /* dp */
struct atl_span { float top, bottom; };                                 /* dp, window */
#define ATL_EXCLUSION_SPANS_MAX 16
struct atl_gesture_exclusion {
	int left_count, right_count;
	struct atl_span left[ATL_EXCLUSION_SPANS_MAX], right[ATL_EXCLUSION_SPANS_MAX];
};
```

`loop_main_post` returns `bool`: false before `loop_main_prepare` in every backend (poll stops
queueing early posts), and false after `loop_main_quit` in poll and cfrunloop. glib has no
`loop_main_run`/`loop_main_quit`: the gtk host runs GApplication and the process exits with it.
`loop_main_post` is the one running-state check; artbridge keeps no guard of its own.

### Host slot: `src/slots/host.h`

The first host slot functions. Called on the Android main thread; every host implements them.

| Function | gtk (`src/main-executable/`) | cli | embedded |
|---|---|---|---|
| `bool host_task_to_back(void)` | false | true | true |
| `void host_task_moved(bool front, bool by_host)` | no-op | prints `host: task back app` (or `front`, `host`) | listener `task_moved` |
| `void host_gesture_exclusion_changed(const struct atl_gesture_exclusion *)` | no-op | prints `host: exclusion left <spans> right <spans>` | listener `exclusion_changed` |

cli prints spans as `top-bottom` pairs separated by commas, `-` for none, rounded to whole dp.

`Activity.moveTaskToBack(boolean nonRoot)` becomes public. It returns false when `nonRoot` is false
and the activity isn't the task root, as in AOSP. Otherwise it asks `host_task_to_back()` and, on
true, moves the task to the back.

### Events

- `task_moved(front, by_host)` fires on every change of `task_front`. `by_host` is true when an
  `atl_nav_home` or `atl_nav_front` call caused it, false for the app's own `moveTaskToBack`
  (including Back on the root). The first start fires nothing.
- Dine updates its UI at once for its own actions, so it ignores events with `by_host` true; a late
  echo of a Home can't dismiss a container the user has since brought back. An event with `by_host`
  false and `front` false is handled like Home: dismiss the container, pop the launcher to its root.
- `exited(status)` fires right before `atl_embedded_main` returns. When `atl_embedded_vm_options`
  fails, artbridge returns before `atl_embedded_main` and calls `exited(-1)` itself.
- Dine presents the container when `dine_atl_run` starts the app.

### Embedded host and artbridge

```c
struct atl_embedded_listener {
	void *context;
	void (*task_moved)(void *context, bool front, bool by_host);
	void (*exclusion_changed)(void *context, const struct atl_gesture_exclusion *exclusion);
	void (*exited)(void *context, int status);
};
```

- Defined in `nav.h`. `atl_embedded_config` gets `const struct atl_embedded_listener *listener`;
  `dine_atl_run` takes it and passes it through.
- The callbacks run on the Android main thread. Swift copies the arguments and continues with
  `DispatchQueue.main.async`, never `sync`. The exclusion spans live on the main queue and the
  recognizer reads them there, so the UIKit thread never calls into Java.

## Dine

- **`AppContainerController`:** UIKit, full screen, presented outside the launcher's
  `NavigationStack`, so no pop gesture competes with the left edge. It holds ATL's window (M3), with
  the shown activity's frame color (`ATLSurface`) behind the status bar.
- **Recognizers:** `UIPanGestureRecognizer` with a delegate that checks the start point, since
  `UIScreenEdgePanGestureRecognizer` has no adjustable width. `cancelsTouchesInView` is on; the
  uikit backend maps `touchesCancelled` to `ACTION_CANCEL`. The classifier is a pure function
  of start point, translation, velocity, settings and exclusion spans, returning an action or none.
- **Launcher root:** popping to the root needs `NavigationStack(path:)` with value-based links in
  place of today's destination links. The launcher's recognizer and its custom action sit on the
  root view of the window's `UIHostingController`, enabled only while the path is empty and no
  container or running apps list is presented.
- **Accessibility:** edge swipes don't work under VoiceOver, and the debug agent drives the UI
  through accessibility.
  - The container's `accessibilityPerformEscape` is Back, so VoiceOver's escape gesture and
    `dbg ui back` inside an app send Android Back.
  - `accessibilityCustomActions`: "Back", "Home" and "Recent apps" on the container, "Recent apps"
    on the launcher's hosting root view.
- **`RunningApps`:** an observable list fed by the listener; the running apps list screen and
  AtlView read it.
- **Log lines** (os_log, category `art`), which smoke waits on:
  - `nav: container shown <app>`
  - `nav: container dismissed <reason>`, with reason `home`, `back`, `list` or `exit`
  - `nav: launcher root`

## Tests

### Test APK

`dine-atl/tests/headless/nav/`, built with `tests/harness/apk.py`: package `dev.dine.nav`, minSdk
29, activities `MainActivity` (A) and `SecondActivity` (B). A starts B once, guarded by a static
flag, from its first `onResume`. Both log their lifecycle and register an
`OnApplyWindowInsetsListener` that logs `nav: <A|B> insets <gesture l t r b> <mandatory l t r b>
<navigation bars l t r b>`, values in whole px. B sets one exclusion rect, 100 px tall, at its right edge.

### Linux

- **cli host option `-c`:** a reader thread takes commands on stdin and calls `atl_nav_*`: `back`,
  `home`, `front`, and `insets` with 12 dp (system gestures, mandatory gestures, navigation bars,
  each left top right bottom); M4a's `touch` and `key` lines go to the headless backend. The loop
  slot has no fd watch, hence the thread. It is opt-in, so `run-looper.sh` and other runs that
  inherit a terminal's stdin are unaffected.
- **`run-nav.sh`** drives the APK through a coproc, like `run-demo.sh`, and checks in order. A
  command that must do nothing is checked by the next command's lines arriving with nothing between.
  1. B shown: `nav: B insets 0 0 0 0 0 0 0 0 0 0 0 0` (Linux sets no insets at start)
  2. `insets 20 10 20 10 0 10 0 10 0 0 0 10`: `nav: B insets 20 10 20 10 0 10 0 10 0 0 0 10` and
     `host: exclusion left - right <B's span>`
  3. `back`: B finishes, A resumes and logs its insets line
  4. `back` on A: `host: task back app`, A's `onPause` and `onStop`
  5. `back` (nothing), then `front`: `host: task front host`, A's `onRestart`, `onStart`, `onResume`
  6. `front` (nothing), then `home`: `host: task back host`, A's `onPause` and `onStop`
  7. `home` and `front` with A's list shown in the back, then `back`: the list cancels and closes
  8. kill ATL, like `run-demo.sh`
- Register `nav` in `tools/py/dine/linux.py` next to gd, demo and looper. The demo golden doesn't
  change.

### iOS

- **Debug agent:**
  - `action "Name"`: walks like `back` (content last, climbing `accessibilityContainer` and
    `nextResponder`) and runs the first custom action with that name.
  - `defaults <key> <json>`: on the main queue, stores the JSON text as the key's String value;
    `null` removes the key.
  - Both set `gBefore`/`gResult` like `tap` and `back`, so `settle` works.
  - Register them in `tools/py/dine/dbg/server.py` and the `cli.py` choices as
    `tools/dine dbg ui action <name>` and `tools/dine dbg ui defaults <key> <json>`. Smoke `Step`
    gets `action=` and `defaults=` fields.
- **APK:** `build-ios-atl.sh` builds `nav.apk` into `out/tests/apks`, which dev builds bundle in `dev/`; AtlView gets "run nav"
  with activity `dev/dine/nav/MainActivity`.
- **Smoke scenario `atl-nav`,** with `uses_vm=True, needs_clean=True`, in `SCENARIOS` after
  `atl-looper`. The safe-area values are unknown to the test, so its regexes accept any top and
  bottom values.
  1. `defaults navigation null`, so a value left by an earlier run can't leak in
  2. tap "atl"
  3. tap "run nav": `nav: insets B 20 <t> 20 <b> 0 <t> 0 <b>`
  4. action "Back": B finishes, A resumes
  5. `defaults navigation {"stripWidth":{"left":30,"right":30}}`:
     `nav: insets A 30 <t> 30 <b> 0 <t> 0 <b>`
  6. `defaults navigation null`: A's insets line back at 20
  7. `back`: A's `onStop`, `nav: launcher root`
  8. action "Recent apps", tap "nav": A's `onRestart`, `onResume`, `nav: container shown nav`
  9. action "Home": `nav: launcher root`
- **Existing scenarios:** `atl-demo` ends with action "Home" waiting for `nav: launcher root`,
  instead of `back`. `atl-looper`'s run step also waits for `nav: container dismissed exit` before
  its `back`. Both dismissals follow an async ATL event that arrives after the agent's `settle` has
  returned, so the step waits for the log line.

### By hand on the phone

iOS has no public touch synthesis, so the swipes themselves are checked by hand:

- each default binding fires its action, and a short swipe cancels
- a vertical scroll in the middle of the screen never fires Home
- a swipe starting in the top-left corner opens Notification Center, not Home
- after `tools/dine dbg ui defaults navigation '{"bindings":{"left.inward":"none"}}'`, a left-edge
  inward swipe does nothing; `defaults navigation null` restores it

## Stages

1. **dine-atl on Linux:** `loop_main_post` returning bool, task state, `nav.h`, `host.h` in the
   three hosts, the Java back, insets and exclusion work, cli `-c`, the nav APK and
   `linux smoke nav`. Merge upstream first: the Java edits land in upstream files (`View.java`,
   `ViewGroup.java`, `WindowInsets.java`, `Activity.java`).
   Done when `tools/dine linux build`, `tools/dine linux smoke` (gd, demo, looper, nav),
   `tools/dine test runtime` and `tools/dine ios build-atl` pass.
2. **iOS:** the embedded listener, artbridge, the container, settings, recognizers, the running apps
   list, the agent commands and the smoke changes.
   Done when `tools/dine dbg smoke` passes, `atl-nav` included.
3. **By hand:** the checklist above on the phone.
4. **Docs:** `CLAUDE.md` (`dbg ui action|defaults`, `linux smoke nav`, `run-nav.sh`, the smoke
   lists), `tests/README.md`, and `notes/atl-port.md` where it says the host exports no slot
   functions; `notes/decisions.md` for the upstream files touched.

## Out of scope

- `OnBackInvokedDispatcher` and predictive back.
- Real window size and density on iOS (M3).
- Closing apps from the running apps list (M8e).

## Risks

- No androidx app sees the insets while ATL's level is below 29 ([Reach](#reach)).
- framework-res says 3-button navigation (`config_navBarInteractionMode` 0,
  `config_backGestureInset` 0dp). Apps that detect gesture navigation from these resources assume
  buttons; changing them needs `-Dregenerate_framework_res`.
- A vertical scroll that starts within 20 pt of the left edge can fire Home; the 96 pt down commit
  distance and app exclusion rects are the only guards.
- Edge pans compete with Android-hosted `UIScrollView`s (M4a); unchecked by hand. If they lose,
  intercept edge touches in `UIWindow.sendEvent` before hit-testing.

## Unverified

- Whether ATL keeps the left and top of every view current at the end of the root's layout on gtk,
  which the parent-chain walk needs.
- On the phone: iPhone safe-area values and the iOS 26+ full-content pop gesture. (The agent's
  up-walk reaching the container and the hosting view's custom action: verified, see Status.)
