"""Conditional W6 tail fallback; W6 is never the primary W5Pro planner."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TailFallbackController:
    no_signal_limit: int = 3
    no_signal_streak: int = 0
    counts: dict[str, int] | None = None

    def __post_init__(self) -> None:
        self.counts = {"w6_rescue": 0, "w3_coarse": 0, "w2_fallback": 0}

    def choose(self, *, nbv_gain: float, route_opportunity: bool, no_progress: bool,
               result: str | None = None) -> str | None:
        if result == "no_signal":
            self.no_signal_streak += 1
        elif result is not None:
            self.no_signal_streak = 0
        if not (nbv_gain <= 0.0 or self.no_signal_streak >= self.no_signal_limit
                or not route_opportunity or no_progress):
            return None
        if no_progress or self.no_signal_streak >= self.no_signal_limit:
            action = "w6_rescue"
        elif nbv_gain <= 0.0:
            action = "w3_coarse"
        else:
            action = "w2_fallback"
        self.counts[action] += 1
        return action
