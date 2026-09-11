from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .api_client import SimulatorTransportError
from .geometry import (
    Circle,
    distance,
    localization_region,
    max_distance_to_vertices,
    minimum_enclosing_circle,
    polygon_centroid,
)
from .logger import JsonlLogger
from .models import ChannelStatus, Measurement, Point, SourceTrack
from .planner import Q3BaselinePlanner, Q3Config
from .routing import optimize_open_route as optimize_dynamic_open_route


ARENA_RADIUS_M = 1800.0
GUARANTEED_RECEIVE_RADIUS_M = 1000.0


def theoretical_outer_radius(n: int) -> float:
    radicand = GUARANTEED_RECEIVE_RADIUS_M**2 - (ARENA_RADIUS_M * math.sin(math.pi / n)) ** 2
    if n < 3 or radicand < 0.0:
        raise ValueError(f"n={n} does not admit guaranteed 1000m ring coverage")
    return ARENA_RADIUS_M * math.cos(math.pi / n) - math.sqrt(radicand)


def theoretical_route_length(n: int) -> float:
    a_n = theoretical_outer_radius(n)
    return a_n + (n - 1) * 2.0 * a_n * math.sin(math.pi / n)


THEORETICAL_HEX_RADIUS_M = theoretical_outer_radius(6)


class OfflineRunnerClient:
    """Adapter from offline_sim EpisodeRunner to the Q3 planner client shape."""

    def __init__(self, runner: Any):
        if hasattr(runner, "case"):
            raise SimulatorTransportError("policy runner exposes ground truth case; use PolicyRunnerProxy")
        self.runner = runner
        self.current_position = Point(0.0, 0.0)
        self.last_virtual_time_s: float | None = None

    def _accepted_response(self, response: dict | None, action: str) -> dict:
        if response is None:
            raise SimulatorTransportError(f"offline runner returned None during {action}")
        if "virtual_time_s" in response:
            self.last_virtual_time_s = float(response["virtual_time_s"])
        return response

    def enter(self) -> dict:
        response = self._accepted_response(self.runner.enter(), "enter")
        self.current_position = Point(0.0, 0.0)
        return response

    def measure(self, position: Point, channel: int) -> dict:
        response = self._accepted_response(self.runner.measure(position.x, position.y, int(channel)), "measure")
        result = response.get("measure_result")
        if result not in {"direction", "near", "no_signal"}:
            raise SimulatorTransportError(f"unexpected offline measure_result: {response}")
        if result == "direction" and "svd_deg" not in response:
            raise SimulatorTransportError(f"offline direction response missing svd_deg: {response}")
        self.current_position = position
        return response

    def clear(self, position: Point, channel: int) -> dict:
        response = self._accepted_response(self.runner.clear(position.x, position.y, int(channel)), "clear")
        result = response.get("clear_result")
        if result not in {"success", "no_target_in_range"}:
            raise SimulatorTransportError(f"unexpected offline clear_result: {response}")
        self.current_position = position
        return response

    def exit(self) -> dict:
        return self._accepted_response(self.runner.exit(), "exit")


def policy_v0(runner: Any, n: int = 6) -> None:
    """Q3 V0 policy for offline_sim: deterministic 7-point coverage + set localization."""
    client = OfflineRunnerClient(runner)
    radius = theoretical_outer_radius(n)
    planner = Q3BaselinePlanner(
        client,
        logger=JsonlLogger(None),
        config=Q3Config(
            search_radius=radius,
            search_points_n=n,
            clear_radius=20.0,
            clear_safety_radius=20.0,
            max_localization_measures=8,
            localize_on_detection=False,
            scan_found_at_search_points=False,
        ),
    )
    planner.run()


def policy_v1(runner: Any, n: int = 6) -> None:
    """V1: reuse later seven-point search locations as zero-movement localization points."""
    client = OfflineRunnerClient(runner)
    radius = theoretical_outer_radius(n)
    planner = Q3BaselinePlanner(
        client,
        logger=JsonlLogger(None),
        config=Q3Config(
            search_radius=radius,
            search_points_n=n,
            clear_radius=20.0,
            clear_safety_radius=20.0,
            max_localization_measures=8,
            localize_on_detection=False,
            scan_found_at_search_points=True,
        ),
    )
    planner.run()


