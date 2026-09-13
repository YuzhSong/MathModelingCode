"""Protected CLEAR lifecycle for W5Pro."""
from __future__ import annotations

from dataclasses import dataclass

from q3.models import Point
from q4.w5pro_tasks import W5ProTask


@dataclass
class ClearLifecycle:
    channel: int
    ready: bool = False
    clear_ready_time_s: float | None = None
    failed_attempts: int = 0
    last_failed_point: Point | None = None

    def mark_ready(self, time_s: float) -> None:
        self.ready = True
        if self.clear_ready_time_s is None:
            self.clear_ready_time_s = float(time_s)

    def mark_failed(self, point: Point) -> None:
        self.failed_attempts += 1
        self.last_failed_point = point

    def can_try(self, point: Point) -> bool:
        return self.last_failed_point != point

    def task(self, point: Point) -> W5ProTask:
        return W5ProTask("CLEAR", point, channel=self.channel, mandatory=True,
                         meta={"clear_ready_time_s": self.clear_ready_time_s,
                               "failed_attempts": self.failed_attempts})
