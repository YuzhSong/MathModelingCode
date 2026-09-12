from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

from .geometry import clip_bearing_wedge, distance, max_distance_to_vertices, minimum_enclosing_circle
from .models import ChannelStatus, Point, SourceTrack
from .offline_policy import Task
from .v5_prediction import CandidatePrediction, V5PredictionConfig
from .v6_policy import RouteAwareCandidate, RouteAwareDecision, RouteAwareSupplementPolicy


WAY3_NEAR_FIELD_RADIUS_M = 85.0
MIN_RECEIVE_RADIUS_M = 1000.0


@dataclass(frozen=True)
class Stage2Candidate(RouteAwareCandidate):
    family: str
    worst_mec_after_m: float
    stage2_objective_s: float


@dataclass(frozen=True)
class Stage2Decision:
    selected: Stage2Candidate
    highest_p_clear: Stage2Candidate
    v6_selected: Stage2Candidate

    @property
    def abandoned_high_p_clear(self) -> bool:
        return self.selected.p_clear + 1e-12 < self.highest_p_clear.p_clear


def _point_key(point: Point) -> tuple[int, int]:
    return round(point.x * 1_000_000), round(point.y * 1_000_000)


def _deduplicate(points: Iterable[tuple[Point, str]]) -> list[tuple[Point, str]]:
    output: list[tuple[Point, str]] = []
    seen: set[tuple[int, int]] = set()
    for point, family in points:
        key = _point_key(point)
        if key in seen:
            continue
        seen.add(key)
        output.append((point, family))
    return output


