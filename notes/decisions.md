# Decisions

Short entries that steer porting upstream changes into our forks. Newest first within a section.

## dine-atl

- Our delta: `git diff upstream/master...dine`. Local `master` lags upstream.
- Upstream isn't merged: read its commits since the last merge and reimplement the wanted ones
  by hand.
- EditText's text is Java's Editable (AOSP's TextView setText, ChangeWatcher and listener list, in
  `EditText.java`); the toolkit field reports each edit to `EditText.atlEdited` and takes Java's
  snapshots (`ui_edit_*`, `src/shared/android_widget_EditText.c`). The gtk GtkText is
  `src/backends/ui/gtk/edit.c`; the legacy EditText natives are gone: port upstream EditText fixes
  into the Java or that file. InputMethodManager's keyboard state is Java; only a view with its
  own InputConnection reaches the gtk IM context (`nativeInit`, lazily).
- Input is AOSP's Java: View/ViewGroup touch dispatch and `onTouchEvent`, focus, FocusFinder, the
  Activity/Dialog key chain. Backends call `atl_upcall_touch`/`atl_upcall_key`
  (`src/shared/input.c`) for a window's root view, which reach `android.view.ATLInput`
  (ViewRootImpl's part: touch mode, focus navigation; ESC falls back to BACK there, ATL's own
  choice). `onTouchEventInternal`,
  `ViewGroup.native_dispatchTouchEvent`, the listener and focus natives and GTK's per-widget input
  controllers are gone: drop upstream edits to them, port upstream input fixes into the Java.
- gtk input: one capture-phase touch controller and key controllers per GtkWindow
  (`src/backends/ui/gtk/input.c`). A legacy constructor of a widget that takes its own presses
  calls `input_take_native`; upstream's new GTK widgets of that kind need it. The Button family's
  widgets take no presses: drop upstream's click and toggle signal handlers for them.
- MotionEvent's pointer methods are Java over `ids`/`coords` (`split`, `getPointerIdBits`,
  `findPointerIndex`, `offsetLocation`, `transform`); the hosts' constructor takes the down time;
  single-pointer `obtain` uses pointer id 0.
- Scroll is the toolkit's: `ui_scroll_new`, `ui_view_scroll_to`, `View.atlScrolled` mirrors the
  offset and drops echoes. Port upstream ScrollView edits into this ScrollView, not its AOSP
  ScrollView branch.
- DrawableContainer's natives are shared behind `gfx_container_*`; ContainerPaintable is gsk's
  (`src/backends/gfx/gsk/container.c`).
- `ViewGroup.shouldDelayChildPressedState` is AOSP's true; FrameLayout, LinearLayout, RelativeLayout
  and AbsoluteLayout say false. ViewConfiguration's scaled values are dp.
- `atl_nav_back` is BACK down and up through `ATLInput.key`: a shown dialog takes it.
- Code ported from AOSP keeps its notice and goes in `doc/AOSP.md`; `LICENSE-APACHE-2.0.txt` holds
  the license.
- The host's window (`struct atl_window_config`: px size, density, night) goes to `atl_vm_init`,
  which sets `Display.window_*` and `Display.density_dpi`; `DisplayMetrics.getDeviceDensity` and
  `AssetManager_init` read it, `atl_display_apply` writes dp. Port upstream density code there.
- TextView sizes go through one px method, package-private `setRawTextSize`; `setTextSize(float)`
  is sp. EditText overrides `setRawTextSize`, not `setTextSize`: port upstream overrides that way.
- `setTypeface(tf, style)` calls `native_setTextStyle` (`ui_text_set_style`); gtk's `ATL-font-*`
  CSS classes are in `src/backends/ui/gtk/text.c`. `setAllCaps` upper-cases the shown text in
  TextView's Java, `setTextAlignment` calls `ui_text_set_alignment`, and the gtk button backend sets
  `ATL-no-border` from the view's background; `native_addClass` and its siblings are gone: drop
  upstream edits to them.
- Button family: `Button.native_new(kind)` (`src/shared/android_widget_Button.c`) makes a
  `ui_button_new` text node; CompoundButton is AOSP 10's (Java checked state, toggle on
  `performClick`, RadioGroup's widget listener). Their legacy gtk natives are gone: port upstream
  widget fixes into the Java or `src/backends/ui/gtk/widgets.c`.
