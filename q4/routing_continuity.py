from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from q3.geometry import distance
from q3.models import Point
from q3.offline_policy import Task
from q3.routing import nearest_neighbor_order, optimize_open_point_route, route_length_points


ROUTE_EPS_M = 1e-6


@dataclass(frozen=True)
class BackboneRouteMetrics:
    name: str
    order: list[int]
    length_m: float
    max_jump_m: float
    jumps_over_1000m: int
    turns_over_120deg: int
    turns_over_150deg: int


@dataclass(frozen=True)
class InsertionDecision:
    task: Task
    now_detour_m: float
    best_future_detour_m: float
    best_future_segment: int

    @property
    def ready_now(self) -> bool:
        return self.now_detour_m <= self.best_future_detour_m + ROUTE_EPS_M


def snake_order(points: Sequence[Point]) -> list[int]:
    rows = sorted({round(point.y, 6) for point in points})
    order: list[int] = []
    for row_index, y in enumerate(rows):
        indices = [index for index, point in enumerate(points) if round(point.y, 6) == y]
        indices.sort(key=lambda index: points[index].x, reverse=bool(row_index % 2))
        order.extend(indices)
    return order


def angular_ring_order(points: Sequence[Point]) -> list[int]:
    return sorted(
        range(len(points)),
        key=lambda index: (
            round(math.hypot(points[index].x, points[index].y), 6),
            math.atan2(points[index].y, points[index].x),
        ),
    )


def route_metrics(name: str, start: Point, points: Sequence[Point], order: list[int]) -> BackboneRouteMetrics:
    route_points = [start] + [points[index] for index in order]
    jumps = [distance(left, right) for left, right in zip(route_points, route_points[1:])]
    angles: list[float] = []
    for left, middle, right in zip(route_points, route_points[1:], route_points[2:]):
        ux, uy = middle.x - left.x, middle.y - left.y
        vx, vy = right.x - middle.x, right.y - middle.y
        nu, nv = math.hypot(ux, uy), math.hypot(vx, vy)
        if nu <= ROUTE_EPS_M or nv <= ROUTE_EPS_M:
            continue
        cosine = max(-1.0, min(1.0, (ux * vx + uy * vy) / (nu * nv)))
        angles.append(math.degrees(math.acos(cosine)))
    return BackboneRouteMetrics(
        name=name,
        order=order,
        length_m=route_length_points(start, points, order),
        max_jump_m=max(jumps, default=0.0),
        jumps_over_1000m=sum(jump > 1000.0 + ROUTE_EPS_M for jump in jumps),
        turns_over_120deg=sum(angle > 120.0 + ROUTE_EPS_M for angle in angles),
        turns_over_150deg=sum(angle > 150.0 + ROUTE_EPS_M for angle in angles),
    )


def compare_backbone_routes(start: Point, points: Sequence[Point]) -> list[BackboneRouteMetrics]:
    candidates = {
        "triangular_snake": snake_order(points),
        "nearest_neighbor": nearest_neighbor_order(start, points),
        "angular_ring": angular_ring_order(points),
        "greedy_2opt_open": optimize_open_point_route(start, points).order,
    }
    return [route_metrics(name, start, points, order) for name, order in candidates.items()]


def future_detour(
    task: Task,
    remaining_backbone: Sequence[Point],
) -> tuple[float, int]:
    """Best insertion after reaching the next backbone point.

    Segment index zero means after the first remaining backbone point. The final
    open-route endpoint is included as an option without a forced return.
    """

    if not remaining_backbone:
        return 0.0, -1
    best = distance(remaining_backbone[-1], task.point)
    best_segment = len(remaining_backbone) - 1
    for index in range(len(remaining_backbone) - 1):
        left = remaining_backbone[index]
        right = remaining_backbone[index + 1]
        detour = distance(left, task.point) + distance(task.point, right) - distance(left, right)
        if detour < best - ROUTE_EPS_M:
            best = detour
            best_segment = index
    return best, best_segment


def insertion_decisions(
    current: Point,
    next_backbone: Point,
    remaining_backbone: Sequence[Point],
    tasks: Sequence[Task],
) -> list[InsertionDecision]:
    direct = distance(current, next_backbone)
    output: list[InsertionDecision] = []
    for task in tasks:
        now = distance(current, task.point) + distance(task.point, next_backbone) - direct
        future, segment = future_detour(task, remaining_backbone)
        output.append(InsertionDecision(task, now, future, segment))
    return output


def fixed_end_route_order(start: Point, end: Point, tasks: Sequence[Task]) -> list[Task]:
    """Nearest + 2-opt route through tasks with both endpoints fixed."""

    remaining = list(tasks)
    order: list[Task] = []
    current = start
    while remaining:
        index = min(range(len(remaining)), key=lambda pos: distance(current, remaining[pos].point))
        task = remaining.pop(index)
        order.append(task)
        current = task.point

    def length(route: Sequence[Task]) -> float:
        points = [start] + [task.point for task in route] + [end]
        return sum(distance(left, right) for left, right in zip(points, points[1:]))

    improved = True
    while improved:
        improved = False
        best = length(order)
        for left in range(len(order) - 1):
            for right in range(left + 2, len(order) + 1):
                candidate = order[:left] + list(reversed(order[left:right])) + order[right:]
                candidate_length = length(candidate)
                if candidate_length < best - ROUTE_EPS_M:
                    order = candidate
                    improved = True
                    break
            if improved:
                break
    return order
