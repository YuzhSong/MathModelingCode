"""Adaptive channel scheduler and backlog controller."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ScanMode(str, Enum):
    EARLY = "early"
    MID = "mid"
    VERIFICATION = "verification"


@dataclass(frozen=True)
class BacklogState:
    found: int
    clear_ready: int
    oldest_found_age: float
    oldest_clear_age: float

    @property
    def pressure(self) -> float:
        return self.found + 2.0 * self.clear_ready + max(self.oldest_found_age, self.oldest_clear_age) / 1000.0


@dataclass
class GlobalMapMaturity:
    channels_seen: set[int] = None
    positive_channels: set[int] = None
    scans: int = 0
    hard_certificate_debt: int = 0

    def __post_init__(self):
        self.channels_seen = set(self.channels_seen or set())
        self.positive_channels = set(self.positive_channels or set())

    @property
    def fraction(self) -> float:
        return len(self.channels_seen) / 20.0

    @property
    def mature(self) -> bool:
        return len(self.channels_seen) >= 20 or (self.fraction >= 0.75 and self.scans >= 2)

    def observe(self, channel: int, positive: bool = False) -> None:
        self.channels_seen.add(int(channel)); self.scans += 1
        if positive:
            self.positive_channels.add(int(channel))


class AdaptiveScanSession:
    """Re-rank after every observation; hard channels cannot be STOP-ed."""

    def __init__(self, scheduler: AdaptiveScanScheduler | None = None):
        self.scheduler = scheduler or AdaptiveScanScheduler()
        self.map = GlobalMapMaturity()
        self.current_channel: int | None = None
        self.stop_reason: str | None = None

    def rank(self, channels: set[int], *, values: dict[int, float] | None = None,
             must_include: set[int] | None = None, clear_ready: set[int] | None = None,
             cleared: set[int] | None = None) -> list[int]:
        cleared = cleared or set()
        allowed = set(channels) - cleared
        self.scheduler.set_must_include(must_include or set())
        return self.scheduler.prioritize(allowed, clear_ready=clear_ready, channel_value=values)

    def observe(self, channel: int, result: str) -> list[int]:
        self.map.observe(channel, result in {"direction", "near"})
        self.current_channel = channel
        return []

    def should_stop_optional(self, positive_voi: bool, hard_required: bool = False) -> bool:
        return not positive_voi and not hard_required


class AdaptiveScanScheduler:
    def __init__(self, early_cap: int = 20, mid_cap: int = 6, starvation_age_s: float = 3000.0):
        self.early_cap = early_cap
        self.mid_cap = mid_cap
        self.starvation_age_s = starvation_age_s
        self.mode = ScanMode.EARLY
        self.must_include: set[int] = set()
        self.scan_log: list[dict] = []

    def update_mode(self, *, discovered: int, hard_complete: bool, backlog: BacklogState) -> ScanMode:
        if hard_complete:
            self.mode = ScanMode.VERIFICATION
        elif discovered == 0 and backlog.pressure < 1.0:
            self.mode = ScanMode.EARLY
        else:
            self.mode = ScanMode.MID
        return self.mode

    def set_must_include(self, channels: set[int]) -> None:
        self.must_include = set(channels)

    def prioritize(self, channels: set[int], *, clear_ready: set[int] | None = None, channel_value: dict[int, float] | None = None) -> list[int]:
        clear_ready = clear_ready or set()
        channel_value = channel_value or {}
        # Clear-ready and hard-required channels dominate ordinary scanning.
        protected = self.must_include | clear_ready
        candidates = channels | protected
        if self.mode is ScanMode.VERIFICATION:
            candidates = protected
        cap = self.early_cap if self.mode is ScanMode.EARLY else self.mid_cap
        ranked = sorted(candidates, key=lambda c: (c not in protected, -channel_value.get(c, 0.0), c))
        selected = ranked if len(protected) > cap else ranked[:cap]
        self.scan_log.append({"mode": self.mode.value, "must_include": sorted(self.must_include), "selected": selected})
        return selected

    def sensing_efficiency(self, value: float, sensing_time_s: float) -> float:
        return float(value) / max(1e-9, float(sensing_time_s))
