# Tests

Two worlds: the code that runs Android apps (`android-compat`), and Dine itself (`launcher`).
Each suite lives in the repo that owns the code it tests; the engine stays here.

| Suite | Lives in | Status |
|---|---|---|
| runtime: ART interpreter + libcore (AOSP ART run-tests) | `dine-art/tests/runtime/` | working (Linux) |
| headless: ATL's headless build runs demo_app (view-tree dump vs golden), the looper APK (loop paths, clean exit), the dialog APK (scripted answers; also on gtk) and the nav APK (Back, Home, front through `-c`); `tools/dine linux smoke` runs them | `dine-atl/tests/headless/` | working (Linux) |
| framework: `android.*` APIs (ATL's api-impl) | `dine-atl/tests/framework/` | placeholder |
| package: APK parsing and install | `dine-atl/tests/package/` | placeholder |
| apps: real APKs end to end | `tests/android-compat/apps/` | placeholder |
| launcher: Dine's UI and logic | `tests/launcher/` | placeholder |

`tests/harness/` is the engine (`tools/dine test runtime`). The corpus is mostly **harvested**
(AOSP ART run-tests, CTS, F-Droid apps), not written by hand; our own tests cover edge cases the
harvested ones miss.
