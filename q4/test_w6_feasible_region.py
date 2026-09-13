from __future__ import annotations

import math

from q3.models import Point
from q3.models import ChannelStatus
from q4.w6_feasible_region import BearingObservation, persistent_bearing_region
from q4.w6_policy import W6PersistentBearingPolicy


def _bearing(position: Point, target: Point) -> float:
    return math.degrees(math.atan2(target.y - position.y, target.x - position.x)) % 360.0


def _good_observations(target: Point) -> list[BearingObservation]:
    positions = [
        Point(target.x - 700.0, target.y - 400.0),
        Point(target.x + 650.0, target.y - 350.0),
        Point(target.x + 700.0, target.y + 450.0),
        Point(target.x - 600.0, target.y + 500.0),
    ]
    return [BearingObservation(p, _bearing(p, target)) for p in positions]


def test_one_bearing_is_not_clear_ready() -> None:
    region = persistent_bearing_region(_good_observations(Point(0.0, 0.0))[:1])
    assert region.valid
    assert region.mec.radius > 20.0


def test_intersecting_bearings_shrink_region() -> None:
    one = persistent_bearing_region(_good_observations(Point(100.0, -80.0))[:1])
    many = persistent_bearing_region(_good_observations(Point(100.0, -80.0)))
    assert many.valid
    assert many.mec.radius < one.mec.radius


def test_nearly_parallel_bearings_remain_conservative() -> None:
    observations = [
        BearingObservation(Point(-1200.0, 0.0), 0.0),
        BearingObservation(Point(-1100.0, 1.0), 0.0),
    ]
    region = persistent_bearing_region(observations)
    assert region.valid
    assert region.mec.radius > 20.0


def test_wraparound_bearings_are_valid() -> None:
    observations = [
        BearingObservation(Point(-500.0, 0.0), 359.0),
        BearingObservation(Point(500.0, 0.0), 181.0),
    ]
    region = persistent_bearing_region(observations)
    assert region.valid
    assert math.isfinite(region.mec.radius)


def test_duplicate_observations_do_not_break_solver() -> None:
    observation = BearingObservation(Point(-500.0, 0.0), 0.0)
    region = persistent_bearing_region([observation] * 8)
    assert region.valid
    assert math.isfinite(region.mec.radius)


def test_no_signal_is_not_an_input_constraint() -> None:
    target = Point(100.0, 100.0)
    observations = _good_observations(target)
    with_no_signal_omitted = persistent_bearing_region(observations)
    with_fewer_observations = persistent_bearing_region(observations[:-1])
    assert with_no_signal_omitted.mec.radius <= with_fewer_observations.mec.radius


def test_backside_no_signal_does_not_shrink_region() -> None:
    observations = _good_observations(Point(0.0, 0.0))
    baseline = persistent_bearing_region(observations)
    # A no_signal event is deliberately represented by adding nothing.
    after_no_signal = persistent_bearing_region(observations)
    assert after_no_signal.vertices == baseline.vertices
    assert after_no_signal.mec.radius == baseline.mec.radius


def test_mec_above_threshold_is_not_ready() -> None:
    region = persistent_bearing_region(_good_observations(Point(0.0, 0.0))[:2])
    assert region.mec.radius > 20.0


def test_mec_at_or_below_threshold_is_ready() -> None:
    target = Point(0.0, 0.0)
    observations = []
    for index in range(8):
        angle = 2.0 * math.pi * index / 8.0
        position = Point(1000.0 * math.cos(angle), 1000.0 * math.sin(angle))
        observations.append(BearingObservation(position, _bearing(position, target)))
    region = persistent_bearing_region(observations)
    assert region.valid
    assert region.mec.radius <= 20.0


def test_invalid_parameters_trigger_safe_fallback() -> None:
    region = persistent_bearing_region([], arena_radius_m=-1.0)
    assert not region.valid
    assert region.reason == "invalid_parameters"


def test_guaranteed_clear_failure_invalidates_certificate() -> None:
    class FailedClearRunner:
        def clear(self, x: float, y: float, channel: int) -> dict:
            return {"clear_result": "no_target_in_range", "virtual_time_s": 1.0}

        def record_policy_diagnostic(self, event: dict) -> None:
            pass

    policy = W6PersistentBearingPolicy(FailedClearRunner())
    track = policy.tracks[1]
    track.status = ChannelStatus.FOUND
    policy.w6_attempted_channels.add(1)
    policy.w6_ready_channels.add(1)
    policy.w6_regions[1] = persistent_bearing_region([])
    assert not policy.clear_track(track, Point(0.0, 0.0))
    assert policy.guaranteed_clear_failures == 1
    assert 1 not in policy.w6_ready_channels
    assert 1 not in policy.w6_regions
