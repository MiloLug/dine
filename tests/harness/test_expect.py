import json
import tempfile
import unittest
from pathlib import Path

from expect import NO_TESTS, compare, inventory_path, settle, update

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


class Settle(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name, "linux.json")
        self.path.write_text(json.dumps({"002-fails": {"expect": "fail", "reason": "ART-1"}}))
        inventory_path(self.path).write_text("001-ok\n002-fails\n")
        self.lines = []

    def settle(self, results, *, whole=True, record=False, **kwargs):
        return settle(results, self.path, whole=whole, record=record, new_reason="baseline",
                      out=self.lines.append, **kwargs)[1]

    def stored(self):
        return json.loads(self.path.read_text()), inventory_path(self.path).read_text().split()

    def test_baseline_run_is_green(self):
        self.assertEqual(self.settle({"001-ok": "pass", "002-fails": "fail"}), 0)

    def test_regression_fails_and_is_never_recorded(self):
        results = {"001-ok": "crash", "002-fails": "fail"}
        self.assertEqual(self.settle(results), 1)
        self.assertEqual(self.settle(results, record=True), 1)
        self.assertEqual(self.stored(), ({"002-fails": {"expect": "fail", "reason": "ART-1"}}, ["001-ok", "002-fails"]))

    def test_stale_entry_fails_until_recorded(self):
        results = {"001-ok": "pass", "002-fails": "pass"}
        self.assertEqual(self.settle(results), 1)
        self.assertEqual(self.settle(results, record=True), 0)
        self.assertEqual(self.stored()[0], {})
        self.assertEqual(self.settle(results), 0)

    def test_listed_test_that_did_not_run_is_a_regression(self):
        self.assertEqual(self.settle({"002-fails": "fail"}), 1)
        self.assertEqual(self.settle({"001-ok": "skip", "002-fails": "fail"}), 1)
        self.assertIn("MISSING: 001-ok", " ".join(self.lines))
        self.assertEqual(self.settle({"002-fails": "fail"}, record=True), 1)
        self.assertEqual(self.stored()[1], ["001-ok", "002-fails"])

    def test_optional_and_filtered_runs_may_leave_tests_out(self):
        self.assertEqual(self.settle({"002-fails": "fail"}, optional=frozenset({"001-ok"})), 0)
        self.assertEqual(self.settle({"002-fails": "fail"}, whole=False), 0)

    def test_new_test_is_listed_by_record_only(self):
        results = {"001-ok": "pass", "002-fails": "fail", "003-new": "pass", "suite:x": "pass"}
        self.assertEqual(self.settle(results, listed=lambda n: not n.startswith("suite:")), 0)
        self.assertEqual(self.stored()[1], ["001-ok", "002-fails"])
        self.assertEqual(self.settle(results, record=True, listed=lambda n: not n.startswith("suite:")), 0)
        self.assertEqual(self.stored()[1], ["001-ok", "002-fails", "003-new"])

    def test_filtered_record_keeps_the_inventory(self):
        self.assertEqual(self.settle({"002-fails": "pass"}, whole=False, record=True), 0)
        self.assertEqual(self.stored(), ({}, ["001-ok", "002-fails"]))

    def test_run_of_nothing_is_an_error(self):
        self.assertEqual(self.settle({}), NO_TESTS)
        self.assertEqual(self.settle({"001-ok": "skip"}, whole=False), NO_TESTS)

    def test_first_record_of_a_suite_writes_its_failures(self):
        self.path.unlink()
        inventory_path(self.path).unlink()
        self.assertEqual(self.settle({"001-ok": "pass", "005-new": "fail"}, record=True), 0)
        self.assertEqual(self.stored(), ({"005-new": {"expect": "fail", "reason": "baseline"}}, ["001-ok", "005-new"]))


if __name__ == "__main__":
    unittest.main()
