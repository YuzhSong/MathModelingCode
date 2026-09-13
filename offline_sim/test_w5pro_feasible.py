from __future__ import annotations

import unittest

from q3.models import Point
from q4.w5pro_feasible import FeasibleRegion


class W5ProFeasibleRegionTests(unittest.TestCase):
    def test_arena_constraint_is_always_present(self):
        region = FeasibleRegion(sample_step_m=100)
        self.assertTrue(region.contains(Point(0, 0)))
        self.assertFalse(region.contains(Point(1801, 0)))

    def test_positive_bearing_uses_set_membership_wedge(self):
        region = FeasibleRegion(sample_step_m=20)
        region.add_bearing(Point(0, 0), 0, tolerance_deg=1, max_range_m=1500)
        self.assertTrue(region.contains(Point(1000, 0)))
        self.assertFalse(region.contains(Point(0, 1000)))
        self.assertLess(region.diameter(), 3600)

    def test_near_shrinks_position_without_heading_state(self):
        region = FeasibleRegion(sample_step_m=1)
        region.add_near(Point(100, 100), radius_m=5)
        self.assertLessEqual(region.diameter(), 15)
        self.assertEqual(len(region.observations), 1)


if __name__ == "__main__":
    unittest.main()
