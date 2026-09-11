from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .models import Point
from .routing import exact_open_route_length, optimize_open_point_route


@dataclass(frozen=True)
class OracleBenchmark:
    time_s: float
    route_length_m: float
    method: str
    exact_route: bool
    service_time_s: float
    switch_time_s: float = 0.0


def _measure_switch_count(actions: Sequence[Any], order: Sequence[int]) -> int:
    current_channel = 1
    switches = 0
    for idx in order:
        action = actions[idx]
        if action.action != "measure":
            continue
        channel = int(action.channel)
        if channel != current_channel:
            switches += 1
        current_channel = channel
    return switches


def conditional_route_oracle(actions: Sequence[Any]) -> OracleBenchmark:
    """
    Approximate Conditional Route Oracle Benchmark.

    It is intentionally post-hoc: given the exact measure/clear actions a policy
    actually generated, pretend all action endpoints are known from the start
    and optimize only the open visiting route. It is not a strict lower bound.
    """
    points = [Point(float(a.x), float(a.y)) for a in actions]
    solution = optimize_open_point_route(Point(0.0, 0.0), points)
    clear_success = sum(1 for a in actions if a.action == "clear" and a.result == "success")
    clear_fail = sum(1 for a in actions if a.action == "clear" and a.result != "success")
    measure_count = sum(1 for a in actions if a.action == "measure")
    service_time = 5.0 * measure_count + 5.0 * clear_success + 3.0 * clear_fail
    switch_time = float(_measure_switch_count(actions, solution.order))
    return OracleBenchmark(
        time_s=solution.length_m / 5.0 + service_time + switch_time,
        route_length_m=solution.length_m,
        method=f"approx-{solution.method}",
        exact_route=False,
        service_time_s=service_time,
        switch_time_s=switch_time,
    )


def full_information_oracle_proxy(case: Any) -> OracleBenchmark:
    """
    Full-information Oracle Proxy.

    This post-hoc benchmark may read ground truth: all source centers are known,
    no search or measure is needed, and clearing visits source centers directly.
    It is still a proxy, not a theoretical lower bound, because true clear only
    requires entering a 20m neighborhood.
    """
    points = [Point(float(j.x), float(j.y)) for j in case.jammers]
    solution = exact_open_route_length(Point(0.0, 0.0), points)
    service_time = 5.0 * len(points)
    return OracleBenchmark(
        time_s=solution.length_m / 5.0 + service_time,
        route_length_m=solution.length_m,
        method="full-info-proxy-" + solution.method,
        exact_route=solution.exact,
        service_time_s=service_time,
        switch_time_s=0.0,
    )


def attach_oracle_benchmarks(case: Any, result: Any) -> None:
    conditional = conditional_route_oracle(result.action_log)
    result.conditional_route_oracle_time_s = conditional.time_s
    result.conditional_route_oracle_method = conditional.method
    result.conditional_route_oracle_exact = conditional.exact_route
    result.conditional_route_oracle_gap = (
        (result.virtual_time_s - conditional.time_s) / conditional.time_s
        if conditional.time_s > 0.0
        else None
    )

    full = full_information_oracle_proxy(case)
    result.full_oracle_proxy_time_s = full.time_s
    result.full_oracle_proxy_method = full.method
    result.full_oracle_proxy_exact_route = full.exact_route
    result.full_oracle_proxy_gap = (
        (result.virtual_time_s - full.time_s) / full.time_s
        if full.time_s > 0.0
        else None
    )
