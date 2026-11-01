# Findings: dine-atl's per-app and process-wide state

What in dine-atl assumes one app per process, as needed by `design.md`. A snapshot read on
2026-10-31; line numbers drift. Paths are under `dine-atl/src/` unless noted. **C**: read in code.
**U**: inference, unchecked. How apps are launched and hosted is in `findings-hosting.md`.

## Process-wide state that holds an app

| Symbol | Where | Holds | Tag |
|---|---|---|---|
| `ATLLoadedApp.primary_application` | `api-impl/android/atl/ATLLoadedApp.java:37,79-99` | the one app, read once from `atl.app.class.path`. Readers: PackageManager, ContentProvider, `Activity.internalCreateActivity`, Binder, PendingIntent, ActivityThread, `Application.getProcessName`, ActivityManager, Looper, Parcel, AndroidKeyStore, SQLiteGlobal, SoundPool, NotificationManager | C |
| `Context.getApplicationContext()` | `content/Context.java:168-170` | the primary's Application for every context, guests included | C |
| `Context.this_application` | `Context.java:102,151` | the primary's Application; read from C in `content/android_content_Context.c:153,183`, `gtk_util.c:164,187`, `main-executable/actions.c:13,27,41` (all gtk-only) | C |
| `Context.package_manager` | `Context.java:96,121` | one PackageManager with the primary's info, built with GET_META_DATA only (`PackageManager.java:1348,1358`) | C |
| `Context.sys_config` | `Context.java:97,114` | one `Configuration`, passed by reference into every app's Resources (`ATLLoadedApp.java:111,133,140`) and changed in place by `atl_display_apply` (`shared/android_content_Context.c:9-29`) | C |
| `Context.receiverMap` | `Context.java:111` | dynamically registered receivers of every app | C |
| `Context.sharedPrefs` | `Context.java:362-375` | preferences keyed by file name only | C |
| `Environment.app_data_dir_file` | `os/Environment.java:36,328-333` | the primary's data dir; `getFilesDir`, prefs, `getDatabasePath` and `openFileOutput` of every app resolve into it | C |
| `ContentProvider.atl_providers` | `ContentProvider.java:20-45` | the primary's authorities plus "media" | C |
| `Looper.sMainLooper` | `os/Looper.java:59` | one main looper; 32 `getMainLooper()` call sites | C |
| `JobScheduler.pendingJobs`, `runningServices` | `app/job/JobScheduler.java:13-14` | keyed by job id and by Class | C |
| `LayoutInflater.constructorCache` | `view/LayoutInflater.java:37,94-103` | View constructors keyed by class name: a second app's same-named androidx view would get the first app's class (U) | C |
| `Dialog.shown` | `app/Dialog.java:33` | dialogs of every app | C |
| `InputMethodManager` statics | `view/inputmethod/InputMethodManager.java:13-18` | IME focus for the process | C |
| `Display.window_width/height/density_dpi` | `view/Display.java:9-11`, set once in `shared/startup.c:268-271` | one window size | C |
| `ATLLoadedAppManager.loaded_apps/loaded_packages` | `ATLLoadedAppManager.java:15-16` | guests by package; read at `:39-46,59` outside `load_lock` (race: U) | C |
| C: `apk_path`, `app_data_dir`, `atl_window`, `atl_window_config` | `shared/startup.c:36-41` | the primary's paths and the one window | C |
| VM option `java.library.path` | `startup.c:185-193` | natives dir plus the primary's lib dir | C |
| C: `backlog`, `activity_current`, `task_front` | `shared/activity.c:20-25` | one activity stack, one task | C |
| C: `paths`, `started`, `listener` | `backends/host/embedded/embedded.c:12-14` | one embedded run; `started` refuses a second (`:25-29`) | C |
| C: windows | `backends/ui/records/ui.c:23`; `backends/ui/uikit/view.m:536-541`; `main-executable/main.c:46` plus about 12 gtk natives | the one app window | C |
| C: insets, `main_loop` | `shared/insets.c:19-25`; `backends/loop/cfrunloop/loop.c` | one set; one Android main thread. `main_loop.quit` is set at `loop.c:128` and never cleared | C |

