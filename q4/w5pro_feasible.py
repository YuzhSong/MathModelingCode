"""Hard set-membership feasible region F_c for Q4 localization."""
from __future__ import annotations

import math
from dataclasses import dataclass

from q3.models import Point


def angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


@dataclass(frozen=True)
class BearingWedge:
    observer: Point
    bearing_deg: float
    tolerance_deg: float = 1.0
    max_range_m: float = 1500.0

    def contains(self, point: Point) -> bool:
        dx, dy = point.x - self.observer.x, point.y - self.observer.y
        distance = math.hypot(dx, dy)
        bearing = math.degrees(math.atan2(dy, dx)) % 360.0
        return distance <= self.max_range_m + 1e-9 and angle_diff(bearing, self.bearing_deg) <= self.tolerance_deg + 1e-9


class FeasibleRegion:
    """Conservative predicate intersection; no Gaussian covariance shortcut."""

    def __init__(self, arena_radius_m: float = 1800.0, sample_step_m: float = 20.0):
        self.arena_radius_m = float(arena_radius_m)
        self.sample_step_m = float(sample_step_m)
        self._constraints: list[callable] = [lambda p: math.hypot(p.x, p.y) <= self.arena_radius_m + 1e-9]
        self.observations: list[tuple[str, Point, float | None]] = []

    def add_bearing(self, observer: Point, bearing_deg: float, tolerance_deg: float = 1.0,
                    max_range_m: float = 1500.0) -> None:
        wedge = BearingWedge(observer, bearing_deg, tolerance_deg, max_range_m)
        self._constraints.append(wedge.contains)
        self.observations.append(("bearing", observer, bearing_deg))

    def add_near(self, observer: Point, radius_m: float = 5.0) -> None:
        self._constraints.append(lambda p: math.hypot(p.x-observer.x, p.y-observer.y) <= radius_m + 1e-9)
        self.observations.append(("near", observer, radius_m))

    def contains(self, point: Point) -> bool:
        return all(constraint(point) for constraint in self._constraints)

    def samples(self) -> list[Point]:
        n = math.ceil(self.arena_radius_m / self.sample_step_m)
        return [Point(ix*self.sample_step_m, iy*self.sample_step_m)
                for ix in range(-n, n+1) for iy in range(-n, n+1)
                if self.contains(Point(ix*self.sample_step_m, iy*self.sample_step_m))]

    def diameter(self) -> float:
        points = self.samples()
        if not points:
            return 0.0
        # Bounding-box diameter is a conservative O(n) upper bound for the
        # sampled feasible set and avoids quadratic pair enumeration.
        xs, ys = [p.x for p in points], [p.y for p in points]
        return math.hypot(max(xs) - min(xs), max(ys) - min(ys))

    def summary(self) -> dict[str, float | int]:
        points = self.samples()
        return {"sample_count": len(points), "diameter_m": self.diameter(),
                "empty": int(not points), "constraint_count": len(self._constraints)}
