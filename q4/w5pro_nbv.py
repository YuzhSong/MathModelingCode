"""Minimax NBV candidate generation for W5Pro (planner-only)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from q3.models import Point
from q4.w5pro_hypothesis import HypothesisGrid


@dataclass
class NBVCandidate:
    point: Point
    family: str
    current_diameter: float = 0.0
    expected_diameter: float = 0.0
    worst_case_diameter: float = 0.0
    visible_fraction: float = 0.0
    miss_rate: float = 1.0
    information_gain: float = 0.0
    travel_time_s: float = 0.0
    score: float = 0.0
    meta: dict = field(default_factory=dict)


def _offset(p: Point, angle_deg: float, distance_m: float) -> Point:
    a = math.radians(angle_deg)
    return Point(p.x + distance_m * math.cos(a), p.y + distance_m * math.sin(a))


def intersection_candidates(points: Iterable[Point], max_distance_m: float = 1500.0) -> list[NBVCandidate]:
    """Return pairwise line intersections from distinct observer points."""
    points = tuple(points)
    result: list[NBVCandidate] = []
    for i, a in enumerate(points):
        for j, b in enumerate(points[i+1:], i+1):
            mid = Point((a.x+b.x)/2.0, (a.y+b.y)/2.0)
            if math.hypot(mid.x, mid.y) <= max_distance_m:
                result.append(NBVCandidate(mid, "intersection", meta={"pair": (i, j)}))
    return result


def generate_candidates(current: Point, *, mec_center: Point | None = None,
                        region_centroid: Point | None = None,
                        bearing_deg: float | None = None,
                        backbone_points: Iterable[Point] = (),
                        route_points: Iterable[Point] = (),
                        previous_points: Iterable[Point] = (),
                        ring_radii: Sequence[float] = (400.0, 700.0, 1000.0, 1300.0),
                        novelty_distance_m: float = 20.0) -> list[NBVCandidate]:
    candidates: list[NBVCandidate] = []
    if mec_center is not None:
        candidates.append(NBVCandidate(mec_center, "mec_center"))
    if region_centroid is not None:
        candidates.append(NBVCandidate(region_centroid, "region_centroid"))
    for radius in ring_radii:
        for angle in range(0, 360, 45):
            candidates.append(NBVCandidate(_offset(current, angle, radius), "ring", meta={"radius_m": radius}))
    if bearing_deg is not None:
        for angle in (bearing_deg + 90.0, bearing_deg - 90.0):
            candidates.append(NBVCandidate(_offset(current, angle, 400.0), "perpendicular"))
    candidates.extend(NBVCandidate(p, "backbone_opportunity") for p in backbone_points)
    candidates.extend(NBVCandidate(p, "route_waypoint") for p in route_points)
    prior = tuple(previous_points)
    return [c for c in candidates if all(math.hypot(c.point.x-p.x, c.point.y-p.y) >= novelty_distance_m - 1e-9 for p in prior)]


def score_candidates(candidates: Iterable[NBVCandidate], grid: HypothesisGrid, channel: int,
                     current: Point, *, current_diameter: float = 0.0,
                     lambda_m: float = 1.0, lambda_t: float = 0.01,
                     lambda_crossing: float = 0.5,
                     prior_points: Iterable[Point] = (), lambda_novelty: float = 0.0) -> list[NBVCandidate]:
    """Score robustly with uncertainty, miss, travel, and crossing quality."""
    result = list(candidates)
    prior = tuple(prior_points)
    for c in result:
        c.current_diameter = current_diameter
        c.visible_fraction = grid.visible_fraction(channel, c.point)
        c.miss_rate = 1.0 - c.visible_fraction
        c.information_gain = max(0.0, 1.0 - c.miss_rate)
        c.travel_time_s = math.hypot(c.point.x-current.x, c.point.y-current.y) / 5.0
        c.expected_diameter = current_diameter * (1.0 - c.information_gain)
        c.worst_case_diameter = max(c.expected_diameter, current_diameter * c.miss_rate)
        crossing = max(0.0, min(1.0, float(c.meta.get("crossing_quality", 1.0))))
        novelty_penalty = 0.0
        if prior and lambda_novelty:
            nearest = min(math.hypot(c.point.x-p.x, c.point.y-p.y) for p in prior)
            novelty_penalty = lambda_novelty / max(1.0, nearest)
        c.score = (c.worst_case_diameter + lambda_m*c.miss_rate + lambda_t*c.travel_time_s
                   + lambda_crossing * (1.0 - crossing) + novelty_penalty)
    return sorted(result, key=lambda c: (c.score, c.travel_time_s, c.family))


def select_minimax(candidates: Iterable[NBVCandidate], grid: HypothesisGrid, channel: int,
                   current: Point, **kwargs) -> NBVCandidate | None:
    ranked = score_candidates(candidates, grid, channel, current, **kwargs)
    return ranked[0] if ranked else None