@dataclass
class Task:
    kind: str
    channel: int
    point: Point
    search_index: int | None = None


class RouteOptimizedPolicy:
    def __init__(self, runner: Any, n: int = 6, dynamic_insert_clear: bool = False):
        self.client = OfflineRunnerClient(runner)
        self.tracks = {ch: SourceTrack(ch) for ch in range(1, 21)}
        self.n = n
        self.search_radius = theoretical_outer_radius(n)
        self.search_points = Q3BaselinePlanner.make_search_points(self.search_radius, n)
        self.dynamic_insert_clear = dynamic_insert_clear
        self.max_rounds = 8
        self.insert_delta_limit_m = self.search_radius * 0.2

    def run(self) -> None:
        self.client.enter()
        try:
            self.run_search_route()
            for track in self.tracks.values():
                if track.status == ChannelStatus.UNKNOWN:
                    track.status = ChannelStatus.ABSENT
            self.resolve_remaining_tasks()
        finally:
            self.client.exit()

    def run_search_route(self) -> None:
        for idx, point in enumerate(self.search_points):
            for channel in self.channels_to_scan(idx):
                self.measure_channel(point, channel)
            if self.dynamic_insert_clear:
                self.try_insert_clear_before_next(idx)

    def channels_to_scan(self, search_index: int) -> list[int]:
        channels = [
            ch
            for ch, track in self.tracks.items()
            if (
                track.status == ChannelStatus.UNKNOWN
                and self.discovered_count() < 16
            )
            or (
                track.status == ChannelStatus.FOUND
                and self.found_scan_has_value(track, self.search_points[search_index])
            )
        ]
        if search_index % 2 == 1:
            channels.reverse()
        return channels

    def discovered_count(self) -> int:
        return sum(1 for track in self.tracks.values() if track.status in {ChannelStatus.FOUND, ChannelStatus.CLEARED})

    def found_scan_has_value(self, track: SourceTrack, point: Point) -> bool:
        if track.status != ChannelStatus.FOUND:
            return False
        if any(distance(point, m.position) < 10.0 for m in track.direction_measurements):
            return False
        region, circle = self.localization_state(track)
        if circle is not None and circle.radius <= 20.0:
            return False
        if not region:
            return False
        if max_distance_to_vertices(point, region) > 995.0:
            return False
        center = circle.center if circle is not None else polygon_centroid(region)
        return Q3BaselinePlanner.crossing_quality(track, point, center) >= 0.2

    def measure_channel(self, point: Point, channel: int) -> None:
        track = self.tracks[channel]
        if track.status in {ChannelStatus.CLEARED, ChannelStatus.ABSENT}:
            return
        response = self.client.measure(point, channel)
        result = response["measure_result"]
        svd = float(response["svd_deg"]) if result == "direction" else None
        if result == "no_signal":
            return
        measurement = Measurement(point, channel, result, svd, float(response["virtual_time_s"]))
        track.add_measurement(measurement)
        if result == "near":
            self.clear_track(track, point)

    def clear_track(self, track: SourceTrack, point: Point) -> bool:
        if track.status == ChannelStatus.CLEARED:
            return True
        response = self.client.clear(point, track.channel)
        track.clear_response = response
        if response["clear_result"] == "success":
            track.status = ChannelStatus.CLEARED
            track.clear_position = point
            return True
        return False

    def try_insert_clear_before_next(self, search_index: int) -> None:
        if search_index + 1 >= len(self.search_points):
            return
        current = self.client.current_position
        nxt = self.search_points[search_index + 1]
        while True:
            candidates = self.ready_clear_tasks()
            best: Task | None = None
            best_delta = float("inf")
            direct = distance(current, nxt)
            for task in candidates:
                delta = distance(current, task.point) + distance(task.point, nxt) - direct
                if delta < best_delta:
                    best_delta = delta
                    best = task
            if best is None or best_delta > self.insert_delta_limit_m:
                return
            self.clear_track(self.tracks[best.channel], best.point)
            current = self.client.current_position

    def resolve_remaining_tasks(self) -> None:
        for _ in range(self.max_rounds):
            tasks = self.build_tasks()
            if not tasks:
                return
            ordered = optimize_open_route(self.client.current_position, tasks)
            for task in ordered:
                track = self.tracks[task.channel]
                if track.status == ChannelStatus.CLEARED:
                    continue
                if task.kind == "clear":
                    self.clear_track(track, task.point)
                else:
                    self.measure_channel(task.point, task.channel)
            if all(t.status in {ChannelStatus.CLEARED, ChannelStatus.ABSENT, ChannelStatus.UNKNOWN} for t in self.tracks.values()):
                return

    def build_tasks(self) -> list[Task]:
        tasks = self.ready_clear_tasks()
        for track in self.tracks.values():
            if track.status != ChannelStatus.FOUND:
                continue
            if any(task.channel == track.channel and task.kind == "clear" for task in tasks):
                continue
            candidate = self.localization_candidate(track)
            if candidate is not None:
                tasks.append(Task("measure", track.channel, candidate))
        return tasks

    def ready_clear_tasks(self) -> list[Task]:
        tasks: list[Task] = []
        for track in self.tracks.values():
            if track.status != ChannelStatus.FOUND:
                continue
            circle = self.localization_circle(track)
            if circle is not None and circle.radius <= 20.0:
                tasks.append(Task("clear", track.channel, circle.center))
        return tasks

    @staticmethod
    def localization_state(track: SourceTrack) -> tuple[list[Point], Circle | None]:
        measurements = track.direction_measurements
        key = tuple((m.position.x, m.position.y, m.svd_deg) for m in measurements)
        if track.localization_cache_key == key:
            return track.localization_region_cache or [], track.localization_circle_cache
        region = localization_region(measurements) if measurements else []
        circle = minimum_enclosing_circle(region) if region else None
        track.localization_cache_key = key
        track.localization_region_cache = region
        track.localization_circle_cache = circle
        return region, circle

    @staticmethod
    def localization_circle(track: SourceTrack) -> Circle | None:
        return RouteOptimizedPolicy.localization_state(track)[1]

    def localization_candidate(self, track: SourceTrack) -> Point | None:
        region, circle = self.localization_state(track)
        if not region or circle is None:
            return None
        center = circle.center if math.isfinite(circle.radius) else polygon_centroid(region)
        offsets = [0.0, 250.0, 500.0, 750.0, 950.0]
        angles = [math.radians(15.0 * k) for k in range(24)]
        candidates: list[Point] = []
        for radius in offsets:
            if radius == 0.0:
                candidates.append(center)
            else:
                candidates.extend(Point(center.x + radius * math.cos(a), center.y + radius * math.sin(a)) for a in angles)

        best_point: Point | None = None
        best_score = -float("inf")
        current = self.client.current_position
        for point in candidates:
            if abs(point.x) > 2_000_000 or abs(point.y) > 2_000_000:
                continue
            if max_distance_to_vertices(point, region) > 995.0:
                continue
            quality = Q3BaselinePlanner.crossing_quality(track, point, center)
            move_penalty = distance(current, point) / 5000.0
            repeat_penalty = 1.0 if any(distance(point, m.position) < 10.0 for m in track.direction_measurements) else 0.0
            score = quality - move_penalty - repeat_penalty
            if score > best_score:
                best_score = score
                best_point = point
        return best_point or center


