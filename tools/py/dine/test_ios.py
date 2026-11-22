import asyncio
import contextlib
import io
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from dine import ios, linux
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

    def test_install_covers_resources_and_the_payloads_sources(self):
        for name in ("apps/App/Resources/Assets.xcassets/Contents.json", "dine-atl/tests/headless/nav/src/A.java",
                     "dine-atl/tests/package/fixtures/driver/src/Main.java", "dine-atl/tests/package/keys/a.p12",
                     "dine-art/tests/runtime/authored/dine-0002-jni-args/src/Main.java"):
            with self.subTest(name):
                (self.tmp / "out/ios/App.installed").write_text(ios.install_fingerprint("App"))
                (self.tmp / name).parent.mkdir(parents=True)
                (self.tmp / name).write_text("edited")
                with self.assertRaisesRegex(DineError, "ios run"):
                    ios.check_installed("App")

    def test_a_golden_edit_needs_no_install(self):
        (self.tmp / "dine-atl/tests/headless/nav").mkdir(parents=True)
        (self.tmp / "out/ios/App.installed").write_text(ios.install_fingerprint("App"))
        (self.tmp / "dine-atl/tests/headless/views.viewtree").write_text("viewtree: end")
        ios.check_installed("App")


class DeviceDeadlineTest(unittest.TestCase):
    def test_a_device_call_that_never_returns_ends(self):
        rsd = mock.Mock()
        rsd.close = mock.AsyncMock()

        async def hangs(_):
            await asyncio.sleep(5)
        start = time.monotonic()
        with mock.patch("pymobiledevice3.tunneld.api.get_tunneld_devices", mock.AsyncMock(return_value=[rsd])):
            with self.assertRaisesRegex(DineError, "didn't answer within"):
                ios._with_rsd(hangs, timeout=0.2)
        self.assertLess(time.monotonic() - start, 2)
        rsd.close.assert_awaited()

    def test_the_calls_own_timeout_stays_its_own(self):
        rsd = mock.Mock()
        rsd.close = mock.AsyncMock()

        async def times_out(_):
            raise TimeoutError
        with mock.patch("pymobiledevice3.tunneld.api.get_tunneld_devices", mock.AsyncMock(return_value=[rsd])):
            with self.assertRaises(TimeoutError):
                ios._with_rsd(times_out, timeout=5)


class BuildNativeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        lib = self.tmp / "native/dev/probe"
        (lib / "include").mkdir(parents=True)
        (lib / "CMakeLists.txt").write_text("project(probe CXX)\nadd_library(dineprobe STATIC probe.cpp)\n")
        (lib / "include/dineprobe.h").write_text("")
        for name in ("lib/libdineprobe.a", "lib/libart.a", "include/dineprobe.h", "include/jni.h"):
            (self.tmp / "out/ios" / name).parent.mkdir(parents=True, exist_ok=True)
            (self.tmp / "out/ios" / name).write_text("")
        for name, value in (("ROOT", self.tmp), ("OUT", self.tmp / "out")):
            patch = mock.patch.object(ios.paths, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def build(self, release: str) -> set[str]:
        with mock.patch.dict(os.environ, {"DINE_RELEASE": release}), \
                mock.patch.object(ios, "run_libexec", return_value=0) as run:
            self.assertEqual(ios.build_native("artbridge"), 0)
        run.assert_called_once_with("build-ios-native.sh", "artbridge")
        return {p.name for p in (self.tmp / "out/ios").rglob("*") if p.is_file()}

    def test_release_removes_what_a_dev_build_installed(self):
        self.assertEqual(self.build("1"), {"libart.a", "jni.h"})

    def test_dev_removes_nothing(self):
        self.assertEqual(self.build(""), {"libdineprobe.a", "libart.a", "dineprobe.h", "jni.h"})


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        for patch in (mock.patch.object(ios, "require_tunnel"),
                      mock.patch.object(ios, "build_native", return_value=0),
                      mock.patch.object(ios, "_install_stamp", return_value=self.tmp / "stamp")):
            patch.start()
            self.addCleanup(patch.stop)

    def test_release_takes_no_lock_on_the_linux_builds(self):
        busy = DineError("the Linux builds are being built")
        with mock.patch.dict(os.environ, {"DINE_RELEASE": "1"}), mock.patch.object(linux, "builds", side_effect=busy), \
                mock.patch.object(ios, "run_libexec", side_effect=lambda script, *a: int("assets" in script)):
            self.assertEqual(ios.cmd_install("Dine"), 1)

    def test_a_dev_bundle_without_a_marker_fails(self):
        with mock.patch.dict(os.environ, {"DINE_RELEASE": ""}), \
                mock.patch.object(linux, "builds", return_value=contextlib.nullcontext()), \
                mock.patch.object(ios, "run_libexec", return_value=0), \
                mock.patch.object(ios.subprocess, "Popen") as popen, mock.patch.object(ios.os, "read", return_value=b""), \
                mock.patch.object(ios, "install_fingerprint", return_value="fingerprint"), \
                mock.patch.object(ios, "dev_marker_problems", return_value=["Dine lacks 'probe done '"]), \
                contextlib.redirect_stderr(io.StringIO()) as said:
            popen.return_value.wait.return_value = 0
            self.assertEqual(ios.cmd_install("Dine"), 1)
        self.assertIn("lacks 'probe done '", said.getvalue())
        self.assertFalse((self.tmp / "stamp").exists())


class LaunchTest(unittest.TestCase):
    def test_a_refused_launch_names_the_phones_state(self):
        from pymobiledevice3.dtx.exceptions import DTXNsError
        refused = DTXNsError.__new__(DTXNsError)
        Exception.__init__(refused, "Request to launch dev.dine.Dine failed.")
        with mock.patch.object(ios, "require_tunnel"), mock.patch.object(ios, "_with_rsd", side_effect=refused):
            with self.assertRaisesRegex(DineError, "phone locked"):
                ios.launch("Dine")


class ReleaseBundleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bundle = self.tmp / "App.app"
        (self.bundle / "dev").mkdir(parents=True)
        (self.bundle / "App").write_bytes(b"\xcf\xfa release code")
        (self.bundle / "Assets.car").write_bytes(b"DefaultApp")
        self.lib = self.tmp / "lib"
        self.lib.mkdir()
        (self.lib / "libart.a").write_bytes(b"!<arch>")

    def problems(self):
        return ios.release_problems(self.bundle, "App", self.lib)

    def test_clean_release(self):
        self.assertEqual(self.problems(), [])

    def test_payload(self):
        (self.bundle / "dev/package").mkdir()
        (self.bundle / "dev/package/ext.apk").write_bytes(b"PK")
        self.assertIn("dev/package/ext.apk", "\n".join(self.problems()))

    def test_each_marker(self):
        for file, markers in ios.DEV_MARKERS.items():
            path = self.bundle / file.format(app="App")
            before = path.read_bytes()
            for marker in markers:
                with self.subTest(marker):
                    path.write_bytes(before + marker.encode() + b"\0")
                    self.assertIn(marker, "\n".join(self.problems()))
            path.write_bytes(before)

    def test_dev_archive_left_to_the_link(self):
        for name in ios.dev_archives():
            with self.subTest(name):
                (self.lib / name).write_bytes(b"!<arch>")
                self.assertIn(name, "\n".join(self.problems()))
                (self.lib / name).unlink()

    def test_a_marker_gone_from_a_dev_bundle_is_named(self):
        for file, markers in ios.DEV_MARKERS.items():
            path = self.bundle / file.format(app="App")
            path.write_bytes("\0".join(markers).encode())
        self.assertEqual(ios.dev_marker_problems(self.bundle, "App"), [])
        for file, markers in ios.DEV_MARKERS.items():
            path = self.bundle / file.format(app="App")
            whole = path.read_bytes()
            for marker in markers:
                with self.subTest(marker):
                    path.write_bytes(whole.replace(marker.encode(), b"renamed"))
                    self.assertIn(marker, "\n".join(ios.dev_marker_problems(self.bundle, "App")))
            path.write_bytes(whole)

    def test_every_dev_lib_is_known(self):
        self.assertEqual(sorted(ios.dev_archives()), ["libdbgagent.a", "libdinehello.a", "libruntimetests.a"])

    def test_no_bundle(self):
        shutil.rmtree(self.bundle)
        self.assertTrue(self.problems())


if __name__ == "__main__":
    unittest.main()
