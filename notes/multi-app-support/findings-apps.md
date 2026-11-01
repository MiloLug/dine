# Findings: how real apps use the multi-app parts of Android

What the scenario apps call, and how Android itself handles low memory and app identity, so the
layer knows what to provide. Researched on the web on 2026-10-31 from source files and Android
docs; line numbers are for the branch heads of that day. **unsourced**: from memory, no source.
The design that answers these is `design.md`.

## Mihon and TachiyomiSY extensions

TachiyomiSY's `ExtensionLoader.kt` and `ExtensionInstaller.kt` differ from Mihon's by one import;
lines are Mihon's (https://github.com/mihonapp/mihon, `app/src/main/java/eu/kanade/tachiyomi/
extension/util/`).

- Discovery: `getInstalledPackages(GET_CONFIGURATIONS | GET_META_DATA | GET_SIGNATURES
  [| GET_SIGNING_CERTIFICATES on 28+])` (`ExtensionLoader.kt:57-60,114`). A package is an extension
  when `reqFeatures` contains `tachiyomi.extension` (`:480`). Single package: `getPackageInfo`
  (`:232`); private APK files: `getPackageArchiveInfo(path, flags)` (`:148,218`).
- Metadata keys (`:45-52`): `tachiyomi.extension.class` (`;`-separated, a leading `.` is
  package-relative), `tachiyomi.extension.factory`, `tachiyomi.extension.nsfw`, `tachiyomix.name`,
  `tachiyomix.extensionLib`, `tachiyomix.contentWarning`. Supported lib versions 1.4 and 1.6.
- Loading: `DelegateLastClassLoaderCompat(appInfo.sourceDir, null, context.classLoader)` (`:392`):
  the platform `DelegateLastClassLoader`, or a `PathClassLoader` subclass that looks in the boot
  loader, then its own dex, then the parent (Tachiyomi's loader). Classes by `Class.forName(name,
  false, loader)`.
- Install, by user preference LEGACY, PACKAGEINSTALLER, SHIZUKU or PRIVATE (TachiyomiSY
  `BasePreferences.kt:33-38`):
  - LEGACY: `ACTION_INSTALL_PACKAGE` with `EXTRA_RETURN_RESULT` and a read URI grant;
  - PACKAGEINSTALLER: a `MODE_FULL_INSTALL` session, `setRequireUserAction(NOT_REQUIRED)` on 31+,
    `openWrite`, `fsync`, `commit` with a broadcast PendingIntent; `STATUS_PENDING_USER_ACTION`
    starts `EXTRA_INTENT`;
  - SHIZUKU: a Shizuku user service;
  - PRIVATE: `filesDir/exts/<pkg>.ext` written through a `.part` file, read-only, rejecting a lower
    versionCode or changed signatures, then an app-internal broadcast. A shared install wins over a
    private one at an equal or higher versionCode.
- Trust: SHA-256 of the signing certificates; trusted when the repo's signing key matches or the
  user trusted `<pkg>:<versionCode>:<sigHash>`.
- Events: a runtime receiver (`RECEIVER_NOT_EXPORTED`) for `PACKAGE_ADDED/REPLACED/REMOVED` with
  scheme `package`. Host permissions: `QUERY_ALL_PACKAGES`, `REQUEST_INSTALL_PACKAGES`,
  `REQUEST_DELETE_PACKAGES`, `UPDATE_PACKAGES_WITHOUT_USER_ACTION`.

## F-Droid and Droid-ify

- F-Droid (https://gitlab.com/fdroid/fdroidclient): a session install with
  `setPackageSource(STORE)` and `setRequestUpdateOwnership(true)`, result to a not-exported
  receiver (`install/SessionInstallManager.kt:426-446`); `ACTION_INSTALL_PACKAGE` with a
  FileProvider URI as fallback (`:531`). "Open" is `getLaunchIntentForPackage` plus `startActivity`
  (`ui/details/AppDetailsViewModel.kt:121`). It tracks installs with a runtime receiver for
  `PACKAGE_ADDED/REMOVED` and `getInstalledPackages(GET_SIGNATURES)` at start
  (`install/InstalledAppsCache.kt:42-43`).
- Droid-ify (https://github.com/Droid-ify/client): the same session pattern, plus legacy, root and
  Shizuku installers. "Open" queries `ACTION_MAIN`/`CATEGORY_LAUNCHER` activities of the package and
  starts an explicit component with `FLAG_ACTIVITY_NEW_TASK` (`ui/appDetail/AppDetailFragment.kt:
  500-507`).

## microG GmsCore

https://github.com/microg/GmsCore

- Clients bind with `Intent(action).setPackage("com.google.android.gms")` and `BIND_AUTO_CREATE`
  (`play-services-base/.../MultiConnectionKeeper.java:246-290`). They accept the target only when it
  is a system app (`FLAG_SYSTEM` or an updated system app) or carries a Google or microG signature
  (`:66-78`).
- Actions come from the `GmsService` enum (`com.google.android.gms.common.service.START`,
  `...signin.service.START`, ...). The bound object is an `IGmsServiceBroker`; clients call
  `getService(callback, GetServiceRequest{serviceId, packageName, extras})`.
- Caller checks (`play-services-base/core/.../PackageUtils.java`): `Binder.getCallingUid` and
  `getCallingPid`; the pid maps to a package through `getRunningAppProcesses` (one package per
  process), else `getPackagesForUid(uid)`; a mismatch with the claimed package is a
  `SecurityException`. Sign-in uses the SHA-1 of the caller's signature.
- Providers: `content://com.google.android.gsf.gservices` (reads need the same uid, a Google
  package, or the `READ_GSERVICES` permission) and `com.google.settings`.