def route_length(start: Point, tasks: list[Task]) -> float:
    total = 0.0
    current = start
    for task in tasks:
        total += distance(current, task.point)
        current = task.point
    return total


def nearest_neighbor_route(start: Point, tasks: list[Task]) -> list[Task]:
    remaining = list(tasks)
    ordered: list[Task] = []
    current = start
    while remaining:
        idx = min(range(len(remaining)), key=lambda i: distance(current, remaining[i].point))
        task = remaining.pop(idx)
        ordered.append(task)
        current = task.point
    return ordered


def two_opt_open(start: Point, tasks: list[Task]) -> list[Task]:
    ordered = list(tasks)
    improved = True
    while improved:
        improved = False
        best_len = route_length(start, ordered)
        for i in range(len(ordered) - 1):
            for j in range(i + 2, len(ordered) + 1):
                candidate = ordered[:i] + list(reversed(ordered[i:j])) + ordered[j:]
                cand_len = route_length(start, candidate)
                if cand_len + 1e-6 < best_len:
                    ordered = candidate
                    best_len = cand_len
                    improved = True
                    break
            if improved:
                break
    return ordered


def optimize_open_route(start: Point, tasks: list[Task]) -> list[Task]:
    if len(tasks) <= 2:
        return nearest_neighbor_route(start, tasks)
    return two_opt_open(start, nearest_neighbor_route(start, tasks))


