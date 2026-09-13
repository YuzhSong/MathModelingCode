"""Discrete refinement neighborhoods (first-stage TSPN approximation)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from q3.models import Point
from q4.w5pro_nbv import NBVCandidate


@dataclass(frozen=True)
class RefinementNeighborhood:
    channel: int
    candidates: tuple[NBVCandidate, ...]
    visibility_threshold: float
    crossing_threshold: float
    gain_threshold: float

    def nearest_to(self, point: Point) -> NBVCandidate | None:
        return min(self.candidates, key=lambda c: (c.point.x-point.x)**2 + (c.point.y-point.y)**2) if self.candidates else None


def sample_neighborhood(channel: int, candidates: Iterable[NBVCandidate], *, visibility_threshold: float = 0.1,
                       crossing_threshold: float = 0.2, gain_threshold: float = 0.05) -> RefinementNeighborhood:
    selected = tuple(c for c in candidates if c.visible_fraction >= visibility_threshold and
                     c.meta.get("crossing_quality", 1.0) >= crossing_threshold and c.information_gain >= gain_threshold)
    return RefinementNeighborhood(channel, selected, visibility_threshold, crossing_threshold, gain_threshold)