class Stage2SupplementPolicy(RouteAwareSupplementPolicy):
    """Independent V6-derived policy used only for controlled stage-2 ablations."""

    variant = "stage2"
    minimax_mode = "none"
    minimax_beta_s_per_m = 0.0
    near_field_enabled = False
    large_angle_enabled = False

    def __init__(
        self,
        runner: Any,
        n: int = 8,
        prediction_config: V5PredictionConfig | None = None,
    ):
        super().__init__(runner, n=n, prediction_config=prediction_config)
        self._worst_cache: dict[tuple, float] = {}

    def difficult_source(self, track: SourceTrack) -> bool:
        circle = self.localization_circle(track)
        return bool(
            circle is not None
            and math.isfinite(circle.radius)
            and circle.radius > 20.0
            and len(track.direction_measurements) >= 2
        )

    def near_field_candidates(self, track: SourceTrack) -> list[Point]:
        circle = self.localization_circle(track)
        if circle is None:
            return []
        return [
            Point(
                circle.center.x + WAY3_NEAR_FIELD_RADIUS_M * math.cos(math.radians(45.0 * index)),
                circle.center.y + WAY3_NEAR_FIELD_RADIUS_M * math.sin(math.radians(45.0 * index)),
            )
            for index in range(8)
        ]

    def large_angle_candidates(self, track: SourceTrack) -> list[Point]:
        circle = self.localization_circle(track)
        if circle is None or not track.direction_measurements:
            return []
        latest = track.direction_measurements[-1].position
        vx = circle.center.x - latest.x
        vy = circle.center.y - latest.y
        norm = math.hypot(vx, vy)
        if norm <= 1e-9:
            return []
        px, py = -vy / norm, vx / norm
        output: list[Point] = []
        for radius in self.prediction_config.candidate_radii_m:
            for sign in (-1.0, 1.0):
                output.append(
                    Point(
                        circle.center.x + sign * radius * px,
                        circle.center.y + sign * radius * py,
                    )
                )
        return output

    def candidate_points_with_family(
        self,
        track: SourceTrack,
        region: list[Point],
        v4_point: Point,
    ) -> list[tuple[Point, str]]:
        base = [(point, "v6") for point in super().candidate_points(track, region, v4_point)]
        if not self.difficult_source(track):
            return base

        expanded = list(base)
        if self.near_field_enabled:
            expanded.extend((point, "near_field_85m") for point in self.near_field_candidates(track))
        if self.large_angle_enabled:
            expanded.extend((point, "large_angle_perpendicular") for point in self.large_angle_candidates(track))

        eligible: list[tuple[Point, str]] = []
        for point, family in _deduplicate(expanded):
            if max_distance_to_vertices(point, region) > self.prediction_config.guaranteed_receive_distance_m:
                continue
            if any(
                distance(point, measurement.position) < self.prediction_config.repeat_distance_m
                for measurement in track.direction_measurements
            ):
                continue
            eligible.append((point, family))
        return eligible or base

    def worst_mec_after(
        self,
        track: SourceTrack,
        region: list[Point],
        candidate: Point,
    ) -> float:
        key = (
            track.channel,
            self._track_key(track),
            round(candidate.x, 6),
            round(candidate.y, 6),
        )
        cached = self._worst_cache.get(key)
        if cached is not None:
            return cached

        samples = self.samples_for(track, region)
        residuals: list[float] = []
        no_signal_samples = [
            point
            for point in samples
            if distance(candidate, point) > MIN_RECEIVE_RADIUS_M
        ]
        if no_signal_samples:
            residuals.append(minimum_enclosing_circle(no_signal_samples).radius)

        for possible_source in samples:
            if distance(candidate, possible_source) <= 5.0:
                residuals.append(5.0)
                continue
            true_bearing = math.degrees(
                math.atan2(possible_source.y - candidate.y, possible_source.x - candidate.x)
            ) % 360.0
            for error_deg in self.prediction_config.bearing_error_offsets_deg:
                reported = round((true_bearing + error_deg) % 360.0, 2)
                after_region = clip_bearing_wedge(region, candidate, reported)
                if after_region:
                    residuals.append(minimum_enclosing_circle(after_region).radius)

        worst = max(residuals, default=float("inf"))
        self._worst_cache[key] = worst
        return worst

    def stage2_candidate(
        self,
        track: SourceTrack,
        region: list[Point],
        point: Point,
        family: str,
        context_tasks: list[Task],
    ) -> Stage2Candidate:
        prediction: CandidatePrediction = self.geometry_prediction(track, region, point)
        c_before = self.route_travel_time(self.client.current_position, context_tasks)
        c_with = self.route_travel_time(
            self.client.current_position,
            context_tasks + [Task("measure", track.channel, point)],
        )
        route_marginal = max(0.0, c_with - c_before)
        v6_objective = (
            route_marginal
            + self.prediction_config.measure_time_s
            + prediction.expected_remaining_time_s
        )
        worst = (
            self.worst_mec_after(track, region, point)
            if self.minimax_mode != "none"
            else prediction.expected_mec_after_m
        )
        if self.minimax_mode == "pure":
            stage2_objective = worst
        elif self.minimax_mode == "weighted":
            stage2_objective = v6_objective + self.minimax_beta_s_per_m * worst
        else:
            stage2_objective = v6_objective
        return Stage2Candidate(
            point=point,
            search_index=self.search_index_for_point(point),
            p_clear=prediction.p_clear,
            expected_mec_after_m=prediction.expected_mec_after_m,
            route_marginal_s=route_marginal,
            c_before_s=c_before,
            c_with_s=c_with,
            expected_future_cost_s=prediction.expected_remaining_time_s,
            objective_s=v6_objective,
            family=family,
            worst_mec_after_m=worst,
            stage2_objective_s=stage2_objective,
        )

    def route_aware_decision(
        self,
        track: SourceTrack,
        region: list[Point],
        v4_point: Point,
        context_tasks: list[Task],
    ) -> Stage2Decision:
        estimates = [
            self.stage2_candidate(track, region, point, family, context_tasks)
            for point, family in self.candidate_points_with_family(track, region, v4_point)
        ]
        selected = min(
            estimates,
            key=lambda item: (item.stage2_objective_s, item.objective_s, -item.p_clear),
        )
        highest = max(estimates, key=lambda item: (item.p_clear, -item.objective_s))
        v6_selected = min(estimates, key=lambda item: (item.objective_s, -item.p_clear))
        return Stage2Decision(selected, highest, v6_selected)

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
        self.emit(
            "stage2_supplement_execution",
            channel=channel,
            time_s=self.client.last_virtual_time_s,
            selected_family=selected.family,
            selected_worst_mec_after_m=selected.worst_mec_after_m,
            selected_stage2_objective_s=selected.stage2_objective_s,
            selected_v6_objective_s=selected.objective_s,
            v6_selected_x=decision.v6_selected.point.x,
            v6_selected_y=decision.v6_selected.point.y,
            v6_selected_family=decision.v6_selected.family,
            v6_selected_worst_mec_after_m=decision.v6_selected.worst_mec_after_m,
            v6_selected_objective_s=decision.v6_selected.objective_s,
            changed_from_v6=bool(distance(selected.point, decision.v6_selected.point) > 1e-6),
            minimax_mode=self.minimax_mode,
            minimax_beta_s_per_m=self.minimax_beta_s_per_m,
        )


class MinimaxOnlyPolicy(Stage2SupplementPolicy):
    variant = "m1"
    minimax_mode = "pure"


class MinimaxRoutePolicy(Stage2SupplementPolicy):
    variant = "m2"
    minimax_mode = "weighted"

    def __init__(
        self,
        runner: Any,
        n: int = 8,
        prediction_config: V5PredictionConfig | None = None,
        beta_s_per_m: float = 0.25,
    ):
        super().__init__(runner, n=n, prediction_config=prediction_config)
        if beta_s_per_m < 0.0:
            raise ValueError("beta_s_per_m must be non-negative")
        self.minimax_beta_s_per_m = float(beta_s_per_m)
        self.variant = f"m2_b{str(beta_s_per_m).replace('.', 'p')}"


