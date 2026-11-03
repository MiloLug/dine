# Findings: how apps are hosted today

How an app is started, lives and ends on Linux and in Dine, where its files go, and which notes
assume one app per process. A snapshot read on 2026-10-31; line numbers drift. **C**: read in code.
**U**: inference, unchecked. dine-atl's per-app state is in `findings-framework.md`.

## Linux

- Both builds are named `android-translation-layer` (`dine-atl/meson.build:358,382`). The gtk one
  is installed; the headless one runs from `out/linux/build/dine-atl-headless` with
  `RUN_FROM_BUILDDIR=1`. C
- gtk options (`dine-atl/src/main-executable/main.c:540-555`): APKs are positional, the first is the
  app; `-l ACTIVITY`, `-w`, `-h`, `-X JVMOPT`, `-e k=v`, `--instrument`, `--install`,
  `--install-internal`, `--uri`, `--gapplication-app-id`. cli: `[-c] [-d DPI] [-l ACTIVITY |
  --instrument CLASS] [-X OPT]... APK...` (`backends/host/cli/main.c:21`), no glib, no D-Bus; its
  only inbound channel is the `-c` stdin reader. C
- VM options: `java.library.path`, `java.class.path`, `atl.app.class.path`, `atl.app.library.path`,
  `-Xcheck:jni`; no heap flags (`shared/startup.c:179-253`). C
- Data base: `$ANDROID_APP_DATA_DIR`, else `$XDG_DATA_HOME/android_translation_layer`, else
  `~/.local/share/android_translation_layer` (`startup.c:91-114`, mirrored in `ATLPaths.java`). The
  app's dir is `<base>/<APK file name>_/` (`startup.c:136`) with `files/`, `shared_prefs/`,
  `databases/`, `no_backup/<pkg>`, `Android/obb/<pkg>`, `lib/`. External storage and
  `getExternalFilesDir` resolve into the same dir, and `/storage/emulated/0/` is rewritten into it
  (`libc_bio_path_overrides.c:112-123`). Cache: `/tmp/atl_cache/<pkg>`. Installed copies:
  `<base>/_installed_apks_/`. C
- One app has three identities that don't line up: the GApplication id
  (`com.example.demo_application` unless overridden; `--install` writes the override into the
  `.desktop` Exec line), the package name (known only after VM start, `main.c:331`), and the data
  dir (APK file name; `startup.c:132-136` has a TODO about it). Guest libs are looked up at
  `<base>/<pkg>_/lib`, which matches the app's own dir only when the file is named `<pkg>.apk`. Two
  APKs with the same file name share a data dir. C
- Single instance: the app runs with `G_APPLICATION_NON_UNIQUE` (`main.c:585`) and claims its bus
  name by hand after start (`main.c:507-517`), so a second launch of the same app is a new process
  and a new VM. `open()` and `activate()` have branches for a D-Bus request to a running app
  (`main.c:220,522`); whether GLib exports `org.freedesktop.Application` under NON_UNIQUE is U. C
- Start (gtk): `atl_prepare`, `atl_vm_start`, `atl_app_create`, `atl_activity_create_main`,
  `activity_start` (`main.c:242-255`). End: `close-request` closes every activity, then `atl_exit`
  calls `System.exit`. cli ends when the last activity finishes (`cli/main.c:216`). No main
  activity is `System.exit(1)` (`Activity.java:104`). C
- Tests run one process per check with a temporary `ANDROID_APP_DATA_DIR`, `timeout 60` and
  `-X -Xint` (`tests/headless/run-controls.sh:21-23`, `tools/py/dine/linux.py:58-60`). C

### IPC that exists

| Channel | Where | Notes |
|---|---|---|
| session bus name = package, `.service` file in `$XDG_DATA_HOME/dbus-1/services/` | `main.c:184-215` | written by `--install`; D-Bus activation starts the app |
| inbound `ActivateAction` `startActivity`, `startService`, `sendBroadcast`, payload `(sssa{sv}s)` | `main-executable/actions.c:49-53`, `dine-atl/doc/DBusIntentApi.md` | gtk only; delivered to `Context.this_application`; flags, type and categories are lost |
| outbound `nativeStartExternalService` | `api-impl-jni/content/android_content_Context.c:226-236` | only `startService`, only when the target isn't loadable in-process and the intent names a package |
| UnifiedPush, MPRIS, portals | `android_content_Context.c:199-213`, `android_app_NotificationManager.c` | own the package bus name, call desktop services |
| debug agent socket | `backends/ui/gtk/agent.c:450-477` | `ATL_DBG_AGENT`, test hooks, gtk only |
| process spawn | `Activity.java:331` | the one spawn: `android-translation-layer --install` |

All C.

## Dine on iOS

- `dine_atl_run` copies its arguments, starts a detached 8 MiB pthread, and refuses a second call
  (`native/artbridge/artbridge.cpp:221-244`); `gAtlStarted` is never reset; `CreateVm` pauses
  forever when VM creation fails (`:135`). C
