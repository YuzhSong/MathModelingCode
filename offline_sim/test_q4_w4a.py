from __future__ import annotations

import unittest

from q3.models import Measurement, Point
from q3.offline_policy import Task
from q4.routing import one_step_route_consequence, select_task
from q4.run_w4a_benchmark import assert_policy_isolated
from q4.w2_policy import TargetLifecycle
from q4.w4a_policy import W4AUnifiedRoutingPolicy


class MinimalRunner:
    virtual_time_s = 0.0
    position = (0.0, 0.0)
    current_channel = 1

    def record_policy_diagnostic(self, event: dict) -> None:
        pass


class Q4W4ARoutingTests(unittest.TestCase):
    def test_policy_has_no_ground_truth_access(self) -> None:
        assert_policy_isolated()

    def test_unified_pool_keeps_search_and_reacquisition_together(self) -> None:
        policy = W4AUnifiedRoutingPolicy(MinimalRunner(), routing_method="open_route")
        track = policy.tracks[7]
        track.add_measurement(Measurement(Point(0.0, 0.0), 7, "direction", 0.0, 5.0))
        policy.target_states[7].lifecycle = TargetLifecycle.REACQUIRE

        tasks = policy.build_dynamic_tasks()
        self.assertTrue(any(task.kind == "search" for task in tasks))
        self.assertTrue(any(task.kind == "reacquire" and task.channel == 7 for task in tasks))

    def test_route_consequence_uses_complete_open_route(self) -> None:
        tasks = [
            Task("search", 0, Point(1.0, 0.0)),
            Task("clear", 2, Point(10.0, 0.0)),
            Task("measure", 3, Point(11.0, 0.0)),
        ]
        selected = one_step_route_consequence(Point(0.0, 0.0), tasks)
        self.assertEqual(selected.point, Point(1.0, 0.0))
        self.assertEqual(select_task(Point(0.0, 0.0), tasks, "nearest"), tasks[0])


if __name__ == "__main__":
    unittest.main()
