from __future__ import annotations

import unittest

from q3.models import Point
from q4.w5pro_clear import ClearLifecycle
from q4.w5pro_route_repair import relocate, repair_route, swap
from q4.w5pro_spatial import cluster_tasks
from q4.w5pro_tasks import W5ProTask


class W5ProClearRouteTests(unittest.TestCase):
    def test_clear_lifecycle_is_protected_and_records_ready_time(self):
        lifecycle = ClearLifecycle(3)
        lifecycle.mark_ready(100.0)
        lifecycle.mark_ready(200.0)
        self.assertEqual(lifecycle.clear_ready_time_s, 100.0)
        self.assertTrue(lifecycle.task(Point(0, 0)).mandatory)

    def test_failed_clear_cannot_repeat_same_point(self):
        lifecycle = ClearLifecycle(3)
        p = Point(1, 1)
        lifecycle.mark_failed(p)
        self.assertFalse(lifecycle.can_try(p))
        self.assertTrue(lifecycle.can_try(Point(2, 2)))

    def test_route_repair_keeps_locked_macro_first(self):
        locked = Point(10, 0)
        repaired = repair_route(Point(0, 0), [Point(100, 0), Point(20, 0)], locked_macro=locked)
        self.assertEqual(repaired.route[0], locked)
        self.assertGreater(repaired.total_seconds, 0)

    def test_relocate_and_swap_are_available_for_unlocked_route(self):
        points = [Point(1, 0), Point(2, 0), Point(3, 0)]
        self.assertEqual(relocate(points, 0, 2), [points[1], points[2], points[0]])
        self.assertEqual(swap(points, 0, 2), [points[2], points[1], points[0]])

    def test_spatial_bundle_reports_route_synergy_and_route_aware_point(self):
        tasks = [W5ProTask("REFINE", Point(100, 10), channel=1),
                 W5ProTask("CLEAR", Point(120, 20), channel=2)]
        stops = cluster_tasks(tasks, radius_m=50, route=(Point(0, 0), Point(100, 0)))
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0].point, tasks[0].point)
        self.assertGreaterEqual(stops[0].route_synergy_s, 0.0)


if __name__ == "__main__":
    unittest.main()
