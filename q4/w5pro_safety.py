"""Safety gates separating W5Pro candidate generation from execution."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from q3.models import Point
from q4.w5pro_tasks import W5ProTask


@dataclass(frozen=True)
class ProgressSignature:
    discovered_count: int
    cleared_count: int
    alive_hypotheses: int
    uncertified_triangles: int
    region_diameter: float


class LivelockGuard:
    def __init__(self, no_progress_limit: int = 5):
        self.no_progress_limit = no_progress_limit
        self.last: ProgressSignature | None = None
        self.streak = 0
        self.blacklist: set[tuple] = set()

    def observe(self, signature: ProgressSignature) -> bool:
        self.streak = self.streak + 1 if signature == self.last else 1
        self.last = signature
        return self.streak >= self.no_progress_limit

    def failed_action(self, channel: int | None, family: str, point: Point) -> None:
        self.blacklist.add((channel, family, round(point.x / 20.0), round(point.y / 20.0)))

    def is_blacklisted(self, channel: int | None, family: str, point: Point) -> bool:
        return (channel, family, round(point.x / 20.0), round(point.y / 20.0)) in self.blacklist

    def next_family(self, current: str) -> str:
        order = ("ring", "perpendicular", "backbone_opportunity", "intersection", "coarse_fallback")
        return order[(order.index(current) + 1) % len(order)] if current in order else order[0]


class SafetyShield:
    def __init__(self, guard: LivelockGuard | None = None):
        self.guard = guard or LivelockGuard()

    def filter(self, candidates: Iterable[W5ProTask], *, hard_complete: bool,
               discovered_count: int, clear_ready_channels: set[int] | None = None) -> list[W5ProTask]:
        clear_ready_channels = clear_ready_channels or set()
        result: list[W5ProTask] = []
        for task in candidates:
            if task.kind == "CLEAR" and task.channel not in clear_ready_channels:
                continue
            if task.kind in {"SEARCH", "VERIFY"} and discovered_count >= 16 and not task.mandatory:
                continue
            if task.kind != "CLEAR" and task.channel in clear_ready_channels:
                continue
            if task.channel is not None and self.guard.is_blacklisted(task.channel, task.kind, task.point):
                continue
            result.append(task)
        return result

    def can_exit(self, hard_complete: bool) -> bool:
        return bool(hard_complete)

    def fallback(self, legacy_tasks: Iterable[W5ProTask]) -> list[W5ProTask]:
        return [t for t in legacy_tasks if t.kind in {"SEARCH", "VERIFY", "CLEAR"}]
