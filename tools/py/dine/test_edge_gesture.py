"""tests/launcher's check of Dine's edge classifier, built for this machine with swift-bin's swiftc."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from dine import paths

SOURCE = paths.APPS / "Dine/Sources/Dine/EdgeGesture.swift"
TEST = paths.ROOT / "tests/launcher/edge_gesture_test.swift"


class EdgeGestureTest(unittest.TestCase):
    def test_classifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "edge-gesture"
            built = subprocess.run(["swiftc", "-swift-version", "6", "-parse-as-library", "-o", str(binary), str(SOURCE), str(TEST)],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual((ran.returncode, ran.stdout.strip()), (0, "edge gestures ok"), ran.stdout + ran.stderr)


if __name__ == "__main__":
    unittest.main()
