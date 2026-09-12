from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from .geometry import distance, max_distance_to_vertices
from .models import ChannelStatus, Point, SourceTrack
from .offline_policy import DynamicRoutingPolicy, Task
from .v5_prediction import (
    CandidatePrediction,
    V5PredictionConfig,
    eligible_candidates,
    predict_candidate,
    sample_feasible_polygon,
)


def _finite_radius(track: SourceTrack, policy: DynamicRoutingPolicy) -> float | None:
    circle = policy.localization_circle(track)
    if circle is None or not math.isfinite(circle.radius):
        return None
    return circle.radius


class DiagnosticDynamicRoutingPolicy(DynamicRoutingPolicy):
    """V4 behavior with policy-visible source diagnostics only."""

    variant = "v4"

    def __init__(self, runner: Any, n: int = 8):
        super().__init__(runner, n=n)
        self._active_search_index: int | None = None
        self._wait_assignments: dict[int, int] = {}

    def emit(self, event: str, **payload: Any) -> None:
        recorder = getattr(self.client.runner, "record_policy_diagnostic", None)
        if recorder is not None:
            recorder({"event": event, "variant": self.variant, **payload})

    def execute_search_task(self, search_index: int) -> None:
        self._active_search_index = search_index
        try:
            super().execute_search_task(search_index)
        finally:
            self._active_search_index = None

    def measure_channel(self, point: Point, channel: int) -> None:
        track = self.tracks[channel]
        status_before = track.status
        position_before = self.client.current_position
        measurements_before = len(track.measurements)
        mec_before = _finite_radius(track, self) if status_before == ChannelStatus.FOUND else None
        waited_for_search = bool(
            self._active_search_index is not None
            and self._wait_assignments.get(channel) == self._active_search_index
        )

        super().measure_channel(point, channel)

        new_measurement = track.measurements[-1] if len(track.measurements) > measurements_before else None
        result = new_measurement.result if new_measurement is not None else "no_signal"
        measure_time = (
            new_measurement.virtual_time_s
            if new_measurement is not None and new_measurement.virtual_time_s is not None
            else self.client.last_virtual_time_s
        )
        if status_before == ChannelStatus.UNKNOWN and track.status in {ChannelStatus.FOUND, ChannelStatus.CLEARED}:
            self.emit(
                "first_found",
                channel=channel,
                time_s=measure_time,
                x=point.x,
                y=point.y,
                result=result,
            )
        if status_before != ChannelStatus.FOUND:
            return

        mec_after = 0.0 if result == "near" else _finite_radius(track, self)
        self.emit(
            "supplement_measure",
            channel=channel,
            time_s=measure_time,
            x=point.x,
            y=point.y,
            result=result,
            mec_before_m=mec_before,
            mec_after_m=mec_after,
            arrival_move_m=distance(position_before, point),
            at_mandatory_search=bool(self._active_search_index is not None),
            search_index=self._active_search_index,
            waited_for_search=waited_for_search,
            clearable_after=bool(result == "near" or (mec_after is not None and mec_after <= 20.0)),
        )

    def clear_track(self, track: SourceTrack, point: Point) -> bool:
        if track.status == ChannelStatus.CLEARED:
            return True
        position_before = self.client.current_position
        final_mec = _finite_radius(track, self)
        success = super().clear_track(track, point)
        self.emit(
            "clear",
            channel=track.channel,
            time_s=self.client.last_virtual_time_s,
            x=point.x,
            y=point.y,
            result="success" if success else "no_target_in_range",
            final_mec_m=final_mec,
            arrival_move_m=distance(position_before, point),
        )
        return success


