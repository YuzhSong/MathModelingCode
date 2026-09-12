from __future__ import annotations

import unittest

from offline_sim.case import generate_case
from offline_sim.harness import run_episode
from q3.models import Point
from q3.offline_policy import policy_v4
from q3.v5_policy import policy_v4_diagnostic, policy_v5a, policy_v5b
from q3.v5_prediction import sample_feasible_polygon


class V5RegressionTests(unittest.TestCase):
    def test_polygon_sampling_is_reproducible(self) -> None:
        polygon = [Point(0.0, 0.0), Point(10.0, 0.0), Point(10.0, 10.0), Point(0.0, 10.0)]
        first = sample_feasible_polygon(polygon, count=16, seed=20260911)
        second = sample_feasible_polygon(polygon, count=16, seed=20260911)
        self.assertEqual(first, second)
        self.assertTrue(all(0.0 <= point.x <= 10.0 and 0.0 <= point.y <= 10.0 for point in first))

    def test_diagnostic_v4_preserves_frozen_policy_behavior(self) -> None:
        base = run_episode(
            generate_case(seed=0, problem=3, mode="practice", field_kind="smooth"),
            lambda runner: policy_v4(runner, n=8),
            include_oracles=False,
        )
        diagnostic = run_episode(
            generate_case(seed=0, problem=3, mode="practice", field_kind="smooth"),
            lambda runner: policy_v4_diagnostic(runner, n=8),
            include_oracles=False,
        )
        self.assertEqual(base.virtual_time_s, diagnostic.virtual_time_s)
        self.assertEqual(base.move_distance_m, diagnostic.move_distance_m)
        self.assertEqual(base.n_measure, diagnostic.n_measure)
        self.assertEqual(base.n_channel_switch, diagnostic.n_channel_switch)
        self.assertEqual(base.n_clear_fail, diagnostic.n_clear_fail)

    def test_v5_variants_clear_smoke_case(self) -> None:
        for policy in (policy_v5a, policy_v5b):
            with self.subTest(policy=policy.__name__):
                result = run_episode(
                    generate_case(seed=0, problem=3, mode="practice", field_kind="smooth"),
                    lambda runner, selected=policy: selected(runner, n=8),
                    include_oracles=False,
                )
                self.assertTrue(result.success)
                self.assertEqual(result.n_clear_fail, 0)
                self.assertFalse(result.error)


if __name__ == "__main__":
    unittest.main()
