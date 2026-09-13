from __future__ import annotations

import bisect
import math
import random
from dataclasses import dataclass

from .geometry import (
    Circle,
    clip_bearing_wedge,
    distance,
    max_distance_to_vertices,
    minimum_enclosing_circle,
)
from .models import Measurement, Point, SourceTrack
from .planner import Q3BaselinePlanner


@dataclass(frozen=True)
class V5PredictionConfig:
    """Fixed, reproducible geometry-prediction settings for V5."""

    sample_seed: int = 20260911
    sample_count: int = 12
    bearing_error_offsets_deg: tuple[float, ...] = (-1.0, 0.0, 1.0)
    candidate_radii_m: tuple[float, ...] = (500.0, 950.0)
    candidate_angle_step_deg: float = 30.0
    guaranteed_receive_distance_m: float = 995.0
    repeat_distance_m: float = 10.0
    robot_speed_mps: float = 5.0
    measure_time_s: float = 5.0
    clear_time_s: float = 5.0


@dataclass(frozen=True)
class CandidatePrediction:
    point: Point
    p_clear: float
    expected_mec_after_m: float
    expected_remaining_time_s: float
    expected_total_incremental_time_s: float
    outcome_count: int


def _triangle_area2(a: Point, b: Point, c: Point) -> float:
    return abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x))


def sample_feasible_polygon(poly: list[Point], count: int, seed: int) -> list[Point]:
    """Uniformly sample a convex feasible polygon with a fixed local RNG."""
    if not poly or count <= 0:
        return []
    if len(poly) < 3:
        return [poly[i % len(poly)] for i in range(count)]

    anchor = poly[0]
    triangles: list[tuple[Point, Point, Point]] = []
    cumulative: list[float] = []
    total = 0.0
    for i in range(1, len(poly) - 1):
        tri = (anchor, poly[i], poly[i + 1])
        area2 = _triangle_area2(*tri)
        if area2 <= 1e-12:
            continue
        total += area2
        triangles.append(tri)
        cumulative.append(total)
    if not triangles:
        return [poly[i % len(poly)] for i in range(count)]

    rng = random.Random(seed)
    samples: list[Point] = []
    for _ in range(count):
        tri_idx = min(bisect.bisect_left(cumulative, rng.random() * total), len(triangles) - 1)
        a, b, c = triangles[tri_idx]
        root = math.sqrt(rng.random())
        v = rng.random()
        wa = 1.0 - root
        wb = root * (1.0 - v)
        wc = root * v
        samples.append(Point(wa * a.x + wb * b.x + wc * c.x, wa * a.y + wb * b.y + wc * c.y))
    return samples


def candidate_grid(circle: Circle, config: V5PredictionConfig) -> list[Point]:
    points = [circle.center]
    steps = int(round(360.0 / config.candidate_angle_step_deg))
    for radius in config.candidate_radii_m:
        for i in range(steps):
            angle = math.radians(i * config.candidate_angle_step_deg)
            points.append(Point(circle.center.x + radius * math.cos(angle), circle.center.y + radius * math.sin(angle)))
    return points


def eligible_candidates(
    track: SourceTrack,
    region: list[Point],
    circle: Circle,
    config: V5PredictionConfig,
    extra_points: tuple[Point, ...] = (),
) -> list[Point]:
    points = candidate_grid(circle, config) + list(extra_points)
    eligible: list[Point] = []
    seen: set[tuple[int, int]] = set()
    for point in points:
        key = (round(point.x * 1_000_000), round(point.y * 1_000_000))
        if key in seen:
            continue
        seen.add(key)
        if max_distance_to_vertices(point, region) > config.guaranteed_receive_distance_m:
            continue
        if any(distance(point, m.position) < config.repeat_distance_m for m in track.direction_measurements):
            continue
        eligible.append(point)
    return eligible


def _fallback_point(
    measurements: list[Measurement],
    region: list[Point],
    circle: Circle,
    current: Point,
    config: V5PredictionConfig,
) -> Point:
    synthetic = SourceTrack(measurements[0].channel if measurements else 0)
    synthetic.measurements = list(measurements)
    best = circle.center
    best_score = -float("inf")
    for point in candidate_grid(circle, config):
        if max_distance_to_vertices(point, region) > config.guaranteed_receive_distance_m:
            continue
        quality = Q3BaselinePlanner.crossing_quality(synthetic, point, circle.center)
        move_penalty = distance(current, point) / 5000.0
        repeat_penalty = 1.0 if any(
            distance(point, m.position) < config.repeat_distance_m for m in synthetic.direction_measurements
        ) else 0.0
        score = quality - move_penalty - repeat_penalty
        if score > best_score:
            best_score = score
            best = point
    return best


def predict_candidate(
    track: SourceTrack,
    region: list[Point],
    candidate: Point,
    current_position: Point,
    samples: list[Point],
    config: V5PredictionConfig,
    mandatory_search_point: bool = False,
) -> CandidatePrediction:
    """Estimate one-step clearance and remaining completion time from visible geometry."""
    clearable = 0
    mec_values: list[float] = []
    remaining_times: list[float] = []
    outcome_count = 0

    for possible_source in samples:
        if distance(candidate, possible_source) <= 5.0:
            for _ in config.bearing_error_offsets_deg:
                clearable += 1
                outcome_count += 1
                mec_values.append(0.0)
                remaining_times.append(config.clear_time_s)
            continue

        true_bearing = math.degrees(
            math.atan2(possible_source.y - candidate.y, possible_source.x - candidate.x)
        ) % 360.0
        for error_deg in config.bearing_error_offsets_deg:
            reported = round((true_bearing + error_deg) % 360.0, 2)
            after_region = clip_bearing_wedge(region, candidate, reported)
            if not after_region:
                continue
            after_circle = minimum_enclosing_circle(after_region)
            outcome_count += 1
            mec_values.append(after_circle.radius)
            if after_circle.radius <= 20.0:
                clearable += 1
                remaining_times.append(
                    distance(candidate, after_circle.center) / config.robot_speed_mps + config.clear_time_s
                )
                continue

            synthetic_measure = Measurement(candidate, track.channel, "direction", reported, None)
            fallback = _fallback_point(
                track.direction_measurements + [synthetic_measure],
                after_region,
                after_circle,
                candidate,
                config,
            )
            remaining_times.append(
                distance(candidate, fallback) / config.robot_speed_mps
                + config.measure_time_s
                + distance(fallback, after_circle.center) / config.robot_speed_mps
                + config.clear_time_s
            )

    if outcome_count == 0:
        return CandidatePrediction(candidate, 0.0, float("inf"), float("inf"), float("inf"), 0)

    move_time = 0.0 if mandatory_search_point else distance(current_position, candidate) / config.robot_speed_mps
    expected_remaining = sum(remaining_times) / len(remaining_times)
    return CandidatePrediction(
        point=candidate,
        p_clear=clearable / outcome_count,
        expected_mec_after_m=sum(mec_values) / len(mec_values),
        expected_remaining_time_s=expected_remaining,
        expected_total_incremental_time_s=move_time + config.measure_time_s + expected_remaining,
        outcome_count=outcome_count,
    )
