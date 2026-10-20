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


if __name__ == "__main__":
    unittest.main()