class V5TaskGenerationPolicy(DiagnosticDynamicRoutingPolicy):
    """Change only FOUND-source MEASURE task generation; inherit V4 routing."""

    def __init__(
        self,
        runner: Any,
        n: int = 8,
        mode: str = "final",
        prediction_config: V5PredictionConfig | None = None,
    ):
        super().__init__(runner, n=n)
        if mode not in {"a", "b", "final"}:
            raise ValueError(f"unknown V5 mode: {mode}")
        self.mode = mode
        self.variant = f"v5{mode}"
        self.prediction_config = prediction_config or V5PredictionConfig()
        self._sample_cache: dict[tuple, list[Point]] = {}
        self._prediction_cache: dict[tuple, CandidatePrediction] = {}
        self._last_decision_key: dict[int, tuple] = {}

    @staticmethod
    def _track_key(track: SourceTrack) -> tuple:
        return tuple((m.position.x, m.position.y, m.svd_deg) for m in track.direction_measurements)

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

    def prediction(
        self,
        track: SourceTrack,
        region: list[Point],
        point: Point,
        mandatory_search_point: bool,
    ) -> CandidatePrediction:
        cache_key = (
            track.channel,
            self._track_key(track),
            round(point.x, 6),
            round(point.y, 6),
        )
        base = self._prediction_cache.get(cache_key)
        if base is None:
            base = predict_candidate(
                track,
                region,
                point,
                self.client.current_position,
                self.samples_for(track, region),
                self.prediction_config,
                mandatory_search_point=True,
            )
            self._prediction_cache[cache_key] = base
        move_time = 0.0 if mandatory_search_point else distance(self.client.current_position, point) / self.prediction_config.robot_speed_mps
        return replace(
            base,
            expected_total_incremental_time_s=(
                move_time
                + self.prediction_config.measure_time_s
                + base.expected_remaining_time_s
            ),
        )

    def dedicated_prediction(self, track: SourceTrack, region: list[Point], use_v5_candidates: bool) -> CandidatePrediction | None:
        v4_point = self.localization_candidate(track)
        if v4_point is None:
            return None
        points = [v4_point]
        if use_v5_candidates:
            circle = self.localization_circle(track)
            if circle is not None:
                points = eligible_candidates(
                    track,
                    region,
                    circle,
                    self.prediction_config,
                    extra_points=(v4_point,),
                )
        predictions = [self.prediction(track, region, point, False) for point in points]
        if self.mode in {"b", "final"}:
            return max(
                predictions,
                key=lambda item: (item.p_clear, -item.expected_total_incremental_time_s),
                default=None,
            )
        return min(predictions, key=lambda item: item.expected_total_incremental_time_s, default=None)

    def search_prediction(self, track: SourceTrack, region: list[Point]) -> tuple[int, CandidatePrediction] | None:
        candidates: list[tuple[int, CandidatePrediction]] = []
        for idx in sorted(self.remaining_search_indices):
            point = self.search_points[idx]
            if max_distance_to_vertices(point, region) > self.prediction_config.guaranteed_receive_distance_m:
                continue
            if any(distance(point, m.position) < self.prediction_config.repeat_distance_m for m in track.direction_measurements):
                continue
            candidates.append((idx, self.prediction(track, region, point, True)))
        return min(candidates, key=lambda item: item[1].expected_total_incremental_time_s, default=None)

    def measure_task_for(self, track: SourceTrack) -> Task | None:
        region, circle = self.localization_state(track)
        if not region or circle is None:
            return None

        use_v5_candidates = self.mode in {"b", "final"}
        dedicated = self.dedicated_prediction(track, region, use_v5_candidates)
        future_search = self.search_prediction(track, region) if self.mode in {"a", "final"} else None

        choose_wait = bool(
            future_search is not None
            and dedicated is not None
            and future_search[1].expected_total_incremental_time_s
            <= dedicated.expected_total_incremental_time_s
            and (
                self.mode == "a"
                or future_search[1].p_clear >= dedicated.p_clear
            )
        )
        if choose_wait:
            search_index, search_estimate = future_search
            self._wait_assignments[track.channel] = search_index
            selected_kind = "wait_search"
            selected = search_estimate
        else:
            selected_kind = "dedicated"
            selected = dedicated

        decision_key = (
            self._track_key(track),
            selected_kind,
            None if selected is None else round(selected.point.x, 6),
            None if selected is None else round(selected.point.y, 6),
        )
        if self._last_decision_key.get(track.channel) != decision_key:
            self._last_decision_key[track.channel] = decision_key
            self.emit(
                "measure_decision",
                channel=track.channel,
                mode=self.mode,
                selected_kind=selected_kind,
                selected_x=None if selected is None else selected.point.x,
                selected_y=None if selected is None else selected.point.y,
                selected_p_clear=None if selected is None else selected.p_clear,
                selected_expected_mec_m=None if selected is None else selected.expected_mec_after_m,
                selected_expected_total_s=None if selected is None else selected.expected_total_incremental_time_s,
                dedicated_p_clear=None if dedicated is None else dedicated.p_clear,
                dedicated_expected_total_s=None if dedicated is None else dedicated.expected_total_incremental_time_s,
                search_index=None if future_search is None else future_search[0],
                search_p_clear=None if future_search is None else future_search[1].p_clear,
                search_expected_total_s=None if future_search is None else future_search[1].expected_total_incremental_time_s,
            )

        if choose_wait or dedicated is None:
            return None
        return Task("measure", track.channel, dedicated.point)

    def build_dynamic_tasks(self) -> list[Task]:
        self._wait_assignments = {}
        tasks: list[Task] = []
        if self.discovered_count() < 16:
            for idx in sorted(self.remaining_search_indices):
                point = self.search_points[idx]
                if self.channels_to_scan_search_point(idx):
                    tasks.append(Task("search", 0, point, search_index=idx))

        tasks.extend(self.ready_clear_tasks())
        clear_channels = {task.channel for task in tasks if task.kind == "clear"}
        for track in self.tracks.values():
            if track.status != ChannelStatus.FOUND or track.channel in clear_channels:
                continue
            task = self.measure_task_for(track)
            if task is not None:
                tasks.append(task)
        return tasks

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


def policy_v4_diagnostic(runner: Any, n: int = 8) -> None:
    DiagnosticDynamicRoutingPolicy(runner, n=n).run()


def policy_v5a(runner: Any, n: int = 8) -> None:
    V5TaskGenerationPolicy(runner, n=n, mode="a").run()


def policy_v5b(runner: Any, n: int = 8) -> None:
    V5TaskGenerationPolicy(runner, n=n, mode="b").run()


def policy_v5_final(runner: Any, n: int = 8) -> None:
    V5TaskGenerationPolicy(runner, n=n, mode="final").run()
