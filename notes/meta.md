# dine — project meta

General context, not a plan. Sources: the original research chat
(https://claude.ai/share/92b42b89-7fa3-4fec-bf44-26b9a0a76926) and the 2026-10-15 environment
setup session.

## What it is

A generic **Android app runner for iOS**, built as a *translation layer* ("Wine for Android"),
not a full-system emulator. Android apps run as Dalvik/ART bytecode inside one iOS app. Their
Android API calls get reimplemented on top of iOS (UIKit, Metal, WKWebView, …).

It isn't tied to any particular app. TachiyomiSY is useful as a realistic test case (see below),
nothing more.

## Why a translation layer, not an emulator

- **Full-system emulation already exists:** UTM SE (QEMU, on the App Store) can boot Android on
  an iPhone. Without JIT or a hypervisor, the whole OS runs through an interpreter: boots take
  minutes and the UI crawls. Many "Android on iPhone" demos are really a Mac VM streamed to the
  phone.
- **"Needs low-level access" is a myth.** The real obstacles are performance and Apple policy.
- **A translation layer** interprets only the app's bytecode; everything below the API is native
  iOS code. That makes it much faster than UTM, and apps can look and behave like iOS apps.
- **Prior art:**
  - **Android Translation Layer (ATL):** Linux, NLnet/NGI-funded, reuses AOSP's ART + libcore,
    runs apps unmodified, still early. This is the practical starting point.
  - Myriad Alien Dalvik (2011): its iPad version was secretly cloud-backed.
  - Waydroid: a container running full AOSP, so not applicable to iOS.
  - iAndroid: a fake jailbreak launcher.
- **Nothing usable exists for iOS today.**

## iOS constraints that shape everything

- **No JIT** for normal apps: memory the app wrote can't be made executable. ART must work
  **interpreter-only**. Early Android ran fully interpreted on ~500 MHz phones, so ordinary apps
  should feel acceptable on a modern iPhone.
- **Code signing:** the APK's own `.so` libraries can't be loaded, even though they are the same
  ARM64. Without JIT, native libraries need iOS builds of the same open-source code, or iOS
  system equivalents (SQLite, JavaScriptCore, ImageIO) behind the same JNI entry points. Unknown
  native code fails cleanly.
- **No hypervisor access** for apps, so virtualizing an ARM64-on-ARM64 guest is off the table.
- **One process:** iOS apps can't spawn processes. All Android apps share one iOS process,
  isolated only by class loaders and separate folders. One crash or memory spike takes them all
  down.
- **Background limits:** WorkManager-style long jobs stop when the app isn't in the foreground.
- **JIT when available:**
  - Sideloaded, dev-cert-signed apps can get JIT through **StikDebug** (iOS 17.4+). This is
    fragile: iOS 26.4 broke it for some users.
  - Jailbreaks are rare (none for iPhone 16/17; iPhone 12–15 only up to 17.3.1).
  - With JIT, ART's real JIT can run, and the APK's own `.so` files could run directly at native
    speed.
  - **Design rule:** interpreted by default, native speed whenever JIT is available. The layer
    must be fully correct without JIT.

## Distribution

- **The App Store is effectively closed** to this:
  - **2.5.2:** downloaded code adding functionality. A "Wine for Android" isn't one of 4.7's
    named exceptions.
  - **4.7.2:** exposing native iOS APIs to downloaded software. Mapping WebView, files and
    notifications is exactly that.
  - **3.2.2:** an in-app catalog of Android apps would count as an App Store-like interface.
  - UTM SE got in only as a "PC emulator" (4.7, added Aug 2024), and because it exposes nothing
    but virtual hardware.
  - "The more native and usable, the less approvable."
- **EU alternative marketplaces** still require notarization, which enforces 2.5.2 and 4.7.2.
- **Target = sideloading:**
  - **AltStore/SideStore with a free Apple ID:** 3 apps, 10 installs per week, 7-day expiry.
  - **A paid developer account:** 1-year certificates, no 3-app limit.
  - Requires Developer Mode (iOS 16+). TrollStore only works up to iOS 17.0.

## Architecture shape (agreed layers)

1. **Runtime:** ART ported from AOSP (GC, threads, class loading, libcore `java.*`). Runs
   interpreted, uses JIT when available. Ported, not rewritten.
2. **Native code:** a JNI bridge plus a bionic (Android libc) compatibility shim. With JIT, load
   the APK's `.so` files; without it, substitute iOS builds of known libraries.
3. **Framework:** the Android API surface. **The big open decision:**
   - **Reimplement it** (the ATL/Wine way).
   - **Run AOSP's real Java framework** and implement only the system services underneath.
     Compatibility comes much closer to free, but it's heavy to start under an interpreter.
4. **Graphics + input:** `android.graphics` drawn through Skia onto Metal on iOS (Vulkan/GL on
   Linux), plus touch, the on-screen keyboard and fonts. This is the biggest single piece, and
   nearly every app depends on it (for example Jetpack Compose).
5. **System services:** a fake `system_server` covering activities/intents, app install
   (including APK parsing and signature checks), content providers, storage layout, permissions,
   notifications and background jobs.
6. **Platform bridges:** GPS, camera, WebView → WKWebView, files, and so on. These are not 1:1:
   - WKWebView can't intercept http/https the way `shouldInterceptRequest` does.
   - Push notifications depend on Google's servers.
   - iOS limits background work.
7. **Play Services replacement** (optional): microG-style stubs. Many apps won't start without it.

**Practical start:** port ATL. It already has the runtime and much of the API working on Linux.
The iOS work is mostly replacing its Linux desktop (GTK) backend with UIKit/Metal, plus adding
the native-code layer.

## Reference test app: TachiyomiSY

TachiyomiSY is a good stress case. It's pure Kotlin and needs no Play Services (Firebase is only
used for analytics and can be stubbed). Its 1,430 extensions are plain dex loaded through a
class loader, with no `.so` files: for an interpreter that's just data, so code signing never
comes into it.

