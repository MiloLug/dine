# Filesystem slot: proposal

A slot that owns every path dine-atl hands to an app and the on-disk layout of Dine's data on each
platform. State: the path model, the hidden app-specific dirs and the picker's place are decided
(the user's words below); the rest is proposed, nothing built. The facts it rests on are
`findings.md`. The prefix and the one shared storage are decided in
`notes/multi-app-support/design.md` ("Prefix"); isolation between apps and from the host is
[ATL-32](../general-todo.md#atl-32); the OS features it touches are in `notes/os-features.md`.

## The user's words

- Linux: "all dine data is stored under the prefix, for example ~/.dine". The Android file
  explorer shows the shared storage "with Downloads, CIMD and other typical dirs. Under
  ~/.dine/shared". "all apps have access to shared, if allowed (typical android permissions
  thing)". "when an app needs to select a file, it uses the normal system dialog". "no app has
  access to the host files directly, only shared. I can either manually copy fiels to shared or
  hardlink something (for example, linking the downloads to linux downloads)". "apps don't use
  different virtual sdcards, they reside on one system storage. E.g. if some app sends a file:///
  link to another app, it must work."
- iOS: "all the same, except shared IS the dine public files, so any ios app can access it". The
  picker is the iOS file picker; "there's no shared subfloder, they are the dine files in picker".
- "later this filesystem could introduce some other platform-specific things. So it must be a
  separate slot. Also we need to move the data folders out of host".
- Paths: "mapped(1)" (Android's paths, mapped). Enforcement: "any app can just write whatever path
  they want. But this is fine for now. And on iphone it doesn't matter. So when we do
  filesystem/todo - let's add linux mounts and perms to the later stage"; the hardening is ATL-32.
- `Android/data`, `Android/obb`, `Android/media`: "hide".
- Picker: "the picker dialog is os-oriented in the first place, so it's not about our fs. We access
  our fs from it, through the host os means".

## The `fs` slot (proposed)

Owns:
- the prefix: where it is, its layout, creating it with the standard shared dirs;
- every path the framework hands out: an app's data, cache and code-cache dirs, external storage
  and its public dirs, the app-specific external dirs, each package's APK dir, `java.io.tmpdir`, the
  runtime's caches (ART's `ANDROID_DATA`, fontconfig's `XDG_CACHE_HOME`);
- the mapping between Android's paths and host paths, both ways;
- the host's view of the shared storage: the Files app keys on iOS;
- later, platform things: iOS backup exclusion, coordinating with other iOS apps that edit files in
  Documents, change notifications for `FileObserver` and a MediaStore scan.

Doesn't own anything that goes through the host OS's own services: the file picker (item 9), MIME
lookup (item 6), opening a file in another app and share (items 7 and 8), downloads (item 20,
which writes into `Download/`). They reach the prefix as files on the host. Isolation is ATL-32.

Backends: `linux` (desktop and headless builds; tests set a temporary prefix) and `ios`. A mount
namespace backend for Linux comes in the later stage (see "Later stage").

Java gets every root through one native, in place of `ATLPaths.java`'s copy of the env logic; an
app's data dir is its record's (`ApplicationInfo.dataDir`).

The `host` slot keeps process entry, VM creation, the classpath, launching an app and the window
container; its "data dirs" move to fs. What moves, from `findings.md`: `data_dir_base`,
`atl_app_prepare`'s dirs and the app's data dir (`struct atl_app`) in `shared/`; `ATLPaths.java`; the path
methods of `Context` and `Environment`, `getCacheDir`'s `/tmp/atl_cache`; artbridge's
`ANDROID_APP_DATA_DIR`, `ANDROID_DATA`, `XDG_CACHE_HOME` and `java.io.tmpdir`, and the Caches
argument from `AtlView`/`ArtView`; `NotificationManager.c`'s icon path; the storage rewrite of
`libc_bio_path_overrides.c` (glib-free); `StorageManager`'s volume.

## Layout (proposed)

Linux. The prefix is `~/.dine`, or `$DINE_PREFIX` (as Wine's `WINEPREFIX`):

```
~/.dine/
  shared/                       /storage/emulated/0, the one sdcard every app sees
    Alarms/ DCIM/ Documents/ Download/ Movies/ Music/ Notifications/ Pictures/ Podcasts/ Ringtones/
  shared-android/               /storage/emulated/0/Android, hidden
    data/<pkg>/ obb/<pkg>/ media/<pkg>/
  data/<pkg>/                   /data/user/0/<pkg>: files, shared_prefs, databases, no_backup, lib,
                                cache, code_cache
  apps/<pkg>/                   each installed package's APK; the multi-app registry sits next to it
  tmp/                          java.io.tmpdir
  runtime/                      ART's and fontconfig's caches
```

The shared dirs are Android's `Environment.DIRECTORY_*` names (`Download`, singular), created with
the prefix so a file manager shows them in an empty prefix. `/storage/emulated/0/Android` maps as a
whole to `shared-android/`, so an app's `mkdirs` of `Android/data/<pkg>/files` creates nothing in
`shared/`.

iOS:

```
Documents/                              shared, as the Files app's "Dine" folder (no shared/ level)
Library/Application Support/dine/       shared-android/, data/<pkg>/, apps/, the registry, runtime/
Library/Caches/dine/<pkg>/              each app's cache dirs, internal and external
tmp/                                    java.io.tmpdir
```

Private data leaves Caches, which iOS may purge; an app's cache dirs go there, since Android may
clear them as well. Documents holds only the shared storage. Info.plist gets `UIFileSharingEnabled`
and `LSSupportsOpeningDocumentsInPlace`; adding keys depends on `notes/os-features.md` item 1.

Existing data under `~/.local/share/android_translation_layer` and Caches is not migrated.

## Paths apps see (decided: Android's paths, mapped)

- `Environment` and `Context` return `/storage/emulated/0/...` and `/data/user/0/<pkg>/...`;
  `/sdcard`, `/mnt/sdcard`, `/storage/self/primary` and `/data/data/<pkg>` are aliases. A
  `file://` URI means the same file in every app, paths an app stores stay valid if the iOS
  container moves (whether it moves: `findings.md`, a probe), and hardcoded `/sdcard` works.
- fs maps them by rules, longest first; a rule can name the package (on iOS
  `/data/user/0/<pkg>/cache` goes to Caches). Paths that come back to apps (`getCanonicalPath`,
  `realpath`, `readlink`, `getcwd`) are mapped back.
- Linux runs the same mapping iOS needs, so the fast loop tests it.

### Where the mapping applies

Every path an app gets from Android's APIs is an Android path: `getFilesDir`, `getDataDir`,
`ApplicationInfo.dataDir`, `getExternalFilesDir`, and the NDK's `ANativeActivity`
`internalDataPath`/`externalDataPath`, which ATL fills from the Java dirs. Any code that hands such
a path to the OS has to go through the mapping:
- Java I/O: the entry points in `findings.md` (libcore's java.io, `Libcore.os`, NIO, `ZipFile`,
  ART's dex loading; ATL's SQLite open). dine-art can't link dine-atl, so libcore and ART get a hook
  that ATL registers at start (as bionic_translation's `libc_bio_set_apply_path_overrides_func`),
  the identity without ATL.
- The APK's own `.so` files (gtk build): every libc call they make goes through
  bionic_translation, which maps `open` and `fopen` today; `stat`, `opendir`, `mkdir`, `unlink`,
  `rename`, `access`, `realpath` and the other path calls need the same.
- iOS: no APK `.so` files load. iOS builds of known libraries that replace them are built by us
  and link against the same path wrappers.
- Libraries of our own that pick their own paths (fontconfig, ICU, ART's caches) get host paths
  from fs and need no mapping.

Doing the mapping once at the libc layer for the whole process (an interposer for `open`, `stat`
and the rest) would cover all of the above in one place. Traps: glibc's internal calls bypass
interposed symbols, and Mach-O's two-level namespace allows it on iOS only at static link time for
our own libraries (both U). Which of the two ways: decided when the stage is planned.

## Shared storage on the host

- Linux: `~/.dine/shared` is a plain dir. A directory can't be hardlinked; linking the Linux
  Downloads in is a symlink (`ln -s ~/Downloads ~/.dine/shared/Download`, after removing the empty
  dir). Files can be hardlinked.
- iOS: Documents shows in the Files app and in other apps' pickers as "Dine"; its subdirs are the
  shared dirs. Whether the Files app hides dot files (`.nomedia`, `.thumbnails`): U.

## Picker (decided: the `os` slot)

The picker is `notes/os-features.md` item 9. It reaches the shared storage through the host OS:
the Linux dialog opens `~/.dine/shared`, the iOS picker shows "Dine". The facts item 9 starts from
are in `findings.md` "Picker and URIs" (the gtk dialog hands apps a `file://` host path; tree URIs
have no provider behind them).

## Later stage

To be added as the later stage when the fs todo is written (the user's words above):
- Linux mounts: a mount namespace (as bubblewrap does) that binds `shared/`, `shared-android/` and
  `data/` at Android's paths, so they are real for all code and the host is out of reach. A
  symlink from `shared/` to a host dir then resolves only if that dir is bound in too.
  Unprivileged user namespaces may be disabled on some distros (U).
- Storage permissions: `READ_`/`WRITE_EXTERNAL_STORAGE` granted from the manifest at install, as
  SDK 21 does, in place of today's grant to every app. Checking them per call needs the calling
  app, which on iOS means the per-thread app record of the multi-app design.

Until then nothing stops code from opening any host path by absolute path.

## Depends on, and affects

- Multi-app: `design.md` "Prefix" points to this layout (approved with the design, 2026-11-02). MA1 built the prefix's root (`DINE_PREFIX`,
  `~/.dine`) with `registry.sqlite`, `apps/<pkg>/` and `data/<pkg>/`, the app's dirs set after VM
  start from its registry row; the rest of this layout and the `fs` slot are still to build.
- `notes/os-features.md` items 1 (Info.plist keys), 7 and 8 (files handed to other apps), 9 (the
  picker), 20 (`Download/`); [ART-11](../bug-tracker.md#art-11) (`java.nio.file` on iOS), one of
  the entry points.
- Notes to update once the stage is planned: the slot table and build table in
  `notes/atl-port.md` (the `host` row, a new `fs` row), `findings-hosting.md` "Storage on iOS", and the env var's readers listed in `findings.md`.

My calls, not asked: the slot name `fs`; `DINE_PREFIX` in place of `ANDROID_APP_DATA_DIR`, since it
names the whole prefix; `~/.dine` as the default; the shared dirs created with the prefix;
`shared-android/` as the hidden dir's name; each app's cache dirs in Caches on iOS; no migration;
MIME lookup (item 6) stays in the `os` slot, by the picker's reasoning.
