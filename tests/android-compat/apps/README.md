# App tests

Real APKs from `third_party/apks` (never committed), listed in `apps.toml`: each runs to its log markers
(`onResume`; on headless the draw pass's `atl frames` line for an app that keeps drawing), with no
fatal line (`UnsatisfiedLinkError`, a CheckJNI abort), and must still run a few seconds after.
`tools/dine test apps` runs them on the headless build, `--gtk` on the gtk one; `expectations/`
holds each build's known failures. On the phone, `dbg smoke atl-gd` runs Gravity Defied from its
dev tile.
