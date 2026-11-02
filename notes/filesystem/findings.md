# Findings: the filesystem today

Where Dine and dine-atl put an app's files, how apps reach them, and which code paths a mapping of
Android paths would have to cover. A snapshot read on 2026-11-02; line numbers drift. **C**: read
in code. **U**: unchecked (iOS knowledge or inference). The proposal built on it is `proposal.md`.

## Where the paths come from

- No slot owns paths. The data base is computed in `dine-atl/src/shared/startup.c:91-114`
  (`data_dir_base`): `$ANDROID_APP_DATA_DIR`, else `$XDG_DATA_HOME/android_translation_layer`, else
  `~/.local/share/android_translation_layer`. `atl_set_app` (`:116-151`) makes the app's dir
  `<base>/<APK file name>_/` and `lib/` in it; `get_app_data_dir` (`:43`) hands it to C. The `host`
  row of the slot table in `notes/atl-port.md` lists "data dirs", but no host backend computes
  them. C
- `ATLPaths.java` repeats the same env logic in Java (its comment: "Mirror how main.c calculates
  app_data_dir_base") for `app_data_dir_base` and `_installed_apks_`, which
  `ATLLoadedAppManager.java:86,121-122` uses for installed APKs and their libs. C
- Java gets the app's dir through one native, `Environment.native_get_app_data_dir`
  (`api-impl-jni/android_os_Environment.c`). `Environment.getExternalStorageDirectory()` returns
  it (`Environment.java:328-333`), and `Context` builds every app path on top of
  `getExternalStorageDirectory()`: `ApplicationInfo.dataDir` and `nativeLibraryDir`
  (`Context.java:119-120`), `getDataDir` (`:229-237`), `files/`, `shared_prefs/`, `databases/`,
  `no_backup/<pkg>`, `Android/obb/<pkg>`. External storage and the app's private dir are one dir:
  each app has its own sdcard. C
- `getExternalFilesDir(type)` returns `getFilesDir()` and ignores the type; `getExternalCacheDir`
  returns `getCacheDir()` (`Context.java:257-308`). `openFileOutput` builds its path from
  `getExternalStorageDirectory()` directly instead of `getFilesDir()` (`:393`). C
- `getCacheDir` is `/tmp/atl_cache/<pkg>` on every build (`Context.java:286-296`). C
- `Environment.getDataDirectory()` is `$ANDROID_DATA`, else `/data` (`Environment.java:255`);
  `/data/media` and `/data/secure` are hardcoded defaults (`:62,260`). C
- `android_app_NotificationManager.c:125` builds an icon path from `get_app_data_dir()`. C
- `StorageManager` reports one volume and gets the cache quota from `StatFs` of
  `Environment.getDataDirectory()` (`os/storage/StorageManager.java`). C

## Dine on iOS

- artbridge sets `ANDROID_APP_DATA_DIR=<data_dir>/atl` (`native/artbridge/artbridge.cpp:174-177`),
  and `ANDROID_ROOT`, `ANDROID_DATA=<data_dir>`, `XDG_CACHE_HOME=<data_dir>`,
  `-Djava.io.tmpdir=<data_dir>` (`:104-117`). `data_dir` is Caches (`Dev/AtlView.swift:46`,
  `Dev/ArtView.swift:39`), which iOS may purge (U, iOS knowledge). C
- Application Support holds only `dine.sqlite` (`AppLibrary.swift:25`). Documents is unused. C
- `apps/Dine/xtool.yml`'s `infoPath` is accord's generated plist; it has neither
  `UIFileSharingEnabled` nor `LSSupportsOpeningDocumentsInPlace`, the two keys that show an app's
  Documents in the Files app as "On My iPhone > Dine" and let other apps open files there in place
  (the keys: U, iOS knowledge). Merging extra keys is an open point of `notes/os-features.md` item
  1. C
- Whether an app's data container path (`/var/mobile/Containers/Data/Application/<UUID>/`) stays
  the same across a reinstall or an update by xtool: U. Apple's guidance is to never store
  absolute container paths (iOS knowledge). A free account's profile expires after 7 days (iOS
  knowledge, U). Whether `tools/dine ios run` or a re-sign moves the data container is what the
  probe answers: log `NSHomeDirectory()`, run `tools/dine ios run`, compare.
- Whether `/tmp` is writable for `getCacheDir`: U.
- The iOS build loads no APK `.so` files (`notes/meta.md`, code signing), so guest native code
  doesn't touch files there. C

## Who reads `ANDROID_APP_DATA_DIR`

Code: `dine-atl/src/shared/startup.c`, `startup.h`, `ATLPaths.java`, `main-executable/main.c:415`
(passed on by `--install`), `backends/host/embedded/atl_embedded.h` (contract line),
`native/artbridge/artbridge.cpp`. Tests and tools: `tests/harness/apps.py:66`,
`tests/harness/framework.py:113`, `tools/py/dine/dbg/targets/gtk.py:99`, nine
`dine-atl/tests/headless/run-*.sh`. Docs: `README.md`, `dine-atl/README.md`, `dine-atl/doc/Envs.md`,
`notes/dev-reference.md`, `notes/multi-app-support/design.md`, `findings-hosting.md`. C

