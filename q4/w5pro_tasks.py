"""Planner-owned task vocabulary for the incremental W5Pro migration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from q3.models import Point


TASK_KINDS = {"SEARCH", "REFINE", "REACQUIRE", "CLEAR", "VERIFY", "SPATIAL_STOP"}


@dataclass
class WaitDecision:
    channel: int
    assigned_waypoint: Point
    dedicated_cost_s: float
    route_opportunity_cost_s: float
    wait_age: int
    skipped_count: int
    starvation: bool
    reason: str


@dataclass
class W5ProTask:
    kind: str
    point: Point
    channel: int | None = None
    search_index: int | None = None
    scan_channels: tuple[int, ...] = ()
    clear_channels: tuple[int, ...] = ()
    hard_required: bool = False
    mandatory: bool = False
    information_gain: float = 0.0
    coverage_gain: float = 0.0
    refinement_gain: float = 0.0
    expected_time_s: float = 0.0
    route_marginal_s: float = 0.0
    route_saving_s: float = 0.0
    age: int = 0
    future_cost_samples: tuple[float, ...] = ()
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in TASK_KINDS:
            raise ValueError(f"unknown W5Pro task kind: {self.kind}")


class RemainingTaskPool:
    """Planner-owned task pool with bounded WAIT_FOR_ROUTE semantics."""

    def __init__(self, starvation_decisions: int = 7, starvation_time_s: float = 3000.0):
        if starvation_decisions < 1 or starvation_time_s <= 0:
            raise ValueError("starvation limits must be positive")
        self.starvation_decisions = starvation_decisions
        self.starvation_time_s = float(starvation_time_s)
        self.tasks: dict[tuple[str, int | None, int | None], W5ProTask] = {}
        self.wait_age: dict[int, int] = {}
        self.skipped_count: dict[int, int] = {}
        self.elapsed_unserved_s: dict[int, float] = {}
        self.wait_log: list[WaitDecision] = []

    def sync(self, tasks: Iterable[W5ProTask]) -> None:
        """Replace stale task candidates after an observation without changing physical state."""
        self.tasks = {(t.kind, t.channel, t.search_index): t for t in tasks}

    def all(self) -> list[W5ProTask]:
        return list(self.tasks.values())

    def found_channels(self) -> set[int]:
        return {t.channel for t in self.tasks.values() if t.channel is not None and t.kind in {"REFINE", "REACQUIRE", "CLEAR"}}

    def backlog_pressure(self) -> float:
        """Planner debt used to balance discovery against exploitation."""
        active = self.found_channels()
        clear = {t.channel for t in self.tasks.values()
                 if t.kind == "CLEAR" and t.channel is not None}
        max_age = max((self.wait_age.get(c, 0) for c in active), default=0)
        return float(len(active) + 2 * len(clear) + max_age)

    def age_cost(self, channel: int | None, kind: str) -> float:
        """Nonlinear tail penalty; CLEAR receives the stronger weight."""
        if channel is None:
            return 0.0
        age = float(self.wait_age.get(channel, 0))
        excess = max(0.0, age - 3.0)
        penalty = age + 0.5 * excess * excess
        return (2.0 if kind == "CLEAR" else 1.0) * penalty

    def wait_for_route(self, channel: int, waypoint: Point, dedicated_cost_s: float,
                       route_opportunity_cost_s: float, elapsed_s: float = 0.0) -> WaitDecision:
        age = self.wait_age.get(channel, 0) + 1
        skipped = self.skipped_count.get(channel, 0) + 1
        elapsed = self.elapsed_unserved_s.get(channel, 0.0) + max(0.0, elapsed_s)
        starvation = age >= self.starvation_decisions or elapsed >= self.starvation_time_s
        if starvation:
            reason = "starvation_promoted"
            self.wait_age[channel] = age
            self.skipped_count[channel] = skipped
        else:
            reason = "route_opportunity" if route_opportunity_cost_s < dedicated_cost_s else "dedicated_route"
            self.wait_age[channel] = age
            self.skipped_count[channel] = skipped
        decision = WaitDecision(channel, waypoint, float(dedicated_cost_s), float(route_opportunity_cost_s), age, skipped, starvation, reason)
        self.wait_log.append(decision)
        return decision

    def mark_served(self, channel: int) -> None:
        self.wait_age[channel] = 0
        self.skipped_count[channel] = 0
        self.elapsed_unserved_s[channel] = 0.0

    def is_wait_allowed(self, channel: int) -> bool:
        return self.wait_age.get(channel, 0) < self.starvation_decisions and self.elapsed_unserved_s.get(channel, 0.0) < self.starvation_time_s