class NearFieldPolicy(Stage2SupplementPolicy):
    variant = "n1"
    near_field_enabled = True


class LargeAnglePolicy(Stage2SupplementPolicy):
    variant = "n2"
    large_angle_enabled = True


class NearFieldLargeAnglePolicy(Stage2SupplementPolicy):
    variant = "n3"
    near_field_enabled = True
    large_angle_enabled = True


class MinimaxNearFieldPolicy(MinimaxRoutePolicy):
    variant = "mn"
    near_field_enabled = True

    def __init__(
        self,
        runner: Any,
        n: int = 8,
        prediction_config: V5PredictionConfig | None = None,
        beta_s_per_m: float = 0.10,
    ):
        super().__init__(
            runner,
            n=n,
            prediction_config=prediction_config,
            beta_s_per_m=beta_s_per_m,
        )
        self.variant = "mn"


class V6AuditPolicy(RouteAwareSupplementPolicy):
    """Behavior-identical V6 with extra policy-visible SEARCH/detour diagnostics."""

    variant = "v6audit"

    def __init__(
        self,
        runner: Any,
        n: int = 8,
        prediction_config: V5PredictionConfig | None = None,
    ):
        super().__init__(runner, n=n, prediction_config=prediction_config)
        self._audit_context: dict[int, dict[str, Any]] = {}

    def build_dynamic_tasks(self) -> list[Task]:
        self._audit_context = {}
        return super().build_dynamic_tasks()

    def route_aware_decision(
        self,
        track: SourceTrack,
        region: list[Point],
        v4_point: Point,
        context_tasks: list[Task],
    ) -> RouteAwareDecision:
        decision = super().route_aware_decision(track, region, v4_point, context_tasks)
        remaining = [self.search_points[index] for index in sorted(self.remaining_search_indices)]
        legal_search = [
            point
            for point in remaining
            if max_distance_to_vertices(point, region)
            <= self.prediction_config.guaranteed_receive_distance_m
            and not any(
                distance(point, measurement.position) < self.prediction_config.repeat_distance_m
                for measurement in track.direction_measurements
            )
        ]
        best_future_search = min(
            (
                self.route_aware_candidate(track, region, point, context_tasks)
                for point in legal_search
            ),
            key=lambda item: item.objective_s,
            default=None,
        )
        self._audit_context[track.channel] = {
            "remaining_search_count": len(remaining),
            "legal_future_search_count": len(legal_search),
            "nearest_future_search_to_selected_m": min(
                (distance(decision.selected.point, point) for point in remaining),
                default=None,
            ),
            "best_future_search_objective_s": None if best_future_search is None else best_future_search.objective_s,
            "best_future_search_route_marginal_s": (
                None if best_future_search is None else best_future_search.route_marginal_s
            ),
            "best_future_search_p_clear": None if best_future_search is None else best_future_search.p_clear,
        }
        return decision

    def measure_channel(self, point: Point, channel: int) -> None:
        status_before = self.tracks[channel].status
        decision = self._selected_decisions.get(channel)
        context = self._audit_context.get(channel)
        super().measure_channel(point, channel)
        if (
            status_before != ChannelStatus.FOUND
            or decision is None
            or context is None
            or distance(point, decision.selected.point) > 1e-6
        ):
            return
        dedicated = decision.selected.search_index is None
        self.emit(
            "v6_decision_audit",
            channel=channel,
            time_s=self.client.last_virtual_time_s,
            selected_is_dedicated=dedicated,
            selected_route_marginal_s=decision.selected.route_marginal_s,
            selected_p_clear=decision.selected.p_clear,
            selected_objective_s=decision.selected.objective_s,
            **context,
        )


def policy_m1(runner: Any, n: int = 8) -> None:
    MinimaxOnlyPolicy(runner, n=n).run()


def make_policy_m2(beta_s_per_m: float):
    def policy(runner: Any, n: int = 8) -> None:
        MinimaxRoutePolicy(runner, n=n, beta_s_per_m=beta_s_per_m).run()

    return policy


def policy_n1(runner: Any, n: int = 8) -> None:
    NearFieldPolicy(runner, n=n).run()


def policy_n2(runner: Any, n: int = 8) -> None:
    LargeAnglePolicy(runner, n=n).run()


def policy_n3(runner: Any, n: int = 8) -> None:
    NearFieldLargeAnglePolicy(runner, n=n).run()


def policy_v6_audit(runner: Any, n: int = 8) -> None:
    V6AuditPolicy(runner, n=n).run()


def policy_mn(runner: Any, n: int = 8) -> None:
    MinimaxNearFieldPolicy(runner, n=n, beta_s_per_m=0.10).run()
