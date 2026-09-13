from __future__ import annotations

from typing import Any

from q3.models import Point
from q3.v6_policy import RouteAwareSupplementPolicy
from q4.geometry import TriangularGridSpec, triangular_grid_points


W1_GRID_SPEC = TriangularGridSpec(
    side_m=1000.0,
    rotation_deg=0.0,
    offset_u=0.0,
    offset_v=0.5,
)


def w1_search_points() -> list[Point]:
    """Q4 W1 expanded triangular detection backbone."""

    return triangular_grid_points(W1_GRID_SPEC)


class W1TriangularDetectionPolicy(RouteAwareSupplementPolicy):
    """W1: frozen V6 logic with only the SEARCH detection backbone replaced."""

    variant = "w1"

    def __init__(self, runner: Any):
        super().__init__(runner, n=8)
        self.search_points = w1_search_points()
        self.search_radius = W1_GRID_SPEC.crop_radius_m
        self.n = len(self.search_points)
        self.remaining_search_indices = set(range(len(self.search_points)))


def policy_w1(runner: Any) -> None:
    W1TriangularDetectionPolicy(runner).run()