Already per app: the `ATLLoadedApp` instance fields (resources, class loader, package, application,
theme, running services, `:38-45`); `ContextImpl.atl_loaded_app` (`app/ContextImpl.java:49`);
`getPackageCodePath`; `getCacheDir` (`/tmp/atl_cache/<pkg>`, `Context.java:288`), `getObbDir`,
`getNoBackupFilesDir`; `Service.getApplication`. C

## Loading and discovery

- Primary: `loadFromPath` builds a `PathClassLoader` over api-impl's loader (ghax.jar first when
  `ATL_GHAX` is on), an AssetManager, Resources with `sys_config`, and v1 JAR certificates
  (`ATLLoadedApp.java:103-129`). C
- Guests: `ATLLoadedAppManager.loadApplication` loads `_installed_apks_/<pkg>.apk`, libs from
  `<base>/<pkg>_/lib` (`:109-144`); a GMS-family package without an APK becomes an ATLGStub fake
  (`ATLGStub.java:51-62`). C
- Visibility gate (`ATLLoadedAppManager.java:146-148`): a package is visible only when the source or
  target is `com.android.vending`, `com.google.android.gms` or `com.google.android.gsf`. The source
  is always the primary. Tachiyomi can see none of its extensions. C
- A guest never gets `Application.onCreate` (only `startup.c:317` calls it, for the primary); its
  providers and manifest receivers are not registered; `dataDir` is never set; every uid is -1
  (`content/pm/PackageParser.java:3372`). C
- Discovery reads only `<data base>/_installed_apks_` (`ATLPaths.java:21-32`). `--install` copies
  the APK under its original file name, only `--install-internal` writes `<pkg>.apk`
  (`main-executable/main.c:390-392`), so `--install`ed packages are not found as guests (U). C

## PackageManager

