from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable

from offline_sim.case import ARENA_RADIUS_M, DIRECTIONAL_HALF_ANGLE_DEG, ang_diff, norm_deg
from q3.geometry import distance
from q3.models import Point
from q3.routing import optimize_open_point_route


MIN_RECEIVE_RADIUS_M = 1000.0


@dataclass(frozen=True)
class TriangularGridSpec:
    side_m: float
    rotation_deg: float = 0.0
    offset_u: float = 0.0
    offset_v: float = 0.0
    arena_radius_m: float = ARENA_RADIUS_M
    receive_radius_m: float = MIN_RECEIVE_RADIUS_M
    crop_margin_m: float | None = None

    @property
    def crop_radius_m(self) -> float:
        margin = self.side_m if self.crop_margin_m is None else self.crop_margin_m
        return self.arena_radius_m + margin

    @property
    def theoretical_circumradius_m(self) -> float:
        return self.side_m / math.sqrt(3.0)


def triangular_grid_points(spec: TriangularGridSpec) -> list[Point]:
    """Generate an expanded equilateral triangular lattice around the arena."""

    side = float(spec.side_m)
    height = side * math.sqrt(3.0) / 2.0
    theta = math.radians(spec.rotation_deg)
    c, s = math.cos(theta), math.sin(theta)
    basis_u = (side * c, side * s)
    basis_v = (height * -s, height * c)
    origin_x = spec.offset_u * basis_u[0] + spec.offset_v * basis_v[0]
    origin_y = spec.offset_u * basis_u[1] + spec.offset_v * basis_v[1]
    limit = spec.crop_radius_m + 2.0 * side
    i_max = int(math.ceil(limit / side)) + 3
    j_max = int(math.ceil(limit / height)) + 3
    points: list[Point] = []
    seen: set[tuple[int, int]] = set()
    for j in range(-j_max, j_max + 1):
        row_shift_x = 0.5 * side if j % 2 else 0.0
        for i in range(-i_max, i_max + 1):
            local_x = i * side + row_shift_x
            local_y = j * height
            x = origin_x + local_x * c - local_y * s
            y = origin_y + local_x * s + local_y * c
            if math.hypot(x, y) <= spec.crop_radius_m + 1e-9:
                key = (round(x * 1_000_000), round(y * 1_000_000))
                if key not in seen:
                    seen.add(key)
                    points.append(Point(x, y))
    return sorted(points, key=lambda p: (math.atan2(p.y, p.x), math.hypot(p.x, p.y)))


def bearing_from_source(source: Point, detector: Point) -> float:
    return norm_deg(math.degrees(math.atan2(detector.y - source.y, detector.x - source.x)))


def visible_for_direction(source: Point, detector: Point, direction_deg: float, receive_radius_m: float = MIN_RECEIVE_RADIUS_M) -> bool:
    if distance(source, detector) > receive_radius_m + 1e-9:
        return False
    return ang_diff(bearing_from_source(source, detector), direction_deg) <= DIRECTIONAL_HALF_ANGLE_DEG + 1e-9


def closest_visible_distance(source: Point, direction_deg: float, points: Iterable[Point], receive_radius_m: float) -> float | None:
    best: float | None = None
    for point in points:
        d = distance(source, point)
        if d <= receive_radius_m + 1e-9 and ang_diff(bearing_from_source(source, point), direction_deg) <= DIRECTIONAL_HALF_ANGLE_DEG + 1e-9:
            if best is None or d < best:
                best = d
    return best


def random_point_in_disk(rng: random.Random, radius: float) -> Point:
    r = radius * math.sqrt(rng.random())
    theta = rng.uniform(0.0, 2.0 * math.pi)
    return Point(r * math.cos(theta), r * math.sin(theta))