## Path rewriting

- `main-executable/libc_bio_path_overrides.c` rewrites `/storage/emulated/0/` into the app's dir,
  maps `/system/etc/fonts.xml` and `/system/fonts/*` through fontconfig, and logs `/system/` and
  `/data/` access. It uses glib. C
- It runs only for guest native code: bionic_translation calls it from `bionic_open` and
  `bionic_fopen` (`third_party/bionic_translation/libc/libc-open-overrides.c`), and only the gtk executable
  registers it (`main.c:562-572`; `meson.build:368` builds it into the gtk executable only).
  Java file I/O, the headless build and iOS never see it. C
- `/sdcard`, `/mnt/sdcard`, `/storage/self/primary`, `/data/data/<pkg>`, `/data/user/0/<pkg>`:
  nothing maps them. C

## Path entry points

The places a mapping between Android paths and host paths would have to cover, by layer. C unless
marked.

| Layer | Where | Count or form |
|---|---|---|
| `java.io.File` | `libcore/ojluni/src/main/native/UnixFileSystem_md.c` | 15 natives; paths through `WITH_PLATFORM_STRING` / `WITH_FIELD_PLATFORM_STRING` (`io_util.h:87`), 16 uses |
| `FileInputStream`, `FileOutputStream` | native `open0`, `io_util_md.c` `fileOpen` | one `WITH_PLATFORM_STRING` use |
| `RandomAccessFile`, `android.system.Os` | `IoBridge.open`, then `Libcore.os` | `Libcore.os` is a non-final static (`Libcore.java:32`), already wrapped by `BlockGuardOs`; `ForwardingOs` exists. Natives in `libcore_io_Linux.cpp` (38 `ScopedUtfChars`, not all paths) |
| `java.nio.file` | `UnixNativeDispatcher.c` | broken on iOS anyway ([ART-11](../bug-tracker.md#art-11)) |
| `ZipFile` | native `open(String name, ...)` (`ZipFile.java:838`) | one |
| dex loading (`DexClassLoader`, `DexFile`) | `art/runtime/native/dalvik_system_DexFile.cc` | U: count not taken |
| SQLite | `android_database_SQLiteConnection.c:133` `sqlite3_open_v2(path)` | one, plus sqlite's own journal and WAL files next to it |
| guest native code | bionic_translation `bionic_open`, `bionic_fopen` | gtk only; `stat`, `opendir` and the rest unhooked |
| NDK `ANativeActivity` | `internalDataPath`, `externalDataPath` filled from Java's dirs (`android_app_NativeActivity.c:345-349`) | native code opens them through libc |
| paths returned to apps | `canonicalize0`, `realpath`, `readlink`, `getcwd` (`user.dir`, `System.c`) | would need the reverse mapping (U: full list) |

## Picker and URIs

- `ACTION_OPEN_DOCUMENT`, `CREATE_DOCUMENT`, `OPEN_DOCUMENT_TREE` and `GET_CONTENT` call
  `Activity.nativeFileChooser` with GtkFileChooserAction ints (`Activity.java:296-328`). The gtk
  dialog returns `g_file_get_uri()` (`api-impl-jni/app/android_app_Activity.c:53`): a `file://` URI
  of the host path. Apps get host paths. C
- No `DocumentsProvider` exists. `DocumentsContract`'s tree helpers build `content://` tree URIs
  from the tree URI's authority (`DocumentsContract.java:101-121`); with a `file://` tree from the
  picker that has no provider behind it (what apps then get: U). `createDocument` and
  `copyDocument` throw. C
- `ContentResolver` opens `file://` URIs directly and asks `native_query_file_info` (GIO) for
  `_display_name` and `mime_type`; `content://` goes to an in-process provider by authority, else
  null (`ContentResolver.java:36-110`). C
- `ATLMediaContentProvider` opens a GtkFileDialog to pick a media folder
  (`api-impl-jni/content/android_atl_ATLMediaContentProvider.c:24-26`). C

## Permissions

- `READ_EXTERNAL_STORAGE` and `WRITE_EXTERNAL_STORAGE` are always granted
  (`content/pm/PackageManager.java:1872-1878`), with upstream's comment: "we shouldn't just
  automatically grant these once we have bubblewrap set up; for now, the app can access anything it
  wants". `requestPermissions` logs and does nothing (`Activity.java:705-706`). C
- At SDK 21 both are install-time permissions: no runtime prompt exists on Android 5 (Android
  knowledge). Isolation between apps and from the host is
  [ATL-32](../general-todo.md#atl-32), later. C for the note.