- The thread sets `ANDROID_APP_DATA_DIR=<data_dir>/atl`, gets ATL's VM options for one APK
  (`embedded.c:34`), creates the VM, then runs `atl_embedded_main`: `atl_vm_init`,
  `atl_app_create(ui_window_new(surface))`, the main activity, and `CFRunLoopRun` on that thread
  (`embedded.c:74-92`, `cfrunloop/loop.c:68,120`). C
- VM options: `-Xint -Xusejit:false -Xnorelocate -XX:DumpNativeStackOnSigQuit:false
  -Djava.io.tmpdir=<data_dir>` plus ATL's four (`artbridge.cpp:115-118`); dev builds add
  `-Xcheck:jni` and the junit boot jars (`dev.cpp:214-220`). C
- Threads: the UIKit main thread (a CADisplayLink, `view.m:1015`; text measurement uses
  `dispatch_sync`, `view.m:898`); the Android main thread; a stdout/stderr relay to os_log
  (`artbridge.cpp:42-51`); one `loop_worker` per Java Looper thread
  (`android_os_MessageQueue.c:27`). ART daemons and the debug agent thread: U.
- The host API takes an app handle (`struct atl_app`): `nav.h`, `host.h`, `atl_embedded.h`,
  `dineart.h`, and listener events carry it. C
- UIKit: a new `AppSurfaceView` per run, an `AppContainerController` presented full screen
  (`apps/Dine/Sources/Dine/Navigation.swift:59-86,181-191,271-313`). `Navigator` keeps the running
  apps by handle and shows one at a time. The running apps list is a placeholder ("Running apps / under construction",
  `:372-418`). A later `dine_atl_run` starts its app in ATL's VM; it returns -1 while the first run starts and
  when the art screen made the VM. C
- Not built: `RunningApps` (spec only, `notes/nav-gestures.md`), AtlView run states
  ([DINE-9](../general-todo.md#dine-9)), launcher tiles that launch (`LauncherView.swift:115-117`);
  `AppLibrary` stores `id` and `name` (`AppLibrary.swift:7-10`). C

## Storage on iOS

- `data_dir` is Caches (`Dev/AtlView.swift:45`). The ATL root is `<Caches>/atl`, an app's dir
  `<Caches>/atl/<apk>_/`. `ANDROID_DATA`, `XDG_CACHE_HOME` and `java.io.tmpdir` are Caches too
  (`artbridge.cpp:104-117`). iOS may purge Caches (iOS knowledge). C
- Application Support holds only `dine.sqlite`, table `apps(id, name)` (`AppLibrary.swift:24-31`).
  Documents is unused. C
- APKs come from the app bundle, `dev/<name>.apk`, dev builds only; there is no import. C
- `getCacheDir` is `/tmp/atl_cache/<pkg>` on every build; whether `/tmp` is writable in the iOS
  sandbox is U. On failure it logs and returns null (`Context.java:290-296`). C

## Notes that assume one app per process

Since the design's approval (2026-11-02) each place names the multi-app stage that changes it;
`atl-port.md` Tests keeps restarting Dine every N tests, since tests change VM-wide state that a
drop doesn't reset.

| Note | Place | Assumption |
|---|---|---|
| `atl-port.md` | slot table, `host` row | one container that holds activity windows |
| `atl-port.md` | M1 | `dine_atl_run` refuses once any VM exists |
| `atl-port.md` | M3 | one `atl_window_config` per process; `Navigator.run` makes one fixed-size surface; one `ui_window` per process |
| `atl-port.md` | M8a | app dir from the APK file name; metadata read without the VM because there is one VM; no launcher activity ends Dine through `System.exit(1)`; import rejects an APK without a launcher activity; one app per launch |
| `atl-port.md` | M8b, M8c | `atl_nav_home` and `atl_nav_front` for "the app"; one insets set |
| `atl-port.md` | M8e, Tests | the globals; one VM per process, Dine restarts every N tests |
| `nav-gestures.md` | Behaviour, host API, events, `RunningApps`, Insets | one run per process, no close action; `atl_nav_*` and events without an app id; one `Navigator.sendInsets`. Its line cite of `artbridge.cpp:379-452` is stale (the file has 244 lines) |
| `os-features.md` | items 7, 10, 17, 18, 19, 21 | another app's service is `none` on iOS; keystore keys live per process (U); UnifiedPush and MPRIS own one bus name per process; a tap goes to "the running app"; alarms and jobs go through the one main Looper |
| `decisions.md` | window config, dialogs, `moveTaskToBack`, base JNI frame | one window per VM, one task, one Android thread |
| `bug-tracker.md` | DINE-1 | `Navigator.home()` handles one container |
| `general-todo.md` | DINE-9 | "ATL runs once per process: relaunch Dine" |
| `meta.md` | One process | already says all apps share one process |
