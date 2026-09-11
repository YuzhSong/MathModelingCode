from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def as_payload(self) -> dict[str, float]:
        return {"x": float(self.x), "y": float(self.y)}


@dataclass(frozen=True)
class Measurement:
    position: Point
    channel: int
    result: str
    svd_deg: float | None
    virtual_time_s: float | None = None


class ChannelStatus(str, Enum):
    UNKNOWN = "unknown"
    FOUND = "found"
    CLEARED = "cleared"
    ABSENT = "absent"


@dataclass
class SourceTrack:
    channel: int
    status: ChannelStatus = ChannelStatus.UNKNOWN
    measurements: list[Measurement] = field(default_factory=list)
    clear_position: Point | None = None
    clear_response: dict[str, Any] | None = None
    localization_attempts: int = 0
    localization_cache_key: tuple[tuple[float, float, float | None], ...] | None = field(default=None, repr=False)
    localization_region_cache: Any | None = field(default=None, repr=False)
    localization_circle_cache: Any | None = field(default=None, repr=False)

    @property
    def direction_measurements(self) -> list[Measurement]:
        return [m for m in self.measurements if m.result == "direction"]

    def add_measurement(self, measurement: Measurement) -> None:
        self.measurements.append(measurement)
        self.localization_cache_key = None
        self.localization_region_cache = None
        self.localization_circle_cache = None
        if self.status == ChannelStatus.UNKNOWN:
            self.status = ChannelStatus.FOUND
