import re
import unittest
from unittest import mock

from dine.dbg import smoke
from dine.dbg.targets.ios import parked_in_kernel

GOLDEN = """viewtree: android.widget.FrameLayout 0,0 960x540
viewtree:   android.widget.LinearLayout 0,0 960x540
viewtree:     android.widget.TextView 0,0 135x17 "hello PoC world!"
viewtree:     android.widget.TextView 0,17 160x17 "second one (static)"
viewtree: end
"""
PHONE = """since launch #3
5 matches
viewtree: android.widget.FrameLayout 0,0 1170x2391
viewtree:   android.widget.LinearLayout 0,0 1170x2391 
viewtree:     android.widget.TextView 0,0 351x51 "hello PoC world!"
viewtree:     android.widget.TextView 0,51 402x51 "second one (static)"
viewtree: end
cursor 40"""


class SmokeTableTest(unittest.TestCase):
    def test_table_shape(self):
        scenarios = smoke.table("Dine")
        names = [sc.name for sc in scenarios]
        self.assertEqual(len(names), len(set(names)))
        for sc in scenarios:
            self.assertTrue(sc.steps, sc.name)
            last = sc.steps[-1]
            self.assertTrue(last.back or last.action == "Home", f"{sc.name} must end back on the launcher")
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

    def test_viewtree_shape_against_golden(self):
        self.assertIsNone(smoke.viewtree_problem(GOLDEN, GOLDEN))
        self.assertIsNone(smoke.viewtree_problem(PHONE, GOLDEN))
        cases = [
            ("another tree", PHONE.replace('viewtree:     android.widget.TextView 0,51 402x51 "second one (static)"\n', "")),
            ("line 3: another view", PHONE.replace("hello PoC", "hello")),
            ("line 3: another x", PHONE.replace("0,0 351x51", "4,0 351x51")),
            ("line 4: not below its previous sibling", PHONE.replace("0,51 402x51", "0,50 402x51")),
            ("line 2: doesn't fill the window", PHONE.replace("0,0 1170x2391 ", "0,0 1170x2000")),
            ("line 3: empty text", PHONE.replace("351x51", "0x51")),
            ("another tree", PHONE.replace("viewtree: end", "")),
        ]
        for problem, log in cases:
            with self.subTest(problem):
                self.assertIn(f"({problem})", smoke.viewtree_problem(log, GOLDEN) or "")


class FakeServer:
    """The debug server as smoke.run uses it: a tap logs the lines scripted for its label."""

    def __init__(self, taps: dict[str, list[str]]):
        self.taps, self.log, self.mark = taps, ["loaded 0 apps"], 0

    def call(self, cmd, args=None, timeout=None):
        args = args or {}
        if cmd == "ui_tap":
            self.mark = len(self.log)
            self.log += self.taps[args["arg"]]
        elif cmd == "wait":
            for line in self.log[self.mark:]:
                for pattern in args["log_re"]:
                    if re.search(pattern, line):
                        return {"code": 0, "text": f"matched --log-re {pattern!r}: {line}"}
            return {"code": 2, "text": "timeout"}
        elif cmd == "log":
            hits = [line for line in self.log[args["since"]:] if re.search(args["pattern"], line, re.I)]
            return {"code": 0, "text": "\n".join([f"{len(hits)} matches", *hits[-1:], f"cursor {len(self.log)}"])}
        return {"code": 0, "text": "", "cursor": len(self.log)}


class SmokeRunTest(unittest.TestCase):
    STEPS = [smoke.Step("go", tap="go", ok=("done",), fail=("bad",)),
             smoke.Step("quiet", tap="quiet", fail=("bad",)),
             smoke.Step("back", back=True)]

    def run_smoke(self, **taps) -> tuple[int, str]:
        server = FakeServer({"go": ["done"], "quiet": [], **taps})
        lines = []
        with mock.patch.object(smoke.client, "call", server.call), \
                mock.patch.dict(smoke.SCENARIOS, {"T": [smoke.Scenario("s", self.STEPS)]}), \
                mock.patch.dict(smoke.STARTUP, {"T": "loaded"}):
            return smoke.run("T", [], False, lambda: 1, out=lines.append), "\n".join(lines)

    def test_clean_run_passes(self):
        self.assertEqual(self.run_smoke()[0], 0)

    def test_missing_ok_line_fails(self):
        self.assertEqual(self.run_smoke(go=["other"])[0], 1)

    def test_fail_line_before_the_ok_line_fails(self):
        rc, text = self.run_smoke(go=["bad", "done"])
        self.assertEqual((rc, "s: go: FAILED (bad)" in text), (1, True))

    def test_fail_line_after_the_ok_line_fails(self):
        rc, text = self.run_smoke(go=["done", "bad"])
        self.assertEqual((rc, "s: go: FAILED ('bad': bad)" in text), (1, True))

    def test_fail_line_in_a_step_that_waits_for_nothing_fails(self):
        rc, text = self.run_smoke(quiet=["bad"])
        self.assertEqual((rc, "s: quiet: FAILED" in text), (1, True))

    def test_fatal_line_fails_the_scenario(self):
        rc, text = self.run_smoke(quiet=["E/art: java.lang.UnsatisfiedLinkError: No implementation found"])
        self.assertEqual((rc, "s: FAILED: 'UnsatisfiedLinkError'" in text), (1, True))


class ExecGuardTest(unittest.TestCase):
    def test_parked_in_kernel(self):
        self.assertTrue(parked_in_kernel("com.apple.root.default-qos", "libsystem_kernel.dylib"))
        self.assertTrue(parked_in_kernel(None, "libsystem_kernel.dylib"))
        self.assertFalse(parked_in_kernel("com.apple.main-thread", "libsystem_kernel.dylib"))
        self.assertFalse(parked_in_kernel(None, "Dine"))


if __name__ == "__main__":
    unittest.main()