| API | Behaviour | Line (`content/pm/PackageManager.java`) |
|---|---|---|
| `getInstalledPackages(flags)` | the primary only, flags ignored | 1772-1775 |
| `getInstalledPackages(flags, user)`, `getInstalledApplications` | null | 1850, 2134 |
| `getPackageInfo` | primary generated with the flags; others through the gate; GET_META_DATA, GET_SIGNATURES (v1 only, `PackageParser.java:454,614-640`) and reqFeatures (`:326-329`) honoured | 1395-1412 |
| `getApplicationInfo` | the primary's cached info whatever the flags | 1606-1616 |
| `getLaunchIntentForPackage` | first LAUNCHER activity of the primary or a visible package, an `ACTION_MAIN` intent without `FLAG_ACTIVITY_NEW_TASK` (AOSP's sets it, unchecked here) | 1452-1468 |
| `resolveActivity`, `queryIntentActivities` | the primary only, action match only; http(s) VIEW returns a fake `atl.browser` | 2232-2330 |
| `queryIntentServices` | `intent.getPackage()` through the gate, else the primary | 2475-2500 |
| `resolveService` | null | 2456 |
| `getServiceInfo`, `getProviderInfo`, `resolveContentProvider` | the primary only | 1698-1740, 2555 |
| `getPackageUid`, `getPackagesForUid`, `checkSignatures` | -1, null, -1 | 1502, 2077, 2036 |

- `createPackageContext` (`app/ContextImpl.java:405-436`): itself, "android", a guest ContextImpl
  (INCLUDE_CODE and RESTRICTED honoured); an unknown package falls back to the primary. C
- `PackageInstaller` is a 25-line stub. `ACTION_INSTALL_PACKAGE` works only through
  `startActivityForResult`, which runs `android-translation-layer --install` with `ProcessBuilder`
  and waits (`app/Activity.java:329-340`). ACTION_VIEW of an APK is not special-cased. C

## Cross-package calls

- Explicit `startActivity` into another package uses only the class name (`ContextImpl.java:
  319-320`); `internalCreateActivity` loads it from the primary's loader and rewrites the
  component's package (`Activity.java:66`, `ATLLoadedApp.java:222`), so the start fails with a
  printed exception (U for the exception type). A guest starting its own activity fails the same
  way. C
- Implicit without data matches only the caller's own activities by action (`ContextImpl.java:
  368-375`); with data it goes to `nativeOpenURI` or `nativeOpenFile`, gtk-only natives (headless
  and iOS throw `UnsatisfiedLinkError`, U). C
- Of the start flags only `FLAG_ACTIVITY_CLEAR_TOP` is read (`ContextImpl.java:387`). NEW_TASK,
  NEW_DOCUMENT, MULTIPLE_TASK, `launchMode` and `taskAffinity` are ignored. C
- Services: `startOrBindService` (`ATLLoadedApp.java:234-283`) matches the target package's services
  by action, creates the service on the main looper and hands the `onBind` object to the client
  directly. `unbindService` does nothing (`Context.java:503`). C
- Binder is a stub: `queryLocalInterface` returns null, `transact` returns false, there is no
  `onTransact`, and `equals` is true for any two Binders (`os/Binder.java:31-43`). AIDL calls do
  nothing, also to a microG loaded in the same process (U). C
- `ContentResolver` reaches only `atl_providers`. `sendBroadcast` goes to `receiverMap` (every app,
  action match only, synchronous) plus the primary's manifest receivers (`Context.java:485-495`);
  `sendOrderedBroadcast` only prints. C
- Identity: `Process.myPid` is `getpid`, `myUid` is -1, `Binder.getCallingUid` is -1,
  `getCallingPid` is 0 (`os/Process.java:389-418`). C
- microG: loaded as a guest from `_installed_apks_/com.google.android.gms.apk` or stubbed;
  signatures spoofed (ATLSigHelper); c2dm REGISTER goes over D-Bus (`ContextImpl.java:245-302`). C

## Windows and tasks

- One `ui_window` per process (`atl_window`, `startup.c:40,299`); input goes to the records
  backend's `the_window->shown` (`records/ui.c:159-169`); dialogs are separate `ui_window`s. C
- One task: `activity_start` pushes onto `backlog` and shows in `atl_window` (`activity.c:297-320`);
  `moveTaskToBack` moves the whole stack; the last finish closes the window and quits the main
  loop (`records/ui.c:206-210`). An activity started "in a new task" lands on the same stack and
  window. C
- gtk: a GtkStack in one window; `isInMultiWindowMode` is `!maximized` (`gtk/window.c:10-68`). C
- The uikit backend defines Objective-C classes (`ATLView`, `ATLDialog`, `ATLLabel`, `ATLButton`,
  `ATLScrollView` and more in `backends/ui/uikit/view.m`, `dialog.m`), which can exist once per
  process. C

## Low-memory lifecycle

Nothing is implemented. C:
- `onLowMemory` and `onTrimMemory` are empty and never called; `ComponentCallbacks2` is an empty
  interface and `registerComponentCallbacks` does nothing (`Context.java:404-406`).
- `onSaveInstanceState` is empty and never called; `onRestoreInstanceState` does not exist;
  `activity_start` passes a null Bundle to `onCreate` (`activity.c:302,310`); `recreate()` makes a
  new instance without a Bundle (`Activity.java:520-536`); `View.saveHierarchyState` does nothing
  (`View.java:2697`).
- A configuration change updates `sys_config` in place; no `onConfigurationChanged` dispatch or
  activity recreation was found.
- `ActivityManager.getMemoryClass()` returns 20 and `getLargeMemoryClass()` 60, fixed
  (`app/ActivityManager.java:98-99`).