- `src/backends/ui/records/` serves headless and uikit through the hooks in `records.h`;
  headless metrics are in `headless/views.c`, UIKit views in `uikit/view.m`.
- `ViewGroup.native_removeView` and `View.native_destructor` are in `src/shared/` behind
  `ui_view_remove_child` and `ui_view_free`; gtk's bodies are in `src/backends/ui/gtk/view.c`, and
  its remove skips a child held by another parent. The destructor posts the free to the main loop,
  so gtk's unref runs on the GTK thread.
- `atl_display_apply` writes `UI_MODE_TYPE_NORMAL` into `uiMode`, and night only when known.
- `Drawable.native_ref`/`native_unref` are in `src/shared/` behind `gfx_drawable_ref`/`_unref`
  (gsk: `g_object_ref`/`unref` in `gfx/gsk/paint.c`); unref posts to the main loop.
- Paintable ownership: a native that makes one hands over its ref; Java takes it with
  `adoptPaintable` (NinePatchDrawable, `Drawable(long)`), `setPaintable` refs a borrowed one
  (BitmapDrawable). DrawableContainer has no constructor: `Drawable()` calls its
  `native_constructor`. ContainerPaintable refs its child; NinePatchPaintable frees its texture
  and chunk. Port upstream drawable constructors that way.
- C code that a post, a GTK callback or host startup runs is in the Android thread's base JNI
  frame, which never pops: `task_move`, `activity_close_all`, `atl_upcall_display_changed` and
  WrapperWidget's `get_property` push a local frame, other spots delete their refs.
- `defines.h`: the `_GET/_SET_*_FIELD` macros look up through `_FIELD_ID_OF`, and
  `_METHOD_OF(obj, …)` replaces `_METHOD(_CLASS(obj), …)`; both delete the class ref. Port
  upstream `_METHOD(_CLASS(x), …)` as `_METHOD_OF(x, …)`.
- `Dialog.finalize` → `nativeDestroy` → `ui_dialog_free`, posted to the main loop. gtk's
  `ui_window_set_java` frees the old ref (data destroy notify), and `WrapperWidget`'s root-change
  callback skips collected views.
- meson `test_hooks` (default on): `ATL_DIALOG_ANSWERS` and the view-tree dump live in
  `src/shared/test_hooks.c` and `src/backends/ui/{records,gtk}/dump.c`; callers see inline no-ops
  from `test_hooks.h` without it. Dine's iOS release build turns it off. With
  `ATL_DUMP_VIEWTREE`, records backends also print `viewfreed:`, `dialogfreed:` and
  `drawablefreed: record` lines; gsk's paintables print `drawablefreed: <GType name>`.
- `jstring_to_utf8` (`util.c`) gives ui slots valid UTF-8 (U+FFFD for U+0000 and lone
  surrogates); the `src/shared/` text natives use it. `attribute_set_get_string` returns its
  result, so callers `free()` it (gtk `Button.c` too). Upstream's gtk-only text natives keep
  `GetStringUTFChars`.
- Dialogs follow the task: `task_move` calls the static `Dialog.atlTaskMoved`
  (`handle_cache.dialog`) before the lifecycle; `Dialog.nativeTaskFront` reads `activity.c`'s task
  state. `show()` in the back waits for the front; results count only while drawn; `shown` is a
  `LinkedHashSet`.
- Natives moved into `src/shared/` or `src/backends/` take upstream edits as ports, not merges:
  e.g. `View.native_constructor` is `src/shared/android_view_View.c` + `ui_view_new`.
- JavaWidget is defined in `src/backends/ui/gtk/view.c`; legacy `View.c` and `ViewGroup.c` only
  declare it. Drop upstream's definition from `View.c`.
- Dialog and AlertDialog are ours: natives in `src/shared/android_app_Dialog.c`, GTK in
  `src/backends/ui/gtk/dialog.c`. Port upstream Dialog fixes there. `getButton` returns
  AlertDialog's own Button views (AOSP's AlertController semantics: their click listener is the
  dialog's listener and dismiss), changed in place through `ui_dialog_set_button`;
  `atlDialogResult` returns whether the dialog is still drawn. `ATLKeyboardDialog.nativeInit` uses
  `ui_dialog_new`.
