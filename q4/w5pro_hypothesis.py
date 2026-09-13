"""Conservative Q4 position/type/direction hypothesis grid.

This module is planner-only.  It consumes observations and never accesses a
case, jammer, effective radius, or simulator oracle.
"""
from __future__ import annotations

import math
from functools import cached_property
from dataclasses import dataclass
from typing import Iterable

from q3.models import Point

try:
    import numpy as np
except ImportError:  # pragma: no cover - simulator environments may omit NumPy
    np = None


@dataclass(frozen=True)
class HypothesisCell:
    center: Point
    half: float

    @cached_property
    def corners(self) -> tuple[Point, ...]:
        return tuple(Point(self.center.x + dx, self.center.y + dy)
                     for dx, dy in ((-self.half, -self.half), (-self.half, self.half),
                                    (self.half, -self.half), (self.half, self.half)))


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _heading_covers(point: Point, observer: Point, heading: float) -> bool:
    # Source-to-observer bearing must lie in the directional 180-degree arc.
    bearing = math.degrees(math.atan2(observer.y - point.y, observer.x - point.x)) % 360.0
    return _angle_diff(bearing, heading) <= 90.0 + 1e-9


class HypothesisGrid:
    """Per-channel conservative omni and directional hypothesis sets."""

    def __init__(self, spacing_m: float = 60.0, arena_radius_m: float = 1800.0,
                 heading_bins: int = 36, guaranteed_radius_m: float = 1000.0):
        if spacing_m <= 0 or heading_bins <= 0:
            raise ValueError("spacing_m and heading_bins must be positive")
        self.spacing_m = float(spacing_m)
        self.arena_radius_m = float(arena_radius_m)
        self.heading_bins = int(heading_bins)
        self.guaranteed_radius_m = float(guaranteed_radius_m)
        half = self.spacing_m / 2.0
        limit = self.arena_radius_m + math.sqrt(2.0) * half
        n = math.ceil(limit / self.spacing_m)
        self.cells = tuple(HypothesisCell(Point(ix * self.spacing_m, iy * self.spacing_m), half)
                           for ix in range(-n, n + 1) for iy in range(-n, n + 1)
                           if math.hypot(ix * self.spacing_m, iy * self.spacing_m) <= limit + 1e-9)
        self._omni: dict[int, set[int]] = {}
        self._directional: dict[int, dict[int, set[int]]] = {}
        self._guaranteed_cache: dict[tuple[float, float], frozenset[int]] = {}
        self._directional_no_signal_cache: dict[tuple[float, float], dict[int, frozenset[int]]] = {}

    def add_channel(self, channel: int) -> None:
        # Do not use setdefault here: its default expression is evaluated on
        # every call, rebuilding the full 2965 x 36 hypothesis state even when
        # the channel already exists.
        if channel not in self._omni:
            self._omni[channel] = set(range(len(self.cells)))
        if channel not in self._directional:
            self._directional[channel] = {
                h: set(range(len(self.cells))) for h in range(self.heading_bins)
            }

    def alive_count(self, channel: int) -> int:
        self.add_channel(channel)
        return len(self._omni[channel]) + sum(len(v) for v in self._directional[channel].values())

    def alive_fraction(self, channel: int) -> float:
        self.add_channel(channel)
        total = len(self.cells) * (1 + self.heading_bins)
        return self.alive_count(channel) / total if total else 0.0

    def _cell_within_guaranteed_range(self, cell: HypothesisCell, q: Point) -> bool:
        return max(math.hypot(p.x - q.x, p.y - q.y) for p in cell.corners) <= self.guaranteed_radius_m + 1e-9

    def update_no_signal(self, channel: int, q: Point) -> None:
        """Apply only guaranteed-negative eliminations (never use 1500m)."""
        self.add_channel(channel)
        omni = self._omni[channel]
        directional = self._directional[channel]
        key = (round(q.x, 6), round(q.y, 6))
        guaranteed = self._guaranteed_cache.get(key)
        if guaranteed is None:
            guaranteed = frozenset(i for i, cell in enumerate(self.cells)
                                    if self._cell_within_guaranteed_range(cell, q))
            self._guaranteed_cache[key] = guaranteed
        omni.difference_update(guaranteed)
        directional_masks = self._directional_no_signal_cache.get(key)
        if directional_masks is None:
            directional_masks = {}
            for h in range(self.heading_bins):
                heading = h * 360.0 / self.heading_bins
                edge = 180.0 / self.heading_bins
                removable = [i for i in guaranteed
                             if all(_heading_covers(p, q, heading + d)
                                    for p in self.cells[i].corners for d in (-edge, edge))]
                directional_masks[h] = frozenset(removable)
            self._directional_no_signal_cache[key] = directional_masks
        for h, alive in directional.items():
            alive.difference_update(directional_masks[h])

    def update_bearing(self, channel: int, q: Point, bearing_deg: float,
                       bearing_tolerance_deg: float = 1.0, upper_range_m: float = 1500.0) -> None:
        self.add_channel(channel)
        if np is not None:
            # Vectorize the conservative corner test.  The predicate is the
            # same as the reference loop: any cell corner may witness a legal
            # source configuration, so no unsafe cell is removed.
            corners = np.asarray([[(p.x, p.y) for p in cell.corners]
                                  for cell in self.cells], dtype=float)
            dx = corners[:, :, 0] - q.x
            dy = corners[:, :, 1] - q.y
            distance_ok = np.hypot(dx, dy) <= upper_range_m + 1e-9
            angle = np.degrees(np.arctan2(dy, dx))
            delta = np.abs((angle - bearing_deg + 180.0) % 360.0 - 180.0)
            omni_keep = np.any(distance_ok & (delta <= bearing_tolerance_deg + 1e-9), axis=1)
            omni_alive = self._omni[channel]
            omni_alive.intersection_update(np.flatnonzero(omni_keep).tolist())
            for h, alive in self._directional[channel].items():
                heading = h * 360.0 / self.heading_bins
                bearing_ok = delta <= bearing_tolerance_deg + 1e-9
                source_heading = np.degrees(np.arctan2(q.y - corners[:, :, 1],
                                                       q.x - corners[:, :, 0]))
                heading_delta = np.abs((source_heading - heading + 180.0) % 360.0 - 180.0)
                keep = np.any(distance_ok & bearing_ok & (heading_delta <= 90.0 + 1e-9), axis=1)
                alive.intersection_update(np.flatnonzero(keep).tolist())
            return
        omni = self._omni[channel]
        directional = self._directional[channel]
        for i in tuple(omni):
            if not any(math.hypot(p.x - q.x, p.y - q.y) <= upper_range_m + 1e-9 and
                       _angle_diff(math.degrees(math.atan2(p.y-q.y, p.x-q.x)), bearing_deg) <= bearing_tolerance_deg + 1e-9
                       for p in self.cells[i].corners):
                omni.remove(i)
        for h, alive in directional.items():
            heading = h * 360.0 / self.heading_bins
            for i in tuple(alive):
                cell = self.cells[i]
                if not any(math.hypot(p.x-q.x, p.y-q.y) <= upper_range_m + 1e-9 and
                           _angle_diff(math.degrees(math.atan2(p.y-q.y, p.x-q.x)), bearing_deg) <= bearing_tolerance_deg + 1e-9
                           and _heading_covers(p, q, heading) for p in cell.corners):
                    alive.remove(i)

    def update_near(self, channel: int, q: Point, radius_m: float = 5.0) -> None:
        self.add_channel(channel)
        for alive in [self._omni[channel], *self._directional[channel].values()]:
            alive.intersection_update(i for i, cell in enumerate(self.cells)
                                      if min(math.hypot(p.x-q.x, p.y-q.y) for p in cell.corners) <= radius_m + cell.half * math.sqrt(2.0))

    def directional_entropy(self, channel: int) -> float:
        self.add_channel(channel)
        values = [len(v) for v in self._directional[channel].values()]
        total = sum(values)
        if not total:
            return 0.0
        return -sum((v/total) * math.log(v/total) for v in values if v)

    def visible_fraction(self, channel: int, q: Point, upper_range_m: float = 1500.0) -> float:
        self.add_channel(channel)
        alive = self._directional[channel]
        total = sum(len(v) for v in alive.values())
        visible = sum(1 for h, cells in alive.items() for i in cells
                      if any(math.hypot(p.x-q.x, p.y-q.y) <= upper_range_m and
                             _heading_covers(p, q, h*360.0/self.heading_bins) for p in self.cells[i].corners))
        return visible / total if total else 0.0

    def guaranteed_elimination_gain(self, channel: int, q: Point) -> int:
        """Number of currently alive omni hypotheses safely eliminated by NO_SIGNAL."""
        self.add_channel(channel)
        key = (round(q.x, 6), round(q.y, 6))
        guaranteed = self._guaranteed_cache.get(key)
        if guaranteed is None:
            guaranteed = frozenset(i for i, cell in enumerate(self.cells)
                                   if self._cell_within_guaranteed_range(cell, q))
            self._guaranteed_cache[key] = guaranteed
        return len(self._omni[channel] & guaranteed)

    def positive_detection_mass(self, channel: int, q: Point,
                                upper_range_m: float = 1500.0) -> int:
        """Count alive position/heading hypotheses visible from an observer."""
        self.add_channel(channel)
        total = 0
        for cells in self._directional[channel].values():
            total += sum(1 for i in cells if any(
                math.hypot(p.x - q.x, p.y - q.y) <= upper_range_m + 1e-9
                for p in self.cells[i].corners))
        return total
