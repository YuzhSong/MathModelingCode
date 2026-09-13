"""Planner-owned W5Pro state; physical execution state stays in q3 models."""
from __future__ import annotations

from dataclasses import dataclass

from q3.models import Point
from q4.w2_policy import TargetLifecycle


@dataclass
class W5ProTargetState:
    channel: int
    lifecycle: TargetLifecycle = TargetLifecycle.ACTIVE
    first_found_time_s: float | None = None
    last_positive_time_s: float | None = None
    last_service_time_s: float | None = None
    wait_age: int = 0
    skipped_count: int = 0
    elapsed_unserved_s: float = 0.0
    mec_center: Point | None = None
    mec_radius: float | None = None
    region_diameter: float | None = None
    assigned_route_waypoint: Point | None = None
    dedicated_cost_s: float = 0.0
    route_opportunity_cost_s: float = 0.0
    consecutive_no_signal: int = 0
    total_reacquire_failures: int = 0
    clear_ready: bool = False
    clear_ready_since_s: float | None = None
