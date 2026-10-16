# Android compatibility tests

Tests for the code that runs Android apps, split by what they exercise:

| Dir | What | Corpus | Status |
|---|---|---|---|
| `runtime/` | ART interpreter + libcore (`java.*`), plain dex, no APK | AOSP ART run-tests | working (Linux) |
| `framework/` | `android.*` APIs (ATL's api-impl) | CTS pieces + our own | placeholder |
| `package/` | APK parsing and install: manifests, splits, signatures, multidex | small purpose-built APK set | placeholder |
| `apps/` | real apps launch and reach `onResume` | F-Droid, `atl_test_apks` | placeholder |
