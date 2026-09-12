from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from q3.geometry import Circle, distance
from q3.models import ChannelStatus, Point, SourceTrack
from q3.offline_policy import Task
from q4.w2_policy import (
    BEARING_TOTAL_BOUND_DEG,
    REACQUIRE_ANGLE_OFFSETS_DEG,
    REACQUIRE_STEP_M,
    TargetLifecycle,
    W2PersistentDirectionalPolicy,
)


COARSE_INITIAL_STEP_M = 500.0
COARSE_MAX_STEP_M = 600.0
COARSE_MIN_STEP_M = 5.0
COARSE_PRIMARY_OFFSETS_DEG = (0.0, -BEARING_TOTAL_BOUND_DEG, BEARING_TOTAL_BOUND_DEG)
MEC_CHECK_LIMIT = 32


@dataclass
class W3LocalState:
    step_m: float = COARSE_INITIAL_STEP_M
    offset_index: int = 0
    last_success_bearing_deg: float | None = None
    successful_coarse_steps: int = 0
    failed_coarse_probes: int = 0
    intersection_pending: bool = False
    intersection_attempts: int = 0
    fallback_active: bool = False
    mec_checks: int = 0
    clear_measure_count: int | None = None
    clear_circle: Circle | None = None


@dataclass(frozen=True)
class W3ProbePlan:
    point: Point
    kind: str
    step_m: float
    angle_offset_deg: float | None


