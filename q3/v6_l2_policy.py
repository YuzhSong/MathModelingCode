from __future__ import annotations

import copy
import math
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from .geometry import Circle, clip_bearing_wedge, distance, minimum_enclosing_circle
from .models import ChannelStatus, Measurement, Point, SourceTrack
from .offline_policy import Task
from .routing import optimize_open_route
from .v5_prediction import _fallback_point
from .v6_policy import (
    RouteAwareCandidate,
    RouteAwareDecision,
    RouteAwareSupplementPolicy,
)


@dataclass(frozen=True)
class HypotheticalState:
    """Policy-visible state used only by the depth-2 evaluator."""

    tracks: dict[int, SourceTrack]
    remaining_search_indices: frozenset[int]
    position: Point
    current_channel: int


@dataclass(frozen=True)
class FrozenV6Plan:
    tasks: tuple[Task, ...]
    decisions: dict[int, RouteAwareDecision]
    wait_assignments: dict[int, int]
    search_channels: dict[int, tuple[int, ...]]


@dataclass(frozen=True)
class MeasurementOutcome:
    result: str
    svd_deg: float | None
    weight: int
    after_region: tuple[Point, ...] | None = None
    after_circle: Circle | None = None


@dataclass(frozen=True)
class L2Candidate:
    base: RouteAwareCandidate
    q2_s: float
    expected_second_action_s: float
    first_outcome_count: int


@dataclass(frozen=True)
class L2Decision:
    selected: L2Candidate
    v6_selected: RouteAwareCandidate
    highest_p_clear: RouteAwareCandidate

    @property
    def changed_from_v6(self) -> bool:
        return distance(self.selected.base.point, self.v6_selected.point) > 1e-6