def adversarial_sources(spec: TriangularGridSpec, points: list[Point]) -> list[tuple[Point, float]]:
    """Boundary and cell-critical samples for detector-geometry validation."""

    samples: list[tuple[Point, float]] = []
    for k in range(720):
        theta = 2.0 * math.pi * k / 720.0
        for r in (spec.arena_radius_m, spec.arena_radius_m - 1.0, spec.arena_radius_m - 30.0):
            point = Point(r * math.cos(theta), r * math.sin(theta))
            outward = norm_deg(math.degrees(theta))
            samples.append((point, outward))
            samples.append((point, norm_deg(outward + 90.0)))
            samples.append((point, norm_deg(outward - 90.0)))

    # Triangle centroids are where the distance-to-vertices is maximized.
    by_y: dict[int, list[Point]] = {}
    for point in points:
        by_y.setdefault(round(point.y), []).append(point)
    for row in by_y.values():
        row.sort(key=lambda p: p.x)
    side = spec.side_m
    height = side * math.sqrt(3.0) / 2.0
    for point in points:
        for angle in (30, 90, 150, 210, 270, 330):
            probe = Point(
                point.x + spec.theoretical_circumradius_m * math.cos(math.radians(angle)),
                point.y + spec.theoretical_circumradius_m * math.sin(math.radians(angle)),
            )
            if distance(Point(0.0, 0.0), probe) <= spec.arena_radius_m + 1e-9:
                for direction in (0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0):
                    samples.append((probe, direction))

    # Edge midpoints exercise half-plane boundary cases.
    for point in points:
        for dx, dy in ((side, 0.0), (0.5 * side, height), (-0.5 * side, height)):
            midpoint = Point(point.x + dx / 2.0, point.y + dy / 2.0)
            if distance(Point(0.0, 0.0), midpoint) <= spec.arena_radius_m + 1e-9:
                base = norm_deg(math.degrees(math.atan2(dy, dx)))
                samples.append((midpoint, base))
                samples.append((midpoint, norm_deg(base + 180.0)))
    return samples


def verify_detection_geometry(
    spec: TriangularGridSpec,
    *,
    random_samples: int = 20_000,
    seed: int = 20260912,
) -> dict:
    points = triangular_grid_points(spec)
    rng = random.Random(seed)
    probes: list[tuple[Point, float, str]] = []
    for _ in range(random_samples):
        probes.append((random_point_in_disk(rng, spec.arena_radius_m), rng.uniform(0.0, 360.0), "random"))
    for point, direction in adversarial_sources(spec, points):
        probes.append((point, direction, "adversarial"))

    misses = 0
    random_misses = 0
    adversarial_misses = 0
    worst_distance_margin = float("inf")
    worst_visible_distance = 0.0
    visible_distances: list[float] = []
    support_margins: list[float] = []
    for source, direction, kind in probes:
        visible = closest_visible_distance(source, direction, points, spec.receive_radius_m)
        if visible is None:
            misses += 1
            if kind == "random":
                random_misses += 1
            else:
                adversarial_misses += 1
            continue
        visible_distances.append(visible)
        worst_visible_distance = max(worst_visible_distance, visible)
        worst_distance_margin = min(worst_distance_margin, spec.receive_radius_m - visible)
        theta = math.radians(direction)
        ux, uy = math.cos(theta), math.sin(theta)
        best_forward = max(
            (point.x - source.x) * ux + (point.y - source.y) * uy
            for point in points
            if distance(source, point) <= spec.receive_radius_m + 1e-9
        )
        support_margins.append(best_forward)

    route = optimize_open_point_route(Point(0.0, 0.0), points)
    return {
        "side_m": spec.side_m,
        "rotation_deg": spec.rotation_deg,
        "offset_u": spec.offset_u,
        "offset_v": spec.offset_v,
        "crop_radius_m": spec.crop_radius_m,
        "theoretical_circumradius_m": spec.theoretical_circumradius_m,
        "point_count": len(points),
        "route_length_m": route.length_m,
        "route_method": route.method,
        "probe_count": len(probes),
        "random_probe_count": random_samples,
        "adversarial_probe_count": len(probes) - random_samples,
        "misses": misses,
        "random_misses": random_misses,
        "adversarial_misses": adversarial_misses,
        "miss_rate": misses / len(probes) if probes else 0.0,
        "worst_distance_margin_m": 0.0 if worst_distance_margin == float("inf") else worst_distance_margin,
        "worst_support_margin_m": min(support_margins) if support_margins else 0.0,
        "max_visible_distance_m": worst_visible_distance,
        "mean_visible_distance_m": sum(visible_distances) / len(visible_distances) if visible_distances else 0.0,
    }

