from __future__ import annotations

import unittest

from offline_sim.case import generate_case
from offline_sim.harness import run_episode
from q3.v6_policy import policy_v6
from scripts.run_v6_eval import assert_v6_ground_truth_isolated


class V6RegressionTests(unittest.TestCase):
    def run_seed(self, seed: int):
        return run_episode(
            generate_case(seed=seed, problem=3, mode="practice", field_kind="smooth"),
            lambda runner: policy_v6(runner, n=8),
            include_oracles=False,
        )

    def test_policy_code_is_ground_truth_isolated(self) -> None:
        assert_v6_ground_truth_isolated()

    def test_seed_83_clears_without_failures_and_emits_route_events(self) -> None:
        result = self.run_seed(83)
        self.assertTrue(result.success)
        self.assertFalse(result.error)
        self.assertEqual(result.n_clear_fail, 0)
        events = [
            event
            for event in result.policy_diagnostics
            if event.get("event") == "route_supplement_execution"
        ]
        self.assertTrue(events)
        self.assertTrue(all(float(event["selected_route_marginal_s"]) >= 0.0 for event in events))

    def test_seed_83_is_reproducible(self) -> None:
        first = self.run_seed(83)
        second = self.run_seed(83)
        self.assertEqual(first.virtual_time_s, second.virtual_time_s)
        self.assertEqual(first.move_distance_m, second.move_distance_m)
        self.assertEqual(first.n_measure, second.n_measure)
        self.assertEqual(first.policy_diagnostics, second.policy_diagnostics)


if __name__ == "__main__":
    unittest.main()
