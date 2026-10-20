#ifndef DINEART_H
#define DINEART_H

#ifdef __cplusplus
extern "C" {
#endif

struct atl_embedded_listener; // atl/nav.h

struct dine_atl_window {
  void *view;        // a UIView the app's views go in; it may adopt ATLSurface (atl/surface.h)
  int width, height; // px
  int density_dpi;   // 160 × the screen's scale: ATL converts px to the view's points with it
  int night;         // Configuration.UI_MODE_NIGHT_YES (0x20) or _NO (0x10); 0: unknown
};

/// Runs `activity` (NULL: the manifest's main one) of `apk` through ATL on a new thread that
/// stays its Android main thread. ATL's jars are in `atl_dir`; app data goes to `data_dir`/atl.
/// `listener` (copied; NULL: none) hears task moves and the exit, on that thread; `exited` also
/// comes when ATL can't start. `window` is copied; ATL retains its view later, on that thread, so
/// the caller keeps the view until `exited`. It creates the process's only VM, so it returns -1
/// once any run started, after logging why.
int dine_atl_run(const char *resource_dir, const char *atl_dir, const char *data_dir,
                 const char *apk, const char *activity, const struct dine_atl_window *window,
                 const struct atl_embedded_listener *listener);

#ifdef __cplusplus
}
#endif

#endif
