from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from q3.geometry import distance
from q3.models import Point


ARENA_RADIUS_M = 1800.0
MIN_RECEIVE_RADIUS_M = 1000.0
GEOMETRY_EPS = 1e-9


@dataclass(frozen=True)
class W5GeometrySpec:
    side_m: float
    cap_extension_m: float
    arena_radius_m: float = ARENA_RADIUS_M
    receive_radius_m: float = MIN_RECEIVE_RADIUS_M

    @property
    def apothem_m(self) -> float:
        return math.sqrt(3.0) * self.side_m

    @property
    def supplement_radius_m(self) -> float:
        return self.apothem_m + self.cap_extension_m


def w5_detection_points(spec: W5GeometrySpec) -> list[Point]:
    """Origin-centered 19-point triangular skeleton plus six cap points."""

    points = [Point(0.0, 0.0)]
    for radius, offset_deg in (
        (spec.side_m, 0.0),
        (2.0 * spec.side_m, 0.0),
        (spec.apothem_m, 30.0),
        (spec.supplement_radius_m, 30.0),
    ):
        for index in range(6):
            angle = math.radians(offset_deg + 60.0 * index)
            points.append(Point(radius * math.cos(angle), radius * math.sin(angle)))
    return points


def feasible_side_interval(
    arena_radius_m: float = ARENA_RADIUS_M,
    receive_radius_m: float = MIN_RECEIVE_RADIUS_M,
) -> tuple[float, float]:
    """Roots of a^2 + (R-sqrt(3)a)^2 <= r^2."""

    discriminant = 4.0 * receive_radius_m**2 - arena_radius_m**2
    if discriminant < 0.0:
        raise ValueError("receive radius is too small for the six-cap construction")
    root = math.sqrt(discriminant)
    return (
        (math.sqrt(3.0) * arena_radius_m - root) / 4.0,
        (math.sqrt(3.0) * arena_radius_m + root) / 4.0,
    )


def cap_side_support_distance(spec: W5GeometrySpec) -> float:
    """Distance from the origin to a cap triangle's sloping outer side."""

    a = spec.side_m
    p = spec.cap_extension_m
    return spec.supplement_radius_m * a / math.hypot(a, p)


def analytic_geometry_checks(spec: W5GeometrySpec) -> dict[str, float | int]:
    lower, upper = feasible_side_interval(spec.arena_radius_m, spec.receive_radius_m)
    cap_height = spec.arena_radius_m - spec.apothem_m
    cap_half_width = math.sqrt(max(0.0, spec.arena_radius_m**2 - spec.apothem_m**2))
    apex_to_adjacent_vertex = math.hypot(spec.side_m, cap_height)
    cap_end_to_supplement = math.hypot(spec.cap_extension_m, cap_half_width)
    side_support = cap_side_support_distance(spec)
    checks = {
        "side_at_most_receive": int(spec.side_m <= spec.receive_radius_m + GEOMETRY_EPS),
        "side_in_cap_interval": int(lower - GEOMETRY_EPS <= spec.side_m <= upper + GEOMETRY_EPS),
        "positive_cap": int(cap_height >= -GEOMETRY_EPS),
        "supplement_beyond_arena": int(spec.supplement_radius_m >= spec.arena_radius_m - GEOMETRY_EPS),
        "cap_inside_local_triangles": int(side_support >= spec.arena_radius_m - GEOMETRY_EPS),
        "cap_apex_within_adjacent_vertex": int(apex_to_adjacent_vertex <= spec.receive_radius_m + GEOMETRY_EPS),
        "cap_end_within_supplement": int(cap_end_to_supplement <= spec.receive_radius_m + GEOMETRY_EPS),
    }
    return {
        "side_lower_bound_m": lower,
        "side_upper_bound_m": upper,
        "apothem_m": spec.apothem_m,
        "cap_height_m": cap_height,
        "cap_half_width_m": cap_half_width,
        "supplement_radius_m": spec.supplement_radius_m,
        "cap_side_support_distance_m": side_support,
        "cap_side_support_margin_m": side_support - spec.arena_radius_m,
        "apex_to_adjacent_vertex_m": apex_to_adjacent_vertex,
        "apex_distance_margin_m": spec.receive_radius_m - apex_to_adjacent_vertex,
        "cap_end_to_supplement_m": cap_end_to_supplement,
        **checks,
        "analytical_pass": int(all(checks.values())),
    }


def maximum_angular_gap_deg(source: Point, points: Sequence[Point], receive_radius_m: float) -> tuple[float, int]:
    vectors: list[tuple[float, float]] = []
    for point in points:
        dx, dy = point.x - source.x, point.y - source.y
        if math.hypot(dx, dy) <= receive_radius_m + GEOMETRY_EPS:
            if abs(dx) <= GEOMETRY_EPS and abs(dy) <= GEOMETRY_EPS:
                return 0.0, 1
            vectors.append((dx, dy))
    if len(vectors) < 2:
        return 360.0, len(vectors)
    angles = sorted(math.atan2(dy, dx) for dx, dy in vectors)
    gaps = [right - left for left, right in zip(angles, angles[1:])]
    gaps.append(angles[0] + 2.0 * math.pi - angles[-1])
    return math.degrees(max(gaps)), len(vectors)


def adjacent_cap_shared_detector_lower_bound(arena_radius_m: float = ARENA_RADIUS_M) -> float:
    """Nearest common point in adjacent outward tangent half-planes."""

    return arena_radius_m * math.tan(math.radians(30.0))


def fixed_skeleton_minimum_argument(spec: W5GeometrySpec) -> dict[str, float | int]:
    required_distance = adjacent_cap_shared_detector_lower_bound(spec.arena_radius_m)
    return {
        "adjacent_cap_common_detector_distance_m": required_distance,
        "receive_radius_m": spec.receive_radius_m,
        "one_point_cannot_cover_adjacent_outward_apices": int(
            required_distance > spec.receive_radius_m + GEOMETRY_EPS
        ),
        "base_point_count": 19,
        "minimum_supplement_count_for_fixed_skeleton": 6,
        "conditional_minimum_total_points": 25,
    }


def nearest_point_distance(source: Point, points: Sequence[Point]) -> float:
    return min(distance(source, point) for point in points)

