from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from q3.geometry import distance
from q3.models import ChannelStatus, Measurement, Point, SourceTrack
from q3.offline_policy import Task
from q3.routing import optimize_open_route
from q4.w1_policy import W1TriangularDetectionPolicy


BEARING_TOTAL_BOUND_DEG = 1.005
REACQUIRE_STEP_M = 5.0
DEFER_AFTER_CONSECUTIVE_FAILURES = 6


class TargetLifecycle(str, Enum):
    ACTIVE = "active"
    REACQUIRE = "reacquire"
    DEFERRED = "deferred"
    RESOLVED = "resolved"


@dataclass
class NoSignalObservation:
    position: Point
    virtual_time_s: float
    role: str


@dataclass
class Q4TargetState:
    lifecycle: TargetLifecycle = TargetLifecycle.ACTIVE
    first_found_time_s: float | None = None
    no_signal_observations: list[NoSignalObservation] = field(default_factory=list)
    reacquisition_attempts: int = 0
    reacquisition_successes: int = 0
    consecutive_reacquisition_failures: int = 0
    probe_cursor: int = 0
    deferred_count: int = 0
    resume_after_search_count: int = 0
    clear_failures: int = 0
    failed_clear_measure_count: int | None = None


def _probe_angle_offsets() -> tuple[float, ...]:
    offsets: list[float] = [0.0, -BEARING_TOTAL_BOUND_DEG, BEARING_TOTAL_BOUND_DEG]
    for angle in (3.0, 6.0, 10.0, 15.0, 25.0, 40.0, 60.0, 90.0, 120.0, 150.0, 180.0):
        offsets.append(-angle)
        if angle != 180.0:
            offsets.append(angle)
    return tuple(offsets)


REACQUIRE_ANGLE_OFFSETS_DEG = _probe_angle_offsets()


