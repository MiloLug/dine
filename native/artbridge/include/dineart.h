#ifndef DINEART_H
#define DINEART_H

#ifdef __cplusplus
extern "C" {
#endif

struct atl_app;               // atl/nav.h
struct atl_embedded_listener; // atl/nav.h

struct dine_atl_window {
  void *view;        // a UIView the app's views go in; it may adopt ATLSurface (atl/surface.h)
  int width, height; // px
  int density_dpi;   // 160 × the screen's scale: ATL converts px to the view's points with it
  int night;         // Configuration.UI_MODE_NIGHT_YES (0x20) or _NO (0x10); 0: unknown
};

/// A handle for the app `dine_atl_run` starts, which atl/nav.h's calls take, also before the
/// start. It lives as long as the process.
struct atl_app *dine_atl_app_new(void);

/// Runs `activity` (NULL: the manifest's main one) of `apk` as `app` through ATL on a new thread
/// that stays its Android main thread. ATL's jars are in `atl_dir`. `prefix_dir` holds the package
/// registry, installed APKs and app data (the APK is installed there unless it already is);
/// `cache_dir` the runtime's caches and tmp files. `listener` (copied; NULL: none) hears task
/// moves and the exit, on that thread; `exited` also comes when ATL can't start. `window` is
/// copied; ATL retains its view later, on that thread, so the caller keeps the view until
/// `exited`. The first run creates the process's only VM; each later one runs its app in that VM.
/// It returns -1, after logging why, while the first run is starting and when the art screen
/// made the VM; a package that already ran in this process gets `exited` with -1.
int dine_atl_run(const char *resource_dir, const char *atl_dir, const char *prefix_dir,
                 const char *cache_dir, const char *apk, const char *activity,
                 const struct dine_atl_window *window, const struct atl_embedded_listener *listener,
                 struct atl_app *app);

#ifdef __cplusplus
}
#endif

#endif
