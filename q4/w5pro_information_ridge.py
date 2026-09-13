"""Shared multi-channel information ridges and protected Pareto pruning."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from q3.models import Point
from q4.w5pro_tasks import W5ProTask


@dataclass(frozen=True)
class InformationRidge:
    point: Point
    channels: tuple[int, ...]
    route_insertion_cost_s: float
    information_gain: float
    route_synergy_s: float = 0.0

    @property
    def score(self) -> float:
        return self.information_gain / max(1e-9, self.route_insertion_cost_s)


def build_ridges(points: Iterable[Point], channels: Iterable[int], gain: Callable[[Point, int], float],
                 route_cost: Callable[[Point], float]) -> list[InformationRidge]:
    result = []
    channels = tuple(channels)
    for point in points:
        active = tuple(c for c in channels if gain(point, c) > 0)
        if len(active) < 2:
            continue
        value = sum(float(gain(point, c)) for c in active)
        cost = max(0.0, float(route_cost(point)))
        result.append(InformationRidge(point, active, cost, value))
    return sorted(result, key=lambda r: (-r.score, r.route_insertion_cost_s))


@dataclass(frozen=True)
class CandidateFeatures:
    immediate_time: float
    hard_certificate_gain: float
    information_gain: float
    route_synergy: float
    age_priority: float


def pareto_prune(candidates: Iterable[W5ProTask], features: dict[int, CandidateFeatures], top_k: int = 6) -> list[W5ProTask]:
    """Prune dominated optional candidates while protecting mandatory work."""
    items = list(candidates)
    protected = [t for t in items if t.mandatory or t.hard_required or t.kind == "CLEAR" or t.meta.get("starvation") or t.meta.get("legacy_fallback")]
    optional = [t for t in items if t not in protected]
    kept: list[W5ProTask] = []
    for a in optional:
        fa = features.get(id(a), CandidateFeatures(0, 0, 0, 0, 0))
        dominated = False
        for b in optional:
            if a is b:
                continue
            fb = features.get(id(b), CandidateFeatures(0, 0, 0, 0, 0))
            no_worse = (fb.immediate_time <= fa.immediate_time and fb.hard_certificate_gain >= fa.hard_certificate_gain
                        and fb.information_gain >= fa.information_gain and fb.route_synergy >= fa.route_synergy and fb.age_priority >= fa.age_priority)
            strict = (fb.immediate_time < fa.immediate_time or fb.hard_certificate_gain > fa.hard_certificate_gain
                      or fb.information_gain > fa.information_gain or fb.route_synergy > fa.route_synergy or fb.age_priority > fa.age_priority)
            if no_worse and strict:
                dominated = True
                break
        if not dominated:
            kept.append(a)
    # Keep a bounded number per task kind, but never touch protected items.
    bounded = []
    for kind in sorted({t.kind for t in kept}):
        group = [t for t in kept if t.kind == kind]
        bounded.extend(group[:top_k])
    return protected + bounded
