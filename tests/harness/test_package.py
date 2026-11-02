import unittest

import package

S = package.Scenario("s", "session:ext", "Install", ("status 0 x",), never=("unscoped", "added"),
                     rows=package._row("x", version_code=2))
OUT = "dialog: show\nscenario: status -1 x\nscenario: status 0 x\n"


class GradeScenarioTest(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(package.grade_scenario(S, 0, OUT, {"x": {"version_code": 2}}), [])

    def test_exit_missing_marker_and_forbidden_line(self):
        problems = package.grade_scenario(S, 1, "scenario: added x replacing=false\n", {"x": {"version_code": 2}})
        self.assertEqual(problems, ["exit 1", "no 'status 0 x'", "printed 'added x replacing=false'"])

    def test_rows(self):
        self.assertEqual(package.grade_scenario(S, 0, OUT, {}), ["x is not installed"])
        self.assertEqual(package.grade_scenario(S, 0, OUT, {"x": {"version_code": 3}}), ["x: {'version_code': (3, 2)}"])
        absent = package.Scenario("a", "", "", (), rows=package._row("x", absent=True))
        self.assertEqual(package.grade_scenario(absent, 0, "", {"x": {}}), ["x is installed"])


if __name__ == "__main__":
    unittest.main()
