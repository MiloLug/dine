# Tests

Two separate worlds, with their own runners:

| Dir | Tests | Status |
|---|---|---|
| `android-compat/` | the code that runs Android apps: runtime, framework, packages, real apps | `runtime/` works; the rest are placeholders |
| `launcher/` | Dine itself: app grid, library database, settings | placeholder |

The corpus is mostly **harvested** (AOSP ART run-tests, CTS, F-Droid apps), not written by hand.
Our own tests cover edge cases the harvested ones miss.
