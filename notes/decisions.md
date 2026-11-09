# Decisions

Short entries that steer porting upstream changes into our forks. Newest first within a section.

## dine-atl

- Our delta: `git diff upstream/master...dine`. Local `master` lags upstream.
- Upstream isn't merged: read its commits since the last merge and reimplement the wanted ones
  by hand.
- The keyboard is the host's IME inset (`atl_window_insets.ime`). adjustResize lays a window out
  above it (`windows_area`) and clips its insets there; adjustPan moves its root by a per-window
  offset in `windows.c`, which `View.getLocationInWindow` subtracts (AOSP's `mCurScrollY`);
  unspecified resizes while a scroll container shows. Upstream IME or `softInputMode` code is ported
  onto `Window`'s `sendSoftInput`/`updatePan`.
- Bar flags reach the host in `struct ui_frame`: fullscreen, `cover_top` (the activity window runs
  under the status bar: layout-fullscreen flags, or a cutout mode that takes the notch), hide
  navigation, immersive; `InsetsController` maps onto the same flags. A hidden bar's visible inset
  is 0, its maximum kept.
- Night is per app (`atl_nav_set_night`, each host for each app): the app's configuration and every
  Resources it made (a weak list in `ATLLoadedApp`) take it, then Application and the activities
  whose manifest's `configChanges` covers uiMode hear it; others keep theirs (recreation: multi-app
  MA5). The Resources caches get Java change bits, as AOSP 10's, and drop a drawable on any change,
  since ATL's drawables keep no changing configurations (`CONFIG_NATIVE_BITS` is empty).
- Bitmaps are ours: `struct gfx_bitmap` (`src/shared/bitmap.c`) holds premultiplied ARGB words
  that never move, stored per config as Android 10's Skia does (lowp rounding; ARGB_4444 made as
  ARGB_8888 except by `copy`). A Canvas(Bitmap) draws into them at once through its own context
  (`gfx_canvas_new_bitmap`): record and gsk with cairo (`src/backends/gfx/cairo/`, gsk's content as
  GSK nodes), CoreGraphics a CGBitmapContext with its own layers and per-pixel blends. Display
  images are copies per change; nothing locks the pixels, as on Android. Row bytes are Skia's (width
  x bytes per pixel), `Config.nativeInt` AOSP's; every Bitmap native is shared. Picture records
  Canvas calls in Java. Upstream's GdkTexture bitmaps and `getTexture()` are gone: port Bitmap fixes
  onto the shared words.
