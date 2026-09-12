from __future__ import annotations

import ast
import unittest
from pathlib import Path

from offline_sim.case import generate_case
from offline_sim.harness import run_episode
from q3.v6_l2_policy import policy_v6_l1, policy_v6_l2
from q3.v6_policy import policy_v6


class V6L2Tests(unittest.TestCase):
    def test_depth_one_replays_frozen_v6(self) -> None:
        left = run_episode(
            generate_case(seed=3, problem=3, mode="practice", field_kind="smooth"),
            lambda runner: policy_v6(runner, n=8),
            include_oracles=False,
        )
        right = run_episode(
            generate_case(seed=3, problem=3, mode="practice", field_kind="smooth"),
            lambda runner: policy_v6_l1(runner, n=8),
            include_oracles=False,
        )
        self.assertEqual(left.success, right.success)
        self.assertAlmostEqual(left.virtual_time_s, right.virtual_time_s, places=6)
        self.assertAlmostEqual(left.move_distance_m, right.move_distance_m, places=6)
        self.assertEqual(left.n_measure, right.n_measure)
        self.assertEqual(left.n_channel_switch, right.n_channel_switch)
        self.assertEqual(left.n_clear_fail, right.n_clear_fail)

    def test_l2_smoke_and_time_identity(self) -> None:
        result = run_episode(
            generate_case(seed=0, problem=3, mode="practice", field_kind="smooth"),
            lambda runner: policy_v6_l2(runner, n=8),
            include_oracles=False,
        )
        components = (
            result.move_time_s
            + result.measure_action_time_s
            + result.channel_switch_time_s
            + result.clear_action_time_s
        )
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.n_clear_fail, 0)
        self.assertAlmostEqual(result.virtual_time_s, components, places=4)

    def test_policy_module_has_no_offline_ground_truth_access(self) -> None:
        root = Path(__file__).resolve().parents[1]
        path = root / "q3/v6_l2_policy.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertFalse((node.module or "").startswith("offline_sim"))
            if isinstance(node, ast.Import):
                self.assertFalse(any(alias.name.startswith("offline_sim") for alias in node.names))
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, {"case", "engine", "sources", "jammers"})


if __name__ == "__main__":
    unittest.main()