def angular_difference_deg(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


class W3CoarseToFinePolicy(W2PersistentDirectionalPolicy):
    """W3 candidates: faster local reacquisition with W2 as the safety fallback."""

    def __init__(self, runner: Any, mode: str = "adaptive"):
        if mode not in {"fixed", "adaptive", "intersection"}:
            raise ValueError(f"unknown W3 mode: {mode}")
        super().__init__(runner)
        self.mode = mode
        self.variant = f"w3_{mode}"
        self.local_states = {channel: W3LocalState() for channel in self.tracks}
        self._probe_plans: dict[int, W3ProbePlan] = {}

    def _adaptive_step(self, track: SourceTrack, local: W3LocalState) -> float:
        if local.fallback_active:
            return REACQUIRE_STEP_M
        region, _ = self.localization_state(track)
        anchor = track.direction_measurements[-1]
        bearing = math.radians(float(anchor.svd_deg))
        ux, uy = math.cos(bearing), math.sin(bearing)
        positive = [
            (point.x - anchor.position.x) * ux + (point.y - anchor.position.y) * uy
            for point in region
        ]
        positive = [value for value in positive if value > 0.0]
        if not positive:
            return max(COARSE_MIN_STEP_M, min(local.step_m, COARSE_MAX_STEP_M))
        upper = max(positive)
        midpoint_step = 0.5 * upper
        return max(COARSE_MIN_STEP_M, min(COARSE_MAX_STEP_M, midpoint_step, local.step_m))

    def _intersection_point(self, track: SourceTrack) -> Point | None:
        candidate = self.localization_candidate(track)
        if candidate is None:
            return None
        state = self.target_states[track.channel]
        if any(distance(candidate, obs.position) <= 1e-6 for obs in state.no_signal_observations):
            anchor = track.direction_measurements[-1]
            bearing = math.radians(float(anchor.svd_deg))
            dx = candidate.x - anchor.position.x
            dy = candidate.y - anchor.position.y
            parallel = dx * math.cos(bearing) + dy * math.sin(bearing)
            lateral = -dx * math.sin(bearing) + dy * math.cos(bearing)
            reflected = Point(
                anchor.position.x + parallel * math.cos(bearing) + lateral * math.sin(bearing),
                anchor.position.y + parallel * math.sin(bearing) - lateral * math.cos(bearing),
            )
            if any(distance(reflected, obs.position) <= 1e-6 for obs in state.no_signal_observations):
                return None
            candidate = reflected
        return candidate

    def reacquisition_point(self, track: SourceTrack, state: Any) -> Point | None:
        directions = track.direction_measurements
        if not directions:
            return None
        local = self.local_states[track.channel]

        if self.mode == "intersection" and local.intersection_pending and not local.fallback_active:
            point = self._intersection_point(track)
            if point is not None:
                plan = W3ProbePlan(point, "intersection", distance(directions[-1].position, point), None)
                self._probe_plans[track.channel] = plan
                return point
            local.intersection_pending = False

        if local.fallback_active:
            cycle, offset_index = divmod(state.probe_cursor, len(REACQUIRE_ANGLE_OFFSETS_DEG))
            step = max(0.5, REACQUIRE_STEP_M / (cycle + 1.0))
            offset = REACQUIRE_ANGLE_OFFSETS_DEG[offset_index]
            kind = "w2_fallback"
        else:
            step = local.step_m if self.mode == "fixed" else self._adaptive_step(track, local)
            offset = COARSE_PRIMARY_OFFSETS_DEG[local.offset_index]
            kind = "coarse"

        anchor = directions[-1]
        angle = math.radians(float(anchor.svd_deg) + offset)
        point = Point(
            anchor.position.x + step * math.cos(angle),
            anchor.position.y + step * math.sin(angle),
        )
        self._probe_plans[track.channel] = W3ProbePlan(point, kind, step, offset)
        return point

    def _on_probe_failure(self, channel: int, plan: W3ProbePlan) -> None:
        local = self.local_states[channel]
        if plan.kind == "intersection":
            local.intersection_pending = False
            local.intersection_attempts += 1
            local.step_m = max(COARSE_MIN_STEP_M, local.step_m * 0.5)
            return
        if plan.kind == "w2_fallback":
            return
        local.failed_coarse_probes += 1
        local.offset_index += 1
        if local.offset_index >= len(COARSE_PRIMARY_OFFSETS_DEG):
            local.offset_index = 0
            local.step_m = max(COARSE_MIN_STEP_M, plan.step_m * 0.5)
        if local.step_m <= COARSE_MIN_STEP_M + 1e-9:
            local.fallback_active = True

    def _on_probe_success(
        self,
        track: SourceTrack,
        plan: W3ProbePlan,
        previous_bearing_deg: float | None,
    ) -> None:
        local = self.local_states[track.channel]
        new_bearing = float(track.direction_measurements[-1].svd_deg)
        reversed_direction = (
            previous_bearing_deg is not None
            and angular_difference_deg(new_bearing, previous_bearing_deg) > 90.0
        )
        if plan.kind == "intersection":
            local.intersection_attempts += 1
            local.intersection_pending = False
            local.step_m = max(COARSE_MIN_STEP_M, min(local.step_m, plan.step_m) * 0.5)
        elif plan.kind == "coarse":
            local.successful_coarse_steps += 1
            local.offset_index = 0
            local.step_m = plan.step_m
            if reversed_direction:
                local.step_m = max(COARSE_MIN_STEP_M, plan.step_m * 0.5)
            if self.mode == "intersection" and len(track.direction_measurements) >= 2:
                local.intersection_pending = True
        local.last_success_bearing_deg = new_bearing

        if local.mec_checks >= MEC_CHECK_LIMIT or local.fallback_active:
            return
        local.mec_checks += 1
        circle = self.localization_circle(track)
        if circle is not None and circle.radius <= 20.0:
            local.clear_measure_count = len(track.direction_measurements)
            local.clear_circle = circle

    def measure_channel(self, point: Point, channel: int) -> None:
        track = self.tracks[channel]
        direction_count_before = len(track.direction_measurements)
        no_signal_before = len(self.target_states[channel].no_signal_observations)
        status_before = track.status
        previous_bearing = (
            float(track.direction_measurements[-1].svd_deg)
            if track.direction_measurements
            else None
        )
        role = self._measure_role
        plan = self._probe_plans.get(channel)

        super().measure_channel(point, channel)

        if status_before == ChannelStatus.FOUND and role == "reacquire" and plan is not None:
            direction_success = len(track.direction_measurements) > direction_count_before
            no_signal = len(self.target_states[channel].no_signal_observations) > no_signal_before
            if direction_success:
                self._on_probe_success(track, plan, previous_bearing)
            elif no_signal:
                self._on_probe_failure(channel, plan)
            self.emit(
                "w3_probe_outcome",
                channel=channel,
                time_s=self.client.last_virtual_time_s,
                mode=self.mode,
                kind=plan.kind,
                x=plan.point.x,
                y=plan.point.y,
                step_m=plan.step_m,
                angle_offset_deg=plan.angle_offset_deg,
                result=("direction" if direction_success else "no_signal" if no_signal else "near_or_clear"),
                next_step_m=self.local_states[channel].step_m,
                fallback_active=self.local_states[channel].fallback_active,
            )

    def ready_clear_tasks(self) -> list[Task]:
        tasks = super().ready_clear_tasks()
        present = {task.channel for task in tasks}
        for track in self.tracks.values():
            if track.status != ChannelStatus.FOUND or track.channel in present:
                continue
            local = self.local_states[track.channel]
            if (
                local.clear_circle is not None
                and local.clear_measure_count == len(track.direction_measurements)
                and self.target_states[track.channel].failed_clear_measure_count
                != len(track.direction_measurements)
            ):
                tasks.append(Task("clear", track.channel, local.clear_circle.center))
        return tasks

    def clear_track(self, track: SourceTrack, point: Point) -> bool:
        success = super().clear_track(track, point)
        if not success:
            local = self.local_states[track.channel]
            local.clear_circle = None
            local.clear_measure_count = None
            local.fallback_active = True
        return success

    def emit_exit_state(self) -> None:
        super().emit_exit_state()
        self.emit(
            "w3_exit_state",
            mode=self.mode,
            coarse_successes=sum(state.successful_coarse_steps for state in self.local_states.values()),
            coarse_failures=sum(state.failed_coarse_probes for state in self.local_states.values()),
            intersection_attempts=sum(state.intersection_attempts for state in self.local_states.values()),
            fallback_targets=sum(state.fallback_active for state in self.local_states.values()),
            mec_checks=sum(state.mec_checks for state in self.local_states.values()),
        )


def policy_w3_fixed(runner: Any) -> None:
    W3CoarseToFinePolicy(runner, mode="fixed").run()


def policy_w3_adaptive(runner: Any) -> None:
    W3CoarseToFinePolicy(runner, mode="adaptive").run()


def policy_w3_intersection(runner: Any) -> None:
    W3CoarseToFinePolicy(runner, mode="intersection").run()


def policy_w3(runner: Any) -> None:
    """Selected W3 entry point; updated only after controlled pilot comparison."""

    policy_w3_adaptive(runner)
