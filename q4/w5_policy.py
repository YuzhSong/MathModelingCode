from __future__ import annotations

from typing import Any

from q4.w4a_policy import W4AUnifiedRoutingPolicy
from q4.w5_geometry import W5GeometrySpec, w5_detection_points


W5_SELECTED_SPEC = W5GeometrySpec(side_m=970.0, cap_extension_m=140.0)


class W5SymmetricDetectionPolicy(W4AUnifiedRoutingPolicy):
    """Frozen W4-A behavior with only the fixed detection geometry replaced."""

    def __init__(self, runner: Any, spec: W5GeometrySpec = W5_SELECTED_SPEC):
        super().__init__(runner, routing_method="open_route")
        self.geometry_spec = spec
        self.search_points = w5_detection_points(spec)
        self.search_radius = spec.supplement_radius_m
        self.n = len(self.search_points)
        self.remaining_search_indices = set(range(self.n))
        self.variant = f"w5_a{spec.side_m:g}_p{spec.cap_extension_m:g}"


def policy_w5_with_spec(runner: Any, side_m: float, cap_extension_m: float) -> None:
    W5SymmetricDetectionPolicy(runner, W5GeometrySpec(side_m, cap_extension_m)).run()


def policy_w5(runner: Any) -> None:
    W5SymmetricDetectionPolicy(runner).run()
