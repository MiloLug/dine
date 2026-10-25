# Licensing and the App Store for a packaged app

Findings from 2026-10-20 to 2026-10-22 on one future option, a **packaged app**: an iOS app that
bundles a single Android app with Dine's runtime (ART + ATL), submitted to the App Store. The
generic runner (any APK, imported or downloaded) is a different case; `meta.md` ("Distribution")
covers it. ATL counts are from dine-atl `e8a9e71b` (2026-10-20). Nobody with legal training has
reviewed this, and claims marked "from memory" weren't checked against a source.

## Verdict

- **Review guidelines:** probably passes. The interpreter and the bytecode both ship inside the
  binary, the same shape as React Native with Hermes bytecode or a Lua-scripted game.
- **Licensing is the blocker:** ATL and wolfSSL are GPLv3, libcore's OpenJDK part is GPLv2 with
  the Classpath exception. App Review doesn't check licenses, but a copyright holder's complaint
  gets the app removed.

## App Store Review Guidelines

Text read from https://developer.apple.com/app-store/review/guidelines/ on 2026-10-20.

| Guideline | For a packaged app |
|---|---|
| 2.5.2: no downloading or executing code "which introduces or changes features" | Bundled dex is fine. A dex update that changes features breaks it; a bug-fix update falls under the Developer Program License Agreement's interpreted-code clause, which CodePush and Expo Updates rely on (from memory). |
| 4.7, 4.7.2, 3.2.2 | Don't apply: 4.7 covers software not embedded in the binary, 3.2.2 an in-app store. |
| 2.5.1: public APIs only | Dine's Swift and `native/` use no `MAP_JIT` and declare no entitlements. The one private API is in the dev-only debug agent (`native/dev/dbgagent` reads `UIAlertAction`'s `handler` through KVC), which release builds don't link. ATL's `uikit` backend wasn't checked ([DINE-10](general-todo.md#dine-10)). The heap reservation above 4 GB needs no `extended-virtual-addressing` (`art-findings.md`, "Phone probe"). |
| 2.1, and the intro of section 4 (Design): "degraded experience" | ART runs only the C++ interpreter (no JIT, no AOT), so a heavy app is sluggish, and reviewers reject on that. Depends on the app. |
| 2.3.10: no names, icons or imagery of other mobile platforms | No Android name, robot icon or Play references in the app or its metadata. A packaged app drops the launcher, the apps list and the Recent apps action. Back on an edge swipe is fine; Material styling is fine (Google's own iOS apps use it). |
| 2.5.6: web browsing must use WebKit | An Android `WebView` must map to `WKWebView`. |
| 5.2.1: submitter owns or licensed the IP | Only your own app, or one you have a license for. |
| 4.2.6: template and app generation services | Porting other people's apps as a service falls here: the content owner must submit the app. |

Not a guideline but an upload check: Apple's required-reason APIs need a `PrivacyInfo.xcprivacy`
declaring them, or the upload is rejected with ITMS-91053. `llvm-nm -u` on the built Dine binary
shows the file timestamp category (`stat`, `fstat`, `lstat`) and the disk space category
(`statvfs`, `fstatvfs`).

## Licenses of what Dine ships

| Shipped in Dine | Component | License | For the App Store |
|---|---|---|---|
| `libtranslation_layer_main.a`; `api-impl.jar`, `ghax.jar`, `gstub.jar`, `framework-res.apk` | ATL | GPLv3, with AOSP parts under Apache 2.0 | blocker |
| `libwolfssl.a`, `libwolfssljni.a`, `wolfssljni-hostdex.jar` | wolfSSL | GPLv3 (wolfSSL also sells a commercial license) | blocker |
| `libopenjdk.a`, `libopenjdkjvm.a`, `core-oj-hostdex.jar` | OpenJDK code in libcore and ART | GPLv2 + Classpath exception | low enforcement risk |
| `libart*.a`, `libdexfile.a`, `libandroidfw.a` and the other AOSP libs; `core-libart-hostdex.jar` (mostly, not checked file by file); `okhttp`, `apache-xml`, `apachehttp` jars | ART, AOSP | Apache 2.0 | notice |
| `bouncycastle-hostdex.jar` | Bouncy Castle | Bouncy Castle License (MIT-style) | notice |
| `libgraphene-1.0.a` | graphene | MIT | notice |
| `libfdlibm.a` | fdlibm | Sun notice (`dine-art/external/fdlibm/NOTICE`) | notice |
| `libicu*.a` | ICU | Unicode License v3, plus the third-party licenses appended to its `LICENSE` | notice |
| `liblz4.a` | lz4 (`lib/` only) | BSD 2-Clause | notice |
| `liblzma.a` | xz | 0BSD | nothing |

- **Why GPL conflicts:** the App Store's Usage Rules limit devices, encrypt the binary with
  FairPlay and bar redistribution. GPLv3 §10 forbids adding restrictions, so shipping there
  breaks the license. Under §8 the license then ends, subject to §8's reinstatement when the
  violation is cured; distributing without it is copyright infringement. This is the FSF's
  position.
- **Precedent (from memory):** VLC was removed from the App Store in 2011 (GPLv2) after one of
  its developers complained. It returned in 2013 after VideoLAN relicensed libVLC to LGPL with its
  contributors' consent.
- GPLv3 §6 "Installation Information" doesn't apply: it covers object code conveyed along with
  the transfer of a User Product, and an App Store download isn't one.
- **OpenJDK code:** the Classpath exception covers code that links against it; the code itself
  stays GPLv2, so the same "no further restrictions" conflict holds in principle. The holders are
  Oracle and Google (AOSP's changes). The risk is low only as a judgement about enforcement:
  OpenJDK-based apps (Gluon) are on the App Store (from memory).

## ATL: who can grant an exception

- GPLv3 §7 lets copyright holders add permissions, such as "may also be distributed through the
  App Store". Only holders can grant one, and only for their own code.
- dine-atl has no contributor agreement or copyright assignment (no CONTRIBUTING, CLA or AUTHORS
  file), and ATL's own C files carry no copyright lines. Each contributor owns what they wrote.
- `git shortlog -sn` on dine-atl lists 34 names: our own commits (as Lia Va), one person under
  two names, and 32 upstream contributors. The two main ones are Julian Winkler (800 commits)
  and Mis012 (348). The **other contributors** (30) also hold copyright in whatever of theirs
  ships: get their consent, or rewrite their parts. Commit counts are a rough guide; `git blame`
  on the shipped files gives the real split.
- Ours, needing nobody's permission: our own changes in dine-atl.
- **AOSP code in ATL:** only the AOSP original is Apache 2.0. ATL contributors' edits to those
  files are theirs, under GPLv3, so take AOSP code straight from AOSP, not from ATL.

## Replacing ATL

### Rewriting it

New code we write is ours, under any license, as long as it copies no ATL code.

- Copying or translating ATL code line by line makes the result a derivative work, still GPLv3.
  The safe form is a clean room: one person reads ATL and writes a spec, another implements it
  without seeing ATL. At minimum, write from AOSP sources and the Android docs, never from ATL's
  files.
- The Android API itself isn't a problem: its declarations are in AOSP under Apache 2.0. (Google
  v. Oracle, 2021, assumed the Java API was copyrightable and held Google's copying of its
  declaring code fair use on those facts.)
- Code moved out of ATL files stays theirs: `src/shared` and the `gtk`, `glib` and `gsk`
  backends. The backends written for Dine (`uikit`, `cfrunloop`, `embedded`, `headless`, `cli`,
  `poll`, `record`, `records`) have only our commits and none on upstream `master`; whether any
  of them carries code moved from ATL files wasn't checked ([DINE-10](general-todo.md#dine-10)).

Size of ATL. An **AOSP header** here means an AOSP or Apache license notice in a file's first
20 lines:

| Part | Lines | Lines in files with an AOSP header |
|---|---|---|
| `src/api-impl` (Java `android.*`) | 331.5k | 151.9k |
| `src/api-impl-jni` (natives) | 30.0k | 2.0k |
| `src/libandroid` | 3.0k | 1.2k |
| `src/shared`, `src/slots`, `src/backends`, `src/main-executable` | 5.4k | 0 |

The Java without an AOSP header (~180k lines) and the natives iOS needs are what a rewrite
covers. Most of `api-impl-jni` is tied to GTK, which iOS doesn't use.

### Swapping in AOSP classes one at a time

Replace ATL code with AOSP code (Apache 2.0), modified to fit the rest, until no ATL-written code
ships. dine-atl does this: `dine-atl/doc/AOSP.md` lists what is ported and how files are marked,
and dine-atl ships `NOTICE-AOSP.txt` and `LICENSE-APACHE-2.0.txt`. Files with ported parts start
with "Portions Copyright ... The Android Open Source Project", which the first-20-lines test
above counts as AOSP; the counts are from before that.

- The license benefit comes only at the end: while one ATL-written file ships in the binary, the
  whole app is under GPLv3.
- Our edits to AOSP code are ours. Apache 2.0 §4(b) asks us to mark the files we changed, and
  §4(d) to keep the NOTICE attributions.
- When adapting an AOSP class, don't carry ATL's logic into it (for example ATL `View`'s
  rendering hooks). Write the hooks fresh against the slot interfaces.

What it saves:

- 835 Java files in `src/api-impl`: 330 with an AOSP header, 505 without. 331 of the 505 are
  under 30 lines: stubs, mostly API declarations, which can be regenerated from AOSP's
  signatures.
- Already AOSP: `Resources`, `LayoutInflater`, `Handler`, `Looper`, `ListView`.
- The app keeps running after every swap, and the smoke tests and goldens catch regressions per
  step. Real AOSP code also behaves more like Android.

What it doesn't save. The core classes have no AOSP header: `View` (2660 lines), `ViewGroup`
(732), `Canvas` (660), `Activity` (683), `Context` (606), `TextView` (542), `AlertDialog` (184).
Their AOSP versions pull in what ATL replaces, and replacing that is the bulk of the work:

| AOSP class | Depends on |
|---|---|
| `View`, `ViewGroup` | `ViewRootImpl`, WindowManager, HWUI/RenderThread |
| `Canvas` | HWUI and Skia natives |
| `Activity` | `ActivityThread`, ActivityManager and WindowManager over Binder |
| `Context` | abstract; `ContextImpl` holds the system services |
| `TextView` | the text layout stack, `Editor`, `InputMethodManager` |
| `AlertDialog` | `AlertController` |

- Glue that adapts AOSP code to the remaining ATL classes is thrown away when those get replaced
  too. Replace leaves first, or swap a cluster at once (`View` + `ViewGroup` + `Canvas`).
- `api-impl-jni` has no AOSP drop-in; AOSP's equivalents are HWUI, Skia and SurfaceFlinger. iOS
  needs only what the `uikit` backend calls, written fresh behind the slots.

## Notices in a packaged app

Every row marked "notice" above is owed already, with or without ATL; replacing ATL with AOSP
code adds entries, not a new kind of obligation. The GPL components owe their license text and a
source offer.

- Apache 2.0 for a binary: §4(a) give recipients a copy of the license; §4(d) include the
  attributions from the NOTICE files. One place §4(d) allows is "a NOTICE text file distributed
  as part of the Derivative Works", so a text file inside the `.app` meets the letter.
- ICU's notice is its whole `LICENSE` file, appended third-party licenses included.
- Where it goes: Dine already bundles `out/ios/assets/Dine/licenses` (`xtool.yml`), which holds
  the icon pack's license. A combined notice file generated at build time belongs there, with
  dine-atl's `NOTICE-AOSP.txt` and `LICENSE-APACHE-2.0.txt`. Dine's bundle carries
  `api-impl.jar` without them: [DINE-5](bug-tracker.md#dine-5).
- Visible without in-app UI: a `Settings.bundle` with an Acknowledgements page, shown in the iOS
  Settings app under the app. It is a resource folder, so xtool can bundle it. Or an "Open source
  licenses" row on the packaged app's about screen.
- Many Android apps have their own licenses screen (Google's `oss-licenses-plugin`); it runs
  through the layer like any other screen.

## Options for an App Store build

1. **wolfSSL:** replace it with a TLS provider backed by Apple's Network or Security framework,
   or buy the commercial license.
2. **ATL:** an App Store exception from Julian Winkler, Mis012 and the other contributors (or a
   rewrite of the other contributors' parts), the way VLC relicensed; or replace ATL as above.
3. **OpenJDK code:** keep it.

## Not checked

[DINE-10](general-todo.md#dine-10).