- Blend modes are SkBlendMode's numbers everywhere (`enum gfx_blend`; `PorterDuff.Mode.nativeInt` as
  AOSP's), and every draw, layer, ComposeShader and color filter takes them; `src/shared/blend.h`
  holds Skia's formulas for the CPU paths. A view's blend mode reaches only the view's own drawing
  (on gsk its children's too), a layer by default: gsk isolates each Java-drawn view
  (`WrapperWidget`), CoreGraphics draws each view in its own layer. Android without a layer reaches
  the window (the draw app's CLEAR rect shows black on a device). gsk's PLUS and MODULATE are GSK's
  arithmetic node, which GTK makes only through its node parser (`parse_arithmetic`). Gaps: ATL-52
  (phone views).
- Several apps per VM: the loop slot has an instance per Android main thread (`struct loop_main`,
  `app->loop`; glib keeps one, gtk runs one app); the cli host runs each `-l`/`--instrument` group
  on its own thread, artbridge each later `dine_atl_run`. An app ends through `host_app_end`
  (`Instrumentation.finish` ends its app, not the VM); every Instrumentation line carries
  `[<package>] `.
  `AsyncTask`'s executors are the calling app's. Upstream loop, host or Instrumentation edits are
  ported onto the instance, the per-app thread and the end hook.
- No primary app: every app is a record (`ATLLoadedApp` plus the C `struct atl_app`, the hosts'
  handle); code reaches it through its Context or object, Android's static APIs through the calling
  thread's record (`ATLLoadedApp.ofCurrentThread`). Upstream code that reads a process-wide app,
  window or `Context` static is ported onto the record; `nav.h`, `host.h` and the embedded
  listener take the handle.
- Packages are ours: the registry (`ATLRegistry`, SQLite in the prefix `DINE_PREFIX`, default
  `~/.dine`) is PackageManager's only source, and `ATLInstaller` its only writer; upstream's
  `_installed_apks_`, `--install`'s copy, `ANDROID_APP_DATA_DIR` and the GMS name list are gone. A
  run by APK path installs the APK; the app's dirs are set after VM start (`prepareApp`). Every
  install, a path run included, refuses a provider authority another package holds. Port
  upstream PackageManager and PackageParser fixes onto the registry's reads.
- Region is ours: y-bands of x-spans in `src/shared/region.c` on every build, `setPath` by pixel
  centres as Skia's non-antialiased fill; upstream's cairo natives are gone. Port upstream Region
  fixes into the shared code.
- An app exception that reaches C where Android's main loop would see it goes to
  `exit_on_exception` (`src/api-impl-jni/util.c`), the thread's uncaught handler; the upcalls that
  print and clear (measure, draw, input, click, dialog result) keep doing so. In ported upstream code
  that describes an exception and goes on, call it instead.
- Rotations from degrees go through `matrix_init_rotate` (`src/shared/matrix.h`), Skia's snap of a
  sin or cos near 0; upstream's graphene rotate calls in Matrix and the record canvas are gone.
- Vibrator: upstream's gudev natives build only with gtk; headless and uikit take no-op natives
  (`src/shared/android_os_Vibrator.c`) until M7's `os` slot. Port upstream Vibrator edits into
  the gtk file.
- Path is ours: a `struct gfx_path` of verbs and points (`src/shared/path.c`, arcs and round
  rects as cubics) behind `android.graphics.Path`'s one handle; upstream's GskPath natives and
  `getGskPath()` are gone (gsk builds a GskPath per draw, `gsk_path_from_gfx`). Port upstream Path
  fixes into the shared code.
- Shaders are ours: Linear, Radial and SweepGradient keep their fields and make a
  `struct gfx_shader` (`src/shared/shader.c`) on first use; `Shader.TileMode` is AOSP's order.
- Nine-patches load as AOSP 10's: BitmapFactory reads `npTc` into `Bitmap.getNinePatchChunk`
  (`src/shared/ninepatch.c`) and Drawable makes the NinePatchDrawable from the chunk; upstream's
  file-path NinePatchDrawable and `Drawable.native_paintable_from_path` are gone.
- `src/api-impl/build.xml` (the ant path) runs `<depend closure="true">`: javac `-h` rewrites only
  the headers of classes it compiles, and a header holds inherited constants. Its gap:
  [ATL-1](bug-tracker.md#atl-1).
- Ours, no upstream counterpart: the gtk debug agent (`src/backends/ui/gtk/agent.c`, test hooks,
  `ATL_DBG_AGENT`, started from `main.c`'s window-ready poll) and `input_tap` in gtk `input.c`.
- Upstream's `android.atl.GskCanvas` is `android.atl.ATLCanvas`; its `snapshot` field is `handle`,
  a `struct gfx_canvas` (gsk: the GtkSnapshot). Save, restore, the transforms, rect, round rect and
  lines, `drawBitmap` and `clipRect` are shared natives behind `gfx_canvas_*`
  (`src/shared/android_atl_ATLCanvas.c`; gsk's bodies in `src/backends/gfx/gsk/canvas.c`, which
  counts each save level's pushes instead of Java's `push_history`), and so are `drawText`,
  `drawPath`, `clipPath`, `drawArc` and `saveLayer`; RenderNode stays in upstream's file, renamed
  `android_atl_ATLCanvas.c` (gtk). Port upstream GskCanvas edits there.
- Text is shared over `gfx_text_*`, in UTF-16 units: Paint's text natives
  (`src/shared/android_graphics_Paint.c`) and `android.text.Layout`, a C line array whose lines the
  backend breaks (`src/shared/android_text_Layout.c`); gsk's Pango is `src/backends/gfx/gsk/text.c`.
  Upstream's Pango Layout natives and Paint text natives are gone: port upstream text fixes there.
  Key listeners are AOSP's (`text/method/`), TextView's line limits AOSP's modes over
  `ui_text_set_lines`.
- View's and ViewGroup's draw natives (`native_drawBackground`, `native_drawContent`,
  `native_drawChildren`, `native_drawChild`) and `ATLCanvas.native_drawDrawable` are shared behind
  `ui_view_draw_*` and `gfx_canvas_draw_drawable`; gtk's bodies are in
  `src/backends/ui/gtk/view.c` and `src/backends/gfx/gsk/canvas.c`. `native_drawBackground` and
  `native_drawContent` return whether the toolkit drew: on records Java draws the background
  (AOSP's `drawBackground`) and ImageView its drawable (AOSP's `configureBounds`).
- Drawables follow AOSP's constant states: the base `getConstantState` is null, a container's copy
  makes its own children from theirs, ColorDrawable, BitmapDrawable and DrawableWrapper have states,
  and stubs copy through `StubState`. Port upstream drawable code onto that; `LayerState` shares a
  child without a state.
- A bitmap or nine-patch drawable's color filter and tint live on its native drawable
  (`PaintableFilter`, `gfx_drawable_set_color_filter`); gsk's bitmap drawable is a paintable over
  the texture that keeps the filter. A color filter is a `struct gfx_color_filter` (blend mode and
  color, or a 4x5 matrix) from `ColorFilter.atlMode/atlColor/atlMatrix`, on paints and drawables.
- The `coregraphics` gfx backend (iOS) is record's display list (`src/backends/gfx/record/`) plus a
  CoreGraphics replay and ImageIO bitmaps; uikit replays each view's list in a layer and paces
  draw passes with a CADisplayLink.
- The records ui backends run a draw pass upstream has no counterpart for (`records/ui.c`): a
  drawing view's `draw()` records into its display list through `View.atlDraw`.
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
  `native_constructor`. ContainerPaintable refs its child; gsk's NinePatchPaintable
  (`src/backends/gfx/gsk/ninepatch.c`) frees its texture and nine-patch. Port upstream drawable
  constructors that way.
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
  from `test_hooks.h` without it. Dine's iOS release build turns it off; `android.atl.ATLTestHooks`
  stays in the jar, which every build shares, and throws UnsatisfiedLinkError there. With
  `ATL_DUMP_VIEWTREE`, records backends also print `viewfreed:`, `dialogfreed:` and
  `drawablefreed: record` lines; gsk's paintables print `drawablefreed: <GType name>`. With
  `ATL_DUMP_DISPLAYLIST`, records backends print each draw's `displaylist:` lines.
- `jstring_to_utf8` (`util.c`) gives ui slots valid UTF-8 (U+FFFD for U+0000 and lone
  surrogates); the `src/shared/` text natives use it. `attribute_set_get_string` returns its
  result, so callers `free()` it (gtk `Button.c` too). Upstream's gtk-only text natives keep
  `GetStringUTFChars`.
- Windows over activities are ours: a Dialog's Window joins its app's registry
  (`src/shared/windows.c`, `Window.nativeAddSubwindow`) with its activity as the token, or as an
  application overlay. The registry shows a window while the task is in front and, for a token
  window, its activity is the shown one; it places windows as WindowManager would, gives the ui slot the
  shown roots (`ui_window_set_roots`) and answers BadTokenException and "not attached to window
  manager". Results count only while the dialog is drawn. Port upstream Dialog show and dismiss
  edits onto the registry. An AlertDialog's window is its decor plus its ui-slot alert: plain
  (title, message, buttons, `setItems`) the backend shows by itself, else a panel the backend draws
  around the decor (`setView`, choice lists, `setAdapter`, ProgressDialog), decided at `show`; the
  panel sets the width (`ui_dialog_chrome`), the theme's window background and least width don't
  apply. Upstream's AlertController layouts aren't used.
- `WindowManager.addView` windows are registry entries too (`Window.atlAddView`): the added view is
  the root, with a `WindowViewParent`. Tokens are per Window (`Window.Token`, `View.getWindowToken`);
  a sub-panel (1000-1999) attaches to the token's window, lays out in its frame, layers above it and
  goes with it; toasts and overlays layer above application windows. Upstream's GtkPopover
  `WindowManagerImpl` and `PopupWindow` natives are gone: PopupWindow is AOSP 10's over the
  registry; gtk draws its roots in the app window's overlay. Port upstream PopupWindow fixes onto
  that copy.
- A window's keep-screen-on, fullscreen, brightness and exclusion rects are stored per window; the
  drawn windows' together reach the host (`windows_state_changed`). Insets reach each drawn window,
  clipped by its frame.
- PopupMenu and text toasts are native per backend (`ui_menu_show`, `ui_toast_show`): GtkPopoverMenu
  and an OSD label on gtk, a UIMenu and a glass capsule in its own window above the alerts on iOS.
  Upstream's GMenu natives are gone; `PopupMenu` keeps its `MenuImpl`. An open PopupMenu takes
  Back (`ATLLoadedApp.open_menu`), as Android's focused popup window would. Each app's toasts queue
  on its main thread (`Toast.Queue`); a toast shows only while its app is in front.
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
- Task state, dialogs' task, the window size and night are per app (the app record, `struct
  atl_app`); they become per task with multi-app MA6 (`notes/multi-app-support/design.md`). The
  screen (`atl_screen`: density, the first window) stays the VM's.
- `SDK_INT` is a device level set by hand: `ro.build.version.sdk` in `SystemProperties.java` (29),
  read by `Build.VERSION`; `RESOURCES_SDK_INT` = `SDK_INT`; `CODENAME` "REL". Upstream's derivation
  (`EarlyPackageParser`, `-DBuild.VERSION.SDK_INT`, `--sdk-int` and `create_vm`'s `sdk_int` in
  `main.c`, now `startup.c`) is gone; a minSdk above it logs and runs (`PackageParser`). Drop
  upstream SDK_INT edits there. bionic_translation's native `ro.build.version.sdk` (`libc.c`, Linux
  only) still says 21: a plain clone, so matching ours needs a local patch
  ([ATL-44](bug-tracker.md#atl-44)). Behaviour may
  follow a later Android version where that is easier or saner (implicit broadcasts reach running
  apps only, as on Android 8 and later).
- `Window` keeps the system bar state (`styleBars`, `updateFrame`, real `addFlags`/`setFlags`);
  `activity_focus` and the `set_frame` native send the shown activity's frame to
  `ui_window_set_frame` (gtk: header bar CSS). `View.setSystemUiVisibility` calls the gtk-only
  `nativeSetFullscreen` only when the fullscreen bits change, and tells the decor's Window the
  light flag. Port upstream Window/system-bar edits there.
- Matrix natives are in `src/shared/android_graphics_Matrix.c` (graphene; the wrap
  `subprojects/graphene.wrap` outside the desktop build). Port upstream Matrix fixes there.
- Paint state natives are shared behind `gfx_paint_*`; gsk's bodies are in
  `src/backends/gfx/gsk/paint.c`. Text bounds and font metrics stay in upstream's file (gtk).
  `Paint(Paint)` and `set` copy the Java-side state too (xfermode, shader, align, color filter);
  the default align is LEFT, as Android's.
- `getLocationInWindow/OnScreen`, `getGlobalVisibleRect`, `offset*RectInto*` and the observer's
  window are Java (no natives): drop upstream edits to those natives.
- Attach state is Java (`dispatchAttachedToWindow`/`dispatchDetachedFromWindow`, `isAttachedToWindow`
  a field); gtk's `notify::root` callback and `currently_unmapping` are gone. Port upstream attach
  fixes into View/ViewGroup Java.
- Visibility, background drawable, invalidate, translation (`native_childrenMoved`), text runs,
  multi-window, ImageView, ProgressBar and ViewTreeObserver natives are shared behind ui slot calls;
  gtk's bodies are in `src/backends/ui/gtk/{view,widgets,window,text}.c`.
- Fullscreen and keep-screen-on are Window state sent for the shown activity (`set_frame`,
  `set_keep_screen_on`); `View.nativeSetFullscreen` and `native_keep_screen_on` are gone.
  `FLAG_KEEP_SCREEN_ON` is Android's 0x80.
- `View.layout` keeps AOSP's layout-required flag: `ui_view_layout` gets `relayout`, and records
  lay out a node's children only then; `offsetTopAndBottom`/`offsetLeftAndRight` move and
  invalidate without a layout. Port upstream layout edits onto the flag. Records cache text
  measures (`records/ui.c`, keyed on every input, runs included) for every app in the VM.
- Styled text is ours: `Html` is AOSP 10's with its TagSoup parser (`doc/AOSP.md`), and TextView sends
  its CharacterStyles as runs (`ui_text_set_styled`: gtk Pango attributes, records' runs, uikit
  attributed strings). Upstream's markup path (`Html.fromHtml` keeping tags, `ui_text_set_markup`)
  is gone; port upstream span edits onto the runs.
- Native lifecycle calls go through `Activity.atlPerformCreate` and the other `atlPerform*`
  wrappers (`handle_cache.c`), which call the API 29 pre and post lifecycle callbacks around the
  app's methods; port upstream lifecycle edits behind them. `getActionBar()` is `ATLActionBar`,
  Android's API drawing nothing ([ATL-42](general-todo.md#atl-42)).
- The cli host has `--instrument`; `test_runner.jar` builds in the headless build dir.
- The C targets depend on hax.jar (order-only), so javac rewrites the JNI headers first.
- Insets are ours: `WindowInsets` stores per type; View/ViewGroup `dispatchApplyWindowInsets` is the
  pre-API-30 dispatch; `fitsSystemWindows` is real (default false). The host's insets come through
  `atl_nav_set_insets` and `Window.dispatchInsets`; exclusion rects through the Window's tracker and
  `src/shared/insets.c`. Port upstream insets edits there.
- Last merge: upstream d658957d (2026-10-20); hand ports start there.

## dine-art

- `OatFileAssistant::GetBestOatFile` returns null, like the dex open path: no oat file, no
  dex2oat. Keep upstream's dex2oat block there (`79ab0c15`, `d58f96f9`) out on merges.
- The "not in a known location" boot class path warning prints only on Android targets
  (android12's gate in `hidden_api.cc`).
- Cleanup per app: libcore's `java.lang.ref.CleanupDomain` (one cleanup thread per app group,
  `ThreadGroup.cleanupDomain`, a class loader may be its `Owner`) takes the finalizers and
  `sun.misc.Cleaner`s of an app's objects off ART's daemons (`FinalizerReference.add`,
  `Cleaner`'s queue, `ReferenceQueue.enqueueLocked`); `Daemons.finalizeReference` is shared. Keep
  them across rebases of those files.
- Native libraries are keyed by (path, class loader) in `java_vm_ext.cc`'s `Libraries`; the
  "already opened by ClassLoader" refusal is gone. `art_register_jni_symbols` lists limit a
  library's `Java_*` lookup (on Apple a library without one resolves none).
- Thread tags for embedders: libcore's `ThreadGroup.embedderTag` (subgroups inherit it) and
  `Thread.joinThreadGroup`; ART copies the tag into a `Thread` member at start and attach and
  exports `art_embedder.h` (`art_thread_embedder_tag`, `art_join_thread_group`,
  `art_set_default_attach_group`). Keep them across rebases.
- Upstream is merged: `git merge upstream/master`.
- `install-ios` puts ART's junit boot jars in `share/art-junit`, apart from the runtime jars:
  Dine's release builds leave them off the boot class path.
- Park's platform calls live in `ParkWait`/`ParkWake` (`art/runtime/thread.cc`): futex on Linux,
  os_sync on Apple. Resolve upstream edits to `Thread::Park/Unpark` there.
- Apple `parkUntil` becomes a timeout at entry: no wall-clock tracking, device sleep delays it
  ([ART-18](bug-tracker.md#art-18)).
- Apple keeps pthread mutexes, condvars and RW locks; only park uses os_sync.

## dine

- Min iOS 17.4 (os_sync): `env.sh` for scripts and CMake, `apps/Dine/Package.swift` for Swift.
  Never equal to the SDK version (compatibility mode).
- Linux gate after a merge: `tools/dine linux smoke` (every check in `tools/py/dine/linux.py`) +
  `tools/dine test runtime` + `tools/dine test framework` (headless, `--gtk`, `--one-vm`) +
  `tools/dine test apps` (headless, `--gtk`) + `tools/dine test package`; iOS gate:
  `tools/dine dbg smoke`.
