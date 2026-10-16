import tempfile
import unittest
from pathlib import Path

from classify import RunSpec, Unsupported, classify, expand_vars, parse_run_script

SHEBANG = "#!/bin/bash\n#\n# Copyright (C) 2017 The Android Open Source Project\n\n"


class ParseRunScript(unittest.TestCase):
    def test_passthrough_gets_testlib(self):
        spec = parse_run_script(SHEBANG + 'exec ${RUN} "${@}" --no-app-image\n')
        self.assertEqual(spec, RunSpec(main_args=["arttestd"]))

    def test_default_run_form(self):
        spec = parse_run_script(SHEBANG + './default-run "$@" --runtime-option -Xmx2m\n')
        self.assertEqual(spec.vm_args, ["-Xmx2m"])
        self.assertEqual(spec.main_args, ["arttestd"])

    def test_args_follow_passthrough(self):
        spec = parse_run_script('exec ${RUN} $@ --args foo\n')
        self.assertEqual(spec.main_args, ["arttestd", "foo"])

    def test_args_before_passthrough(self):
        spec = parse_run_script('exec ${RUN} --args foo "$@"\n')
        self.assertEqual(spec.main_args, ["foo", "arttestd"])

    def test_ignored_flags_consume_their_argument(self):
        spec = parse_run_script(
            'exec ${RUN} $@ --profile -Xcompiler-option --compiler-filter=speed-profile --vdex\n')
        self.assertEqual(spec, RunSpec(main_args=["arttestd"]))

    def test_dex2oat_timeouts_ignored(self):
        spec = parse_run_script('./default-run "$@" --dex2oat-timeout 120 --dex2oat-rt-timeout 180\n')
        self.assertEqual(spec, RunSpec(main_args=["arttestd"]))

    def test_line_continuation_and_set_e(self):
        spec = parse_run_script('set -e\n./default-run "$@" \\\n  --android-runtime-option -Xjitthreshold:0\n')
        self.assertEqual(spec.vm_args, ["-Xjitthreshold:0"])

    def test_secondary_verify_timeout(self):
        spec = parse_run_script('exec ${RUN} "${@}" --secondary --verify-soft-fail --timeout 300\n')
        self.assertTrue(spec.secondary)
        self.assertEqual(spec.vm_args, ["-Xverify:softfail"])
        self.assertEqual(spec.timeout, 300)

    def test_positional_sets_main(self):
        self.assertEqual(parse_run_script('exec ${RUN} "$@" Other\n').main, "Other")

    def test_lib_substitution_counts_as_passthrough(self):
        spec = parse_run_script('exec ${RUN} "${@/#libartd.so/libart.so}"\n')
        self.assertEqual(spec.main_args, ["arttestd"])

    def test_jvmti(self):
        with self.assertRaisesRegex(Unsupported, "^jvmti$"):
            parse_run_script('./default-run "$@" --jvmti\n')

    def test_unknown_flag(self):
        with self.assertRaisesRegex(Unsupported, "--strip-dex"):
            parse_run_script('exec ${RUN} "$@" --strip-dex\n')

    def test_multiple_statements(self):
        with self.assertRaisesRegex(Unsupported, "custom run script"):
            parse_run_script('./default-run "$@"\necho "exit status:" $?\n')

    def test_other_command(self):
        with self.assertRaisesRegex(Unsupported, "custom run script"):
            parse_run_script('echo "Blort."\n')


class ExpandVars(unittest.TestCase):
    def test_braced_and_bare(self):
        env = {"DEX_LOCATION": "/w"}
        self.assertEqual(expand_vars(["-Xmethod-trace-file:${DEX_LOCATION}/t.bin", "$DEX_LOCATION", "x"], env),
                         ["-Xmethod-trace-file:/w/t.bin", "/w", "x"])

    def test_unknown_left_alone(self):
        self.assertEqual(expand_vars(["${NOPE}"], {}), ["${NOPE}"])


class Classify(unittest.TestCase):
    def make(self, files):
        root = Path(tempfile.mkdtemp())
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        return root

    def test_plain(self):
        d = self.make({"src/Main.java": "class Main {}", "expected.txt": ""})
        self.assertEqual(classify(d), (RunSpec(main_args=["arttestd"]), None))

    def test_needs_libarttest(self):
        d = self.make({"src/Main.java": "System.loadLibrary( args[0] );", "expected.txt": ""})
        self.assertEqual(classify(d), (None, "needs libarttest"))

    def test_jvmti_beats_custom_script(self):
        d = self.make({"run": 'if true; then\n./default-run "$@" --jvmti\nfi\n'})
        self.assertEqual(classify(d), (None, "jvmti"))

    def test_unsupported_run(self):
        d = self.make({"run": 'exec ${RUN} "$@" --zygote\n'})
        self.assertEqual(classify(d), (None, "run flag --zygote"))


if __name__ == "__main__":
    unittest.main()
