"""Conditional W6 tail fallback; W6 is never the primary W5Pro planner."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TailFallbackController:
    no_signal_limit: int = 3
    no_signal_streak: int = 0
    counts: dict[str, int] | None = None
    channel_counts: dict[int, int] | None = None
    state_counts: dict[tuple[int, str], int] | None = None
    per_channel_budget: int = 8
    per_state_budget: int = 3
    switched_states: set[tuple[int, str]] | None = None

    def __post_init__(self) -> None:
        self.counts = {"w6_rescue": 0, "w3_coarse": 0, "w2_fallback": 0}
        self.channel_counts = {}
        self.state_counts = {}
        self.switched_states = set()

    def choose(self, *, nbv_gain: float, route_opportunity: bool, no_progress: bool,
               result: str | None = None, channel: int | None = None,
               state: str = "default") -> str | None:
        if result == "no_signal":
            self.no_signal_streak += 1
        elif result is not None:
            self.no_signal_streak = 0
        if not (nbv_gain <= 0.0 or self.no_signal_streak >= self.no_signal_limit
                or not route_opportunity or no_progress):
            return None
        if channel is not None:
            state_key = (channel, state)
            if state_key in self.switched_states:
                self.no_signal_streak = 0
                return None
            if (self.channel_counts.get(channel, 0) >= self.per_channel_budget
                    or self.state_counts.get(state_key, 0) >= self.per_state_budget):
                self.switched_states.add(state_key)
                self.no_signal_streak = 0
                return "switch_strategy"
        if no_progress or self.no_signal_streak >= self.no_signal_limit:
            action = "w6_rescue"
        elif nbv_gain <= 0.0:
            action = "w3_coarse"
        else:
            action = "w2_fallback"
        self.counts[action] += 1
        if channel is not None:
            self.channel_counts[channel] = self.channel_counts.get(channel, 0) + 1
            key = (channel, state)
            self.state_counts[key] = self.state_counts.get(key, 0) + 1
        return action