class W2PersistentDirectionalPolicy(W1TriangularDetectionPolicy):
    """W2: W1 discovery geometry plus a persistent Q4 target lifecycle.

    The policy-facing runner remains the restricted API proxy. No simulator case,
    source position, source type, receive radius, or directional orientation is
    available here.
    """

    variant = "w2"

    def __init__(self, runner: Any):
        super().__init__(runner)
        self.max_steps = 20_000
        self.target_states = {channel: Q4TargetState() for channel in self.tracks}
        self.completed_search_count = 0
        self._measure_role = "unknown"
        self._active_search_index = None
        self._selected_decisions = {}
        self._wait_assignments = {}
        self.termination_reason = "not_started"

    def run(self) -> None:
        self.client.enter()
        self.termination_reason = "running"
        try:
            for _ in range(self.max_steps):
                self.update_unknown_state()
                if self.done_w2():
                    self.termination_reason = "all_resolved"
                    return

                tasks = self.build_dynamic_tasks()
                if not tasks:
                    unresolved = self.unresolved_channels()
                    if unresolved:
                        for channel in unresolved:
                            state = self.target_states[channel]
                            state.lifecycle = TargetLifecycle.REACQUIRE
                        self.emit("w2_stalled_reactivated", channels=unresolved)
                        tasks = self.build_dynamic_tasks()
                    if not tasks:
                        self.termination_reason = "stalled_without_task"
                        return

                next_task = optimize_open_route(self.client.current_position, tasks)[0]
                self.execute_task(next_task)

            self.termination_reason = "max_steps"
        finally:
            self.update_unknown_state()
            self.emit_exit_state()
            self.client.exit()

    def done_w2(self) -> bool:
        discovery_complete = not self.remaining_search_indices
        if not discovery_complete:
            return False
        if self.unresolved_channels():
            return False
        return all(
            track.status in {ChannelStatus.CLEARED, ChannelStatus.ABSENT}
            for track in self.tracks.values()
        )

    def unresolved_channels(self) -> list[int]:
        return sorted(
            track.channel
            for track in self.tracks.values()
            if track.status == ChannelStatus.FOUND
        )

    def update_unknown_state(self) -> None:
        # Sixteen confirmed channels exhaust the simulator's documented source
        # upper bound, so the unfinished backbone is no longer needed for discovery.
        if self.discovered_count() >= 16:
            self.remaining_search_indices.clear()
        if not self.remaining_search_indices:
            for track in self.tracks.values():
                if track.status == ChannelStatus.UNKNOWN:
                    track.status = ChannelStatus.ABSENT

    def ready_clear_tasks(self) -> list[Task]:
        tasks: list[Task] = []
        for track in self.tracks.values():
            if track.status != ChannelStatus.FOUND:
                continue
            state = self.target_states[track.channel]
            # Direction-aware local pursuit terminates on `near`. Rebuilding a
            # polygon from hundreds of almost-collinear 5m bearings at every
            # step adds CPU cost without improving lifecycle correctness.
            if state.lifecycle in {TargetLifecycle.REACQUIRE, TargetLifecycle.DEFERRED}:
                continue
            circle = self.localization_circle(track)
            if circle is None or circle.radius > 20.0:
                continue
            if state.failed_clear_measure_count == len(track.direction_measurements):
                continue
            tasks.append(Task("clear", track.channel, circle.center))
        return tasks

    def build_dynamic_tasks(self) -> list[Task]:
        self._wait_assignments = {}
        self._selected_decisions = {}

        search_tasks: list[Task] = []
        if self.discovered_count() < 16:
            for index in sorted(self.remaining_search_indices):
                if self.channels_to_scan_search_point(index):
                    search_tasks.append(Task("search", 0, self.search_points[index], search_index=index))

        clear_tasks = self.ready_clear_tasks()
        clear_channels = {task.channel for task in clear_tasks}
        selected_tasks = search_tasks + clear_tasks

        reacquire_tasks: list[Task] = []
        normal_candidates: dict[int, Task] = {}
        for track in self.tracks.values():
            if track.status != ChannelStatus.FOUND or track.channel in clear_channels:
                continue
            state = self.target_states[track.channel]
            if state.lifecycle == TargetLifecycle.DEFERRED and self.remaining_search_indices:
                continue
            if state.lifecycle in {TargetLifecycle.REACQUIRE, TargetLifecycle.DEFERRED}:
                point = self.reacquisition_point(track, state)
                if point is not None:
                    reacquire_tasks.append(Task("reacquire", track.channel, point))
                continue
            point = self.localization_candidate(track)
            if point is not None:
                normal_candidates[track.channel] = Task("measure", track.channel, point)

        # Reacquisition is an explicit high-priority lifecycle action. Concurrent
        # CLEAR/reacquisition tasks still use the frozen router; normal localization
        # and SEARCH resume after success or deferral.
        if reacquire_tasks:
            return clear_tasks + reacquire_tasks

        provisional = selected_tasks + list(normal_candidates.values())
        for channel, base_task in normal_candidates.items():
            track = self.tracks[channel]
            region, circle = self.localization_state(track)
            if not region or circle is None:
                selected_tasks.append(base_task)
                continue
            context = [
                task
                for task in provisional
                if not (task.kind == "measure" and task.channel == channel)
            ]
            decision = self.route_aware_decision(track, region, base_task.point, context)
            self._selected_decisions[channel] = decision
            if decision.selected.search_index is not None:
                self._wait_assignments[channel] = decision.selected.search_index
            else:
                selected_tasks.append(Task("measure", channel, decision.selected.point))
        return selected_tasks

    def channels_to_scan_search_point(self, search_index: int) -> list[int]:
        point = self.search_points[search_index]
        channels: list[int] = []
        for channel, track in self.tracks.items():
            if track.status == ChannelStatus.UNKNOWN and self.discovered_count() < 16:
                channels.append(channel)
                continue
            if track.status != ChannelStatus.FOUND:
                continue
            state = self.target_states[channel]
            attempted = any(
                distance(point, observation.position) <= 1e-6
                for observation in state.no_signal_observations
            ) or any(
                distance(point, measurement.position) <= 1e-6
                for measurement in track.measurements
            )
            if not attempted:
                channels.append(channel)
        if search_index % 2 == 1:
            channels.reverse()
        return channels

    def execute_task(self, task: Task) -> None:
        if task.kind == "search":
            if task.search_index is not None:
                self.execute_search_task(task.search_index)
            return
        track = self.tracks[task.channel]
        if track.status == ChannelStatus.CLEARED:
            return
        if task.kind == "clear":
            self.clear_track(track, task.point)
            return
        self._measure_role = "reacquire" if task.kind == "reacquire" else "supplement"
        try:
            self.measure_channel(task.point, task.channel)
        finally:
            self._measure_role = "unknown"

    def execute_search_task(self, search_index: int) -> None:
        point = self.search_points[search_index]
        self._active_search_index = search_index
        try:
            for channel in self.channels_to_scan_search_point(search_index):
                track = self.tracks[channel]
                if track.status == ChannelStatus.UNKNOWN and self.discovered_count() >= 16:
                    continue
                if track.status in {ChannelStatus.CLEARED, ChannelStatus.ABSENT}:
                    continue
                state = self.target_states[channel]
                if track.status == ChannelStatus.FOUND and state.lifecycle in {
                    TargetLifecycle.REACQUIRE,
                    TargetLifecycle.DEFERRED,
                }:
                    self._measure_role = "search_reacquire"
                elif track.status == ChannelStatus.FOUND:
                    self._measure_role = "search_supplement"
                else:
                    self._measure_role = "search_discovery"
                self.measure_channel(point, channel)
        finally:
            self._measure_role = "unknown"
            self._active_search_index = None

        self.remaining_search_indices.discard(search_index)
        self.completed_search_count += 1
        for channel, state in self.target_states.items():
            if (
                state.lifecycle == TargetLifecycle.DEFERRED
                and self.completed_search_count >= state.resume_after_search_count
                and self.tracks[channel].status == ChannelStatus.FOUND
            ):
                state.lifecycle = TargetLifecycle.REACQUIRE
                state.consecutive_reacquisition_failures = 0
                self.emit("w2_target_reactivated", channel=channel, search_index=search_index)

    def reacquisition_point(self, track: SourceTrack, state: Q4TargetState) -> Point | None:
        directions = track.direction_measurements
        if not directions:
            return None
        anchor = directions[-1]
        cycle, offset_index = divmod(state.probe_cursor, len(REACQUIRE_ANGLE_OFFSETS_DEG))
        step = max(0.5, REACQUIRE_STEP_M / (cycle + 1.0))
        angle = math.radians(float(anchor.svd_deg) + REACQUIRE_ANGLE_OFFSETS_DEG[offset_index])
        return Point(
            anchor.position.x + step * math.cos(angle),
            anchor.position.y + step * math.sin(angle),
        )

    def measure_channel(self, point: Point, channel: int) -> None:
        track = self.tracks[channel]
        if track.status in {ChannelStatus.CLEARED, ChannelStatus.ABSENT}:
            return
        state = self.target_states[channel]
        status_before = track.status
        direction_count_before = len(track.direction_measurements)
        lifecycle_before = state.lifecycle
        is_reacquisition = (
            status_before == ChannelStatus.FOUND
            and self._measure_role in {"reacquire", "search_reacquire"}
        )
        if is_reacquisition:
            state.reacquisition_attempts += 1

        response = self.client.measure(point, channel)
        result = response["measure_result"]
        virtual_time_s = float(response["virtual_time_s"])
        svd = float(response["svd_deg"]) if result == "direction" else None

        if result == "no_signal":
            if status_before == ChannelStatus.FOUND:
                state.no_signal_observations.append(
                    NoSignalObservation(point, virtual_time_s, self._measure_role)
                )
                if self._measure_role == "reacquire":
                    state.probe_cursor += 1
                if is_reacquisition:
                    state.consecutive_reacquisition_failures += 1
                state.lifecycle = TargetLifecycle.REACQUIRE
                self.emit(
                    "w2_no_signal_after_found",
                    channel=channel,
                    time_s=virtual_time_s,
                    x=point.x,
                    y=point.y,
                    role=self._measure_role,
                    no_signal_count=len(state.no_signal_observations),
                )
                self.maybe_defer_target(channel)
            return

        measurement = Measurement(point, channel, result, svd, virtual_time_s)
        track.add_measurement(measurement)
        if status_before == ChannelStatus.UNKNOWN:
            state.first_found_time_s = virtual_time_s
            state.lifecycle = TargetLifecycle.ACTIVE
            self.emit(
                "w2_target_discovered",
                channel=channel,
                time_s=virtual_time_s,
                x=point.x,
                y=point.y,
                result=result,
            )
        elif is_reacquisition:
            state.reacquisition_successes += 1
            state.consecutive_reacquisition_failures = 0
            state.probe_cursor = 0
            state.lifecycle = TargetLifecycle.REACQUIRE
            self.emit(
                "w2_reacquisition_success",
                channel=channel,
                time_s=virtual_time_s,
                x=point.x,
                y=point.y,
                result=result,
            )

        if result == "near":
            self.clear_track(track, point)
            return

        circle = (
            self.localization_circle(track)
            if state.lifecycle == TargetLifecycle.ACTIVE
            else None
        )
        self.emit(
            "w2_direction_update",
            channel=channel,
            time_s=virtual_time_s,
            x=point.x,
            y=point.y,
            svd_deg=svd,
            role=self._measure_role,
            direction_count_before=direction_count_before,
            direction_count_after=len(track.direction_measurements),
            mec_radius_m=None if circle is None else circle.radius,
            lifecycle_before=lifecycle_before.value,
            lifecycle_after=state.lifecycle.value,
        )

    def maybe_defer_target(self, channel: int) -> None:
        state = self.target_states[channel]
        if state.consecutive_reacquisition_failures < DEFER_AFTER_CONSECUTIVE_FAILURES:
            return
        if not self.remaining_search_indices:
            return
        state.lifecycle = TargetLifecycle.DEFERRED
        state.deferred_count += 1
        state.resume_after_search_count = self.completed_search_count + 1
        self.emit(
            "w2_target_deferred",
            channel=channel,
            deferred_count=state.deferred_count,
            resume_after_search_count=state.resume_after_search_count,
        )

    def clear_track(self, track: SourceTrack, point: Point) -> bool:
        state = self.target_states[track.channel]
        success = super().clear_track(track, point)
        if success:
            state.lifecycle = TargetLifecycle.RESOLVED
            state.failed_clear_measure_count = None
            self.emit(
                "w2_target_resolved",
                channel=track.channel,
                time_s=self.client.last_virtual_time_s,
                x=point.x,
                y=point.y,
            )
        else:
            state.clear_failures += 1
            state.failed_clear_measure_count = len(track.direction_measurements)
            state.lifecycle = TargetLifecycle.REACQUIRE
            self.emit(
                "w2_clear_failed_persist",
                channel=track.channel,
                time_s=self.client.last_virtual_time_s,
                x=point.x,
                y=point.y,
                clear_failures=state.clear_failures,
            )
        return success

    def emit_exit_state(self) -> None:
        unresolved = self.unresolved_channels()
        self.emit(
            "w2_exit_state",
            termination_reason=self.termination_reason,
            completed_search_points=self.completed_search_count,
            remaining_search_points=len(self.remaining_search_indices),
            unresolved_channels=unresolved,
            number_discovered=self.discovered_count(),
            number_cleared=sum(
                track.status == ChannelStatus.CLEARED for track in self.tracks.values()
            ),
            reacquisition_attempts=sum(
                state.reacquisition_attempts for state in self.target_states.values()
            ),
            reacquisition_successes=sum(
                state.reacquisition_successes for state in self.target_states.values()
            ),
            no_signal_after_found=sum(
                len(state.no_signal_observations) for state in self.target_states.values()
            ),
            ever_deferred_targets=sum(
                state.deferred_count > 0 for state in self.target_states.values()
            ),
        )

    def emit_exit_state(self) -> None:
        unresolved = self.unresolved_channels()
        discovered = sorted(
            channel
            for channel, state in self.target_states.items()
            if state.first_found_time_s is not None
        )
        self.emit(
            "w2_exit_state",
            termination_reason=self.termination_reason,
            completed_search_points=self.completed_search_count,
            remaining_search_points=len(self.remaining_search_indices),
            number_discovered=len(discovered),
            number_cleared=sum(track.status == ChannelStatus.CLEARED for track in self.tracks.values()),
            unresolved_channels=unresolved,
            deferred_channels=sorted(
                channel
                for channel, state in self.target_states.items()
                if state.lifecycle == TargetLifecycle.DEFERRED
            ),
            reacquisition_attempts=sum(state.reacquisition_attempts for state in self.target_states.values()),
            reacquisition_successes=sum(state.reacquisition_successes for state in self.target_states.values()),
            no_signal_after_found=sum(len(state.no_signal_observations) for state in self.target_states.values()),
            ever_deferred_targets=sum(state.deferred_count > 0 for state in self.target_states.values()),
        )


def policy_w2(runner: Any) -> None:
    W2PersistentDirectionalPolicy(runner).run()
