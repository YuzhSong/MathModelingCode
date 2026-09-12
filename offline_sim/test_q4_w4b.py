from __future__ import annotations

import unittest

from q3.models import Point
from q3.offline_policy import Task
from q4.routing_continuity import (
    compare_backbone_routes,
    fixed_end_route_order,
    insertion_decisions,
)
from q4.run_w4b_benchmark import assert_policy_isolated
from q4.w1_policy import w1_search_points


class Q4W4BContinuityTests(unittest.TestCase):
    def test_policy_has_no_ground_truth_access(self) -> None:
        assert_policy_isolated()

    def test_selected_backbone_is_best_tested_coordinate_route(self) -> None:
        routes = compare_backbone_routes(Point(0.0, 0.0), w1_search_points())
        selected = next(route for route in routes if route.name == "greedy_2opt_open")
        self.assertEqual(len(selected.order), 27)
        self.assertEqual(set(selected.order), set(range(27)))
        self.assertEqual(selected.length_m, min(route.length_m for route in routes))
        self.assertEqual(selected.jumps_over_1000m, 0)

    def test_insertion_compares_now_with_best_future_segment(self) -> None:
        current = Point(0.0, 0.0)
        backbone = [Point(10.0, 0.0), Point(20.0, 0.0)]
        near_now = Task("clear", 1, Point(5.0, 1.0))
        near_future = Task("clear", 2, Point(19.0, 1.0))
        decisions = insertion_decisions(current, backbone[0], backbone, [near_now, near_future])
        by_channel = {decision.task.channel: decision for decision in decisions}
        self.assertTrue(by_channel[1].ready_now)
        self.assertFalse(by_channel[2].ready_now)
        self.assertGreater(by_channel[2].now_detour_m, by_channel[2].best_future_detour_m)

    def test_fixed_end_route_preserves_every_task(self) -> None:
        tasks = [
            Task("measure", 1, Point(8.0, 2.0)),
            Task("clear", 2, Point(2.0, 1.0)),
            Task("reacquire", 3, Point(6.0, -1.0)),
        ]
        ordered = fixed_end_route_order(Point(0.0, 0.0), Point(10.0, 0.0), tasks)
        self.assertEqual(len(ordered), len(tasks))
        self.assertEqual({id(task) for task in ordered}, {id(task) for task in tasks})


if __name__ == "__main__":
    unittest.main()
