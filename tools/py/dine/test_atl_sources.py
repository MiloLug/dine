"""Rules for dine-atl's C that no compiler checks (notes/decisions.md)."""

import unittest

from dine import paths
from dine.dbg import smoke

SRC = paths.ROOT / "dine-atl/src"


class JniRefsTest(unittest.TestCase):
    # _METHOD(_CLASS(obj), …) leaves the class's local ref behind; _METHOD_OF(obj, …) deletes it
    def test_no_method_lookup_leaves_a_class_ref(self):
        hits = [f"{path.relative_to(SRC)}:{n}"
                for path in sorted(SRC.rglob("*")) if path.suffix in (".c", ".m", ".h")
                for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1)
                if "_METHOD(_CLASS(" in line]
        self.assertEqual(hits, [])


class ClearedExceptionLineTest(unittest.TestCase):
    # the line clear_app_exception prints is what the framework harness and the phone smoke look for
    def test_the_instruments_read_the_line_c_prints(self):
        line = "atl: app exception cleared"
        self.assertIn(f'"{line}:\\n"', (SRC / "api-impl-jni/util.c").read_text())
        self.assertIn(f'CLEARED = "{line}:"', (paths.ROOT / "tests/harness/framework.py").read_text())
        self.assertIn(line, smoke.FATAL)


if __name__ == "__main__":
    unittest.main()
