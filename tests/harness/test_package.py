import unittest

import package

S = package.Scenario("s", "session:ext", "Install", ("status -1 x", "status 0 x"),
                     rows=package._row("x", version_code=2))
OUT = "dialog: show\nscenario: status -1 x\nscenario: status 0 x\n"


class GradeScenarioTest(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(package.grade_scenario(S, 0, OUT, {"x": {"version_code": 2}}), [])

    def test_exit_and_other_lines(self):
        problems = package.grade_scenario(S, 1, "scenario: added x replacing=false\n", {"x": {"version_code": 2}})
        self.assertEqual(problems, ["exit 1", "printed ['added x replacing=false'], not ['status -1 x', 'status 0 x']"])

    def test_order_repeats_and_extra_lines_fail(self):
        for out in ("scenario: status 0 x\nscenario: status -1 x\n", OUT + "scenario: status 0 x\n",
                    OUT + "scenario: added x replacing=false\n"):
            with self.subTest(out):
                self.assertEqual(len(package.grade_scenario(S, 0, out, {"x": {"version_code": 2}})), 1)

    def test_rows(self):
        self.assertEqual(package.grade_scenario(S, 0, OUT, {}), ["x is not installed"])
        self.assertEqual(package.grade_scenario(S, 0, OUT, {"x": {"version_code": 3}}), ["x: {'version_code': (3, 2)}"])
        absent = package.Scenario("a", "", "", (), rows=package._row("x", absent=True))
        self.assertEqual(package.grade_scenario(absent, 0, "", {"x": {}}), ["x is installed"])


if __name__ == "__main__":
    unittest.main()
