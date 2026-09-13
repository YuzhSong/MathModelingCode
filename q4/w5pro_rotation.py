"""Pre-traversal W5 skeleton rotation with certificate-gated selection."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from q3.models import Point
from q4.w5_geometry import w5_detection_points
from q4.w5_policy import W5_SELECTED_SPEC
from q4.w5pro_triangle_certificate import enumerate_legal_triangles, verify_continuous_mesh


def rotate_points(points: Iterable[Point], angle_deg: float) -> tuple[Point, ...]:
    angle = math.radians(angle_deg)
    c, s = math.cos(angle), math.sin(angle)
    return tuple(Point(p.x*c-p.y*s, p.x*s+p.y*c) for p in points)


@dataclass
class SkeletonRotationSelector:
    angles: tuple[float, ...] = tuple(float(x) for x in range(0, 60, 5))
    selected_angle: float | None = None
    traversal_started: bool = False
    certificate_count: int = 0

    def select(self, score: dict[float, float]) -> float:
        if self.traversal_started or self.certificate_count:
            raise RuntimeError("skeleton orientation is frozen")
        valid = []
        for angle in self.angles:
            points = rotate_points(w5_detection_points(W5_SELECTED_SPEC), angle)
            triangles = enumerate_legal_triangles(points, W5_SELECTED_SPEC.receive_radius_m)
            audit = verify_continuous_mesh(points, triangles, spacing_m=100.0)
            if audit["continuous_audit_pass"]:
                valid.append(angle)
        if not valid:
            raise ValueError("no certificate-valid skeleton orientation")
        self.selected_angle = min(valid, key=lambda a: (score.get(a, float("inf")), a))
        return self.selected_angle

    def start_traversal(self) -> None:
        if self.selected_angle is None:
            raise RuntimeError("select orientation before traversal")
        self.traversal_started = True
