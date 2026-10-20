#ifndef DINEART_DEV_H
#define DINEART_DEV_H

// Dev builds only: artbridge's dev.cpp (CMake DINE_DEV).

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
/// on the VM's stdout and stderr go to os_log. Returns 0, or -1 after logging why not: a
/// previous run is still active, or VM creation failed in this process.
int dine_art_run(const char *resource_dir, const char *data_dir, const char *class_path,
                 const char *main_class);

/// Logs `atl probe now: stack used N KiB …`, the ATL main thread's deepest stack use so far, and
/// the process's physical footprint and its peak. For the debugger (`dbg call`).
void dine_atl_probe(void);

#ifdef __cplusplus
}
#endif

#endif
