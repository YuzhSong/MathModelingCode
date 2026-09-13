"""Conservative persistent-bearing feasible-region geometry for Q4 W6.

This module is policy-safe by construction: it only accepts API-visible direction
observations. Circular constraints are represented by circumscribed polygons, so
the returned polygon is an outer approximation of the true feasible set.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from q3.models import Point
from q3.geometry import Circle, circle_from_three, circle_from_two, contains, distance

EPS = 1e-9
# The simulator's physical error is bounded by 1 degree, then its API rounds
# the returned bearing to 0.01 degree.  The observed value therefore needs the
# existing 1.005-degree total bound for a genuinely conservative certificate.
OBSERVED_BEARING_BOUND_DEG = 1.005


@dataclass(frozen=True)
class BearingObservation:
    position: Point
    bearing_deg: float


@dataclass(frozen=True)
class FeasibleRegion:
    vertices: tuple[Point, ...]
    mec: Circle
    valid: bool
    reason: str = "ok"


def _circumscribed_circle_polygon(center: Point, radius: float, sides: int) -> list[Point]:
    """Return a convex polygon containing the circle exactly by tangent sides."""
    if sides < 8:
        raise ValueError("sides must be at least 8")
    # Vertices are at the intersection of adjacent tangent half-planes.
    apothem = radius / math.cos(math.pi / sides)
    return [
        Point(center.x + apothem * math.cos(2.0 * math.pi * i / sides),
              center.y + apothem * math.sin(2.0 * math.pi * i / sides))
        for i in range(sides)
    ]


def _clip_halfplane(poly: list[Point], a: float, b: float, c: float) -> list[Point]:
    """Clip by a*x+b*y+c >= 0 with a conservative numeric tolerance."""
    if not poly:
        return []
    out: list[Point] = []

    def value(p: Point) -> float:
        return a * p.x + b * p.y + c

    prev = poly[-1]
    prev_v = value(prev)
    prev_inside = prev_v >= -EPS
    for cur in poly:
        cur_v = value(cur)
        cur_inside = cur_v >= -EPS
        if cur_inside != prev_inside:
            denom = a * (cur.x - prev.x) + b * (cur.y - prev.y)
            if abs(denom) <= EPS:
                return []
            t = -prev_v / denom
            out.append(Point(prev.x + t * (cur.x - prev.x),
                             prev.y + t * (cur.y - prev.y)))
        if cur_inside:
            out.append(cur)
        prev, prev_v, prev_inside = cur, cur_v, cur_inside
    return out


def _clip_circle_superset(poly: list[Point], center: Point, radius: float, sides: int) -> list[Point]:
    """Intersect with an outer polygon containing the requested disk."""
    out = poly
    for i in range(sides):
        angle = 2.0 * math.pi * i / sides
        nx, ny = math.cos(angle), math.sin(angle)
        # n dot (p-center) <= radius.
        out = _clip_halfplane(out, -nx, -ny,
                              nx * center.x + ny * center.y + radius)
        if not out:
            return []
    return out


def _clip_bearing_wedge(poly: list[Point], obs: BearingObservation, error_deg: float) -> list[Point]:
    """Intersect with the exact two half-planes of a narrow bearing wedge."""
    lower = math.radians(obs.bearing_deg - error_deg)
    upper = math.radians(obs.bearing_deg + error_deg)
    lx, ly = math.cos(lower), math.sin(lower)
    ux, uy = math.cos(upper), math.sin(upper)
    out = _clip_halfplane(poly, -ly, lx, ly * obs.position.x - lx * obs.position.y)
    return _clip_halfplane(out, uy, -ux, -uy * obs.position.x + ux * obs.position.y)


def _mec(points: Iterable[Point]) -> Circle:
    """Deterministic MEC of polygon vertices; vertices enclose the convex polygon."""
    pts = list(points)
    if not pts:
        return Circle(Point(0.0, 0.0), float("inf"))
    best = Circle(pts[0], 0.0)
    for i, p in enumerate(pts):
        if contains(best, p, 1e-7):
            continue
        best = Circle(p, 0.0)
        for j, q in enumerate(pts[:i]):
            if contains(best, q, 1e-7):
                continue
            best = circle_from_two(p, q)
            for r in pts[:j]:
                if contains(best, r, 1e-7):
                    continue
                c = circle_from_three(p, q, r)
                if c is not None:
                    best = c
    if all(contains(best, p, 1e-6) for p in pts):
        return best
    center = Point(sum(p.x for p in pts) / len(pts), sum(p.y for p in pts) / len(pts))
    return Circle(center, max(distance(center, p) for p in pts))


def persistent_bearing_region(
    observations: Iterable[BearingObservation],
    *,
    arena_radius_m: float = 1800.0,
    receive_radius_upper_m: float = 1500.0,
    bearing_error_deg: float = OBSERVED_BEARING_BOUND_DEG,
    circle_sides: int = 256,
) -> FeasibleRegion:
    """Build a conservative outer approximation of F_c.

    F_c = D(0,1800) intersect all historical bearing wedges intersect all
    D(S_i,1500). ``no_signal`` is intentionally not an input type here.
    """
    if arena_radius_m <= 0 or receive_radius_upper_m <= 0 or bearing_error_deg < 0:
        return FeasibleRegion((), Circle(Point(0.0, 0.0), float("inf")), False, "invalid_parameters")
    obs = tuple(observations)
    poly = _circumscribed_circle_polygon(Point(0.0, 0.0), arena_radius_m, circle_sides)
    for item in obs:
        poly = _clip_bearing_wedge(poly, item, bearing_error_deg)
        if not poly:
            return FeasibleRegion((), Circle(Point(0.0, 0.0), float("inf")), False, "empty_after_bearing")
        poly = _clip_circle_superset(poly, item.position, receive_radius_upper_m, circle_sides)
        if not poly:
            return FeasibleRegion((), Circle(Point(0.0, 0.0), float("inf")), False, "empty_after_range")
    circle = _mec(poly)
    return FeasibleRegion(tuple(poly), circle, True)