- **Native dependencies to rebuild for iOS or replace:**
  - SQLite, plus SQLCipher (only when database encryption is on)
  - QuickJS
  - a libvips-based decoder for AVIF, JXL and HEIF
  - libarchive
  - zstd
  - a WebGPU viewer (only for the optional renderer)
  - Conscrypt (only below Android 10, so it can be skipped)
- **Real work:**
  - Compose graphics (~400 files), plus Bitmap/Canvas in 58 extensions
  - WebView with shared cookies (Cloudflare bypass; 156+ extensions use it)
  - extension install and signature checks
  - WorkManager background jobs
- **Performance:** expect scrolling under interpreted Compose to stutter. This is an estimate,
  not a measurement.

## Development approach (no Mac)

- **Most work on Linux (WSL):** runtime, framework and system services don't depend on iOS, and
  ATL already runs there. ART with `-Xint` reproduces the iPhone's no-JIT situation. Skia can
  use Vulkan/GL on Linux and switch to Metal on iOS.
- **Device-only work:** the UIKit/Metal backend, the platform bridges, and the code-signing
  limits. The iOS Simulator is macOS-only and doesn't enforce code signing, so it would hide the
  biggest problem anyway.
- **Tooling:**
  - **xtool** (Swift package → signed iOS app → install). Gaps: you supply Xcode.xip yourself,
    no debugger launch, no asset catalogs or Interface Builder, app targets only, no App Store
    upload.
  - **clang** cross-compiles the C++ parts (ART, the bionic shim) to `arm64-apple-ios` static
    libraries, which get linked into the Swift app.
  - **pymobiledevice3 / libimobiledevice** for logs, crashes and lldb remote attach.
- **Given up without a Mac:** Instruments (it hurts for interpreter performance work) and
  Xcode's debugger UI. A cloud Mac (GitHub Actions; free in public repos, paid runners about
  $0.062/min) covers official builds and occasional profiling.
- **Legal:** the Xcode license says Apple-branded computers only, so extracting the SDK on Linux
  is a grey area. Apple doesn't seem to pursue hobbyists for it.

## Current state (2026-10-15)

- The dev environment is set up and verified end to end. See `README.md`.
- **Dev device:** iPhone 13 (A15), iOS 27.0.1, connected through Windows AMDS.
- **Signing:** a free Apple ID.
- **Proven so far:**
  - a C++ static library cross-compiled on Linux, linked into a SwiftUI app, signed, installed,
    launched, logged and debugged with lldb on the phone
  - the ATL/ART stack built on Linux, running a test APK with `-Xint` under WSLg
- **Not yet tested:** JIT on this phone and iOS version (StikDebug).
- **Not started:** porting ART/bionic to `arm64-apple-ios`, and the UIKit/Metal backend.
