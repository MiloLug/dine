# Android compatibility tests

Tests for the code that runs Android apps. Suites that test one component live in that
component's fork; only the end-to-end app tests live here.

| Suite | What | Lives in | Status |
|---|---|---|---|
| runtime | ART interpreter + libcore (`java.*`), plain dex, no APK | `dine-art/tests/runtime/` | working (Linux) |
| framework | `android.*` APIs (ATL's api-impl) | `dine-atl/tests/framework/` | working (Linux headless, gtk) |
| package | install, query and removal through the registry | `dine-atl/tests/package/` | working (Linux headless) |
| apps | real apps launch and reach `onResume` | `apps/` | working (Linux headless, gtk) |
