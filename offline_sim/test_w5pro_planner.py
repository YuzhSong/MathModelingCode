from __future__ import annotations

import unittest

from q3.models import Point
from q4.w5pro_future_cost import FutureCost, cvar_cost, risk_adjusted_cost
from q4.w5pro_planner import W5ProPlanner, pareto_prune
from q4.w5pro_tasks import W5ProTask
from q4.w5pro_tasks import W5ProTask


class W5ProPlannerTests(unittest.TestCase):
    def test_cvar_focuses_on_upper_tail_seconds(self):
        self.assertEqual(cvar_cost([1, 2, 3, 100], alpha=0.75), 100.0)
        with self.assertRaises(ValueError):
            cvar_cost([1], alpha=1.0)
        self.assertEqual(risk_adjusted_cost(FutureCost(clear_s=4), mode="cvar", samples=[1, 2, 100]), 100.0)
    def test_pareto_prune_keeps_hard_and_removes_dominated_soft(self):
        dominated = W5ProTask("REFINE", Point(0, 0), expected_time_s=10,
                              information_gain=1)
        winner = W5ProTask("REFINE", Point(1, 0), expected_time_s=5,
                           information_gain=2)
        hard = W5ProTask("VERIFY", Point(2, 0), expected_time_s=100)
        result = pareto_prune([dominated, winner, hard])
        self.assertNotIn(dominated, result)
        self.assertIn(winner, result)
        self.assertIn(hard, result)
    def test_all_costs_are_seconds_and_route_synergy_reduces_joint_cost(self):
        cost = FutureCost(clear_s=10, sensing_s=20, route_synergy_s=15)
        self.assertEqual(cost.additive_s, 30)
        self.assertEqual(cost.total_s, 15)

    def test_horizon_one_selects_one_macro_and_replans(self):
        planner = W5ProPlanner()
        tasks = [W5ProTask("REFINE", Point(100, 0), channel=1), W5ProTask("CLEAR", Point(20, 0), channel=2)]
        chosen = planner.commit_one_macro(Point(0, 0), tasks)
        self.assertIs(chosen.candidate, tasks[1])
        self.assertEqual(planner.replan_count, 1)
        self.assertEqual(len(planner.selected), 1)

    def test_cvar_mode_uses_task_tail_samples_for_ranking(self):
        low_tail = W5ProTask("REFINE", Point(10, 0), future_cost_samples=(1, 2, 3))
        high_tail = W5ProTask("REFINE", Point(1, 0), future_cost_samples=(1, 2, 100))
        chosen = W5ProPlanner(risk_mode="cvar", cvar_alpha=0.66).choose(
            Point(0, 0), [low_tail, high_tail])
        self.assertIs(chosen.candidate, low_tail)


if __name__ == "__main__":
    unittest.main()
