"""Short-horizon, state-agnostic route proposals for W5Pro.

The planner deliberately evaluates only physical task costs.  The policy
replans after every observation, so future tasks are proposals rather than
promises; hard CLEAR/SEARCH gates remain in the caller.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable
from q3.models import Point


@dataclass(frozen=True)
class RouteEstimate:
    tasks: tuple
    travel_s: float
    switch_s: float
    measure_s: float
    clear_s: float

    @property
    def total_s(self) -> float:
        return self.travel_s + self.switch_s + self.measure_s + self.clear_s


def _estimate(start: Point, tasks: tuple, channel=None, speed_mps: float = 5.0,
              switch_s: float = 1.0, measure_s: float = 5.0,
              clear_s: float = 5.0) -> RouteEstimate:
    current = start
    travel = switches = measures = clears = 0.0
    for task in tasks:
        travel += math.hypot(task.point.x - current.x, task.point.y - current.y) / speed_mps
        if task.channel not in (None, channel, 0):
            switches += switch_s
        if task.kind in {"measure", "reacquire"}:
            measures += measure_s
        elif task.kind == "clear":
            clears += clear_s
        current = task.point
        channel = task.channel
    return RouteEstimate(tasks, travel, switches, measures, clears)


def propose_routes(start: Point, tasks: list, *, horizon: int = 3,
                   beam_width: int = 6, current_channel=None,
                   future_discount: float = 0.25,
                   transition: Callable[[tuple, object], bool] | None = None) -> list[RouteEstimate]:
    """Return top short routes; caller executes only the first task."""
    if horizon < 1 or beam_width < 1:
        raise ValueError("horizon and beam_width must be positive")
    if not 0.0 <= future_discount <= 1.0:
        raise ValueError("future_discount must be between 0 and 1")
    def route_objective(route: RouteEstimate) -> float:
        first = _estimate(start, route.tasks[:1], current_channel).total_s
        return first + future_discount * max(0.0, route.total_s - first)
    beam = [()]
    for _ in range(horizon):
        expanded = []
        for prefix in beam:
            used = set(id(task) for task in prefix)
            for task in tasks:
                if id(task) in used:
                    continue
                if transition is not None and prefix and not transition(prefix, task):
                    continue
                route = prefix + (task,)
                expanded.append(_estimate(start, route, current_channel))
        expanded.sort(key=lambda route: (route_objective(route), len(route.tasks),
                                         tuple((t.kind, t.channel or -1) for t in route.tasks)))
        beam = [route.tasks for route in expanded[:beam_width]]
        if not beam:
            break
    return sorted((_estimate(start, route, current_channel) for route in beam),
                  key=route_objective)
