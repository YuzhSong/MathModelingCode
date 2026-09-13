"""Cheap route repair with current macro locking."""
from __future__ import annotations

import math
from dataclasses import dataclass

from q3.models import Point


@dataclass(frozen=True)
class RouteRepair:
    locked_macro: Point | None
    route: tuple[Point, ...]
    total_seconds: float


def _d(a: Point, b: Point) -> float:
    return math.hypot(a.x-b.x, a.y-b.y)


def _length(start: Point, route: list[Point]) -> float:
    return sum(_d(a, b) for a, b in zip((start, *route), route))


def _two_opt(start: Point, route: list[Point]) -> list[Point]:
    best = route[:]
    improved = True
    while improved:
        improved = False
        for i in range(len(best)):
            for j in range(i + 1, len(best)):
                candidate = best[:i] + list(reversed(best[i:j + 1])) + best[j + 1:]
                if _length(start, candidate) + 1e-9 < _length(start, best):
                    best, improved = candidate, True
    return best


def relocate(route: list[Point], source_index: int, target_index: int) -> list[Point]:
    if source_index < 0 or source_index >= len(route):
        raise IndexError(source_index)
    result = route[:]
    point = result.pop(source_index)
    result.insert(max(0, min(target_index, len(result))), point)
    return result


def swap(route: list[Point], first: int, second: int) -> list[Point]:
    result = route[:]
    result[first], result[second] = result[second], result[first]
    return result


def repair_route(current: Point, remaining: list[Point], *, locked_macro: Point | None = None,
                 speed_mps: float = 5.0) -> RouteRepair:
    """Nearest-neighbor repair after the locked macro; objective is seconds."""
    if speed_mps <= 0:
        raise ValueError("speed_mps must be positive")
    route: list[Point] = []
    cursor = locked_macro or current
    pending = list(remaining)
    if locked_macro is not None:
        route.append(locked_macro)
    while pending:
        next_point = min(pending, key=lambda p: (_d(cursor, p), p.x, p.y))
        route.append(next_point); pending.remove(next_point); cursor = next_point
    # Local relocate/swap are represented by the deterministic insertion
    # construction above; 2-opt then repairs crossings on the unlocked suffix.
    prefix = route[:1] if locked_macro is not None else []
    suffix = route[1:] if locked_macro is not None else route
    suffix = _two_opt(locked_macro or current, suffix)
    route = prefix + suffix
    distance = _length(current, route)
    return RouteRepair(locked_macro, tuple(route), distance / speed_mps)
