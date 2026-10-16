# Runtime tests

AOSP's ART run-tests, run on our `dalvikvm` (`dine-art/`) in interpreter mode, the same mode
the iPhone will use (no JIT). Each test is a small Java/smali program with an `expected.txt`;
it passes when the VM exits 0 and prints exactly that output (stdout and stderr merged), as in
upstream `run-test`.

```sh
scripts/test-runtime.sh                       # fetch + build (incremental) + run; exit 1 = regression
scripts/test-runtime.sh -f '^00[0-9]-'        # subset by regex
scripts/test-runtime.sh run                   # rerun existing builds (e.g. after rebuilding ART)
scripts/test-runtime.sh --update-expectations # after a fix: rewrite the baseline, then commit it
python3 -m unittest discover -s tests/android-compat/runtime/harness   # harness unit tests
```

On 16 cores: cold (fetch + build all + run) ~4.5 min, warm ~45 s.

## Corpus

- **Upstream:** `art/test` from `android-security-10.0.0_r75`, the tag art_standalone's ART is
  rebased on (`corpus.toml`). Fetched as a sparse clone into `out/tests/runtime/upstream/`. Bump
  the tag together with any ART rebase, then rebaseline.
- **Authored:** `authored/<name>/`, same layout as upstream (`src/Main.java`, `expected.txt`,
  `info.txt`, optional `run`/`build`/`check`). Name them `dine-NNNN-<what>`.

Current result (2026-10-16, 842 tests): **576 pass**, 22 expected failures, 244 skipped.

## Stages

| Stage | What | Output |
|---|---|---|
| fetch | sparse clone at the pinned commit, fake AOSP tree for the build scripts, tool check | `out/tests/runtime/{upstream,top}` |
| build | upstream `etc/default-build` (or the test's own `build`, which wraps it) with javac 8, d8, smali, jasmin; classifies how to run the test | `out/tests/runtime/build/<test>/` + `bundle.json` |
| run | `dalvikvm -Xint` per test in parallel, in its own work dir (`DEX_LOCATION` = `ANDROID_DATA`) | `out/tests/runtime/runs/<id>/<test>/`, `runs/latest` |
| grade | diff against expected output (or the test's `check` script), then against expectations | `results.json`, summary |

A test is rebuilt only when its sources, `corpus.toml`, the shims, upstream `default-build`, the
build/classify code or art_standalone's libcore change. `bundle.json` is everything the run stage
needs, so builds are done once and reused.

The shims in `shims/` stand in for the AOSP tree: `d8` (build-tools d8 on JDK 21),
`javac-helper.sh` / `bootjars.sh` (compile and desugar against art_standalone's
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
so we don't execute them. `harness/classify.py` translates the common one-line form instead:
- Flags that only matter for dex2oat, images or JIT are ignored.
- `--runtime-option` / `--android-runtime-option` become VM args.
- `--args` adds main args, and `--secondary` adds the `-ex.jar` to the classpath.

## Expectations

`expectations/linux-x86_64.json` lists every test that doesn't pass yet, with what it does
(`fail`, `timeout`, `build-fail`, `flaky`) and why. A test that isn't listed must pass.
- **regression:** a result differs from its expectation (a new failure, or a different kind of
  failure). Exit 1.
- **fixed:** a listed test now passes. It's reported, and `--update-expectations` drops it.

Notable entries: StrictMath returns wrong results (082, 123), and the older libcore (8.1/9) lacks
APIs ART 10's tests use (VarHandles, `DelegateLastClassLoader`, …). A few tests need dex2oat
prebuild or AOSP host tools.

## Known runtime issue

art_standalone's libcore (8.1/9) aborted in `JNI_OnUnload` at every VM shutdown under ART 10
(`JavaVM::GetEnv() failed`, exit 134). It's fixed in dine-art
(`libcore/luni/src/main/native/Register.cpp`). On a tree without the fix, the harness strips
that crash dump when it comes from the runtime's "Shutdown thread" after the test's output, and
counts it in the summary; `--strict` fails those tests instead.
