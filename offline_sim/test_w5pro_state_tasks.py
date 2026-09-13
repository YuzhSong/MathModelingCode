from __future__ import annotations

import unittest
from dataclasses import fields

from q3.models import Point
from q4.w5pro_state import W5ProTargetState
from q4.w5pro_tasks import TASK_KINDS, RemainingTaskPool, W5ProTask
from q4.w5pro_spatial import additive_candidates, cluster_tasks


class W5ProStateTaskTests(unittest.TestCase):
    def test_state_is_planner_owned(self):
        state = W5ProTargetState(channel=3)
        self.assertEqual(state.channel, 3)
        self.assertFalse(state.clear_ready)
        names = {field.name for field in fields(state)}
        self.assertNotIn("status", names)
        self.assertNotIn("source_type", names)

    def test_task_vocabulary(self):
        self.assertEqual(len(TASK_KINDS), 6)
        for kind in TASK_KINDS:
            self.assertEqual(W5ProTask(kind, Point(0.0, 0.0)).kind, kind)

    def test_invalid_task_is_rejected(self):
        with self.assertRaises(ValueError):
            W5ProTask("ABSENT", Point(0.0, 0.0))

    def test_wait_has_bounded_starvation_and_does_not_change_physical_state(self):
        pool = RemainingTaskPool(starvation_decisions=2, starvation_time_s=1000)
        task = W5ProTask("REFINE", Point(10, 10), channel=4)
        pool.sync([task])
        self.assertEqual(pool.found_channels(), {4})
        self.assertFalse(pool.wait_for_route(4, task.point, 100, 10).starvation)
        self.assertTrue(pool.wait_for_route(4, task.point, 100, 10).starvation)
        self.assertFalse(pool.is_wait_allowed(4))
        self.assertEqual(pool.tasks[("REFINE", 4, None)].kind, "REFINE")

    def test_mark_served_clears_planner_debt(self):
        pool = RemainingTaskPool()
        pool.wait_for_route(2, Point(0, 0), 10, 1)
        pool.mark_served(2)
        self.assertTrue(pool.is_wait_allowed(2))

    def test_backlog_pressure_and_tail_age_penalty(self):
        pool = RemainingTaskPool()
        pool.sync([W5ProTask("REFINE", Point(0, 0), channel=1),
                   W5ProTask("CLEAR", Point(1, 0), channel=2)])
        pool.wait_for_route(1, Point(0, 0), 100, 10)
        self.assertGreaterEqual(pool.backlog_pressure(), 4.0)
        self.assertGreater(pool.age_cost(1, "CLEAR"), pool.age_cost(1, "REFINE"))

    def test_spatial_stop_is_additive_and_shared(self):
        tasks = [W5ProTask("REFINE", Point(0, 0), channel=1),
                 W5ProTask("CLEAR", Point(50, 0), channel=2),
                 W5ProTask("SEARCH", Point(1000, 0), search_index=4)]
        stops = cluster_tasks(tasks, radius_m=100)
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0].services, 2)
        self.assertEqual(len(additive_candidates(tasks, radius_m=100)), 4)


if __name__ == "__main__":
    unittest.main()