class Depth2RouteAwareSupplementPolicy(RouteAwareSupplementPolicy):
    """V6-L2: lazy depth-2 rollout at the next executable supplement decision.

    The frozen V6 task pool remains the planning scaffold. Because the online
    policy executes only the first routed task before replanning, L2 evaluation
    is deferred until a supplement is on that executable frontier. Every first
    candidate is then expanded over the same fixed feasible-region samples and
    bearing-error outcomes used by V6.
    """

    variant = "v6l2"

    def __init__(self, runner: Any, n: int = 8, *, lookahead_depth: int = 2):
        super().__init__(runner, n=n)
        if lookahead_depth not in {1, 2}:
            raise ValueError("V6-L2 supports only lookahead_depth=1 or 2")
        self.lookahead_depth = lookahead_depth
        self._terminal_cache: dict[tuple, float] = {}
        self._source_terminal_cache: dict[tuple, float] = {}
        self._second_cache: dict[tuple, float] = {}
        self._outcome_cache: dict[tuple, tuple[MeasurementOutcome, ...]] = {}
        self._selected_l2_decisions: dict[int, L2Decision] = {}
        self._rollout_stats = Counter()

    @staticmethod
    def _measurement_key(measurement: Measurement) -> tuple:
        return (
            round(measurement.position.x, 6),
            round(measurement.position.y, 6),
            measurement.result,
            None if measurement.svd_deg is None else round(measurement.svd_deg, 6),
        )

    def _state_key(self, state: HypotheticalState) -> tuple:
        return (
            round(state.position.x, 6),
            round(state.position.y, 6),
            state.current_channel,
            tuple(sorted(state.remaining_search_indices)),
            tuple(
                (
                    channel,
                    track.status.value,
                    tuple(self._measurement_key(item) for item in track.measurements),
                )
                for channel, track in sorted(state.tracks.items())
            ),
        )

    def _current_channel(self) -> int:
        value = getattr(self.client.runner, "current_channel", 1)
        return int(value)

    def _current_state(self) -> HypotheticalState:
        return HypotheticalState(
            tracks=copy.deepcopy(self.tracks),
            remaining_search_indices=frozenset(self.remaining_search_indices),
            position=self.client.current_position,
            current_channel=self._current_channel(),
        )

    @staticmethod
    def _discovered_count(state: HypotheticalState) -> int:
        return sum(
            track.status in {ChannelStatus.FOUND, ChannelStatus.CLEARED}
            for track in state.tracks.values()
        )

    def _normalize_state(self, state: HypotheticalState) -> HypotheticalState:
        remaining = set(state.remaining_search_indices)
        if self._discovered_count(state) >= 16:
            remaining.clear()
        tracks = state.tracks
        if not remaining and any(track.status == ChannelStatus.UNKNOWN for track in tracks.values()):
            tracks = copy.deepcopy(tracks)
            for track in tracks.values():
                if track.status == ChannelStatus.UNKNOWN:
                    track.status = ChannelStatus.ABSENT
        return HypotheticalState(
            tracks=tracks,
            remaining_search_indices=frozenset(remaining),
            position=state.position,
            current_channel=state.current_channel,
        )

    @contextmanager
    def _use_state(self, state: HypotheticalState) -> Iterator[None]:
        saved_tracks = self.tracks
        saved_remaining = self.remaining_search_indices
        saved_position = self.client.current_position
        saved_decisions = self._selected_decisions
        saved_waits = self._wait_assignments
        self.tracks = state.tracks
        self.remaining_search_indices = set(state.remaining_search_indices)
        self.client.current_position = state.position
        self._selected_decisions = {}
        self._wait_assignments = {}
        try:
            yield
        finally:
            self.tracks = saved_tracks
            self.remaining_search_indices = saved_remaining
            self.client.current_position = saved_position
            self._selected_decisions = saved_decisions
            self._wait_assignments = saved_waits

    def _plan_key(self, plan: FrozenV6Plan) -> tuple:
        return (
            tuple(self._task_key(task) for task in plan.tasks),
            tuple(
                (
                    channel,
                    self._task_key(Task("measure", channel, decision.selected.point)),
                    round(decision.selected.expected_future_cost_s, 6),
                )
                for channel, decision in sorted(plan.decisions.items())
            ),
            tuple(sorted(plan.wait_assignments.items())),
            tuple(sorted(plan.search_channels.items())),
        )

    def _updated_plan(
        self,
        state: HypotheticalState,
        plan: FrozenV6Plan,
        changed_channel: int,
    ) -> FrozenV6Plan:
        """Rebuild the changed source task, then reroute the complete task pool.

        Other sources retain their frozen V6 candidate because their feasible
        regions did not change. Their tasks still participate in every route
        evaluation, while the observed source is regenerated from its new MEC.
        """
        remaining = set(state.remaining_search_indices)
        tasks = [
            task
            for task in plan.tasks
            if task.search_index is None or task.search_index in remaining
        ]
        tasks = [
            task
            for task in tasks
            if not (
                task.channel == changed_channel
                and task.kind in {"measure", "clear"}
            )
        ]
        decisions = dict(plan.decisions)
        decisions.pop(changed_channel, None)
        waits = {
            channel: search_index
            for channel, search_index in plan.wait_assignments.items()
            if channel != changed_channel and search_index in remaining
        }
        search_channels = {
            search_index: tuple(channel for channel in channels if channel != changed_channel)
            for search_index, channels in plan.search_channels.items()
            if search_index in remaining
        }

        track = state.tracks[changed_channel]
        if track.status != ChannelStatus.FOUND:
            return FrozenV6Plan(tuple(tasks), decisions, waits, search_channels)
        region, circle = self.localization_state(track)
        if not region or circle is None:
            return FrozenV6Plan(tuple(tasks), decisions, waits, search_channels)
        if circle.radius <= 20.0:
            tasks.append(Task("clear", changed_channel, circle.center))
            return FrozenV6Plan(tuple(tasks), decisions, waits, search_channels)

        with self._use_state(state):
            fallback = _fallback_point(
                track.direction_measurements,
                region,
                circle,
                state.position,
                self.prediction_config,
            )
            base = self.route_aware_candidate(track, region, fallback, tasks)
            decision = RouteAwareDecision(base, base)
        decisions[changed_channel] = decision
        if decision.selected.search_index is not None:
            waits[changed_channel] = decision.selected.search_index
        else:
            tasks.append(Task("measure", changed_channel, decision.selected.point))
        for search_index in search_channels:
            point = self.search_points[search_index]
            include = self.found_scan_has_value(track, point) or waits.get(changed_channel) == search_index
            channels = set(search_channels[search_index])
            if include:
                channels.add(changed_channel)
            ordered = sorted(channels, reverse=bool(search_index % 2 == 1))
            search_channels[search_index] = tuple(ordered)
        return FrozenV6Plan(tuple(tasks), decisions, waits, search_channels)

    def _search_channels(
        self,
        state: HypotheticalState,
        plan: FrozenV6Plan,
        search_index: int,
    ) -> list[int]:
        return list(plan.search_channels.get(search_index, ()))

    @staticmethod
    def _switch_count(current_channel: int, channels: list[int]) -> tuple[int, int]:
        switches = 0
        active = current_channel
        for channel in channels:
            if channel != active:
                switches += 1
            active = channel
        return switches, active

    def _measurement_outcomes(
        self,
        track: SourceTrack,
        region: list[Point],
        candidate: Point,
    ) -> tuple[MeasurementOutcome, ...]:
        key = (
            track.channel,
            self._track_key(track),
            round(candidate.x, 6),
            round(candidate.y, 6),
        )
        cached = self._outcome_cache.get(key)
        if cached is not None:
            return cached

        counts: Counter[tuple[str, float | None]] = Counter()
        geometry: dict[tuple[str, float | None], tuple[tuple[Point, ...] | None, Circle | None]] = {}
        for possible_source in self.samples_for(track, region):
            if distance(candidate, possible_source) <= 5.0:
                counts[("near", None)] += len(self.prediction_config.bearing_error_offsets_deg)
                continue
            true_bearing = math.degrees(
                math.atan2(possible_source.y - candidate.y, possible_source.x - candidate.x)
            ) % 360.0
            for error_deg in self.prediction_config.bearing_error_offsets_deg:
                reported = round((true_bearing + error_deg) % 360.0, 2)
                after_region = clip_bearing_wedge(region, candidate, reported)
                if after_region:
                    outcome_key = ("direction", reported)
                    counts[outcome_key] += 1
                    if outcome_key not in geometry:
                        geometry[outcome_key] = (
                            tuple(after_region),
                            minimum_enclosing_circle(after_region),
                        )

        outcomes = tuple(
            MeasurementOutcome(
                result,
                bearing,
                weight,
                geometry.get((result, bearing), (None, None))[0],
                geometry.get((result, bearing), (None, None))[1],
            )
            for (result, bearing), weight in sorted(
                counts.items(), key=lambda item: (item[0][0], -1.0 if item[0][1] is None else item[0][1])
            )
        )
        self._outcome_cache[key] = outcomes
        return outcomes

    def _after_measurement(
        self,
        state: HypotheticalState,
        channel: int,
        point: Point,
        outcome: MeasurementOutcome,
    ) -> HypotheticalState:
        tracks = dict(state.tracks)
        track = copy.deepcopy(tracks[channel])
        track.add_measurement(
            Measurement(point, channel, outcome.result, outcome.svd_deg, None)
        )
        if outcome.result == "near":
            track.status = ChannelStatus.CLEARED
            track.clear_position = point
        elif outcome.after_region is not None and outcome.after_circle is not None:
            track.localization_cache_key = tuple(
                (item.position.x, item.position.y, item.svd_deg)
                for item in track.direction_measurements
            )
            track.localization_region_cache = list(outcome.after_region)
            track.localization_circle_cache = outcome.after_circle
        tracks[channel] = track
        return self._normalize_state(
            HypotheticalState(
                tracks=tracks,
                remaining_search_indices=state.remaining_search_indices,
                position=point,
                current_channel=channel,
            )
        )

    def _after_clear(self, state: HypotheticalState, task: Task) -> HypotheticalState:
        tracks = dict(state.tracks)
        track = copy.deepcopy(tracks[task.channel])
        track.status = ChannelStatus.CLEARED
        track.clear_position = task.point
        tracks[task.channel] = track
        return self._normalize_state(
            HypotheticalState(
                tracks=tracks,
                remaining_search_indices=state.remaining_search_indices,
                position=task.point,
                current_channel=state.current_channel,
            )
        )

    def _after_search(
        self,
        state: HypotheticalState,
        task: Task,
        final_channel: int,
    ) -> HypotheticalState:
        remaining = set(state.remaining_search_indices)
        if task.search_index is not None:
            remaining.discard(task.search_index)
        return self._normalize_state(
            HypotheticalState(
                tracks=state.tracks,
                remaining_search_indices=frozenset(remaining),
                position=task.point,
                current_channel=final_channel,
            )
        )

    def _terminal_v6_value(
        self,
        state: HypotheticalState,
        plan: FrozenV6Plan,
    ) -> float:
        state = self._normalize_state(state)
        # Once a complete frozen task pool has been built, its routed travel and
        # service estimate depends on the start pose/channel and the plan, not on
        # unreferenced track geometry. This lets all second-step bearing outcomes
        # share the same global-route terminal computation.
        key = (
            round(state.position.x, 6),
            round(state.position.y, 6),
            state.current_channel,
            self._plan_key(plan),
        )
        cached = self._terminal_cache.get(key)
        if cached is not None:
            self._rollout_stats["terminal_cache_hit"] += 1
            return cached
        self._rollout_stats["terminal_cache_miss"] += 1
        if not plan.tasks:
            self._terminal_cache[key] = 0.0
            return 0.0

        ordered = optimize_open_route(state.position, list(plan.tasks))
        current = state.position
        current_channel = state.current_channel
        travel_s = 0.0
        service_s = 0.0
        for task in ordered:
            travel_s += distance(current, task.point) / self.prediction_config.robot_speed_mps
            current = task.point
            if task.kind == "clear":
                service_s += self.prediction_config.clear_time_s
            elif task.kind == "measure":
                if task.channel != current_channel:
                    service_s += 1.0
                service_s += self.prediction_config.measure_time_s
                current_channel = task.channel
            elif task.kind == "search" and task.search_index is not None:
                channels = self._search_channels(state, plan, task.search_index)
                switches, current_channel = self._switch_count(current_channel, channels)
                service_s += switches + self.prediction_config.measure_time_s * len(channels)

        future_s = sum(
            decision.selected.expected_future_cost_s
            for decision in plan.decisions.values()
        )
        value = travel_s + service_s + future_s
        self._terminal_cache[key] = value
        return value

    def _source_v6_terminal(self, state: HypotheticalState, channel: int) -> float:
        """Frozen V6/V5 source-local heuristic used after the second outcome."""
        key = (self._state_key(state), channel)
        cached = self._source_terminal_cache.get(key)
        if cached is not None:
            return cached
        track = state.tracks[channel]
        if track.status in {ChannelStatus.CLEARED, ChannelStatus.ABSENT}:
            value = 0.0
        else:
            region, circle = self.localization_state(track)
            if not region or circle is None:
                value = float("inf")
            elif circle.radius <= 20.0:
                value = (
                    distance(state.position, circle.center)
                    / self.prediction_config.robot_speed_mps
                    + self.prediction_config.clear_time_s
                )
            else:
                fallback = _fallback_point(
                    track.direction_measurements,
                    region,
                    circle,
                    state.position,
                    self.prediction_config,
                )
                value = (
                    distance(state.position, fallback)
                    / self.prediction_config.robot_speed_mps
                    + self.prediction_config.measure_time_s
                    + distance(fallback, circle.center)
                    / self.prediction_config.robot_speed_mps
                    + self.prediction_config.clear_time_s
                )
        self._source_terminal_cache[key] = value
        return value

    def _terminal_after_second_measure(
        self,
        state: HypotheticalState,
        plan: FrozenV6Plan,
        channel: int,
    ) -> float:
        reduced = FrozenV6Plan(
            tasks=tuple(
                task
                for task in plan.tasks
                if not (
                    task.channel == channel
                    and task.kind in {"measure", "clear"}
                )
            ),
            decisions={
                key: decision
                for key, decision in plan.decisions.items()
                if key != channel
            },
            wait_assignments={
                key: search_index
                for key, search_index in plan.wait_assignments.items()
                if key != channel
            },
            search_channels={
                search_index: tuple(item for item in channels if item != channel)
                for search_index, channels in plan.search_channels.items()
            },
        )
        return self._terminal_v6_value(state, reduced) + self._source_v6_terminal(state, channel)

    def _second_action_value(
        self,
        state: HypotheticalState,
        plan: FrozenV6Plan,
    ) -> float:
        state = self._normalize_state(state)
        key = (self._state_key(state), self._plan_key(plan))
        cached = self._second_cache.get(key)
        if cached is not None:
            self._rollout_stats["second_cache_hit"] += 1
            return cached
        self._rollout_stats["second_cache_miss"] += 1
        if not plan.tasks:
            self._second_cache[key] = 0.0
            return 0.0

        task = optimize_open_route(state.position, list(plan.tasks))[0]
        move_s = distance(state.position, task.point) / self.prediction_config.robot_speed_mps
        if task.kind == "clear":
            value = move_s + self.prediction_config.clear_time_s
            next_state = self._after_clear(state, task)
            next_plan = self._updated_plan(next_state, plan, task.channel)
            value += self._terminal_v6_value(next_state, next_plan)
        elif task.kind == "search":
            if task.search_index is None:
                value = self._terminal_v6_value(state, plan)
            else:
                channels = self._search_channels(state, plan, task.search_index)
                switches, final_channel = self._switch_count(state.current_channel, channels)
                service_s = switches + self.prediction_config.measure_time_s * len(channels)
                next_state = self._after_search(state, task, final_channel)
                next_plan = FrozenV6Plan(
                    tasks=tuple(
                        item
                        for item in plan.tasks
                        if not (
                            item.kind == "search"
                            and item.search_index == task.search_index
                        )
                    ),
                    decisions=dict(plan.decisions),
                    wait_assignments={
                        channel: search_index
                        for channel, search_index in plan.wait_assignments.items()
                        if search_index != task.search_index
                    },
                    search_channels={
                        search_index: channels
                        for search_index, channels in plan.search_channels.items()
                        if search_index != task.search_index
                    },
                )
                value = move_s + service_s + self._terminal_v6_value(next_state, next_plan)
        else:
            decision = plan.decisions.get(task.channel)
            if decision is None:
                value = float("inf")
            else:
                switch_s = 1.0 if task.channel != state.current_channel else 0.0
                reduced = FrozenV6Plan(
                    tasks=tuple(
                        item
                        for item in plan.tasks
                        if not (
                            item.channel == task.channel
                            and item.kind in {"measure", "clear"}
                        )
                    ),
                    decisions={
                        key: item
                        for key, item in plan.decisions.items()
                        if key != task.channel
                    },
                    wait_assignments={
                        key: search_index
                        for key, search_index in plan.wait_assignments.items()
                        if key != task.channel
                    },
                    search_channels={
                        search_index: tuple(
                            channel for channel in channels if channel != task.channel
                        )
                        for search_index, channels in plan.search_channels.items()
                    },
                )
                after_move = HypotheticalState(
                    tracks=state.tracks,
                    remaining_search_indices=state.remaining_search_indices,
                    position=task.point,
                    current_channel=task.channel,
                )
                # predict_candidate already performs the identical fixed-sample
                # o2 expansion. Since the reduced global-plan terminal is
                # independent of o2, linearity of expectation lets us collapse
                # 36 repeated router calls without changing the Q2 value.
                expected = (
                    self._terminal_v6_value(after_move, reduced)
                    + decision.selected.expected_future_cost_s
                )
                value = (
                    move_s
                    + switch_s
                    + self.prediction_config.measure_time_s
                    + expected
                )
        self._second_cache[key] = value
        return value

    def _l2_candidate(
        self,
        state: HypotheticalState,
        track: SourceTrack,
        region: list[Point],
        point: Point,
        context_tasks: list[Task],
        plan: FrozenV6Plan,
    ) -> L2Candidate:
        base = self.route_aware_candidate(track, region, point, context_tasks)
        outcomes = self._measurement_outcomes(track, region, point)
        if not outcomes:
            return L2Candidate(base, float("inf"), float("inf"), 0)
        total_weight = sum(outcome.weight for outcome in outcomes)
        expected_second = 0.0
        for outcome in outcomes:
            next_state = self._after_measurement(state, track.channel, point, outcome)
            next_plan = self._updated_plan(next_state, plan, track.channel)
            near_clear_s = self.prediction_config.clear_time_s if outcome.result == "near" else 0.0
            expected_second += outcome.weight * (
                near_clear_s + self._second_action_value(next_state, next_plan)
            )
        expected_second /= total_weight
        q2 = (
            base.route_marginal_s
            + self.prediction_config.measure_time_s
            + expected_second
        )
        self._rollout_stats["first_candidates"] += 1
        self._rollout_stats["first_outcomes"] += total_weight
        return L2Candidate(base, q2, expected_second, total_weight)

    def _l2_decision(
        self,
        channel: int,
        tasks: list[Task],
    ) -> L2Decision | None:
        track = self.tracks[channel]
        region, circle = self.localization_state(track)
        if not region or circle is None:
            return None
        v4_point = self.localization_candidate(track)
        if v4_point is None:
            return None
        context = [
            task
            for task in tasks
            if not (task.kind == "measure" and task.channel == channel)
        ]
        state = self._current_state()
        plan = FrozenV6Plan(
            tasks=tuple(tasks),
            decisions=dict(self._selected_decisions),
            wait_assignments=dict(self._wait_assignments),
            search_channels={
                task.search_index: tuple(
                    RouteAwareSupplementPolicy.channels_to_scan_search_point(
                        self,
                        task.search_index,
                    )
                )
                for task in tasks
                if task.kind == "search" and task.search_index is not None
            },
        )
        estimates = [
            self._l2_candidate(state, track, region, point, context, plan)
            for point in self.candidate_points(track, region, v4_point)
        ]
        selected = min(
            estimates,
            key=lambda item: (item.q2_s, item.base.objective_s, -item.base.p_clear),
        )
        frozen = self._selected_decisions.get(channel)
        if frozen is None:
            frozen = self.route_aware_decision(track, region, v4_point, context)
        highest = max(estimates, key=lambda item: (item.base.p_clear, -item.base.objective_s)).base
        return L2Decision(selected, frozen.selected, highest)

    def _apply_l2_decision(
        self,
        tasks: list[Task],
        channel: int,
        decision: L2Decision,
    ) -> list[Task]:
        updated = [
            task
            for task in tasks
            if not (task.kind == "measure" and task.channel == channel)
        ]
        self._wait_assignments.pop(channel, None)
        base = decision.selected.base
        self._selected_decisions[channel] = RouteAwareDecision(base, decision.highest_p_clear)
        self._selected_l2_decisions[channel] = decision
        if base.search_index is not None:
            self._wait_assignments[channel] = base.search_index
        else:
            updated.append(Task("measure", channel, base.point))
        return updated

    def build_dynamic_tasks(self) -> list[Task]:
        tasks = RouteAwareSupplementPolicy.build_dynamic_tasks(self)
        self._selected_l2_decisions = {}
        if self.lookahead_depth == 1 or not tasks:
            return tasks

        scored: set[int] = set()
        for _ in range(len(self.tracks) + 1):
            ordered = optimize_open_route(self.client.current_position, tasks)
            if not ordered:
                break
            next_task = ordered[0]
            frontier: list[int] = []
            if next_task.kind == "measure":
                frontier.append(next_task.channel)
            elif next_task.kind == "search" and next_task.search_index is not None:
                frontier.extend(
                    channel
                    for channel, search_index in self._wait_assignments.items()
                    if search_index == next_task.search_index
                )
            frontier = [
                channel
                for channel in sorted(set(frontier))
                if channel not in scored and self.tracks[channel].status == ChannelStatus.FOUND
            ]
            if not frontier:
                break
            for channel in frontier:
                decision = self._l2_decision(channel, tasks)
                scored.add(channel)
                if decision is not None:
                    tasks = self._apply_l2_decision(tasks, channel, decision)
        return tasks

    def measure_channel(self, point: Point, channel: int) -> None:
        status_before = self.tracks[channel].status
        decision = self._selected_l2_decisions.get(channel)
        super().measure_channel(point, channel)
        if (
            status_before != ChannelStatus.FOUND
            or decision is None
            or distance(point, decision.selected.base.point) > 1e-6
        ):
            return
        self.emit(
            "l2_supplement_execution",
            channel=channel,
            time_s=self.client.last_virtual_time_s,
            selected_x=decision.selected.base.point.x,
            selected_y=decision.selected.base.point.y,
            selected_search_index=decision.selected.base.search_index,
            selected_q2_s=decision.selected.q2_s,
            selected_v6_objective_s=decision.selected.base.objective_s,
            selected_p_clear=decision.selected.base.p_clear,
            expected_second_action_s=decision.selected.expected_second_action_s,
            first_outcome_count=decision.selected.first_outcome_count,
            v6_selected_x=decision.v6_selected.point.x,
            v6_selected_y=decision.v6_selected.point.y,
            v6_selected_objective_s=decision.v6_selected.objective_s,
            changed_from_v6=decision.changed_from_v6,
            rollout_first_candidates=self._rollout_stats["first_candidates"],
            rollout_terminal_cache_hits=self._rollout_stats["terminal_cache_hit"],
            rollout_terminal_cache_misses=self._rollout_stats["terminal_cache_miss"],
        )


def policy_v6_l2(runner: Any, n: int = 8) -> None:
    Depth2RouteAwareSupplementPolicy(runner, n=n, lookahead_depth=2).run()


def policy_v6_l1(runner: Any, n: int = 8) -> None:
    """Regression hook: depth disabled must execute frozen V6 exactly."""
    Depth2RouteAwareSupplementPolicy(runner, n=n, lookahead_depth=1).run()
