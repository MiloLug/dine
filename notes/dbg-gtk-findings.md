# gtk visual debugging: findings (2026-10-25)

Whether ATL's gtk build can be screenshotted, or run without opening windows on the Windows
desktop (WSLg), with its output routed elsewhere. A snapshot of a read-only investigation: nothing
here was run.

## Answer

Yes, by three routes. To keep windows off the desktop, the simplest is a headless Wayland
compositor plus a screenshot tool, both in pacman. To get pictures of ATL's own windows without
new packages, ATL itself can save a window to PNG through a test hook, reusing GTK render code it
already has.

## Findings

1. The system GTK is 4.24.1, built with the `broadway`, `wayland` and `x11` backends
   (`pkg-config --variable=targets gtk4`). GTK 4 has no offscreen backend, so a GTK window always
   needs some display server.
2. Already installed: `gtk4-broadwayd` and `gtk4-rendernode-tool`. The latter's `render` command
   turns a saved GTK render node (GTK's description of one drawn frame) into a PNG.
3. Not installed, but in pacman extra: `cage` 0.3.1 and `sway` 1.12 (headless-capable Wayland
   compositors), `grim` 1.5.0 (screenshots on those compositors), `weston` 15.0.1 and
   `xorg-server-xvfb`.
4. ATL already renders GTK drawings to images without a window and saves PNGs:
   - `dine-atl/src/api-impl-jni/graphics/android_graphics_Bitmap.c:23-68` renders with GTK's
     software renderer, or with a renderer on a second display connection on the main thread.
   - `dine-atl/src/api-impl-jni/app/android_app_WallpaperManager.c:22` saves a PNG
     (`gdk_texture_save_to_png`).
   - The gtk test hooks already have a "window is ready" point
     (`dine-atl/src/main-executable/main.c:62-71`, `dine-atl/src/backends/ui/gtk/dump.c`); a
     screenshot hook would sit next to them.
5. Every gtk smoke check opens real windows on WSLg; `tools/py/dine/linux.py:40-43` refuses to
   run them without a display.
6. Claude Code's Playwright browser tool can screenshot Broadway's web page.

## Options

1. **Headless compositor (recommended for "no windows").** Run ATL inside
   `WLR_BACKENDS=headless cage -- android-translation-layer …` on its own Wayland socket, then
   `grim out.png`. Nothing opens on Windows, GTK draws through its usual Wayland path, and the
   smoke scripts would only need this wrapper. Cost: two pacman packages and a small `tools/dine`
   command or smoke flag. Dialogs show as cage stacks them.
2. **ATL test hook `ATL_SCREENSHOT=<file>`.** After the window's first frame, ATL renders its
   window to a PNG. It could also save the render node as text: a diffable golden of what gsk
   draws, like the headless display-list golden. Timing is exact and no packages are needed, but
   it still needs a display (WSLg, or option 1). Options 1 and 2 combine well.
3. **Broadway.** Run `gtk4-broadwayd :5` and start ATL with
   `GDK_BACKEND=broadway BROADWAY_DISPLAY=:5`, then screenshot the page (port 8085 for display 5)
   with Playwright. Nothing to install, but it is a different GDK backend with its own quirks, and
   a browser sits in the loop.
4. **Xvfb.** Run with `GDK_BACKEND=x11` and capture with `xwd`. It works, but tests the X11 path
   while WSLg uses Wayland, and needs extra X packages.

## Unverified

- Whether cage or sway's headless backend starts under the WSL2 kernel. With no GPU device they
  may need `WLR_RENDERER=pixman`.
- Whether GTK picks a working renderer there; it may need `GSK_RENDERER=cairo`.
- Weston's own screenshot tool, which needs `--debug`.
