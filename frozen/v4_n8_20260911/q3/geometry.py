from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .models import Measurement, Point

EPS = 1e-9
BEARING_ERROR_DEG = 1.0
BEARING_QUANTIZATION_DEG = 0.005
DEFAULT_BEARING_ERROR_DEG = BEARING_ERROR_DEG + BEARING_QUANTIZATION_DEG


@dataclass(frozen=True)
class Circle:
    center: Point
    radius: float


def distance(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def regular_polygon(radius: float, sides: int = 128, center: Point = Point(0.0, 0.0)) -> list[Point]:
    return [
        Point(center.x + radius * math.cos(2.0 * math.pi * i / sides), center.y + radius * math.sin(2.0 * math.pi * i / sides))
        for i in range(sides)
    ]


def clip_halfplane(poly: list[Point], a: float, b: float, c: float) -> list[Point]:
    """Clip by a*x + b*y + c >= 0."""
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
            if abs(denom) > EPS:
                t = -prev_v / denom
                out.append(Point(prev.x + t * (cur.x - prev.x), prev.y + t * (cur.y - prev.y)))
        if cur_inside:
            out.append(cur)
        prev, prev_v, prev_inside = cur, cur_v, cur_inside
    return out


def clip_circle_superset(poly: list[Point], center: Point, radius: float, sides: int = 96) -> list[Point]:
    """Clip by a circumscribed regular polygon containing the circle."""
    out = poly
    for i in range(sides):
        angle = 2.0 * math.pi * i / sides
        nx, ny = math.cos(angle), math.sin(angle)
        # n dot (p - center) <= radius  ->  -n dot p + n dot center + radius >= 0
        out = clip_halfplane(out, -nx, -ny, nx * center.x + ny * center.y + radius)
        if not out:
            return []
    return out


def clip_bearing_wedge(poly: list[Point], position: Point, bearing_deg: float, error_deg: float = DEFAULT_BEARING_ERROR_DEG) -> list[Point]:
    lower = math.radians(bearing_deg - error_deg)
    upper = math.radians(bearing_deg + error_deg)
    ux_l, uy_l = math.cos(lower), math.sin(lower)
    ux_u, uy_u = math.cos(upper), math.sin(upper)
    # cross(u_lower, p-position) >= 0
    out = clip_halfplane(poly, -uy_l, ux_l, uy_l * position.x - ux_l * position.y)
    # cross(u_upper, p-position) <= 0
    out = clip_halfplane(out, uy_u, -ux_u, -uy_u * position.x + ux_u * position.y)
    return out


def localization_region(
    measurements: list[Measurement],
    target_radius: float = 1800.0,
    receive_radius_upper: float = 1500.0,
    bearing_error_deg: float = DEFAULT_BEARING_ERROR_DEG,
    sides: int = 160,
) -> list[Point]:
    """Return a conservative superset of the ±1 degree intersection region."""
    start_radius = target_radius / math.cos(math.pi / sides)
    poly = regular_polygon(start_radius, sides=sides)
    poly = clip_circle_superset(poly, Point(0.0, 0.0), target_radius, sides=sides)
    for m in measurements:
        if m.result != "direction" or m.svd_deg is None:
            continue
        poly = clip_bearing_wedge(poly, m.position, m.svd_deg, error_deg=bearing_error_deg)
        if not poly:
            return []
        poly = clip_circle_superset(poly, m.position, receive_radius_upper, sides=96)
        if not poly:
            return []
    return poly


def polygon_centroid(poly: list[Point]) -> Point:
    if not poly:
        return Point(0.0, 0.0)
    area2 = 0.0
    cx = 0.0
    cy = 0.0
    for p, q in zip(poly, poly[1:] + poly[:1]):
        cross = p.x * q.y - q.x * p.y
        area2 += cross
        cx += (p.x + q.x) * cross
        cy += (p.y + q.y) * cross
    if abs(area2) < EPS:
        return Point(sum(p.x for p in poly) / len(poly), sum(p.y for p in poly) / len(poly))
    return Point(cx / (3.0 * area2), cy / (3.0 * area2))


def circle_from_two(a: Point, b: Point) -> Circle:
    return Circle(Point((a.x + b.x) / 2.0, (a.y + b.y) / 2.0), distance(a, b) / 2.0)


def circle_from_three(a: Point, b: Point, c: Point) -> Circle | None:
    d = 2.0 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y))
    if abs(d) < EPS:
        return None
    ux = (
        (a.x * a.x + a.y * a.y) * (b.y - c.y)
        + (b.x * b.x + b.y * b.y) * (c.y - a.y)
        + (c.x * c.x + c.y * c.y) * (a.y - b.y)
    ) / d
    uy = (
        (a.x * a.x + a.y * a.y) * (c.x - b.x)
        + (b.x * b.x + b.y * b.y) * (a.x - c.x)
        + (c.x * c.x + c.y * c.y) * (b.x - a.x)
    ) / d
    center = Point(ux, uy)
    return Circle(center, distance(center, a))


def contains(circle: Circle, point: Point, eps: float = 1e-6) -> bool:
    return distance(circle.center, point) <= circle.radius + eps


def minimum_enclosing_circle(points: list[Point]) -> Circle:
    if not points:
        return Circle(Point(0.0, 0.0), float("inf"))

    # Deterministic incremental MEC. This is mathematically the same boundary
    # construction as the cubic fallback, but avoids pathological slowdowns when
    # clipping creates hundreds of polygon vertices during offline evaluation.
    ordered = list(points)
    random.Random(0).shuffle(ordered)
    best = Circle(ordered[0], 0.0)
    for i, p in enumerate(ordered):
        if contains(best, p):
            continue
        best = Circle(p, 0.0)
        for j, q in enumerate(ordered[:i]):
            if contains(best, q):
                continue
            best = circle_from_two(p, q)
            for r in ordered[:j]:
                if contains(best, r):
                    continue
                c = circle_from_three(p, q, r)
                if c is not None:
                    best = c
    if all(contains(best, p) for p in ordered):
        return best
    # Fallback for numerical edge cases.
    center = polygon_centroid(ordered)
    return Circle(center, max(distance(center, p) for p in ordered))


def max_distance_to_vertices(point: Point, poly: list[Point]) -> float:
    return max((distance(point, p) for p in poly), default=0.0)
