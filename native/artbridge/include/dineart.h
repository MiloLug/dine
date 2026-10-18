#ifndef DINEART_H
#define DINEART_H

#ifdef __cplusplus
extern "C" {
#endif

/// Checks the platform facts ART depends on. Logs each result to os_log as
/// `art probe <name> <value>` and returns them newline-separated; the string stays valid until
/// the next call.
const char *dine_art_probe(void);

/// Runs `main_class`'s `main(String[])` from the dex jar `class_path` on a new thread. The first
/// call creates the process's only VM, with the boot jars and ANDROID_ROOT in `resource_dir` and
/// a writable `data_dir`; from then on the VM's stdout and stderr go to os_log. Returns 0, or -1
/// while a previous run is still active.
int dine_art_run(const char *resource_dir, const char *data_dir, const char *class_path,
                 const char *main_class);

#ifdef __cplusplus
}
#endif

#endif
