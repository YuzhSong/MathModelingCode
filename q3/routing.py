from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Sequence

from .geometry import distance
from .models import Point


class HasPoint(Protocol):
    point: Point


@dataclass(frozen=True)
class RouteSolution:
    order: list[int]
    length_m: float
    method: str
    exact: bool = False


def route_length_points(start: Point, points: Sequence[Point], order: Sequence[int] | None = None) -> float:
    if order is None:
        order = range(len(points))
    total = 0.0
    current = start
    for idx in order:
        total += distance(current, points[idx])
        current = points[idx]
    return total


def nearest_neighbor_order(start: Point, points: Sequence[Point]) -> list[int]:
    remaining = list(range(len(points)))
    ordered: list[int] = []
    current = start
    while remaining:
        best_pos = min(range(len(remaining)), key=lambda k: distance(current, points[remaining[k]]))
        idx = remaining.pop(best_pos)
        ordered.append(idx)
        current = points[idx]
    return ordered


def cheapest_insertion_order(start: Point, points: Sequence[Point]) -> list[int]:
    if not points:
        return []
    first = min(range(len(points)), key=lambda i: distance(start, points[i]))
    route = [first]
    remaining = [i for i in range(len(points)) if i != first]
    while remaining:
        best_idx = remaining[0]
        best_pos = len(route)
        best_delta = float("inf")
        for idx in remaining:
            for pos in range(len(route) + 1):
                prev_point = start if pos == 0 else points[route[pos - 1]]
                next_point = None if pos == len(route) else points[route[pos]]
                remove = 0.0 if next_point is None else distance(prev_point, next_point)
                add = distance(prev_point, points[idx])
                if next_point is not None:
                    add += distance(points[idx], next_point)
                delta = add - remove
                if delta < best_delta:
                    best_delta = delta
                    best_idx = idx
                    best_pos = pos
        route.insert(best_pos, best_idx)
        remaining.remove(best_idx)
    return route


def two_opt_order(start: Point, points: Sequence[Point], order: Sequence[int]) -> list[int]:
    route = list(order)
    if len(route) <= 2:
        return route

    def point_before(pos: int) -> Point:
        return start if pos == 0 else points[route[pos - 1]]

    improved = True
    while improved:
        improved = False
        for i in range(len(route) - 1):
            a = point_before(i)
            b = points[route[i]]
            for j in range(i + 1, len(route)):
                c = points[route[j]]
                d = None if j + 1 == len(route) else points[route[j + 1]]
                old = distance(a, b) + (0.0 if d is None else distance(c, d))
                new = distance(a, c) + (0.0 if d is None else distance(b, d))
                if new + 1e-6 < old:
                    route[i : j + 1] = reversed(route[i : j + 1])
                    improved = True
                    break
            if improved:
                break
    return route


def optimize_open_point_route(start: Point, points: Sequence[Point]) -> RouteSolution:
    if not points:
        return RouteSolution([], 0.0, "empty", exact=True)
    candidates = [("nearest+2opt", two_opt_order(start, points, nearest_neighbor_order(start, points)))]
    if len(points) <= 80:
        candidates.append(("cheapest-insertion+2opt", two_opt_order(start, points, cheapest_insertion_order(start, points))))
    method, order = min(candidates, key=lambda item: route_length_points(start, points, item[1]))
    return RouteSolution(order, route_length_points(start, points, order), method, exact=False)


def optimize_open_route(start: Point, items: Sequence[HasPoint]) -> list[HasPoint]:
    points = [item.point for item in items]
    solution = optimize_open_point_route(start, points)
    return [items[idx] for idx in solution.order]


def exact_open_route_length(start: Point, points: Sequence[Point], max_exact_points: int = 12) -> RouteSolution:
    n = len(points)
    if n == 0:
        return RouteSolution([], 0.0, "exact-dp", exact=True)
    if n > max_exact_points:
        approximate = optimize_open_point_route(start, points)
        return RouteSolution(approximate.order, approximate.length_m, approximate.method, exact=False)

    dp: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {}
    for i, point in enumerate(points):
        dp[(1 << i, i)] = (distance(start, point), (i,))

    for mask in range(1, 1 << n):
        for last in range(n):
            state = (mask, last)
            if state not in dp:
                continue
            base_len, base_order = dp[state]
            remain = ((1 << n) - 1) ^ mask
            bitset = remain
            while bitset:
                bit = bitset & -bitset
                nxt = bit.bit_length() - 1
                new_mask = mask | bit
                cand = base_len + distance(points[last], points[nxt])
                old = dp.get((new_mask, nxt))
                if old is None or cand < old[0]:
                    dp[(new_mask, nxt)] = (cand, base_order + (nxt,))
                bitset ^= bit

    full = (1 << n) - 1
    length, order_tuple = min((dp[(full, last)] for last in range(n) if (full, last) in dp), key=lambda item: item[0])
    return RouteSolution(list(order_tuple), length, "exact-dp", exact=True)
