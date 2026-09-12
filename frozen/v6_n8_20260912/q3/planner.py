from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .api_client import SimulatorClient, SimulatorError
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


@dataclass
class Q3Config:
    search_radius: float = 1150.0
    search_points_n: int = 6
    target_radius: float = 1800.0
    guaranteed_receive_radius: float = 1000.0
    clear_radius: float = 20.0
    clear_safety_radius: float = 19.5
    max_localization_measures: int = 8
    localize_on_detection: bool = True
    scan_found_at_search_points: bool = False


class Q3BaselinePlanner:
    def __init__(self, client: SimulatorClient, logger: JsonlLogger | None = None, config: Q3Config | None = None):
        self.client = client
        self.logger = logger or JsonlLogger(None)
        self.config = config or Q3Config()
        self.channels = {ch: SourceTrack(ch) for ch in range(1, 21)}
        self.search_points = self.make_search_points(self.config.search_radius, self.config.search_points_n)

    @staticmethod
    def make_search_points(radius: float, n: int = 6) -> list[Point]:
        points = [Point(0.0, 0.0)]
        for k in range(n):
            angle = 2.0 * math.pi * k / n
            points.append(Point(radius * math.cos(angle), radius * math.sin(angle)))
        return points

    def run(self) -> dict[str, Any]:
        summary: dict[str, Any] = {"cleared": 0, "absent": 0, "found_not_cleared": []}
        enter_response = self.client.enter()
        self.logger.write("enter_ok", response=enter_response)

        try:
            for idx, point in enumerate(self.search_points):
                self.logger.write("search_point_start", index=idx, point=point.as_payload())
                for ch in self.channels_to_scan_at_search_point(idx):
                    self.scan_channel_at(point, ch)
                self.logger.write("search_point_done", index=idx)

            for track in self.channels.values():
                if track.status == ChannelStatus.FOUND:
                    self.localize_and_clear(track)

            for track in self.channels.values():
                if track.status == ChannelStatus.UNKNOWN:
                    track.status = ChannelStatus.ABSENT
        finally:
            try:
                exit_response = self.client.exit()
                self.logger.write("exit_ok", response=exit_response)
            except SimulatorError as exc:
                self.logger.write("exit_failed", error=repr(exc))

        summary["cleared"] = sum(1 for t in self.channels.values() if t.status == ChannelStatus.CLEARED)
        summary["absent"] = sum(1 for t in self.channels.values() if t.status == ChannelStatus.ABSENT)
        summary["found_not_cleared"] = [t.channel for t in self.channels.values() if t.status == ChannelStatus.FOUND]
        summary["virtual_time_s"] = self.client.last_virtual_time_s
        self.logger.write("summary", summary=summary)
        return summary

    def channels_to_scan_at_search_point(self, search_index: int) -> list[int]:
        channels = [
            ch
            for ch, track in self.channels.items()
            if (
                track.status == ChannelStatus.UNKNOWN
                and self.discovered_count() < 16
            )
            or (
                self.config.scan_found_at_search_points
                and track.status == ChannelStatus.FOUND
                and self.found_scan_has_value(track, self.search_points[search_index])
            )
        ]
        if search_index % 2 == 1:
            channels.reverse()
        return channels

    def discovered_count(self) -> int:
        return sum(1 for track in self.channels.values() if track.status in {ChannelStatus.FOUND, ChannelStatus.CLEARED})

    def found_scan_has_value(self, track: SourceTrack, point: Point) -> bool:
        if track.status != ChannelStatus.FOUND:
            return False
        if any(distance(point, m.position) < 10.0 for m in track.direction_measurements):
            return False
        region, circle = self.localization_state(track)
        if not region or circle is None:
            return False
        if circle.radius <= self.config.clear_radius:
            return False
        if max_distance_to_vertices(point, region) > self.config.guaranteed_receive_radius - 5.0:
            return False
        return self.crossing_quality(track, point, circle.center) >= 0.2

    def localization_state(self, track: SourceTrack) -> tuple[list[Point], Circle | None]:
        measurements = track.direction_measurements
        key = tuple((m.position.x, m.position.y, m.svd_deg) for m in measurements)
        if track.localization_cache_key == key:
            return track.localization_region_cache or [], track.localization_circle_cache
        region = localization_region(measurements, target_radius=self.config.target_radius) if measurements else []
        circle = minimum_enclosing_circle(region) if region else None
        track.localization_cache_key = key
        track.localization_region_cache = region
        track.localization_circle_cache = circle
        return region, circle

    def scan_channel_at(self, point: Point, channel: int) -> None:
        track = self.channels[channel]
        if track.status == ChannelStatus.CLEARED or track.status == ChannelStatus.ABSENT:
            return
        if track.status == ChannelStatus.FOUND and not self.config.scan_found_at_search_points:
            return
        if track.status not in {ChannelStatus.UNKNOWN, ChannelStatus.FOUND}:
            return
        response = self.client.measure(point, channel)
        result = response["measure_result"]
        svd = float(response["svd_deg"]) if result == "direction" else None
        measurement = Measurement(point, channel, result, svd, float(response["virtual_time_s"]))
        self.logger.write("measure_parsed", channel=channel, point=point.as_payload(), result=result, svd_deg=svd)

        if result == "no_signal":
            return
        if result == "near":
            track.add_measurement(measurement)
            self.try_clear(track, point, reason="near")
            return

        track.add_measurement(measurement)
        if self.config.localize_on_detection:
            self.localize_and_clear(track)

    def try_clear(self, track: SourceTrack, position: Point, reason: str) -> bool:
        response = self.client.clear(position, track.channel)
        self.logger.write("clear_parsed", channel=track.channel, point=position.as_payload(), reason=reason, result=response["clear_result"])
        track.clear_response = response
        if response["clear_result"] == "success":
            track.status = ChannelStatus.CLEARED
            track.clear_position = position
            return True
        return False

    def localize_and_clear(self, track: SourceTrack) -> bool:
        if track.status == ChannelStatus.CLEARED:
            return True

        while track.localization_attempts < self.config.max_localization_measures:
            track.localization_attempts += 1
            region, circle = self.localization_state(track)
            if not region or circle is None:
                self.logger.write("localization_empty_region", channel=track.channel)
                return False

            self.logger.write(
                "localization_region",
                channel=track.channel,
                vertices=len(region),
                center=circle.center.as_payload(),
                radius=circle.radius,
            )

            if circle.radius <= self.config.clear_safety_radius:
                if self.try_clear(track, circle.center, reason="mec_radius"):
                    return True
                self.logger.write("clear_failed_continue_localizing", channel=track.channel, point=circle.center.as_payload(), radius=circle.radius)
                if self.measure_for_localization(track, circle.center, event="after_clear_failed_measure"):
                    return True
                continue

            next_point = self.choose_localization_point(track, region, circle)
            if self.measure_for_localization(track, next_point, event="local_measure_parsed"):
                return True

        region, circle = self.localization_state(track)
        if region and circle is not None and circle.radius <= self.config.clear_radius:
            return self.try_clear(track, circle.center, reason="final_radius")
        self.logger.write("localization_gave_up", channel=track.channel)
        return False

    def measure_for_localization(self, track: SourceTrack, point: Point, event: str) -> bool:
        response = self.client.measure(point, track.channel)
        result = response["measure_result"]
        svd = float(response["svd_deg"]) if result == "direction" else None
        measurement = Measurement(point, track.channel, result, svd, float(response["virtual_time_s"]))
        self.logger.write(event, channel=track.channel, point=point.as_payload(), result=result, svd_deg=svd)

        if result == "near":
            track.add_measurement(measurement)
            return self.try_clear(track, point, reason="near_local")
        if result == "direction":
            track.add_measurement(measurement)
            return False

        # For Q3 this should be rare if the candidate was chosen inside the guaranteed receive envelope.
        self.logger.write("local_measure_no_signal", channel=track.channel, point=point.as_payload())
        return False

    def choose_localization_point(self, track: SourceTrack, region: list[Point], circle: Circle) -> Point:
        center = circle.center if math.isfinite(circle.radius) else polygon_centroid(region)
        offsets = [0.0, 250.0, 500.0, 750.0, 950.0]
        angles = [math.radians(15.0 * k) for k in range(24)]
        candidates: list[Point] = []
        for r in offsets:
            if r == 0.0:
                candidates.append(center)
            else:
                candidates.extend(Point(center.x + r * math.cos(a), center.y + r * math.sin(a)) for a in angles)

        best_point = center
        best_score = -float("inf")
        for p in candidates:
            if abs(p.x) > 2_000_000 or abs(p.y) > 2_000_000:
                continue
            # If all vertices are within 1000 m, every possible source in this convex region is detectable.
            if max_distance_to_vertices(p, region) > self.config.guaranteed_receive_radius - 5.0:
                continue
            quality = self.crossing_quality(track, p, center)
            move_penalty = distance(self.client.current_position, p) / 5000.0
            repeat_penalty = 1.0 if any(distance(p, m.position) < 10.0 for m in track.direction_measurements) else 0.0
            score = quality - move_penalty - repeat_penalty
            if score > best_score:
                best_score = score
                best_point = p
        self.logger.write("localization_candidate", channel=track.channel, point=best_point.as_payload(), score=best_score)
        return best_point

    @staticmethod
    def crossing_quality(track: SourceTrack, candidate: Point, estimated_source: Point) -> float:
        vx = estimated_source.x - candidate.x
        vy = estimated_source.y - candidate.y
        norm_v = math.hypot(vx, vy)
        if norm_v < 1e-6:
            return 0.0
        best = 1.0
        for m in track.direction_measurements:
            ux = estimated_source.x - m.position.x
            uy = estimated_source.y - m.position.y
            norm_u = math.hypot(ux, uy)
            if norm_u < 1e-6:
                continue
            sin_angle = abs((ux * vy - uy * vx) / (norm_u * norm_v))
            best = min(best, sin_angle)
        return best
