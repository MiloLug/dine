import re
import unittest

from dine.dbg import smoke
from dine.dbg.targets.ios import parked_in_kernel

GOLDEN = "viewtree: a\nviewtree:   b\nviewtree: end\n"


class SmokeTableTest(unittest.TestCase):
    def test_table_shape(self):
        scenarios = smoke.table("Dine")
        names = [sc.name for sc in scenarios]
        self.assertEqual(len(names), len(set(names)))
        for sc in scenarios:
            self.assertTrue(sc.steps, sc.name)
            self.assertTrue(sc.steps[-1].back, f"{sc.name} must end back on the launcher")
            for st in sc.steps:
                for rx in st.ok + st.fail:
                    re.compile(rx)

    def test_atl_scenarios_get_a_clean_process(self):
        for sc in smoke.table("Dine"):
            if sc.name.startswith("atl"):
                self.assertTrue(sc.needs_clean and sc.uses_vm, sc.name)

    def test_fail_hit_reads_the_matched_condition(self):
        fail = ("art main threw", r"atl main returned (?!0\b)")
        self.assertEqual(smoke.fail_hit("matched --log-re 'art main threw':\n  #5 …", fail), "art main threw")
        self.assertIsNone(smoke.fail_hit("matched --log-re 'jni args ok':\n  #5 …", fail))
        stale = "warning: the server runs older dbg code: …\nmatched --log-re 'art main threw':\n  #5 …"
        self.assertEqual(smoke.fail_hit(stale, fail), "art main threw")
        self.assertIsNone(re.search(fail[1], "atl main returned 0"))
        self.assertIsNotNone(re.search(fail[1], "atl main returned -1"))

    def test_viewtree_against_golden(self):
        log = "since launch #3\n3 matches\nviewtree: a\nviewtree:   b \nviewtree: end\ncursor 40"
        self.assertIsNone(smoke.viewtree_problem(log, GOLDEN))
        self.assertIn("differs", smoke.viewtree_problem("viewtree: a\nviewtree: end", GOLDEN))


class ExecGuardTest(unittest.TestCase):
    def test_parked_in_kernel(self):
        self.assertTrue(parked_in_kernel("com.apple.root.default-qos", "libsystem_kernel.dylib"))
        self.assertTrue(parked_in_kernel(None, "libsystem_kernel.dylib"))
        self.assertFalse(parked_in_kernel("com.apple.main-thread", "libsystem_kernel.dylib"))
        self.assertFalse(parked_in_kernel(None, "Dine"))


if __name__ == "__main__":
    unittest.main()
