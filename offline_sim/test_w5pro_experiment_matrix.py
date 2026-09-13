from __future__ import annotations

import unittest

from q4.w5pro_experiment_matrix import ERROR_FIELD_NAMES, STRESS_SUITE_NAMES, ExperimentSpec, full_matrix, make_experiment_case


class W5ProExperimentMatrixTests(unittest.TestCase):
    def test_all_required_stress_suites_are_constructible(self):
        self.assertEqual(len(STRESS_SUITE_NAMES), 10)
        for suite in STRESS_SUITE_NAMES:
            case = make_experiment_case(ExperimentSpec(suite, 7, "adversarial"))
            self.assertEqual(case.mode, "formal")
            self.assertEqual(case.total, 16 if suite == "max_count" else case.total)

    def test_all_error_fields_are_in_matrix(self):
        self.assertEqual(set(ERROR_FIELD_NAMES), {"smooth", "iid", "biased", "adversarial", "piecewise"})
        matrix = full_matrix(3)
        self.assertEqual(len(matrix), 11 * len(ERROR_FIELD_NAMES))


if __name__ == "__main__":
    unittest.main()
