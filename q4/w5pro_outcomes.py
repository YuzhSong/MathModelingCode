"""Outcome probabilities derived from soft H hypotheses only."""
from __future__ import annotations

from dataclasses import dataclass

from q4.w5pro_hypothesis import HypothesisGrid
from q3.models import Point


@dataclass(frozen=True)
class OutcomeProbabilities:
    no_signal: float
    bearing: float
    near: float


def outcome_probabilities(grid: HypothesisGrid, channel: int, point: Point,
                          near_fraction: float = 0.05, *, mode: str = "robust") -> OutcomeProbabilities:
    if mode not in {"robust", "expected"}:
        raise ValueError("mode must be 'robust' or 'expected'")
    visible = max(0.0, min(1.0, grid.visible_fraction(channel, point)))
    near = max(0.0, min(visible, float(near_fraction) * visible))
    return OutcomeProbabilities(1.0 - visible, visible - near, near)
