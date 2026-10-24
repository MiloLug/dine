# Tests

Two worlds: the code that runs Android apps (`android-compat`), and Dine itself (`launcher`).
Each suite lives in the repo that owns the code it tests; the engine stays here.

| Suite | Lives in | Status |
|---|---|---|
| runtime: ART interpreter + libcore (AOSP ART run-tests) | `dine-art/tests/runtime/` | working (Linux) |
| headless: ATL's headless build runs demo_app (view-tree dump vs golden), the looper APK (loop paths, clean exit), the dialog APK (scripted answers, an alert that changes its buttons in onShow; also on gtk), the nav APK (Back, Home, front and insets through `-c`; the insets each show gets, exclusion spans, Back on a shown list), the views APK (frees, attach, widgets, keep screen on, fullscreen; also on gtk) and the widgets APK (taps, a hold, Tab and Enter, a scrolling drag and keys through `-c`, and its controls activity: buttons, checkboxes, radios, a switch, a toggle and an image button; on iOS also `dbg smoke atl-widgets` for checks by eye and `atl-controls`); `tools/dine linux smoke` runs them | `dine-atl/tests/headless/` | working (Linux) |
| framework: `android.*` APIs (ATL's api-impl), JUnit 3 in-VM on the headless build (`tools/dine test framework`); suites `basics`, `controls` (the Button family, AlertDialog's buttons), `graphics`, `input` (touch dispatch, focus, keys, scroll) | `dine-atl/tests/framework/` | working (Linux headless) |
| package: APK parsing and install | `dine-atl/tests/package/` | placeholder |
| apps: real APKs end to end | `tests/android-compat/apps/` | placeholder |
| launcher: Dine's UI and logic | `tests/launcher/` | placeholder |

`tests/harness/` is the engine (`tools/dine test runtime`, `tools/dine test framework`). The corpus is mostly **harvested**
(AOSP ART run-tests, CTS, F-Droid apps), not written by hand; our own tests cover edge cases the
harvested ones miss.
