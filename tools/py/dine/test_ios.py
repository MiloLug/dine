import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dine import ios
from dine.paths import DineError


class ReleaseFlagTest(unittest.TestCase):
    def test_values(self):
        for value, want in (("", False), ("0", False), ("1", True)):
            with mock.patch.dict(os.environ, {"DINE_RELEASE": value}):
                self.assertEqual(ios.release(), want)
        with mock.patch.dict(os.environ, {"DINE_RELEASE": "true"}):
            with self.assertRaisesRegex(DineError, "DINE_RELEASE='true'"):
                ios.release()


class AtlHooksTest(unittest.TestCase):
    def build(self, options: list[dict]) -> Path:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "meson-info").mkdir()
        (tmp / "meson-info/intro-buildoptions.json").write_text(json.dumps(options))
        return tmp

    def test_matching_build(self):
        self.assertIsNone(ios.atl_hooks_problem(self.build([{"name": "test_hooks", "value": True}]), release=False))
        self.assertIsNone(ios.atl_hooks_problem(self.build([{"name": "test_hooks", "value": False}]), release=True))

    def test_mismatch_names_the_build(self):
        problem = ios.atl_hooks_problem(self.build([{"name": "test_hooks", "value": True}]), release=True)
        self.assertIn("test_hooks=true, this is a release build: run DINE_RELEASE=1 tools/dine ios build-atl", problem)
        problem = ios.atl_hooks_problem(self.build([{"name": "test_hooks", "value": False}]), release=False)
        self.assertIn("test_hooks=false, this is a dev build: run tools/dine ios build-atl", problem)

    def test_missing_build_or_option(self):
        self.assertIn("no iOS ATL build", ios.atl_hooks_problem(Path(tempfile.gettempdir()) / "no-such-build", False))
        self.assertIn("predates its test_hooks option", ios.atl_hooks_problem(self.build([{"name": "ui", "value": "uikit"}]), False))

class AtlJarsTest(unittest.TestCase):
    def test_staged_jars_must_be_the_linux_builds(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        for d in ("linux", "staged"):
            (tmp / d).mkdir()
            for name in ("api-impl.jar", "framework-res.apk"):
                (tmp / d / name).write_bytes(b"same")
        self.assertIsNone(ios.atl_jars_problem(tmp / "linux", tmp / "staged"))
        (tmp / "linux/api-impl.jar").write_bytes(b"rebuilt")
        self.assertIn("ios build-atl", ios.atl_jars_problem(tmp / "linux", tmp / "staged"))
        (tmp / "staged/framework-res.apk").unlink()
        self.assertIn("ios build-atl", ios.atl_jars_problem(tmp / "linux", tmp / "staged"))


class InstalledTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        (self.tmp / "out/ios/lib").mkdir(parents=True)
        (self.tmp / "out/ios/lib/libart.a").write_bytes(b"1")
        (self.tmp / "apps/App/Sources").mkdir(parents=True)
        (self.tmp / "apps/App/Sources/Main.swift").write_text("a")
        for name, value in (("ROOT", self.tmp), ("OUT", self.tmp / "out"), ("APPS", self.tmp / "apps")):
            patch = mock.patch.object(ios.paths, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def test_install_must_match_the_checkout(self):
        with self.assertRaisesRegex(DineError, "ios run"):
            ios.check_installed("App")
        (self.tmp / "out/ios/App.installed").write_text(ios.install_fingerprint("App"))
        ios.check_installed("App")
        (self.tmp / "out/ios/lib/libart.a").write_bytes(b"22")
        with self.assertRaisesRegex(DineError, "ios run"):
            ios.check_installed("App")
        (self.tmp / "out/ios/App.installed").write_text(ios.install_fingerprint("App"))
        (self.tmp / "apps/App/Sources/New.swift").write_text("b")
        with self.assertRaisesRegex(DineError, "ios run"):
            ios.check_installed("App")


if __name__ == "__main__":
    unittest.main()
