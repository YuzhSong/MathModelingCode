from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .geometry import distance, max_distance_to_vertices
from .models import ChannelStatus, Point, SourceTrack
from .offline_policy import OfficialClientRunnerAdapter, Task
from .routing import optimize_open_route
from .v5_policy import DiagnosticDynamicRoutingPolicy
from .v5_prediction import (
    CandidatePrediction,
    V5PredictionConfig,
    eligible_candidates,
    predict_candidate,
    sample_feasible_polygon,
)


@dataclass(frozen=True)
class RouteAwareCandidate:
    point: Point
    search_index: int | None
    p_clear: float
    expected_mec_after_m: float
    route_marginal_s: float
    c_before_s: float
    c_with_s: float
    expected_future_cost_s: float
    objective_s: float


@dataclass(frozen=True)
class RouteAwareDecision:
    selected: RouteAwareCandidate
    highest_p_clear: RouteAwareCandidate

    @property
    def abandoned_high_p_clear(self) -> bool:
        return self.selected.p_clear + 1e-12 < self.highest_p_clear.p_clear


class RouteAwareSupplementPolicy(DiagnosticDynamicRoutingPolicy):
    """V6: route-aware FOUND-source MEASURE task generation on top of V4."""

    variant = "v6"

    def __init__(
        self,
        runner: Any,
        n: int = 8,
        prediction_config: V5PredictionConfig | None = None,
    ):
        super().__init__(runner, n=n)
        self.prediction_config = prediction_config or V5PredictionConfig()
        self._sample_cache: dict[tuple, list[Point]] = {}
        self._prediction_cache: dict[tuple, CandidatePrediction] = {}
        self._route_cache: dict[tuple, float] = {}
        self._selected_decisions: dict[int, RouteAwareDecision] = {}

    @staticmethod
    def _track_key(track: SourceTrack) -> tuple:
        return tuple((m.position.x, m.position.y, m.svd_deg) for m in track.direction_measurements)

    @staticmethod
    def _task_key(task: Task) -> tuple:
        return (
            task.kind,
            task.channel,
            round(task.point.x, 6),
            round(task.point.y, 6),
            task.search_index,
        )

    def route_travel_time(self, start: Point, tasks: list[Task]) -> float:
        key = (
            round(start.x, 6),
            round(start.y, 6),
            tuple(self._task_key(task) for task in tasks),
        )
        cached = self._route_cache.get(key)
        if cached is not None:
            return cached
        ordered = optimize_open_route(start, tasks)
        current = start
        route_m = 0.0
        for task in ordered:
            route_m += distance(current, task.point)
            current = task.point
        route_s = route_m / self.prediction_config.robot_speed_mps
        self._route_cache[key] = route_s
        return route_s

    def samples_for(self, track: SourceTrack, region: list[Point]) -> list[Point]:
        key = (track.channel, self._track_key(track))
        if key not in self._sample_cache:
            seed = (
                self.prediction_config.sample_seed
                + track.channel * 1009
                + len(track.direction_measurements) * 9176
            )
            self._sample_cache[key] = sample_feasible_polygon(
                region,
                self.prediction_config.sample_count,
                seed,
            )
        return self._sample_cache[key]

    def geometry_prediction(
        self,
        track: SourceTrack,
        region: list[Point],
        point: Point,
    ) -> CandidatePrediction:
        key = (
            track.channel,
            self._track_key(track),
            round(point.x, 6),
            round(point.y, 6),
        )
        prediction = self._prediction_cache.get(key)
        if prediction is None:
            prediction = predict_candidate(
                track,
                region,
                point,
                self.client.current_position,
                self.samples_for(track, region),
                self.prediction_config,
                mandatory_search_point=True,
            )
            self._prediction_cache[key] = prediction
        return prediction

    def search_index_for_point(self, point: Point) -> int | None:
        for idx in self.remaining_search_indices:
            if distance(point, self.search_points[idx]) <= 1e-6:
                return idx
        return None

    def candidate_points(
        self,
        track: SourceTrack,
        region: list[Point],
        v4_point: Point,
    ) -> list[Point]:
        circle = self.localization_circle(track)
        if circle is None:
            return [v4_point]
        search_points = tuple(
            self.search_points[idx]
            for idx in sorted(self.remaining_search_indices)
            if max_distance_to_vertices(self.search_points[idx], region)
            <= self.prediction_config.guaranteed_receive_distance_m
            and not any(
                distance(self.search_points[idx], measurement.position)
                < self.prediction_config.repeat_distance_m
                for measurement in track.direction_measurements
            )
        )
        points = eligible_candidates(
            track,
            region,
            circle,
            self.prediction_config,
            extra_points=(v4_point, *search_points),
        )
        if not any(distance(v4_point, point) <= 1e-6 for point in points):
            points.append(v4_point)
        return points

    def route_aware_candidate(
        self,
        track: SourceTrack,
        region: list[Point],
        point: Point,
        context_tasks: list[Task],
    ) -> RouteAwareCandidate:
        prediction = self.geometry_prediction(track, region, point)
        c_before = self.route_travel_time(self.client.current_position, context_tasks)
        candidate_task = Task("measure", track.channel, point)
        c_with = self.route_travel_time(
            self.client.current_position,
            context_tasks + [candidate_task],
        )
        # Exact open-route cost is monotone under task insertion. The clamp only
        # removes negative artifacts caused by the frozen heuristic router.
        route_marginal = max(0.0, c_with - c_before)
        objective = (
            route_marginal
            + self.prediction_config.measure_time_s
            + prediction.expected_remaining_time_s
        )
        return RouteAwareCandidate(
            point=point,
            search_index=self.search_index_for_point(point),
            p_clear=prediction.p_clear,
            expected_mec_after_m=prediction.expected_mec_after_m,
            route_marginal_s=route_marginal,
            c_before_s=c_before,
            c_with_s=c_with,
            expected_future_cost_s=prediction.expected_remaining_time_s,
            objective_s=objective,
        )

    def route_aware_decision(
        self,
        track: SourceTrack,
        region: list[Point],
        v4_point: Point,
        context_tasks: list[Task],
    ) -> RouteAwareDecision:
        estimates = [
            self.route_aware_candidate(track, region, point, context_tasks)
            for point in self.candidate_points(track, region, v4_point)
        ]
        selected = min(estimates, key=lambda item: (item.objective_s, -item.p_clear))
        highest = max(estimates, key=lambda item: (item.p_clear, -item.objective_s))
        return RouteAwareDecision(selected, highest)

    def build_dynamic_tasks(self) -> list[Task]:
        self._wait_assignments = {}
        self._selected_decisions = {}
        search_tasks: list[Task] = []
        if self.discovered_count() < 16:
            for idx in sorted(self.remaining_search_indices):
                point = self.search_points[idx]
                if self.channels_to_scan_search_point(idx):
                    search_tasks.append(Task("search", 0, point, search_index=idx))

        clear_tasks = self.ready_clear_tasks()
        clear_channels = {task.channel for task in clear_tasks}
        v4_measure_tasks: dict[int, Task] = {}
        for track in self.tracks.values():
            if track.status != ChannelStatus.FOUND or track.channel in clear_channels:
                continue
            point = self.localization_candidate(track)
            if point is not None:
                v4_measure_tasks[track.channel] = Task("measure", track.channel, point)

        provisional = search_tasks + clear_tasks + list(v4_measure_tasks.values())
        selected_tasks = search_tasks + clear_tasks
        for channel, v4_task in v4_measure_tasks.items():
            track = self.tracks[channel]
            region, circle = self.localization_state(track)
            if not region or circle is None:
                selected_tasks.append(v4_task)
                continue
            context = [
                task
                for task in provisional
                if not (task.kind == "measure" and task.channel == channel)
            ]
            decision = self.route_aware_decision(track, region, v4_task.point, context)
            self._selected_decisions[channel] = decision
            if decision.selected.search_index is not None:
                self._wait_assignments[channel] = decision.selected.search_index
            else:
                selected_tasks.append(Task("measure", channel, decision.selected.point))
        return selected_tasks

    def channels_to_scan_search_point(self, search_index: int) -> list[int]:
        channels = set(super().channels_to_scan_search_point(search_index))
        channels.update(
            channel
            for channel, assigned_index in self._wait_assignments.items()
            if assigned_index == search_index and self.tracks[channel].status == ChannelStatus.FOUND
        )
        ordered = sorted(channels)
        if search_index % 2 == 1:
            ordered.reverse()
        return ordered

    def measure_channel(self, point: Point, channel: int) -> None:
        status_before = self.tracks[channel].status
        decision = self._selected_decisions.get(channel)
        super().measure_channel(point, channel)
        if (
            status_before != ChannelStatus.FOUND
            or decision is None
            or distance(point, decision.selected.point) > 1e-6
        ):
            return
        selected = decision.selected
        highest = decision.highest_p_clear
        self.emit(
            "route_supplement_execution",
            channel=channel,
            time_s=self.client.last_virtual_time_s,
            selected_x=selected.point.x,
            selected_y=selected.point.y,
            selected_search_index=selected.search_index,
            selected_p_clear=selected.p_clear,
            selected_route_marginal_s=selected.route_marginal_s,
            selected_expected_future_cost_s=selected.expected_future_cost_s,
            selected_objective_s=selected.objective_s,
            highest_p_clear_x=highest.point.x,
            highest_p_clear_y=highest.point.y,
            highest_p_clear=highest.p_clear,
            highest_p_clear_route_marginal_s=highest.route_marginal_s,
            highest_p_clear_objective_s=highest.objective_s,
            abandoned_high_p_clear=decision.abandoned_high_p_clear,
        )


def policy_v6(runner: Any, n: int = 8) -> None:
    RouteAwareSupplementPolicy(runner, n=n).run()


def policy_v6_official(client: Any, n: int = 8) -> RouteAwareSupplementPolicy:
    """Run V6 against the official HTTP client after external practice gating."""
    policy = RouteAwareSupplementPolicy(OfficialClientRunnerAdapter(client), n=n)
    policy.run()
    return policy
