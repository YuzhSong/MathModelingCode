"""W5 geometry/router unchanged; independently switchable local tail patches."""
from __future__ import annotations

import math

from q3.geometry import distance
from q3.models import ChannelStatus, Point
from q4.routing import select_task
from q4.tail_robustness import ObservedW5Policy, longitudinal_extent
from q4.w2_policy import TargetLifecycle
from q4.w3_policy import COARSE_MAX_STEP_M, W3ProbePlan


class W6Policy(ObservedW5Policy):
    def __init__(self, runner, variant="w6a"):
        if variant not in {"w6a", "w6b", "w6c", "disabled"}:
            raise ValueError(variant)
        super().__init__(runner)
        self.variant = variant
        self.acceleration = variant in {"w6a", "w6c"}
        self.rescue = variant in {"w6b", "w6c"}
        self._accelerated_observations = set()
        self._first_dedicated_completed = set()

    def reacquisition_point(self, track, state):
        point = super().reacquisition_point(track, state)
        if not self.acceleration or point is None or len(track.direction_measurements) < 2:
            return point
        key = (track.channel, len(track.direction_measurements))
        if key in self._accelerated_observations:
            return point
        region, _ = self.localization_state(track)
        anchor = track.direction_measurements[-1]
        low, _ = longitudinal_extent(region, anchor.position, float(anchor.svd_deg))
        base_plan = self._probe_plans[track.channel]
        # No candidate can lie behind this transverse plane. This bounds
        # longitudinal overshoot, NOT directional visibility at the new point.
        if low is None or low <= base_plan.step_m + 1e-6:
            return point
        step = min(COARSE_MAX_STEP_M, low)
        if step <= base_plan.step_m + 1e-6:
            return point
        angle = math.radians(float(anchor.svd_deg))
        point = Point(anchor.position.x+step*math.cos(angle), anchor.position.y+step*math.sin(angle))
        if any(distance(point,o.position)<1e-6 for o in state.no_signal_observations):
            return base_plan.point
        self._probe_plans[track.channel] = W3ProbePlan(point,"geometry",step,0.0)
        return point

    def measure_channel(self, point, channel):
        plan = self._probe_plans.get(channel)
        role = self._measure_role
        track = self.tracks[channel]
        count = len(track.direction_measurements)
        if role == "reacquire" and plan and plan.kind == "geometry" and distance(point,plan.point)<1e-6:
            self._accelerated_observations.add((channel,count))
            self.emit("w6_geometry_acceleration",channel=channel,time_s=self.client.last_virtual_time_s,step_m=plan.step_m)
        super().measure_channel(point,channel)
        if self.acceleration and len(track.direction_measurements)>count and track.status==ChannelStatus.FOUND:
            local = self.local_states[channel]
            # Only extend the suppressed local MEC check, not the physical criterion.
            if local.fallback_active or local.mec_checks >= 32:
                circle = self.localization_circle(track)
                if circle is not None and circle.radius <= 20.0:
                    local.clear_circle = circle
                    local.clear_measure_count = len(track.direction_measurements)

    def _on_probe_success(self, track, plan, previous_bearing_deg):
        if plan.kind == "rescue":
            return
        if plan.kind == "geometry":
            plan = W3ProbePlan(plan.point,"coarse",plan.step_m,plan.angle_offset_deg)
        super()._on_probe_success(track,plan,previous_bearing_deg)

    def _on_probe_failure(self, channel, plan):
        if plan.kind != "rescue":
            super()._on_probe_failure(channel,plan)

    def execute_task(self, task):
        track = self.tracks.get(task.channel)
        first = bool(self.rescue and track and task.kind in {"measure","reacquire"} and task.channel not in self._first_dedicated_completed)
        negatives = len(self.target_states[task.channel].no_signal_observations) if first else 0
        super().execute_task(task)
        if not first:
            return
        self._first_dedicated_completed.add(task.channel)
        if track.status != ChannelStatus.FOUND or len(self.target_states[task.channel].no_signal_observations)==negatives:
            return
        self._local_rescue(track)

    def _local_rescue(self, track):
        state = self.target_states[track.channel]
        region, _ = self.localization_state(track)
        if not region or not track.direction_measurements:
            return
        anchor = track.direction_measurements[-1]
        angle = math.radians(float(anchor.svd_deg))
        nx,ny = -math.sin(angle), math.cos(angle)
        lateral = [(p.x-anchor.position.x)*nx+(p.y-anchor.position.y)*ny for p in region]
        width = max(lateral)-min(lateral)
        if width <= 1e-6:
            return
        current = self.client.current_position
        # Two sides of the currently failed ray, scaled by feasible-region width.
        candidates = [Point(current.x+sign*width*nx,current.y+sign*width*ny) for sign in (-1,1)]
        tasks = self.build_dynamic_tasks()
        if not tasks:
            return
        next_task = select_task(current,tasks,self.routing_method)
        endpoint = next_task.point
        # Spend at most the next movement's time; service is charged in the
        # same metre-equivalent units (5 s measurement, worst-case 1 s switch).
        budget = distance(current,endpoint)
        attempted = False
        for _ in range(len(candidates)):
            current = self.client.current_position
            def detour(p):
                return distance(current,p)+distance(p,endpoint)-distance(current,endpoint)
            point = min(candidates,key=detour)
            candidates.remove(point)
            cost = detour(point)+5.0*(5.0+1.0)
            if cost > budget or any(distance(point,o.position)<1e-6 for o in state.no_signal_observations):
                continue
            budget -= cost
            attempted = True
            self.emit("w6_rescue_attempt",channel=track.channel,time_s=self.client.last_virtual_time_s,detour_m=cost-30,budget_remaining_m=budget)
            before = len(track.measurements)
            self._probe_plans[track.channel] = W3ProbePlan(point,"rescue",distance(anchor.position,point),None)
            self._measure_role = "reacquire"
            try:
                self.measure_channel(point,track.channel)
            finally:
                self._measure_role = "unknown"
            success = len(track.measurements)>before
            self.emit("w6_rescue_success" if success else "w6_rescue_failure",channel=track.channel,time_s=self.client.last_virtual_time_s)
            if success:
                if track.status == ChannelStatus.FOUND:
                    state.lifecycle = TargetLifecycle.ACTIVE
                return
        if attempted and track.status == ChannelStatus.FOUND:
            self._defer_after_rescue(track.channel)

    def _defer_after_rescue(self, channel):
        state = self.target_states[channel]
        if state.lifecycle != TargetLifecycle.DEFERRED:
            state.lifecycle = TargetLifecycle.DEFERRED
            state.deferred_count += 1
            state.resume_after_search_count = self.completed_search_count + 1
            self.emit("w2_target_deferred",channel=channel,
                      time_s=self.client.last_virtual_time_s,
                      deferred_count=state.deferred_count,
                      resume_after_search_count=state.resume_after_search_count)
        # Inherited build_dynamic_tasks includes DEFERRED targets when no
        # SEARCH remains, so this cannot leave a target permanently stranded.


def policy_w6(runner):
    W6Policy(runner,variant="w6a").run()
