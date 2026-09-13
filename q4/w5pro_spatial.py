"""Additive spatial task bundling for W5Pro."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from q3.models import Point
from q4.w5pro_tasks import W5ProTask


@dataclass(frozen=True)
class SpatialStop:
    point: Point
    members: tuple[W5ProTask, ...]
    route_insertion_cost_s: float = 0.0
    route_synergy_s: float = 0.0

    @property
    def services(self) -> int:
        return len(self.members)


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _representative(tasks: list[W5ProTask], route: tuple[Point, ...]) -> Point:
    points = [t.point for t in tasks]
    if not route:
        return Point(sum(p.x for p in points) / len(points), sum(p.y for p in points) / len(points))
    # Route-aware representative: choose the member closest to the route, so
    # bundling cannot silently create a long detour.
    return min(points, key=lambda p: min(_distance(p, r) for r in route))


def cluster_tasks(tasks: Iterable[W5ProTask], radius_m: float = 120.0,
                  route: Iterable[Point] = ()) -> list[SpatialStop]:
    """Radius-cluster eligible tasks; CLEAR is included only when shared."""
    if radius_m <= 0:
        raise ValueError("radius_m must be positive")
    eligible = [t for t in tasks if t.kind in {"SEARCH", "REFINE", "VERIFY", "CLEAR", "SPATIAL_STOP"}]
    route_points = tuple(route)
    clusters: list[list[W5ProTask]] = []
    for task in eligible:
        target = next((c for c in clusters if _distance(task.point, c[0].point) <= radius_m), None)
        if target is None:
            clusters.append([task])
        else:
            target.append(task)
    stops: list[SpatialStop] = []
    for members in clusters:
        # A single task is not a shared service and must not be wrapped.
        if len(members) < 2:
            continue
        point = _representative(members, route_points)
        direct = sum(_distance(m.point, point) / 5.0 for m in members)
        bundled = _distance(members[0].point, point) / 5.0
        stops.append(SpatialStop(point, tuple(members), bundled, max(0.0, direct - bundled)))
    return stops


def additive_candidates(legacy: Iterable[W5ProTask], radius_m: float = 120.0,
                        route: Iterable[Point] = ()) -> list[W5ProTask | SpatialStop]:
    """Return legacy tasks plus bundles; legacy options are never deleted."""
    original = list(legacy)
    return original + cluster_tasks(original, radius_m, route)