- `Activity.onBackPressed` moves the task root to the back when the host allows (gtk doesn't);
  `moveTaskToBack` is public and real; `activity.c` keeps task state and an activity's `stopped`.
- `DialogInterface.OnCancelListener.onCancel` added (upstream's is empty).
- `SDK_INT` is a device level set by hand: `ro.build.version.sdk` in `SystemProperties.java` (21),
  read by `Build.VERSION`; `RESOURCES_SDK_INT` = `SDK_INT`; `CODENAME` "REL". Upstream's derivation
  (`EarlyPackageParser`, `-DBuild.VERSION.SDK_INT`, `--sdk-int` and `create_vm`'s `sdk_int` in
  `main.c`, now `startup.c`) is gone; a minSdk above it logs and runs (`PackageParser`). Drop
  upstream SDK_INT edits there. bionic_translation's native `ro.build.version.sdk` (`libc.c`, Linux
  only) also says 21; raising ours past it needs a local patch of that plain clone.
- `Window` keeps the system bar state (`styleBars`, `updateFrame`, real `addFlags`/`setFlags`);
  `activity_focus` and the `set_frame` native send the shown activity's frame to
  `ui_window_set_frame` (gtk: header bar CSS). `View.setSystemUiVisibility` calls the gtk-only
  `nativeSetFullscreen` only when the fullscreen bits change, and tells the decor's Window the
  light flag. Port upstream Window/system-bar edits there.
- Matrix natives are in `src/shared/android_graphics_Matrix.c` (graphene; the wrap
  `subprojects/graphene.wrap` outside the desktop build). Port upstream Matrix fixes there.
- Paint state natives are shared behind `gfx_paint_*`; gsk's bodies are in
  `src/backends/gfx/gsk/paint.c`. Text bounds and font metrics stay in upstream's file (gtk).
- `getLocationInWindow/OnScreen`, `getGlobalVisibleRect`, `offset*RectInto*` and the observer's
  window are Java (no natives): drop upstream edits to those natives.
- Attach state is Java (`dispatchAttachedToWindow`/`dispatchDetachedFromWindow`, `isAttachedToWindow`
  a field); gtk's `notify::root` callback and `currently_unmapping` are gone. Port upstream attach
  fixes into View/ViewGroup Java.
- Visibility, background drawable, invalidate, translation (`native_childrenMoved`), markup,
  multi-window, ImageView, ProgressBar and ViewTreeObserver natives are shared behind ui slot calls;
  gtk's bodies are in `src/backends/ui/gtk/{view,widgets,window,text}.c`.
- Fullscreen and keep-screen-on are Window state sent for the shown activity (`set_frame`,
  `set_keep_screen_on`); `View.nativeSetFullscreen` and `native_keep_screen_on` are gone.
  `FLAG_KEEP_SCREEN_ON` is Android's 0x80.
- The cli host has `--instrument`; `test_runner.jar` builds in the headless build dir.
- The C targets depend on hax.jar (order-only), so javac rewrites the JNI headers first.
- Insets are ours: `WindowInsets` stores per type; View/ViewGroup `dispatchApplyWindowInsets` is the
  pre-API-30 dispatch; `fitsSystemWindows` is real (default false). The host's insets come through
  `atl_nav_set_insets` and `Window.dispatchInsets`; exclusion rects through the Window's tracker and
  `src/shared/insets.c`. Port upstream insets edits there.
- Last merge: upstream d658957d (2026-10-20); hand ports start there.

## dine-art

- `install-ios` puts ART's junit boot jars in `share/art-junit`, apart from the runtime jars:
  Dine's release builds leave them off the boot class path.
- Park's platform calls live in `ParkWait`/`ParkWake` (`art/runtime/thread.cc`): futex on Linux,
  os_sync on Apple. Resolve upstream edits to `Thread::Park/Unpark` there.
- Apple `parkUntil` becomes a timeout at entry: no wall-clock tracking, device sleep delays it.
- Apple keeps pthread mutexes, condvars and RW locks; only park uses os_sync.

## dine

- Min iOS 17.4 (os_sync): `env.sh` for scripts and CMake, `apps/Dine/Package.swift` for Swift.
  Never equal to the SDK version (compatibility mode).
- Linux gate after a merge: `tools/dine linux smoke` (gd, demo, demo-480, looper, dialog, dialog-gtk, nav,
  views, views-gtk, widgets, controls) + `tools/dine test runtime` + `tools/dine test framework`; iOS gate:
  `tools/dine dbg smoke`.
