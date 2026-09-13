"""Planner-owned backbone candidate library for the frozen W5 geometry."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from q3.models import Point
from q4.w5_geometry import w5_detection_points
from q4.w5_policy import W5_SELECTED_SPEC
from q4.w5pro_triangle_certificate import CertificateTriangle


@dataclass
class BackboneAnchor:
    index: int
    point: Point
    hard_required: bool = True
    visited_channels: set[int] = field(default_factory=set)
    score: float = 0.0


class W5BackboneState:
    """25 immutable geometric anchors with dynamic planner metadata."""

    def __init__(self, points: Iterable[Point] | None = None):
        pts = tuple(points or w5_detection_points(W5_SELECTED_SPEC))
        if len(pts) != 25:
            raise ValueError("W5 backbone must contain exactly 25 anchors")
        self.anchors = [BackboneAnchor(i, p) for i, p in enumerate(pts)]
        self._certificate_masks: dict[int, set[int]] = {}
        self._coverage_debt: dict[int, float] = {}

    def mark_visited(self, anchor_index: int, channel: int) -> None:
        self.anchors[anchor_index].visited_channels.add(channel)

    def set_certificate_masks(self, masks: Mapping[int, Iterable[int]]) -> None:
        self._certificate_masks = {i: set(v) for i, v in masks.items()}

    def set_coverage_debt(self, debt: Mapping[int, float]) -> None:
        self._coverage_debt = {int(c): max(0.0, float(v)) for c, v in debt.items()}

    def certificate_marginal_gain(self, anchor_index: int, unfinished: set[int]) -> int:
        return len(self._certificate_masks.get(anchor_index, set()) & unfinished)

    def channel_gain(self, anchor_index: int, channel: int) -> float:
        if channel in self.anchors[anchor_index].visited_channels:
            return 0.0
        return float(channel in self._certificate_masks.get(anchor_index, set()))

    def score(self, anchor_index: int, unfinished: set[int], *, discovery_gain: float = 0.0,
              certificate_gain: float | None = None, alpha: float = 1.0,
              beta: float = 1.0, gamma: float = 1.0, travel_time_s: float = 1.0,
              scan_time_s: float = 1.0) -> float:
        """Return gain/(move+scan), with coverage debt as a starvation term."""
        if certificate_gain is None:
            certificate_gain = self.certificate_marginal_gain(anchor_index, unfinished)
        debt = sum(self._coverage_debt.get(c, 0.0) for c in unfinished
                   if c not in self.anchors[anchor_index].visited_channels)
        denominator = max(1e-9, float(travel_time_s) + float(scan_time_s))
        value = float(certificate_gain) * gamma + float(discovery_gain) * alpha + debt * beta
        self.anchors[anchor_index].score = value / denominator
        return self.anchors[anchor_index].score

    def ranked(self, unfinished: set[int], **kwargs) -> list[BackboneAnchor]:
        for anchor in self.anchors:
            self.score(anchor.index, unfinished, **kwargs)
        return sorted(self.anchors, key=lambda a: (-a.score, a.index))

    def required_indices(self, discovered_count: int, hard_complete: bool) -> set[int]:
        if discovered_count >= 16 or hard_complete:
            return set()
        return {a.index for a in self.anchors if a.hard_required}


def anchor_certificate_masks(anchors: W5BackboneState,
                             triangles: Iterable[CertificateTriangle]) -> dict[int, set[int]]:
    masks: dict[int, set[int]] = {a.index: set() for a in anchors.anchors}
    for triangle in triangles:
        for vertex in triangle.vertices:
            masks[vertex].add(triangle.triangle_id)
    anchors.set_certificate_masks(masks)
    return masks
