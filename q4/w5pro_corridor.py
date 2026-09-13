"""Route-corridor opportunity candidates for REFINE and CLEAR service."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from q3.models import Point
from q4.w5pro_tasks import W5ProTask


@dataclass(frozen=True)
class CorridorOpportunity:
    point: Point
    segment_index: int
    insertion_cost_s: float
    detour_m: float
    task: W5ProTask


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a.x-b.x, a.y-b.y)


def _lerp(a: Point, b: Point, t: float) -> Point:
    return Point(a.x + t*(b.x-a.x), a.y + t*(b.y-a.y))


def route_insertion_cost(route: tuple[Point, ...], segment_index: int, point: Point, speed_mps: float = 5.0) -> float:
    a, b = route[segment_index], route[segment_index+1]
    return (_distance(a, point) + _distance(point, b) - _distance(a, b)) / speed_mps


def corridor_candidates(route: Iterable[Point], tasks: Iterable[W5ProTask], samples_per_segment: int = 5) -> list[CorridorOpportunity]:
    route = tuple(route)
    if len(route) < 2 or samples_per_segment < 2:
        return []
    result: list[CorridorOpportunity] = []
    for index in range(len(route)-1):
        for step in range(1, samples_per_segment):
            point = _lerp(route[index], route[index+1], step/samples_per_segment)
            for task in tasks:
                if task.kind not in {"REFINE", "CLEAR"}:
                    continue
                detour = _distance(point, task.point)
                result.append(CorridorOpportunity(point, index,
                    route_insertion_cost(route, index, point) + detour/5.0,
                    detour, task))
    return sorted(result, key=lambda x: (x.insertion_cost_s, x.task.kind, x.task.channel or 0))


def bind_waiting_opportunities(opportunities: Iterable[CorridorOpportunity], dedicated_cost_s: dict[int, float], threshold: float = 1.0) -> list[CorridorOpportunity]:
    """Return only opportunities materially cheaper than dedicated service."""
    return [o for o in opportunities if o.task.channel is not None and
            o.insertion_cost_s <= dedicated_cost_s.get(o.task.channel, float("inf")) * threshold]
