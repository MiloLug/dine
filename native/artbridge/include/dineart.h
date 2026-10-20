#ifndef DINEART_H
#define DINEART_H

#ifdef __cplusplus
extern "C" {
#endif

struct atl_embedded_listener; // atl/nav.h

/// Runs `activity` (NULL: the manifest's main one) of `apk` through ATL on a new thread that
/// stays its Android main thread. ATL's jars are in `atl_dir`; app data goes to `data_dir`/atl.
/// `listener` (copied; NULL: none) hears task moves and the exit, on that thread; `exited` also
/// comes when ATL can't start. It creates the process's only VM, so it returns -1 once any run
/// started, after logging why.
int dine_atl_run(const char *resource_dir, const char *atl_dir, const char *data_dir,
                 const char *apk, const char *activity, const struct atl_embedded_listener *listener);

#ifdef __cplusplus
}
#endif

#endif
