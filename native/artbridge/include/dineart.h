#ifndef DINEART_H
#define DINEART_H

#ifdef __cplusplus
extern "C" {
#endif

/// Checks the platform facts ART depends on. Logs each result to os_log as
/// `art probe <name> <value>` and returns them newline-separated; the string stays valid until
/// the next call.
const char *dine_art_probe(void);

/// Runs `main(String[])` of `main_class` (a binary name, `a.b.Main`) from the dex jar `class_path`
/// on a new thread, through one class loader per jar. The first call creates the process's only
/// VM, with the boot jars and ANDROID_ROOT in `resource_dir` and a writable `data_dir`; from then
/// on the VM's stdout and stderr go to os_log. Returns 0, or -1 while a previous run is still
/// active.
int dine_art_run(const char *resource_dir, const char *data_dir, const char *class_path,
                 const char *main_class);

/// Runs `activity` (NULL: the manifest's main one) of `apk` headless through ATL on a new thread
/// that stays its Android main thread. ATL's jars are in `atl_dir`; app data goes to
/// `data_dir`/atl. It creates the process's only VM, so it returns -1 once any run started.
int dine_atl_run(const char *resource_dir, const char *atl_dir, const char *data_dir,
                 const char *apk, const char *activity);

/// Logs `atl probe stack used N KiB`, the ATL main thread's deepest stack use since the VM was
/// created, and the process's physical footprint. For the debugger (`dbg call`).
void dine_atl_probe(void);

#ifdef __cplusplus
}
#endif

#endif
