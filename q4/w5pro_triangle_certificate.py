"""Hard, per-channel certificate over the frozen W5 anchors.

The verifier is intentionally independent from the soft hypothesis grid. A
triangle becomes certified only after NO_SIGNAL has been observed at all three
of its vertices for the same channel.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from q3.models import Point
from q4.w5_geometry import w5_detection_points
from q4.w5_policy import W5_SELECTED_SPEC


@dataclass(frozen=True)
class CertificateTriangle:
    triangle_id: int
    vertices: tuple[int, int, int]


def _area(a: Point, b: Point, c: Point) -> float:
    return abs((b.x-a.x)*(c.y-a.y) - (b.y-a.y)*(c.x-a.x)) / 2.0


def enumerate_legal_triangles(points: Sequence[Point], guaranteed_radius_m: float = 1000.0) -> tuple[CertificateTriangle, ...]:
    """Enumerate non-degenerate triples whose every edge is <= guaranteed range."""
    result: list[CertificateTriangle] = []
    for vertices in itertools.combinations(range(len(points)), 3):
        if _area(*(points[i] for i in vertices)) <= 1e-7:
            continue
        if all(math.hypot(points[i].x-points[j].x, points[i].y-points[j].y) <= guaranteed_radius_m + 1e-9
               for i, j in itertools.combinations(vertices, 2)):
            result.append(CertificateTriangle(len(result), vertices))
    return tuple(result)


def select_certificate_mesh(points: Sequence[Point], *, arena_radius_m: float = 1800.0,
                            guaranteed_radius_m: float = 1000.0) -> tuple[CertificateTriangle, ...]:
    """Select a deterministic Delaunay certificate mesh when geometry permits.

    The disk is certified to lie inside the point-set convex hull by checking
    every hull supporting line. Delaunay faces are then retained only when all
    three edges satisfy the guaranteed-radius bound. This is an offline
    construction helper; failure is explicit when the sufficient conditions
    do not hold.
    """
    try:
        import numpy as np
        from scipy.spatial import Delaunay
    except ImportError as exc:  # pragma: no cover - environment diagnostic
        raise RuntimeError("scipy is required for certificate mesh selection") from exc
    if len(points) < 3:
        raise ValueError("at least three points are required")
    coords = np.array([(p.x, p.y) for p in points], dtype=float)
    hull = Delaunay(coords).convex_hull
    # Every supporting edge must be at least arena_radius from the origin.
    for i, j in hull:
        a, b = coords[i], coords[j]
        edge = b - a
        distance_to_line = abs(a[0] * b[1] - a[1] * b[0]) / math.hypot(*edge)
        if distance_to_line < arena_radius_m - 1e-7:
            raise ValueError("point hull does not contain the requested disk")
    faces = Delaunay(coords).simplices
    legal_faces = [face for face in faces
                   if all(math.hypot(points[i].x-points[j].x, points[i].y-points[j].y) <= guaranteed_radius_m + 1e-9
                          for i, j in itertools.combinations(map(int, face), 2))]
    if len(legal_faces) != len(faces):
        raise ValueError("Delaunay triangulation contains faces outside guaranteed radius")
    selected: list[CertificateTriangle] = []
    for face in legal_faces:
        selected.append(CertificateTriangle(len(selected), tuple(map(int, face))))
    if not selected:
        raise ValueError("no legal Delaunay faces satisfy guaranteed radius")
    return tuple(selected)


def point_in_triangle(p: Point, tri: Sequence[Point], eps: float = 1e-7) -> bool:
    a, b, c = tri
    signed = lambda u, v, w: (v.x-u.x)*(w.y-u.y) - (v.y-u.y)*(w.x-u.x)
    values = (signed(a, b, p), signed(b, c, p), signed(c, a, p))
    return min(values) >= -eps or max(values) <= eps


def verify_continuous_mesh(points: Sequence[Point], triangles: Sequence[CertificateTriangle],
                           arena_radius_m: float = 1800.0, spacing_m: float = 20.0,
                           guaranteed_radius_m: float = 1000.0) -> dict[str, float | int]:
    """Finite conservative audit of a proposed mesh over a disk.

    This is an offline verifier, not a policy shortcut: it reports uncovered
    samples and the maximum vertex distance. A production hard proof must use
    the returned audit plus a formally bounded cell subdivision.
    """
    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")
    samples = uncovered = 0
    max_vertex_distance = 0.0
    n = math.ceil(arena_radius_m / spacing_m)
    for ix in range(-n, n + 1):
        for iy in range(-n, n + 1):
            p = Point(ix * spacing_m, iy * spacing_m)
            if math.hypot(p.x, p.y) > arena_radius_m + 1e-9:
                continue
            samples += 1
            containing = [t for t in triangles if point_in_triangle(p, [points[i] for i in t.vertices])]
            if not containing:
                uncovered += 1
            for t in containing:
                max_vertex_distance = max(max_vertex_distance, *(math.hypot(points[i].x-p.x, points[i].y-p.y) for i in t.vertices))
    return {"samples": samples, "uncovered_samples": uncovered,
            "max_vertex_distance_m": max_vertex_distance,
            "guaranteed_radius_m": guaranteed_radius_m,
            "continuous_audit_pass": int(samples > 0 and uncovered == 0 and max_vertex_distance <= guaranteed_radius_m + 1e-9)}


def verify_bounded_cells(points: Sequence[Point], triangles: Sequence[CertificateTriangle], *,
                         arena_radius_m: float = 1800.0, cell_size_m: float = 10.0,
                         guaranteed_radius_m: float = 1000.0) -> dict[str, float | int]:
    """Conservative square-cell certificate for continuous mesh coverage.

    A cell is certified only when all four corners are in the same convex
    triangle and every corner-to-vertex distance plus the cell diagonal is
    within the guaranteed radius. Boundary cells intersecting the disk but
    failing these sufficient conditions remain unresolved rather than being
    silently treated as covered.
    """
    if cell_size_m <= 0:
        raise ValueError("cell_size_m must be positive")
    half = cell_size_m / 2.0
    diagonal = math.sqrt(2.0) * cell_size_m
    n = math.ceil(arena_radius_m / cell_size_m)
    cells = certified = unresolved = outside = 0
    max_bound = 0.0
    for ix in range(-n, n):
        for iy in range(-n, n):
            x0, y0 = ix * cell_size_m, iy * cell_size_m
            corners = (Point(x0, y0), Point(x0 + cell_size_m, y0),
                       Point(x0, y0 + cell_size_m), Point(x0 + cell_size_m, y0 + cell_size_m))
            if all(math.hypot(p.x, p.y) > arena_radius_m + diagonal for p in corners):
                outside += 1
                continue
            cells += 1
            found = False
            for t in triangles:
                tri = [points[i] for i in t.vertices]
                if not all(point_in_triangle(p, tri) for p in corners):
                    continue
                bound = max(math.hypot(p.x-v.x, p.y-v.y) for p in corners for v in tri) + diagonal
                max_bound = max(max_bound, bound)
                if bound <= guaranteed_radius_m + 1e-9:
                    found = True
                    break
            if found:
                certified += 1
            else:
                unresolved += 1
    return {"cells": cells, "certified_cells": certified, "unresolved_cells": unresolved,
            "outside_cells": outside, "max_bound_m": max_bound,
            "guaranteed_radius_m": guaranteed_radius_m,
            "bounded_cell_pass": int(cells > 0 and unresolved == 0)}


class ChannelTriangleCertificate:
    """Per-channel hard state; PRESENT is terminal and never becomes ABSENT."""

    def __init__(self, triangles: Sequence[CertificateTriangle]):
        self.triangles = tuple(triangles)
        self._no_signal: dict[int, set[int]] = {}
        self.present_channels: set[int] = set()

    def observe(self, channel: int, vertex_index: int, result: str) -> None:
        if result != "no_signal":
            if result in {"direction", "near", "clear", "bearing"}:
                self.present_channels.add(channel)
            return
        if channel in self.present_channels:
            return
        self._no_signal.setdefault(channel, set()).add(vertex_index)

    def certified_triangles(self, channel: int) -> set[int]:
        seen = self._no_signal.get(channel, set())
        return {t.triangle_id for t in self.triangles if set(t.vertices) <= seen}

    def hard_complete(self, channel: int) -> bool:
        return channel not in self.present_channels and len(self.certified_triangles(channel)) == len(self.triangles)

    def certificate_gain(self, channel: int, vertex_index: int) -> int:
        before = len(self.certified_triangles(channel))
        seen = self._no_signal.get(channel, set()) | {vertex_index}
        return sum(set(t.vertices) <= seen for t in self.triangles) - before


def frozen_w5_certificate() -> tuple[tuple[Point, ...], tuple[CertificateTriangle, ...]]:
    points = tuple(w5_detection_points(W5_SELECTED_SPEC))
    return points, enumerate_legal_triangles(points, W5_SELECTED_SPEC.receive_radius_m)
