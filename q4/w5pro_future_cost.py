"""Mission-time future-cost model for W5Pro planner decisions."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable


def cvar_cost(samples: Iterable[float], alpha: float = 0.8) -> float:
    """Return upper-tail conditional value at risk in mission seconds."""
    values = sorted(max(0.0, float(value)) for value in samples)
    if not values:
        return 0.0
    if not 0.0 <= alpha < 1.0:
        raise ValueError("alpha must satisfy 0 <= alpha < 1")
    cutoff = int(len(values) * alpha)
    tail = values[cutoff:] or values[-1:]
    return sum(tail) / len(tail)


def risk_adjusted_cost(cost: "FutureCost", *, mode: str = "expected",
                       samples: Iterable[float] = (), alpha: float = 0.8) -> float:
    """Return future cost in seconds under an explicit risk policy."""
    if mode == "expected":
        return cost.total_s
    if mode == "cvar":
        values = tuple(samples)
        return cvar_cost(values, alpha=alpha) if values else cost.total_s
    raise ValueError("mode must be 'expected' or 'cvar'")


@dataclass(frozen=True)
class FutureCost:
    clear_s: float = 0.0
    localize_s: float = 0.0
    backbone_s: float = 0.0
    sensing_s: float = 0.0
    starvation_s: float = 0.0
    route_synergy_s: float = 0.0

    @property
    def additive_s(self) -> float:
        return sum((self.clear_s, self.localize_s, self.backbone_s, self.sensing_s, self.starvation_s))

    @property
    def total_s(self) -> float:
        return max(0.0, self.additive_s - max(0.0, self.route_synergy_s))


def estimate_future_cost(*, clear_s: float = 0.0, localize_s: float = 0.0,
                         backbone_s: float = 0.0, sensing_s: float = 0.0,
                         starvation_s: float = 0.0, route_synergy_s: float = 0.0) -> FutureCost:
    return FutureCost(*(max(0.0, float(x)) for x in
                        (clear_s, localize_s, backbone_s, sensing_s, starvation_s)),
                      max(0.0, float(route_synergy_s)))
