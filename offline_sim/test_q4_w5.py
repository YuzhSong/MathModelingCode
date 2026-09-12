from __future__ import annotations

import math
import unittest

from q3.models import Point
from q4.run_w5_benchmark import assert_policy_isolated
from q4.w5_geometry import (
    W5GeometrySpec,
    analytic_geometry_checks,
    feasible_side_interval,
    fixed_skeleton_minimum_argument,
    maximum_angular_gap_deg,
    w5_detection_points,
)
from q4.w5_policy import W5SymmetricDetectionPolicy


class MinimalRunner:
    virtual_time_s = 0.0
    position = (0.0, 0.0)
    current_channel = 1

    def record_policy_diagnostic(self, event: dict) -> None:
        pass


class Q4W5GeometryTests(unittest.TestCase):
    def test_policy_has_no_ground_truth_access(self) -> None:
        assert_policy_isolated()

    def test_origin_centered_geometry_has_19_plus_6_points(self) -> None:
        spec = W5GeometrySpec(990.0, 160.0)
        points = w5_detection_points(spec)
        self.assertEqual(len(points), 25)
        self.assertEqual(points[0], Point(0.0, 0.0))
        self.assertEqual(sum(math.isclose(math.hypot(point.x, point.y), spec.supplement_radius_m, abs_tol=1e-6) for point in points), 6)

    def test_analytic_side_upper_bound_is_derived(self) -> None:
        lower, upper = feasible_side_interval()
        self.assertAlmostEqual(lower, 561.477916228961)
        self.assertAlmostEqual(upper, 997.3678105830284)
        checks = analytic_geometry_checks(W5GeometrySpec(990.0, 160.0))
        self.assertEqual(checks["analytical_pass"], 1)

    def test_boundary_cap_apex_satisfies_angular_gap(self) -> None:
        spec = W5GeometrySpec(990.0, 160.0)
        source = Point(1800.0 * math.cos(math.radians(30.0)), 1800.0 * math.sin(math.radians(30.0)))
        gap, nearby = maximum_angular_gap_deg(source, w5_detection_points(spec), 1000.0)
        self.assertLessEqual(gap, 180.0 + 1e-9)
        self.assertGreaterEqual(nearby, 3)

    def test_six_supplement_lower_bound_is_conditional(self) -> None:
        result = fixed_skeleton_minimum_argument(W5GeometrySpec(990.0, 160.0))
        self.assertEqual(result["minimum_supplement_count_for_fixed_skeleton"], 6)
        self.assertGreater(result["adjacent_cap_common_detector_distance_m"], 1000.0)

    def test_w5_changes_only_search_geometry_after_w4a_initialization(self) -> None:
        policy = W5SymmetricDetectionPolicy(MinimalRunner(), W5GeometrySpec(990.0, 160.0))
        self.assertEqual(policy.routing_method, "open_route")
        self.assertEqual(len(policy.search_points), 25)
        self.assertEqual(policy.remaining_search_indices, set(range(25)))


if __name__ == "__main__":
    unittest.main()
