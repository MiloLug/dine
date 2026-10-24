# M7 and M8 split: preliminary

**Applied 2026-10-24** to `notes/atl-port.md` (milestones M4b to M9) and `notes/service-impl.md`;
every item below is marked Applied, Changed or Dropped.

A proposal for cutting M7 (services) and M8 (inside Dine) in `notes/atl-port.md` into lettered
stages. It defers to `notes/atl-port.md` for the milestones, to `notes/background-processes.md`
for background work on iOS, to `notes/multi-head-exec-maybes.md` for several apps per process and
to `notes/nav-gestures.md` for navigation.

The standing decision (2026-10-22) is: M7 is split only when an app needs a service; M8 and M9 stay
coarse. This proposal keeps the per-service rule for M7's rows and revises the rest.

## Findings

- **The services slot doesn't exist.** The service natives sit in dine-atl's `meson.build` list of
  natives not yet behind a slot, built only with `ui=gtk`: Vibrator, NotificationManager,
  AudioTrack, ClipboardManager, Context (D-Bus intents), LocationManager, MediaPlayer,
  AndroidKeyStore, SensorManager. Also waiting for the slot: the GVariant intent helpers in legacy
  `gtk_util.c` (M0's status block) and three Java GTK-isms (file chooser kinds, the `xdgportal`
  provider name, D-Bus external intents; [Java](atl-port.md#java)). None of this needs a target app.
  - **Changed:** `notes/service-impl.md` item 1 builds the slot with a services test APK, and each
    service is an item of its own. The gtk-only list has 13 more service natives than named here.
- **M6a's triage depends on it.** M6a moves service stops to M7. On headless and iOS a call to one
  of the natives above throws `UnsatisfiedLinkError`, so without `none` stubs a triage run stops at
  the first service native (an external intent opening a URL, for example) before the UI stops M6a
  is for. Not confirmed by a triage run.
  - **Changed:** M6c, a search after M6b, finds what M7 and later stages will hit. A static read
    found one such stop: accelerometerdemo's sensors call in `onCreate`. Under M6a's rule a service
    stop goes to its M7 item.
- **The M7 table misses rows** that `src/api-impl-jni/` has: MediaPlayer, MediaSession (MPRIS),
  AudioRecord, WallpaperManager, the Email portal.
  - **Changed:** `notes/service-impl.md` lists 20 services. The Email portal is part of Share,
    WebView went to M9, brightness to M6b, keyboard apps under Not staged.
- **WebView is a View.** The slot table gives toolkit widgets to `ui` but lists WebView under
  `services`. WebView and media codecs are M9-sized.
  - **Changed:** WebView is in M9 as a ui node kind. Media codecs stay an M7 item; their video
    output into a Surface waits for M9's SurfaceView.
- **M7's background rows wait on the phone.** Notifications, downloads and background jobs depend
  on the open questions in `notes/background-processes.md`. A notification tap (PendingIntent)
  needs M8's path for starting an app, and background jobs need M8's foreground and background
  lifecycle.
  - **Applied:** service-impl.md's notifications, media session, downloads and jobs items wait for
    M8a, M8b and M8d.
- **M8's items have unlike blockers:**
  - APK import and launch: unblocked. `AppLibrary` stores only a name per app; the package suite
    (`dine-atl/tests/package`) is a placeholder. A release build strips every `Java_*` symbol, so
    the release fix in M8 is a precondition for any app the launcher starts in release.
  - The navigation settings store: specified (`notes/nav-gestures.md` Settings), and M6b's
    immersive setting waits for it, so an M8 item blocks M6b.
  - Foreground and background lifecycle: Dine has no `scenePhase`, `didEnterBackground` or
    `willResignActive` handling.
  - The running apps list and closing apps: wait for the multi-app design. With one app per launch
    the list has one entry and closing is a relaunch; with several apps in one VM it is the largest
    job in the plan.
  - **Changed:** M8a to M8e in `notes/atl-port.md`. The one-app running list is already specified
    (`notes/nav-gestures.md`) and went to M8a; closing apps and several apps are M8e. Only one M6b
    item needs the settings store: the hide-home-indicator setting, which moved with it to M8c.
    The lifecycle (M8b) reuses `atl_nav_home` and `atl_nav_front`, already graded on headless.
- **No target.** The milestone rule says a stage from M5 on has one target graded on headless plus a
  check on the phone, and a milestone too big for that splits before its work starts. M8 has no
  single target.
  - **Applied:** M8 has letters. M8a's package suite runs on headless; how the Dine-only stages
    M8b to M8d are graded is settled when the first one starts.

## Proposed split

**M7a: the services slot.** The meson option, a `none` stub for every row, the existing natives
moved into `desktop-linux`, the three Java rows. No behaviour change on Linux. Graded by: headless
and iOS builds reach the `none` stubs instead of `UnsatisfiedLinkError`; the gtk gate passes
unchanged. Later M7 stages stay cut per service when a target app needs one. The table gains the
missing rows; WebView moves to M9 or the ui slot.

**Changed:** no M7a. M7 points to `notes/service-impl.md`: item 1 builds the slot and the test APK,
items 2-21 implement one service each (`desktop-linux`, `none`, `ios`). The fixes letter the user
first gave M7a became M6c, a search.

**M8a: APK import and launch.** Import, parse, install into a per-app data dir, start from the
launcher; the release build keeps its `Java_*` symbols (`llvm-nm` count). The package suite starts
here. Graded by: the package suite on headless; a release build imports `demo_app.apk` and shows it
on the phone.

**Applied** as M8a, with more: the APK reader is shared C over androidfw's C API (no VM), each app
gets a dir outside Caches, import rejects an APK without a launcher activity, the one-app running
list, and the trap of release force-loading `libruntimetests.a`.

**M8b: background probes.** A dev screen answers the open questions in
`notes/background-processes.md` (BGTaskScheduler runs, `BGContinuedProcessingTask`,
`beginBackgroundTask` length, notification authorization on a free account, the keep-alive
questions). Graded by: one log line per question on the phone; no headless part. Its answers set
the order of M7's notifications, downloads and background rows.

**Changed:** this is M8d. One log line answers question 3 and question 2's "exists and submits",
and question 5 takes one tap; question 1 needs days, question 4 the user's hands, and questions 6
to 8 are code reads or the user's decisions.

**M8c: lifecycle.** iOS foreground and background drive onPause, onStop, onRestart and onResume;
the Dialogs and Home race from `notes/nav-gestures.md` Status. Graded by: the nav APK's lifecycle
lines in `dbg smoke`.

**Changed:** this is M8b, Dine-only: it calls `atl_nav_home` and `atl_nav_front`. `dbg smoke` can't
background Dine today; pymobiledevice3's HID home button and `dvt launch --no-kill-existing` are
untried on the phone.

**M8d: several apps.** First the design: a diverger run over the options in
`notes/multi-head-exec-maybes.md`. Then the running apps list and closing apps for the chosen
option. Splits again once the design is chosen.

**Changed:** this is M8e; the one-app running list went to M8a.

**The settings store moves to M6b**, next to immersive mode, so no earlier stage waits for M8.
Otherwise it becomes an M8 letter done before M6b.

**Changed:** its own letter, M8c, with the hide-home-indicator setting; M6b's immersive mode
doesn't need the store.

M8a, M8b and M8d are Dine-side work with no headless target: the milestone rule needs a written
exception for them.

**Changed:** M8a has a headless target, the package suite. The Dine-only stages are M8b to M8d,
and how they are graded is settled when the first one starts.

**Order:** M7's notifications and background rows need M8a and M8c, which argues for M8a before
M7's per-service stages.

**Changed:** only the notifications, media session, downloads and jobs items wait for parts of
M8a, M8b and M8d; the other services don't need M8.

## Alternatives

- M7a only, M8 stays whole: a smaller edit, but M6b still waits for M8 and M8 has no target to
  finish against.
- No change: M6a's triage may stop on service natives, and M8 can't start under the milestone
  rule.

**Dropped:** neither alternative was taken.

## Unverified

- Whether a headless triage stops on a service native before M6a.
  - **Changed:** a static read shows accelerometerdemo's sensors call in `onCreate`; M6c checks by
    a run.
- Whether target apps need the dev payload to reach the phone before M8a.
  - **Applied:** they do (`build-ios-dev.sh` bundles only demo_app and the authored APKs); M5d's
    Gravity Defied goes into the dev payload.
