"""Horizon-one, mission-time W5Pro planner."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from q3.models import Point
from q4.w5pro_future_cost import FutureCost, risk_adjusted_cost
from q4.w5pro_spatial import SpatialStop
from q4.w5pro_tasks import W5ProTask


class Candidate(Protocol):
    point: Point


@dataclass(frozen=True)
class PlannedMacro:
    candidate: Candidate
    immediate_cost_s: float
    future_cost: FutureCost
    total_score_s: float


def _point(candidate: Candidate) -> Point:
    return candidate.point


def pareto_prune(candidates: Iterable[Candidate]) -> list[Candidate]:
    """Remove only dominated soft candidates; safety obligations are kept."""
    items = list(candidates)
    def features(c):
        return (float(getattr(c, "expected_time_s", 0.0)),
                -float(getattr(c, "information_gain", 0.0)),
                -float(getattr(c, "coverage_gain", 0.0)),
                -float(getattr(c, "route_saving_s", 0.0)))
    protected = {"CLEAR", "VERIFY", "SPATIAL_STOP"}
    kept = []
    for i, candidate in enumerate(items):
        kind = str(getattr(candidate, "kind", "")).upper()
        if bool(getattr(candidate, "mandatory", False)) or bool(getattr(candidate, "hard_required", False)) or kind in protected:
            kept.append(candidate)
            continue
        a = features(candidate)
        dominated = any(
            j != i and str(getattr(other, "kind", "")).upper() not in protected
            and not getattr(other, "mandatory", False)
            and all(x <= y for x, y in zip(features(other), a))
            and any(x < y for x, y in zip(features(other), a))
            for j, other in enumerate(items))
        if not dominated:
            kept.append(candidate)
    return kept


class W5ProPlanner:
    """Evaluate candidates in seconds and commit exactly one macro."""

    def __init__(self, speed_mps: float = 5.0, *, risk_mode: str = "expected",
                 cvar_alpha: float = 0.8):
        if speed_mps <= 0:
            raise ValueError("speed_mps must be positive")
        self.speed_mps = float(speed_mps)
        if risk_mode not in {"expected", "cvar"}:
            raise ValueError("risk_mode must be 'expected' or 'cvar'")
        self.risk_mode = risk_mode
        self.cvar_alpha = cvar_alpha
        self.replan_count = 0
        self.selected: list[PlannedMacro] = []

    def choose(self, current: Point, candidates: Iterable[Candidate],
               future_costs: dict[int, FutureCost] | None = None) -> PlannedMacro | None:
        options = list(candidates)
        if not options:
            return None
        future_costs = future_costs or {}
        ranked = []
        for i, candidate in enumerate(options):
            distance_s = ((current.x-_point(candidate).x)**2 + (current.y-_point(candidate).y)**2) ** 0.5 / self.speed_mps
            future = future_costs.get(i, FutureCost())
            synergy = getattr(candidate, "route_synergy_s", 0.0)
            if synergy:
                future = FutureCost(future.clear_s, future.localize_s, future.backbone_s,
                                    future.sensing_s, future.starvation_s,
                                    max(future.route_synergy_s, float(synergy)))
            samples = getattr(candidate, "future_cost_samples", ())
            ranked.append(PlannedMacro(candidate, distance_s, future,
                                        distance_s + risk_adjusted_cost(
                                            future, mode=self.risk_mode,
                                            samples=samples, alpha=self.cvar_alpha)))
        selected = min(ranked, key=lambda x: (x.total_score_s, x.immediate_cost_s))
        self.selected.append(selected)
        return selected

    def commit_one_macro(self, current: Point, candidates: Iterable[Candidate],
                         future_costs: dict[int, FutureCost] | None = None) -> PlannedMacro | None:
        """Select one macro; caller executes it, then calls choose again."""
        self.replan_count += 1
        return self.choose(current, candidates, future_costs)