def policy_v2(runner: Any, n: int = 6) -> None:
    """V2: route all post-search localization and clear tasks with nearest-neighbor + 2-opt."""
    RouteOptimizedPolicy(runner, n=n, dynamic_insert_clear=False).run()


def policy_v3(runner: Any, n: int = 6) -> None:
    """V3: V2 plus low-detour clear insertion during the seven-point route."""
    RouteOptimizedPolicy(runner, n=n, dynamic_insert_clear=True).run()


class DynamicRoutingPolicy(RouteOptimizedPolicy):
    """V4: rolling online routing over current SEARCH/MEASURE/CLEAR tasks."""

    def __init__(self, runner: Any, n: int = 8):
        super().__init__(runner, n=n, dynamic_insert_clear=False)
        self.remaining_search_indices = set(range(len(self.search_points)))
        self.max_steps = 1000

    def run(self) -> None:
        self.client.enter()
        try:
            for _ in range(self.max_steps):
                self.update_unknown_state()
                tasks = self.build_dynamic_tasks()
                if not tasks:
                    return
                next_task = optimize_dynamic_open_route(self.client.current_position, tasks)[0]
                self.execute_task(next_task)
                if self.done():
                    return
        finally:
            self.client.exit()

    def done(self) -> bool:
        return all(track.status in {ChannelStatus.CLEARED, ChannelStatus.ABSENT} for track in self.tracks.values())

    def update_unknown_state(self) -> None:
        if self.discovered_count() >= 16:
            self.remaining_search_indices.clear()
        if not self.remaining_search_indices:
            for track in self.tracks.values():
                if track.status == ChannelStatus.UNKNOWN:
                    track.status = ChannelStatus.ABSENT

    def build_dynamic_tasks(self) -> list[Task]:
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
            candidate = self.localization_candidate(track)
            if candidate is not None:
                tasks.append(Task("measure", track.channel, candidate))
        return tasks

    def channels_to_scan_search_point(self, search_index: int) -> list[int]:
        point = self.search_points[search_index]
        channels = []
        for ch, track in self.tracks.items():
            if track.status == ChannelStatus.UNKNOWN and self.discovered_count() < 16:
                channels.append(ch)
            elif track.status == ChannelStatus.FOUND and self.found_scan_has_value(track, point):
                channels.append(ch)
        if search_index % 2 == 1:
            channels.reverse()
        return channels

    def execute_task(self, task: Task) -> None:
        if task.kind == "search":
            if task.search_index is None:
                return
            self.execute_search_task(task.search_index)
            return
        track = self.tracks[task.channel]
        if track.status == ChannelStatus.CLEARED:
            return
        if task.kind == "clear":
            self.clear_track(track, task.point)
        elif task.kind == "measure":
            self.measure_channel(task.point, task.channel)

    def execute_search_task(self, search_index: int) -> None:
        point = self.search_points[search_index]
        for channel in self.channels_to_scan_search_point(search_index):
            track = self.tracks[channel]
            if track.status == ChannelStatus.UNKNOWN and self.discovered_count() >= 16:
                continue
            if track.status in {ChannelStatus.CLEARED, ChannelStatus.ABSENT}:
                continue
            self.measure_channel(point, channel)
        self.remaining_search_indices.discard(search_index)


def policy_v4(runner: Any, n: int = 8) -> None:
    """V4: rolling online routing over SEARCH/MEASURE/CLEAR tasks."""
    DynamicRoutingPolicy(runner, n=n).run()
