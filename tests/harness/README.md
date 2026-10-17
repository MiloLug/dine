# Test harness

The engine behind `scripts/test-runtime.sh`. It runs AOSP ART run-tests on the local
`dalvikvm -Xint`. The suite it runs (corpus pin, expectations, our own tests) lives with the code
it tests, in `dine-art/tests/runtime/` (`RUNTIME` in `common.py`).

```sh
python3 -m unittest discover -s tests/harness   # harness unit tests (pure parts)
```

## Stages

| Stage | What | Output |
|---|---|---|
| fetch | sparse clone of AOSP `art/test` at the suite's pinned commit, fake AOSP tree for the build scripts, tool check | `out/tests/runtime/{upstream,top}` |
| build | upstream `etc/default-build` (or the test's own `build`, which wraps it) with javac 8, d8, smali, jasmin; classifies how to run the test | `out/tests/runtime/build/<test>/` + `bundle.json` |
| run | `dalvikvm` with the suite's `[run]` flags per test in parallel, in its own work dir (`DEX_LOCATION` = `ANDROID_DATA` = `XDG_CACHE_HOME`) | `out/tests/runtime/runs/<id>/<test>/`, `runs/latest` |
| grade | diff against expected output (or the test's `check` script), then against the suite's expectations | `results.json`, summary |

A test is rebuilt only when its sources, the suite's upstream pin (`[upstream]` in
`corpus.toml`), the shims, upstream `default-build`, `build.py`/`classify.py`, `tools/bin/d8` or
libcore's classes change. `bundle.json` is everything the run stage needs, so builds are done once
and reused.

art_standalone keeps its dalvik-cache (boot image, oat files) in `$XDG_CACHE_HOME/art`, not under
`ANDROID_DATA`, so each test gets its own `XDG_CACHE_HOME` and nothing lands in `~/.cache/art`.
With the suite's flags (no boot image, no dex2oat) the runtime writes nothing there anyway.

`d8` is the repo's `tools/bin/d8` (build-tools d8 on JDK 21). The shims in `shims/` stand in for
the AOSP tree: `javac-helper.sh` / `bootjars.sh` (compile and desugar against art_standalone's
`core-all_classes.jar`), and a copyright template the test generators read.

## Statuses

| Status | Meaning |
|---|---|
| `pass` | exit 0 and output matches (a test whose `check` accepts its failed build also passes, like upstream) |
| `fail` | wrong output or non-zero exit |
| `timeout` | over the per-test limit (default 120 s; overrides in `corpus.toml` `[timeouts]` or the test's `run --timeout`) |
| `build-fail` | the build script failed or produced no jar |
| `skip` | can't run here. Recomputed every build, never put in expectations |

Skip reasons:
- **jvmti:** needs the JVMTI test agent.
- **needs libarttest:** calls `System.loadLibrary(args[0])` for upstream's native test library,
  which we don't build yet.
- **custom run script:** the test's `run` script does more than pass flags to the VM.
- **run flag X:** the `run` script uses a flag we don't translate.

Upstream `run` scripts are bash on top of `etc/run-test-jar`, which needs a full AOSP host tree,
so we don't execute them. `classify.py` translates the common one-line form instead:
- Flags that only matter for dex2oat, images or JIT are ignored.
- `--runtime-option` / `--android-runtime-option` become VM args.
- `--args` adds main args, and `--secondary` adds the `-ex.jar` to the classpath.