- Signature spoofing: the system must report Google's signature for `com.google.android.gms`
  (`android.permission.FAKE_PACKAGE_SIGNATURE`).
- What a host must provide (inference): bind by action to a named package, signatures in
  `getPackageInfo`, `getPackagesForUid`, a per-call `getCallingUid`/`getCallingPid` that names the
  real caller, `getRunningAppProcesses`, `FLAG_SYSTEM` for GmsCore, a spoofed signature, and
  providers that know their caller. With every app in one process and one OS uid, the layer has to
  carry the caller's identity itself.

## A second window

- `FLAG_ACTIVITY_NEW_DOCUMENT` and `documentLaunchMode` are API 21 (`always` equals
  `NEW_DOCUMENT | MULTIPLE_TASK`); `FLAG_ACTIVITY_MULTIPLE_TASK` is API 1 and pairs with NEW_TASK or
  NEW_DOCUMENT; `FLAG_ACTIVITY_LAUNCH_ADJACENT` is API 24; `singleInstancePerTask` is API 31;
  `PROPERTY_SUPPORTS_MULTI_INSTANCE_SYSTEM_UI` is Android 15 and only adds a System UI button
  (https://developer.android.com/reference/android/content/Intent,
  https://developer.android.com/develop/adaptive-apps/guides/support-desktop-windowing). In desktop
  windowing a new task opens as a new window.
- Chrome's "New Window" uses `singleInstancePerTask` with `LAUNCH_ADJACENT | NEW_TASK`
  (android-developers blog, 2022-02). Chromium's default minSdk is 29 and Chrome ships its own
  `libchrome` native code, so Chrome itself can't run on an SDK 21, interpreted layer; the API 21
  flags above can.

## Android's low-memory model

- Process states: foreground, visible, service, cached
  (https://developer.android.com/guide/components/activities/process-lifecycle). lmkd kills by
  `oom_adj` (https://source.android.com/docs/core/perf/lmkd).
- `onTrimMemory`: `TRIM_MEMORY_UI_HIDDEN` (20) and `TRIM_MEMORY_BACKGROUND` (40) are delivered;
  the other levels are deprecated in API 35 and not sent since API 34.
- Saved state: `onSaveInstanceState` runs after `onStop` for apps targeting P and later, before it
  for older ones. The Bundle goes to system_server (`ActivityRecord.mIcicle`), which outlives the
  app's process; after a kill the activity is relaunched in a new process with that Bundle in
  `onCreate(savedInstanceState)` (AOSP `ActivityThread.java`, `ActivityRecord.java`,
  `ActivityTaskSupervisor.realStartActivityLocked`).
- Cached apps freezer (Android 11+, cgroup v2): cached processes are frozen 10 s after becoming
  cached on Android 14+ and stay in RAM; they thaw when their state rises or for manifest broadcast
  delivery; processes holding contended file locks or serving binder to uncached clients are exempt
  (https://source.android.com/docs/core/perf/cached-apps-freezer).

## Prior art: several APKs in one host

- VirtualApp (https://github.com/asLody/VirtualApp) runs each guest app in its own stub process
  (50 stubs), hooks about 40 system services, swaps stub intents for real ones, and hooks native
  `getCallingUid` to map pid to a virtual uid. Framework statics are isolated by the process, not
  inside one VM. VirtualXposed builds on it.
- RePlugin and DroidPlugin load plugins through class-loader and service-proxy hooks with stub
  components; whether plugins share the host process by default is **unsourced**.
- `sharedUserId` plus a shared `android:process` puts apps in one process only when they share a
  signature; `sharedUserId` is deprecated since API 29.
- No source found isolates framework static state for unrelated apps inside one VM.
