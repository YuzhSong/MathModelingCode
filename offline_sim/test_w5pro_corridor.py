from __future__ import annotations

import unittest

from q3.models import Point
from q4.w5pro_corridor import bind_waiting_opportunities, corridor_candidates
from q4.w5pro_tasks import W5ProTask


class W5ProCorridorTests(unittest.TestCase):
    def test_corridor_generates_refine_and_clear_opportunities(self):
        route = (Point(0, 0), Point(1000, 0))
        tasks = [W5ProTask("REFINE", Point(500, 20), channel=1), W5ProTask("CLEAR", Point(500, 30), channel=2)]
        opportunities = corridor_candidates(route, tasks)
        self.assertTrue(any(o.task.kind == "REFINE" for o in opportunities))
        self.assertTrue(any(o.task.kind == "CLEAR" for o in opportunities))
        self.assertLess(min(o.detour_m for o in opportunities), 120)

    def test_wait_binding_uses_insertion_cost(self):
        route = (Point(0, 0), Point(1000, 0))
        task = W5ProTask("REFINE", Point(500, 10), channel=1)
        opportunities = corridor_candidates(route, [task])
        bound = bind_waiting_opportunities(opportunities, {1: 1000})
        self.assertTrue(bound)

    def test_opportunities_are_segment_indexed_and_exclude_search(self):
        route = (Point(0, 0), Point(500, 0), Point(1000, 0))
        tasks = [W5ProTask("SEARCH", Point(250, 0), search_index=1),
                 W5ProTask("REFINE", Point(750, 20), channel=3)]
        opportunities = corridor_candidates(route, tasks, samples_per_segment=3)
        self.assertTrue(opportunities)
        self.assertEqual({o.segment_index for o in opportunities}, {0, 1})
        self.assertTrue(all(o.insertion_cost_s >= 0.0 for o in opportunities))
        self.assertTrue(all(o.task.kind == "REFINE" for o in opportunities))


if __name__ == "__main__":
    unittest.main()
