"""Q4 Final Frozen Policy: W6-25PFR.

25-Point Symmetric Search with Persistent Feasible-Region Clearing
(25点对称搜索与持续可行域清除策略).  The implementation keeps one source of
truth for the final Q4 policy; W0--W5 remain historical development labels.
"""
from __future__ import annotations

import math
from typing import Any

from q3.models import ChannelStatus, Point, SourceTrack
from q3.offline_policy import Task
from q4.w5_policy import W5SymmetricDetectionPolicy
from q4.w6_feasible_region import BearingObservation, FeasibleRegion, persistent_bearing_region

CERTIFICATE_RADIUS_M = 20.0
FINAL_STRATEGY_NAME = "W6-25PFR"
PAPER_STRATEGY_NAME = "25-Point Symmetric Search with Persistent Feasible-Region Clearing"
FINAL_GEOMETRY_POINT_COUNT = 25
FINAL_GEOMETRY_SIDE_M = 970.0
FINAL_GEOMETRY_CAP_EXTENSION_M = 140.0


class W6PersistentBearingPolicy(W5SymmetricDetectionPolicy):
    """W5 plus a conservative direction-only clear certificate."""

    variant = "w6_persistent_bearing"

    def __init__(self, runner: Any):
        super().__init__(runner)
        self.variant = "w6_persistent_bearing"
        self.w6_regions: dict[int, FeasibleRegion] = {}
        self.w6_ready_channels: set[int] = set()
        self.w6_attempted_channels: set[int] = set()
        self.guaranteed_clear_attempts = 0
        self.guaranteed_clear_successes = 0
        self.guaranteed_clear_failures = 0

    def _region(self, track: SourceTrack) -> FeasibleRegion:
        observations = [
            BearingObservation(m.position, float(m.svd_deg))
            for m in track.direction_measurements
            if m.svd_deg is not None and math.isfinite(float(m.svd_deg))
        ]
        return persistent_bearing_region(observations)

    def _refresh_certificate(self, track: SourceTrack) -> FeasibleRegion:
        region = self._region(track)
        self.w6_regions[track.channel] = region
        ready = (
            track.status == ChannelStatus.FOUND
            and region.valid
            and math.isfinite(region.mec.radius)
            and region.mec.radius <= CERTIFICATE_RADIUS_M
        )
        if ready:
            self.w6_ready_channels.add(track.channel)
            self.emit(
                "w6_guaranteed_clear_ready",
                channel=track.channel,
                time_s=self.client.last_virtual_time_s,
                mec_radius_m=region.mec.radius,
                center_x=region.mec.center.x,
                center_y=region.mec.center.y,
                direction_count=len(track.direction_measurements),
            )
        else:
            self.w6_ready_channels.discard(track.channel)
        return region

    def measure_channel(self, point: Point, channel: int) -> None:
        track = self.tracks[channel]
        before = len(track.direction_measurements)
        super().measure_channel(point, channel)
        if track.status == ChannelStatus.CLEARED:
            self.w6_ready_channels.discard(channel)
            return
        if len(track.direction_measurements) != before:
            self._refresh_certificate(track)

    def ready_clear_tasks(self) -> list[Task]:
        ordinary = super().ready_clear_tasks()
        output: list[Task] = []
        ordinary_certified = set()
        for task in ordinary:
            if task.channel in self.w6_ready_channels:
                ordinary_certified.add(task.channel)
            else:
                output.append(task)
        for channel in sorted(self.w6_ready_channels):
            track = self.tracks[channel]
            region = self.w6_regions.get(channel)
            if (
                track.status != ChannelStatus.FOUND
                or region is None
                or not region.valid
                or region.mec.radius > CERTIFICATE_RADIUS_M
                or channel in self.w6_attempted_channels
            ):
                continue
            output.append(Task("clear", channel, region.mec.center))
        return output

    def execute_task(self, task: Task) -> None:
        if task.kind == "clear" and task.channel in self.w6_ready_channels:
            self.guaranteed_clear_attempts += 1
            self.w6_attempted_channels.add(task.channel)
            self.emit(
                "w6_guaranteed_clear_attempt",
                channel=task.channel,
                time_s=self.client.last_virtual_time_s,
                x=task.point.x,
                y=task.point.y,
            )
        super().execute_task(task)

    def clear_track(self, track: SourceTrack, point: Point) -> bool:
        was_guaranteed = track.channel in self.w6_attempted_channels
        success = super().clear_track(track, point)
        if not was_guaranteed:
            return success
        if success:
            self.guaranteed_clear_successes += 1
            self.w6_ready_channels.discard(track.channel)
            self.w6_regions.pop(track.channel, None)
            self.emit("w6_guaranteed_clear_success", channel=track.channel, time_s=self.client.last_virtual_time_s)
        else:
            self.guaranteed_clear_failures += 1
            self.w6_ready_channels.discard(track.channel)
            self.w6_regions.pop(track.channel, None)
            self.emit("w6_guaranteed_clear_fail", channel=track.channel, time_s=self.client.last_virtual_time_s)
        return success

    def emit_exit_state(self) -> None:
        super().emit_exit_state()
        self.emit(
            "w6_exit_state",
            guaranteed_clear_attempts=self.guaranteed_clear_attempts,
            guaranteed_clear_successes=self.guaranteed_clear_successes,
            guaranteed_clear_failures=self.guaranteed_clear_failures,
            certificate_ready_channels=sorted(self.w6_ready_channels),
        )


def policy_w6(runner: Any) -> None:
    W6PersistentBearingPolicy(runner).run()
