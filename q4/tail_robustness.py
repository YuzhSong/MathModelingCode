"""Policy-visible geometry and observational instrumentation; no simulator access."""
from __future__ import annotations

import math

from q3.models import Point
from q4.w5_policy import W5SymmetricDetectionPolicy


def longitudinal_extent(region, anchor, bearing_deg):
    angle = math.radians(bearing_deg)
    ux, uy = math.cos(angle), math.sin(angle)
    values = [(p.x - anchor.x) * ux + (p.y - anchor.y) * uy for p in region]
    return (min(values), max(values)) if values else (None, None)


class ObservedW5Policy(W5SymmetricDetectionPolicy):
    """Instrument unchanged decisions, with deterministic cached geometry queries."""

    def measure_channel(self, point: Point, channel: int) -> None:
        track = self.tracks[channel]
        state = self.target_states[channel]
        before = len(track.measurements)
        negatives = len(state.no_signal_observations)
        role = self._measure_role
        start = self.client.last_virtual_time_s
        current = self.client.current_position
        previous = track.direction_measurements[-1] if track.direction_measurements else None
        lifecycle = state.lifecycle.value
        old_step = self.local_states[channel].step_m
        super().measure_channel(point, channel)
        latest = track.measurements[-1] if len(track.measurements) > before else None
        result = latest.result if latest else "no_signal" if len(state.no_signal_observations) > negatives else "unknown_no_signal"
        region, circle = self.localization_state(track)
        low, high = longitudinal_extent(region, point, float(latest.svd_deg)) if latest and latest.svd_deg is not None else (None, None)
        variation = abs((float(latest.svd_deg) - float(previous.svd_deg) + 180) % 360 - 180) if latest and latest.svd_deg is not None and previous else None
        self.emit(
            "tail_observation", channel=channel, time_s=self.client.last_virtual_time_s,
            start_time_s=start, x=point.x, y=point.y, role=role, result=result,
            bearing_deg=None if latest is None else latest.svd_deg,
            bearing_variation_deg=variation, longitudinal_low_m=low,
            longitudinal_high_m=high, polygon_vertices=len(region),
            mec_radius_m=None if circle is None else circle.radius,
            move_m=math.hypot(point.x-current.x, point.y-current.y),
            movement_bearing_deg=math.degrees(math.atan2(point.y-current.y, point.x-current.x)),
            lifecycle_before=lifecycle, lifecycle_after=state.lifecycle.value,
            step_before_m=old_step, step_after_m=self.local_states[channel].step_m,
            fallback_active=self.local_states[channel].fallback_active,
            mec_checks=self.local_states[channel].mec_checks,
            deferred_count=state.deferred_count,
        )
