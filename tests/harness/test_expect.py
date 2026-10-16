import unittest

from expect import compare, update

EXPECT = {
    "002-fails": {"expect": "fail", "reason": "libcore too old"},
    "003-flaky": {"expect": "flaky", "reason": "timing"},
    "004-slow": {"expect": "timeout", "reason": "GC stress"},
    "009-gone": {"expect": "fail", "reason": "stale"},
}


class Compare(unittest.TestCase):
    def test_buckets(self):
        results = {
            "001-ok": "pass",
            "002-fails": "fail",
            "003-flaky": "pass",
            "004-slow": "pass",
            "005-new": "fail",
            "006-skip": "skip",
            "007-bf": "build-fail",
        }
        c = compare(results, EXPECT)
        self.assertEqual(c.regressions, ["005-new", "007-bf"])
        self.assertEqual(c.fixed, ["004-slow"])
        self.assertEqual(c.expected_failures, ["002-fails"])

    def test_changed_failure_kind_is_regression(self):
        self.assertEqual(compare({"002-fails": "timeout"}, EXPECT).regressions, ["002-fails"])

    def test_skipped_tests_not_compared(self):
        c = compare({"002-fails": "skip"}, EXPECT)
        self.assertEqual((c.regressions, c.fixed), ([], []))


class Update(unittest.TestCase):
    def test_rewrites_ran_tests_keeps_others(self):
        results = {"002-fails": "pass", "003-flaky": "fail", "004-slow": "timeout", "005-new": "fail",
                   "001-ok": "pass", "006-skip": "skip"}
        new = update(results, EXPECT, "baseline 2026-10-16")
        self.assertEqual(new, {
            "003-flaky": {"expect": "flaky", "reason": "timing"},
            "004-slow": {"expect": "timeout", "reason": "GC stress"},
            "005-new": {"expect": "fail", "reason": "baseline 2026-10-16"},
            "009-gone": {"expect": "fail", "reason": "stale"},
        })

    def test_new_failure_kind_keeps_reason(self):
        new = update({"002-fails": "timeout"}, EXPECT, "baseline")
        self.assertEqual(new["002-fails"], {"expect": "timeout", "reason": "libcore too old"})


if __name__ == "__main__":
    unittest.main()
