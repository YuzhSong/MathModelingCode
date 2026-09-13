"""W5Pro shell with a strict, non-invasive identity mode.

The execution layer deliberately delegates to frozen W5 until a feature gate
is implemented and tested. This makes every future ablation same-seed
comparable and prevents accidental changes to the baseline.
"""
from __future__ import annotations

import math
from typing import Any

from q4.w5_policy import W5_SELECTED_SPEC, W5SymmetricDetectionPolicy
from q4.w2_policy import TargetLifecycle
from q3.models import ChannelStatus
from q3.offline_policy import Task
from q4.w5pro_config import IDENTITY_CONFIG, W5ProConfig
from q4.w5pro_observations import adapt_measurement


class W5ProPolicy(W5SymmetricDetectionPolicy):
    """W5-compatible policy shell; all new mechanisms are feature-gated."""

    def __init__(self, runner: Any, config: W5ProConfig = IDENTITY_CONFIG):
        super().__init__(runner, W5_SELECTED_SPEC)
        self.config = config
        self.variant = "w5pro_identity" if config.identity else "w5pro"
        self._pro_task_pool = None
        self._pro_shield = None
        self._spatial_bundles = {}
        self._no_progress_streak = 0
        self._last_progress = (0, 0, len(self.remaining_search_indices))
        self._spatial_guard_active = False
        self._clear_ready_latched = {}
        self._visibility_cache = {}
        self._ridge_points = {}
        self._bundle_anchor = None
        self._bundle_channels = set()
        self._last_executed_kind = None
        if not config.identity:
            from q4.w5pro_safety import SafetyShield
            from q4.w5pro_tasks import RemainingTaskPool
            from q4.w5pro_feasible import FeasibleRegion
            from q4.w5pro_hypothesis import HypothesisGrid
            from q4.w5pro_triangle_certificate import ChannelTriangleCertificate, frozen_w5_certificate
            from q4.w5pro_scheduler import AdaptiveScanSession
            from q4.w5pro_tail_fallback import TailFallbackController
            self._pro_task_pool = RemainingTaskPool()
            self._pro_shield = SafetyShield()
            self.hypotheses = HypothesisGrid()
            self.feasible_regions = {channel: FeasibleRegion() for channel in self.tracks}
            points, triangles = frozen_w5_certificate()
            self._certificate_points = points
            self.certificates = {channel: ChannelTriangleCertificate(triangles) for channel in self.tracks}
            self.scan_session = AdaptiveScanSession()
            self.tail_fallback = TailFallbackController(
                per_channel_budget=config.tail_budget_per_channel,
                per_state_budget=config.tail_budget_per_state)

    def hard_completion(self) -> bool:
        if self.config.identity:
            return self.done_w2()
        return all(
            track.status.value == "cleared" or
            (self.discovered_count() >= 16 and track.status.value in {"unknown", "absent"}) or
            (self.certificates[channel].hard_complete(channel)
             and (track.status.value in {"unknown", "absent"}
                  or self.discovered_count() >= 16))
            for channel, track in self.tracks.items()
        )

    def update_unknown_state(self) -> None:
        """Only promote UNKNOWN to ABSENT after its hard certificate is done."""
        if self.config.identity:
            super().update_unknown_state()
            return
        if self.discovered_count() >= 16:
            self.remaining_search_indices.clear()
        if not self.remaining_search_indices:
            for channel, track in self.tracks.items():
                if (track.status in {ChannelStatus.UNKNOWN, ChannelStatus.ABSENT}
                        and (self.certificates[channel].hard_complete(channel)
                             or self.discovered_count() >= 16)):
                    track.status = ChannelStatus.ABSENT

    def measure_channel(self, point, channel):
        if self.config.identity:
            return super().measure_channel(point, channel)
        track = self.tracks[channel]
        before = len(track.measurements)
        super().measure_channel(point, channel)
        self.hypotheses.add_channel(channel)
        if len(track.measurements) > before:
            measurement = track.measurements[-1]
            observation = adapt_measurement(measurement)
            if observation.kind == "BEARING":
                self.feasible_regions[channel].add_bearing(point, measurement.svd_deg)
                self.hypotheses.update_bearing(channel, point, measurement.svd_deg)
            elif observation.kind == "NEAR":
                self.feasible_regions[channel].add_near(point)
                self.hypotheses.update_near(channel, point)
            result = measurement.result
        else:
            # No measurement appended means the public response was NO_SIGNAL
            # (or the execution layer ignored an already terminal target).
            self.hypotheses.update_no_signal(channel, point)
            result = "no_signal"
        vertex_index = next((i for i, anchor in enumerate(self._certificate_points)
                             if abs(anchor.x-point.x) <= 1e-6 and abs(anchor.y-point.y) <= 1e-6), None)
        if vertex_index is not None:
            self.certificates[channel].observe(channel, vertex_index, result)
        self.emit("w5pro_hypothesis_update", channel=channel, result=result,
                  h_alive=self.hypotheses.alive_count(channel),
                  h_fraction=self.hypotheses.alive_fraction(channel),
                  f_constraints=len(self.feasible_regions[channel]._constraints),
                  f_observations=len(self.feasible_regions[channel].observations))
        self._visibility_cache.clear()
        if not self.config.identity and self.config.adaptive_scan:
            self.scan_session.observe(channel, result)
            self.emit("w5pro_scan_observe", channel=channel, result=result,
                      map_channels_seen=len(self.scan_session.map.channels_seen))
        if not self.config.identity and self.config.use_tail_rescue:
            action = self.tail_fallback.choose(
                nbv_gain=1.0 if result in {"direction", "near"} else 0.0,
                route_opportunity=True, no_progress=False, result=result,
                channel=channel, state=self.tracks[channel].status.value)
            if action:
                self.emit("w5pro_tail_fallback", action=action,
                          no_signal_streak=self.tail_fallback.no_signal_streak)

    def channels_to_scan_search_point(self, search_index: int) -> list[int]:
        channels = super().channels_to_scan_search_point(search_index)
        if self.config.identity or not self.config.adaptive_scan:
            return channels
        clear_ready = {t.channel for t in self.ready_clear_tasks() if t.channel is not None}
        # During discovery UNKNOWN channels are ordinary scan candidates; do
        # not turn all of them into must_include, otherwise MID cap is silently
        # defeated and every point scans all 20 channels forever. Hard
        # certificate obligations become must_include only after discovery
        # points are exhausted.
        hard_required = set()
        if not self.remaining_search_indices:
            hard_required = {channel for channel, track in self.tracks.items()
                             if track.status.value == "unknown"
                             and not self.certificates[channel].hard_complete(channel)}
        from q4.w5pro_scheduler import BacklogState
        found = {channel for channel, track in self.tracks.items()
                 if track.status.value == "found"}
        if found or clear_ready:
            uncertainty_gain = sum(self.hypotheses.alive_fraction(c) for c in hard_required)
            certificate_gain = float(len(hard_required))
            point = self.search_points[search_index]
            travel_s = math.hypot(point.x - self.client.current_position.x,
                                  point.y - self.client.current_position.y) / 5.0 + 5.0 * max(1, len(channels))
            competing_value = 0.05 if clear_ready else 0.02
            if self.scan_session.map.scans >= 20 and self.scan_session.should_stop_exploration(
                    uncertainty_gain=uncertainty_gain / max(1, len(channels)),
                    certificate_gain=certificate_gain / max(1, len(channels)),
                    delta_time_s=travel_s,
                    competing_task_value=competing_value,
                    threshold=self.config.exploration_efficiency_threshold):
                self.emit("w5pro_exploration_stop", search_index=search_index,
                          marginal_value=(uncertainty_gain + certificate_gain) / travel_s,
                          competing_task_value=competing_value,
                          reason="marginal_value")
                return []
        clear_ready_channels = {task.channel for task in self.ready_clear_tasks()
                                if task.channel is not None}
        self.scan_session.scheduler.update_mode(
            discovered=self.discovered_count(), hard_complete=self.hard_completion(),
            backlog=BacklogState(len(found), len(clear_ready_channels),
                                 max((self._pro_task_pool.wait_age.get(c, 0) for c in found), default=0),
                                 max((self._pro_task_pool.wait_age.get(c, 0) for c in clear_ready_channels), default=0)),
            backbone_step=search_index)
        # The legacy W2 filter is allowed to optimize soft scans, but it must
        # never remove an unfinished hard-certificate channel before ranking.
        # Search-point scans are discovery work only. FOUND channels must be
        # served by localization/CLEAR tasks; repeatedly scanning them was the
        # source of the excessive post-discovery scan_continue tail.
        if self.discovered_count() < 16:
            # Discovery has the same full-channel contract as frozen W5;
            # pruning FOUND channels here can hide later observations and
            # force many extra backbone points.
            scan_channels = set(channels)
        else:
            scan_channels = {channel for channel in channels
                             if self.tracks[channel].status.value == "unknown"}
        scan_channels |= hard_required
        ranked = self.scan_session.rank(scan_channels, clear_ready=set(),
                                        must_include=hard_required,
                                        cleared={c for c, t in self.tracks.items()
                                                 if t.status.value in {"cleared", "absent"}})
        self.emit("w5pro_scan_continue", search_index=search_index,
                  selected_channels=ranked, mode=self.scan_session.scheduler.mode.value)
        return ranked

    def build_dynamic_tasks(self):
        """Use the additive planner layer only when at least one gate is on."""
        tasks = super().build_dynamic_tasks()
        if self.config.identity:
            return tasks
        from q4.w5pro_tasks import W5ProTask
        # Persist the first reliable CLEAR point across transient REACQUIRE
        # lifecycle changes in the legacy W3 local state.
        for task in tasks:
            if task.kind == "clear" and task.channel is not None:
                self._clear_ready_latched[task.channel] = task.point
        current_clear = {task.channel for task in tasks if task.kind == "clear"}
        for channel, point in tuple(self._clear_ready_latched.items()):
            track = self.tracks[channel]
            state = self.target_states[channel]
            if track.status != ChannelStatus.FOUND or channel in current_clear:
                continue
            if state.failed_clear_measure_count == len(track.direction_measurements):
                continue
            tasks.append(Task("clear", channel, point))
            current_clear.add(channel)
            self.emit("w5pro_clear_ready_preempt", channel=channel,
                      radius_m=self.localization_circle(track).radius
                      if self.localization_circle(track) is not None else None,
                      directional=bool(track.direction_measurements),
                      lifecycle=state.lifecycle.value)
        # A reliable localization result outranks a stale REACQUIRE lifecycle.
        # The legacy helper suppresses REACQUIRE channels, which previously
        # allowed a clear-ready source to be postponed by repeated probes.
        existing_clear = {task.channel for task in tasks if task.kind == "clear"}
        for channel, track in self.tracks.items():
            if track.status != ChannelStatus.FOUND or channel in existing_clear:
                continue
            circle = self.localization_circle(track)
            state = self.target_states[channel]
            if (circle is not None and circle.radius <= 20.0
                    and state.failed_clear_measure_count != len(track.direction_measurements)):
                tasks.append(Task("clear", channel, circle.center))
                self.emit("w5pro_clear_ready_preempt", channel=channel,
                          radius_m=circle.radius,
                          directional=bool(track.direction_measurements),
                          lifecycle=state.lifecycle.value)
        # Once discovery is exhausted, unfinished hard certificates enter an
        # explicit completion/VERIFY phase.  These actions are mandatory
        # anchor observations; they cannot be dropped by the soft scheduler.
        if not self.remaining_search_indices:
            for channel, track in self.tracks.items():
                if track.status != ChannelStatus.UNKNOWN:
                    continue
                seen = self.certificates[channel]._no_signal.get(channel, set())
                if channel in self.certificates[channel].present_channels:
                    continue
                for index, point in enumerate(self._certificate_points):
                    if index not in seen:
                        tasks.append(Task("measure", channel, point,
                                          search_index=None))
        if self.config.use_pareto_candidates:
            for channel, track in self.tracks.items():
                if track.status != ChannelStatus.FOUND:
                    continue
                base = next((task for task in tasks
                             if task.channel == channel
                             and task.kind in {"measure", "reacquire"}), None)
                if base is None:
                    continue
                base_distance = math.hypot(base.point.x - self.client.current_position.x,
                                           base.point.y - self.client.current_position.y)
                pareto_points = (self.localization_pareto_candidates(track, limit=2)
                                 if base_distance >= 700.0 else [])
                for point in pareto_points:
                    point_distance = math.hypot(point.x - self.client.current_position.x,
                                               point.y - self.client.current_position.y)
                    if (point_distance >= base_distance - 100.0
                            or math.hypot(point.x - base.point.x,
                                          point.y - base.point.y) < 20.0):
                        continue
                    tasks.append(Task(base.kind, channel, point,
                                      search_index=None))
                self.emit("w5pro_pareto_candidate_generation",
                          channel=channel, generated=len(pareto_points),
                          task_count=sum(1 for task in tasks
                                         if task.channel == channel
                                         and task.kind in {"measure", "reacquire"}))
        kind_map = {"SEARCH": "SEARCH", "MEASURE": "REFINE", "REACQUIRE": "REACQUIRE", "CLEAR": "CLEAR"}
        converted = [W5ProTask(kind_map[t.kind.upper()], t.point, channel=t.channel,
                               search_index=t.search_index,
                               mandatory=t.kind.upper() == "CLEAR") for t in tasks]
        if self.config.use_task_pool:
            from q4.w5pro_information_ridge import build_ridges
            points = tuple(dict.fromkeys((task.point for task in converted)))
            active_channels = tuple(self.tracks)
            ridges = build_ridges(
                points, active_channels,
                lambda point, channel: self.hypotheses.alive_fraction(channel),
                lambda point: math.hypot(point.x - self.client.current_position.x,
                                         point.y - self.client.current_position.y) / 5.0)
            self._ridge_points = {(round(r.point.x, 6), round(r.point.y, 6)): r for r in ridges[:8]}
            for ridge in ridges[:8]:
                self.emit("w5pro_information_ridge", point_x=ridge.point.x,
                          point_y=ridge.point.y, channels=ridge.channels,
                          information_gain=ridge.information_gain,
                          route_insertion_cost_s=ridge.route_insertion_cost_s)
        if self.config.use_wait_for_route and len(converted) > 1:
            from q4.w5pro_corridor import bind_waiting_opportunities, corridor_candidates
            route = tuple([self.client.current_position] + [task.point for task in converted])
            dedicated = {task.channel: math.hypot(task.point.x - self.client.current_position.x,
                                                   task.point.y - self.client.current_position.y) / 5.0 + 5.0
                         for task in converted if task.channel is not None}
            opportunities = bind_waiting_opportunities(
                corridor_candidates(route, converted), dedicated, threshold=0.8)
            for opportunity in opportunities[:8]:
                channel = opportunity.task.channel
                if channel is None or not self._pro_task_pool.is_wait_allowed(channel):
                    continue
                decision = self._pro_task_pool.wait_for_route(
                    channel, opportunity.point, dedicated[channel],
                    opportunity.insertion_cost_s)
                self.emit("w5pro_corridor_opportunity", channel=channel,
                          segment_index=opportunity.segment_index,
                          insertion_cost_s=opportunity.insertion_cost_s,
                          dedicated_cost_s=dedicated[channel],
                          starvation=decision.starvation)
        if self.config.use_future_cost:
            from q4.w5pro_route_repair import repair_route
            original_route = tuple(task.point for task in converted)
            repair = repair_route(self.client.current_position,
                                  list(original_route),
                                  locked_macro=None)
            changed = repair.route != original_route
            self.emit("w5pro_route_plan", route_size=len(repair.route),
                      total_seconds=repair.total_seconds,
                      changed=changed, locked_macro=False)
            if changed:
                self.emit("w5pro_route_repair", route_size=len(repair.route),
                          total_seconds=repair.total_seconds,
                          locked_macro=False, repair_needed=True)
        self._spatial_bundles = {}
        if self.config.use_spatial_stop and not self._spatial_guard_active:
            from q4.w5pro_spatial import cluster_tasks
            for stop in cluster_tasks(converted, radius_m=120.0,
                                      route=(self.client.current_position,)):
                executable = tuple(member for member in stop.members if member.kind != "SEARCH")
                if len(executable) < 2:
                    continue
                # Keep the original task vocabulary for the execution layer;
                # map each member to the shared stop so its service list can
                # be executed with real simulator timing.
                for member in executable:
                    if member.kind == "SEARCH":
                        # SEARCH already scans every eligible channel at the
                        # point; bundling it would double-measure the point.
                        continue
                    key = (member.kind, member.channel, member.search_index,
                           round(member.point.x, 6), round(member.point.y, 6))
                    self._spatial_bundles[key] = stop
                self.emit("w5pro_spatial_bundle", point_x=stop.point.x,
                          point_y=stop.point.y, services=len(executable),
                          route_synergy_s=stop.route_synergy_s)
        self._pro_task_pool.sync(converted)
        clear_ready = {t.channel for t in converted if t.kind == "CLEAR" and t.channel is not None}
        filtered = self._pro_shield.filter(
            converted,
            hard_complete=self.hard_completion(),
            discovered_count=self.discovered_count(),
            clear_ready_channels=clear_ready,
        )
        # VERIFY anchors are hard-completion obligations, not optional soft
        # work.  Reinsert them after the shield so starvation protection can
        # never silently remove the completion phase.
        hard_verify = [task for task in converted
                       if task.kind == "REFINE" and task.channel is not None
                       and self.tracks[task.channel].status == ChannelStatus.UNKNOWN
                       and task.channel not in self.certificates[task.channel].present_channels]
        filtered.extend(task for task in hard_verify if task not in filtered)
        from q4.w5pro_planner import pareto_prune
        filtered = pareto_prune(filtered)
        filtered.extend(task for task in hard_verify if task not in filtered)
        self.emit("w5pro_candidate_pool", pool_size=len(converted), filtered_size=len(filtered),
                  task_kinds=sorted({t.kind for t in filtered}))
        # The execution layer still consumes the frozen lowercase Task
        # vocabulary; planner filtering is translated back without changing
        # the physical action contract.
        allowed = {(t.kind, t.channel, t.search_index) for t in filtered}
        return [original for original in tasks
                if (kind_map[original.kind.upper()], original.channel, original.search_index) in allowed]

    def run(self) -> None:
        if self.config.identity:
            # Identity mode is the frozen W5 oracle.
            super().run()
            return
        self.client.enter()
        self.termination_reason = "running"
        try:
            for _ in range(min(self.max_steps, self.config.max_macro_steps)):
                self.update_unknown_state()
                if self.hard_completion():
                    self.termination_reason = "hard_complete"
                    return
                tasks = self.build_dynamic_tasks()
                if not tasks:
                    unresolved = self.unresolved_channels()
                    if unresolved:
                        for channel in unresolved:
                            self.target_states[channel].lifecycle = TargetLifecycle.REACQUIRE
                        self.emit("w2_stalled_reactivated", channels=unresolved)
                        tasks = self.build_dynamic_tasks()
                    if not tasks:
                        action = self.tail_fallback.choose(
                            nbv_gain=0.0, route_opportunity=False,
                            no_progress=True, channel=0, state="no_progress")
                        if action:
                            self.emit("w5pro_tail_fallback", action=action,
                                      no_progress=True)
                        if not self.hard_completion():
                            # Correctness gate: an empty soft pool is not an
                            # admissible exit while hard coverage is open.
                            self.remaining_search_indices.update(range(self.n))
                            self._spatial_bundles.clear()
                            self.emit("w5pro_hard_fallback_reactivated",
                                      remaining_search=len(self.remaining_search_indices))
                            continue
                        self.termination_reason = "stalled_without_task"
                        return
                task = self._select_pro_task(tasks)
                self.emit_selected_task(task, len(tasks))
                self.execute_task(task)
                self._last_executed_kind = task.kind
                if self.hard_completion():
                    self.termination_reason = "hard_complete"
                    return
                progress = (self.discovered_count(),
                            sum(t.status.value == "cleared" for t in self.tracks.values()),
                            len(self.remaining_search_indices))
                if progress == self._last_progress:
                    self._no_progress_streak += 1
                else:
                    self._no_progress_streak = 0
                    self._last_progress = progress
                if self._no_progress_streak >= 100:
                    # A planner stall must recover to the complete W5 route;
                    # never keep spending steps on stale soft tasks.
                    self._spatial_bundles.clear()
                    self._spatial_guard_active = True
                    self._pro_task_pool = type(self._pro_task_pool)()
                    self.emit("w5pro_no_progress_guard",
                              streak=self._no_progress_streak,
                              discovered=progress[0], cleared=progress[1],
                              remaining_search=progress[2])
                    self._no_progress_streak = 0
            if self.termination_reason == "running":
                self.termination_reason = "max_macro_steps"
        finally:
            self.update_unknown_state()
            self.emit_exit_state()
            self.client.exit()

    def _select_pro_task(self, tasks):
        """Choose one macro using mission seconds plus explicit hard priority."""
        current = self.client.current_position
        current_channel = getattr(self.client, "current_channel", None)
        from q4.w5pro_future_cost import estimate_future_cost, risk_adjusted_cost

        # Hard preemption is intentionally outside the soft score.  A reliable
        # CLEAR must not lose to SEARCH/NBV merely because those tasks have a
        # large information backlog.  Directional fixes are more urgent since
        # their localization is already geometrically constrained.
        clear_tasks = [task for task in tasks if task.kind == "clear"]
        ready_clear = []
        for task in clear_tasks:
            route_s = (math.hypot(task.point.x - current.x,
                                  task.point.y - current.y) / 5.0
                       + (1.0 if task.channel not in (None, current_channel, 0) else 0.0))
            directional = bool(task.channel in self.tracks
                               and self.tracks[task.channel].direction_measurements)
            if route_s <= self.config.clear_ready_route_max_s:
                ready_clear.append((0 if directional else 1, route_s,
                                    task.channel if task.channel is not None else -1,
                                    task))
        if ready_clear:
            selected = min(ready_clear, key=lambda item: item[:3])[-1]
            self.emit("w5pro_clear_ready_hard_preempt",
                      channel=selected.channel,
                      route_seconds=min(item[1] for item in ready_clear),
                      directional=bool(selected.channel in self.tracks
                                       and self.tracks[selected.channel].direction_measurements))
            return selected

        if self.config.use_local_route_planner:
            from q4.w5pro_local_route import propose_routes
            route_tasks = [task for task in tasks
                           if task.kind in {"measure", "reacquire"}]
            if len(route_tasks) >= 2:
                routes = propose_routes(
                    current, route_tasks,
                    horizon=self.config.local_route_horizon,
                    beam_width=self.config.local_route_beam_width,
                    current_channel=current_channel)
                if routes and routes[0].tasks:
                    selected = routes[0].tasks[0]
                    self.emit("w5pro_local_route_choice",
                              horizon=self.config.local_route_horizon,
                              beam_width=self.config.local_route_beam_width,
                              route=[{"kind": task.kind, "channel": task.channel}
                                     for task in routes[0].tasks],
                              travel_s=routes[0].travel_s,
                              switch_s=routes[0].switch_s,
                              measure_s=routes[0].measure_s,
                              clear_s=routes[0].clear_s,
                              route_total_s=routes[0].total_s,
                              alternatives=[route.total_s for route in routes[:4]])
                    return selected

        # CLEAR is a local service endpoint, not a reason to immediately jump
        # to an unrelated refinement point.  Resume the frozen discovery
        # backbone once after a clear, when available; this preserves spatial
        # continuity and leaves later refinement to the next task-pool cycle.
        if self._last_executed_kind == "clear":
            backbone = [task for task in tasks if task.kind == "search"]
            if backbone:
                selected = min(backbone, key=lambda task: (
                    math.hypot(task.point.x - current.x, task.point.y - current.y),
                    task.search_index if task.search_index is not None else -1))
                self.emit("w5pro_post_clear_backbone_resume",
                          search_index=selected.search_index,
                          distance_m=math.hypot(selected.point.x - current.x,
                                                selected.point.y - current.y))
                return selected
            local_after_clear = [task for task in tasks
                                 if task.kind in {"measure", "reacquire"}]
            if local_after_clear:
                selected = min(local_after_clear, key=lambda task: (
                    math.hypot(task.point.x - current.x, task.point.y - current.y),
                    0 if task.kind == "reacquire" else 1,
                    task.channel if task.channel is not None else -1))
                self.emit("w5pro_post_clear_local_resume",
                          kind=selected.kind, channel=selected.channel,
                          distance_m=math.hypot(selected.point.x - current.x,
                                                selected.point.y - current.y))
                return selected

        # Preserve the efficient W5 discovery cadence when the next backbone
        # point is a genuinely local opportunity.  This prevents an early
        # refinement detour from changing the entire search geometry, while
        # still leaving distant exploration to the time-based score below.
        nearby_search = [task for task in tasks if task.kind == "search"
                         and math.hypot(task.point.x - current.x,
                                        task.point.y - current.y) / 5.0 <= 220.0]
        if nearby_search:
            return min(nearby_search, key=lambda task: (
                math.hypot(task.point.x - current.x, task.point.y - current.y),
                task.search_index if task.search_index is not None else -1))

        # State-aware local task bundling: choose a spatial neighborhood before
        # choosing a channel task.  This is deliberately limited to soft local
        # work; SEARCH and CLEAR retain their hard semantics above/below.
        local_tasks = [task for task in tasks
                       if task.kind in {"measure", "reacquire"}]
        if len(local_tasks) >= 3:
            radius_m = 250.0
            clusters: list[list] = []
            for candidate in sorted(local_tasks, key=lambda task: (
                    task.point.x, task.point.y, task.channel or -1)):
                cluster = next((group for group in clusters if any(
                    math.hypot(candidate.point.x - member.point.x,
                               candidate.point.y - member.point.y) <= radius_m
                    for member in group)), None)
                if cluster is None:
                    clusters.append([candidate])
                else:
                    cluster.append(candidate)
            def cluster_key(group):
                span = max(math.hypot(member.point.x - other.point.x,
                                      member.point.y - other.point.y)
                           for member in group for other in group)
                # A bounded service-density credit prevents a large cluster
                # from dominating purely by cardinality.
                continuity = 0.0
                if self._bundle_anchor is not None:
                    remains_local = any(
                        math.hypot(member.point.x - self._bundle_anchor[0],
                                   member.point.y - self._bundle_anchor[1]) <= radius_m
                        for member in group)
                    if remains_local:
                        continuity = 180.0
                if self._bundle_channels.intersection(
                        {member.channel for member in group if member.channel is not None}):
                    continuity += 120.0
                enter = min(math.hypot(member.point.x - current.x,
                                       member.point.y - current.y)
                            for member in group)
                return enter + 0.35 * span - min(len(group), 4) * 120.0 - continuity
            best_cluster = min(clusters, key=cluster_key)
            def cluster_stats(group):
                enter_m = min(math.hypot(member.point.x - current.x,
                                         member.point.y - current.y)
                              for member in group)
                span_m = max((math.hypot(member.point.x - other.point.x,
                                         member.point.y - other.point.y)
                              for member in group for other in group), default=0.0)
                return enter_m, span_m
            enter_m, span_m = cluster_stats(best_cluster)
            self.emit("w5pro_local_bundle_decision",
                      candidate_clusters=len(clusters),
                      selected_members=len(best_cluster),
                      selected_channels=sorted({member.channel for member in best_cluster
                                               if member.channel is not None}),
                      enter_distance_m=enter_m,
                      service_span_m=span_m,
                      continuity_anchor=self._bundle_anchor)
            tasks = [task for task in tasks
                     if task.kind not in {"measure", "reacquire"}
                     or task in best_cluster]

        def key(task):
            distance_s = math.hypot(task.point.x - current.x, task.point.y - current.y) / 5.0
            switch_s = 1.0 if task.channel not in (None, current_channel, 0) else 0.0
            if task.channel in self.tracks:
                # Main-loop scoring uses the cached belief summary.  The
                # expensive cell-corner directional visibility is reserved
                # for explicit NBV candidate evaluation, not repeated for
                # every legacy refinement task.
                information_s = 12.0 * self.hypotheses.alive_fraction(task.channel)
            elif task.kind == "search":
                # Search points are hard backbone work; use the cheap global
                # alive fraction here and reserve geometric visibility scans
                # for channel-specific refinement candidates.
                fractions = [self.hypotheses.alive_fraction(c) for c in self.tracks]
                information_s = 12.0 * (sum(fractions) / len(fractions) if fractions else 1.0)
            else:
                information_s = 0.0
            future_obj = estimate_future_cost(
                sensing_s=information_s,
                backbone_s=distance_s if task.kind == "search" else 0.0,
                starvation_s=0.5 * len(self._pro_task_pool.wait_age),
            )
            future = risk_adjusted_cost(
                future_obj, mode=self.config.risk_mode,
                samples=getattr(task, "future_cost_samples", ()),
                alpha=self.config.cvar_alpha)
            # CLEAR and hard search remain protected; soft tasks compete on
            # actual travel/switch time, which is the mission objective.
            clear_priority = -100000.0
            if task.kind == "clear":
                route_s = distance_s + switch_s
                if route_s <= self.config.clear_ready_route_max_s:
                    clear_priority = -100000000.0
                if task.channel in self.tracks and self.tracks[task.channel].direction_measurements:
                    clear_priority -= 10000.0
            priority = {"clear": clear_priority, "search": -1000.0,
                        "reacquire": -500.0, "measure": -250.0}.get(task.kind, 0.0)
            # Backlog pressure suppresses indiscriminate discovery while the
            # nonlinear age term prevents FOUND/CLEAR work from starving.
            pressure = self._pro_task_pool.backlog_pressure()
            search_penalty = pressure * 4.0 if task.kind == "search" else 0.0
            age_bonus = self._pro_task_pool.age_cost(task.channel, task.kind)
            measure_s = 5.0 if task.kind in {"measure", "reacquire"} else 0.0
            certificate_gain = 1.0 if task.kind in {"search", "verify"} else 0.0
            information_reward = self.config.information_reward_weight * information_s
            certificate_reward = self.config.certificate_reward_weight * certificate_gain
            # Mission objective is elapsed seconds first; information and
            # certificate gains are bounded rewards and cannot dominate travel.
            total = (priority + distance_s + measure_s + switch_s + future
                     + search_penalty - age_bonus - information_reward
                     - certificate_reward)
            return (total, task.kind, task.channel or -1,
                    task.search_index if task.search_index is not None else -1)

        ranked_tasks = sorted(tasks, key=key)
        selected = ranked_tasks[0]
        # Route-marginal evidence: preserve the best few alternatives before
        # execution so long jumps can be attributed to task generation versus
        # ordering.  This is diagnostics only and must not affect selection.
        marginal_rows = []
        for rank, candidate in enumerate(ranked_tasks[:8], start=1):
            other_tasks = [other for other in tasks if other is not candidate]
            next_distances = [math.hypot(candidate.point.x - other.point.x,
                                         candidate.point.y - other.point.y)
                              for other in other_tasks]
            same_region_distances = [distance for other, distance in zip(
                other_tasks, next_distances)
                if candidate.channel is not None and other.channel is not None
                and abs(candidate.channel - other.channel) <= 2]
            direct_distance = math.hypot(candidate.point.x - current.x,
                                         candidate.point.y - current.y)
            nearest_next = min(next_distances, default=0.0)
            nearest_same_region = min(same_region_distances, default=nearest_next)
            marginal_rows.append({
                "rank": rank,
                "kind": candidate.kind,
                "channel": candidate.channel,
                "search_index": candidate.search_index,
                "distance_m": direct_distance,
                "move_time_s": direct_distance / 5.0,
                "nearest_next_task_distance_m": nearest_next,
                "nearest_same_region_task_distance_m": nearest_same_region,
                "route_marginal_distance_m": max(0.0, direct_distance + nearest_next
                                                   - min((math.hypot(other.point.x - current.x,
                                                                     other.point.y - current.y)
                                                          for other in other_tasks),
                                                         default=direct_distance)),
                "route_marginal_time_s": max(0.0, direct_distance + nearest_next
                                               - min((math.hypot(other.point.x - current.x,
                                                                 other.point.y - current.y)
                                                      for other in other_tasks),
                                                     default=direct_distance)) / 5.0,
                "switch_time_s": 1.0 if candidate.channel not in (None, current_channel, 0) else 0.0,
                "score_s": key(candidate)[0],
                "lifecycle": (self.target_states[candidate.channel].lifecycle.value
                               if candidate.channel in self.target_states else None),
                "reacquisition_attempts": (self.target_states[candidate.channel].reacquisition_attempts
                                            if candidate.channel in self.target_states else 0),
                "consecutive_reacquisition_failures": (
                    self.target_states[candidate.channel].consecutive_reacquisition_failures
                    if candidate.channel in self.target_states else 0),
                "failed_clear_measure_count": (
                    self.target_states[candidate.channel].failed_clear_measure_count
                    if candidate.channel in self.target_states else None),
            })
        self.emit("w5pro_route_marginal_candidates",
                  candidate_count=len(tasks), rows=marginal_rows)
        if selected.kind in {"measure", "reacquire"}:
            self._bundle_anchor = (selected.point.x, selected.point.y)
            if selected.channel is not None:
                self._bundle_channels.add(selected.channel)
        elif selected.kind in {"clear", "search"}:
            # A new backbone or clear phase closes the previous soft bundle;
            # it must not bias a later, unrelated localization region.
            self._bundle_channels.clear()
        if selected.channel in self.tracks and selected.kind in {"measure", "reacquire"}:
            from q4.w5pro_outcomes import outcome_probabilities
            probabilities = outcome_probabilities(self.hypotheses, selected.channel,
                                                  selected.point,
                                                  mode=self.config.outcome_mode)
            self.emit("w5pro_outcome_probabilities", channel=selected.channel,
                      point_x=selected.point.x, point_y=selected.point.y,
                      p_no_signal=probabilities.no_signal,
                      p_bearing=probabilities.bearing,
                      p_near=probabilities.near)
        ridge = self._ridge_points.get((round(selected.point.x, 6), round(selected.point.y, 6)))
        if ridge is not None:
            self.emit("w5pro_information_ridge_selected", point_x=ridge.point.x,
                      point_y=ridge.point.y, channels=ridge.channels,
                      score=ridge.score)
        if (self.config.use_nbv and self.discovered_count() >= 16
                and selected.kind in {"measure", "reacquire"}):
            from q4.w5pro_nbv import generate_candidates, select_minimax
            channel = selected.channel
            if channel is not None:
                track = self.tracks[channel]
                latest_bearing = (track.direction_measurements[-1].svd_deg
                                  if track.direction_measurements else None)
                prior = [m.position for m in track.measurements]
                candidates = generate_candidates(
                    current, mec_center=selected.point, bearing_deg=latest_bearing,
                    backbone_points=[self.search_points[i] for i in sorted(self.remaining_search_indices)[:4]],
                    previous_points=prior, ring_radii=(),
                    ring_angles=(0.0, 90.0, 180.0, 270.0),
                    novelty_distance_m=20.0)
                original_time = math.hypot(selected.point.x-current.x,
                                            selected.point.y-current.y) / 5.0
                # Feasibility is a hard gate before minimax selection.  An
                # attractive but unaffordable NBV must not be reported as
                # selected and then rejected, nor contribute information
                # value to the scheduler.
                feasible_candidates = [candidate for candidate in candidates
                                       if candidate.family != "backbone_opportunity"
                                       and candidate.information_gain >= 0.20
                                       and candidate.travel_time_s <= max(1.0,
                                                                           original_time * 0.20)]
                nbv = select_minimax(feasible_candidates, self.hypotheses,
                                     channel, current)
                self.emit("w5pro_nbv_candidates", channel=channel,
                          candidate_count=len(candidates),
                          feasible_count=len(feasible_candidates))
                if nbv is not None:
                    self.emit("w5pro_nbv_selected", channel=channel,
                              family=nbv.family, score=nbv.score,
                              information_gain=nbv.information_gain,
                              travel_time_s=nbv.travel_time_s)
                    candidate_time = nbv.travel_time_s
                    apply_nbv = True
                    if apply_nbv:
                        from q3.offline_policy import Task
                        selected = Task(selected.kind, selected.channel, nbv.point,
                                        search_index=selected.search_index)
                        self.emit("w5pro_nbv_effective", channel=channel,
                                  family=nbv.family, point_x=nbv.point.x,
                                  point_y=nbv.point.y, applied=True)
                    else:
                        self.emit("w5pro_nbv_effective", channel=channel,
                                  family=nbv.family, point_x=nbv.point.x,
                                  point_y=nbv.point.y, applied=False,
                                  reason="travel_cost")
        if (self.config.use_intersection and self.discovered_count() >= 16
                and selected.kind in {"measure", "reacquire"}):
            from q4.w5pro_nbv import intersection_candidates
            track = self.tracks.get(selected.channel) if selected.channel is not None else None
            bearing_points = tuple(m.position for m in track.direction_measurements) if track else ()
            candidates = intersection_candidates(bearing_points) if len(bearing_points) >= 2 else []
            self.emit("w5pro_intersection_attempt", candidate_count=len(candidates),
                      channel=selected.channel)
            if candidates:
                midpoint = min(candidates, key=lambda c: c.travel_time_s or
                                math.hypot(c.point.x-current.x, c.point.y-current.y) / 5.0)
                midpoint_time = math.hypot(midpoint.point.x-current.x,
                                           midpoint.point.y-current.y) / 5.0
                original_time = math.hypot(selected.point.x-current.x,
                                           selected.point.y-current.y) / 5.0
                # Intersection remains an auxiliary diagnostic candidate.  It
                # must not replace the physical localisation point: doing so
                # can destroy MEC/near convergence and starve CLEAR tasks.
                novel_intersection = (track is not None and all(
                    math.hypot(midpoint.point.x - m.position.x,
                               midpoint.point.y - m.position.y) >= 20.0
                    for m in track.measurements))
                if midpoint_time <= original_time and novel_intersection:
                    from q3.offline_policy import Task
                    selected = Task(selected.kind, selected.channel, midpoint.point,
                                    search_index=selected.search_index)
                    self.emit("w5pro_intersection_selected", channel=selected.channel,
                              point_x=midpoint.point.x, point_y=midpoint.point.y,
                              applied=True)
        selected_move_s = math.hypot(selected.point.x - current.x,
                                     selected.point.y - current.y) / 5.0
        selected_switch_s = 1.0 if selected.channel not in (None, current_channel, 0) else 0.0
        selected_measure_s = 5.0 if selected.kind in {"measure", "reacquire"} else 0.0
        selected_info_s = (12.0 * self.hypotheses.alive_fraction(selected.channel)
                           if selected.channel in self.tracks else 0.0)
        self.emit("w5pro_selected_cost_breakdown", kind=selected.kind,
                  channel=selected.channel,
                  move_time_s=selected_move_s,
                  measure_time_s=selected_measure_s,
                  switch_time_s=selected_switch_s,
                  information_value_s=selected_info_s,
                  final_score=key(selected)[0])
        self.emit("w5pro_route_choice", kind=selected.kind,
                  channel=selected.channel, search_index=selected.search_index,
                  estimated_move_time_s=selected_move_s,
                  uses_future_cost=True, uses_nbv=bool(self.config.use_nbv),
                  uses_spatial_stop=bool(self.config.use_spatial_stop))
        return selected

    def execute_task(self, task) -> None:
        """Execute a selected task and its shared spatial services once."""
        original_kind = task.kind
        # VERIFY is planner vocabulary; the physical simulator action remains
        # the ordinary public measure operation.
        if original_kind == "verify":
            task = Task("measure", task.channel, task.point,
                        search_index=task.search_index)
        transition_channel = task.channel
        transition_before = None
        if (not self.config.identity and transition_channel in self.tracks
                and task.kind in {"measure", "reacquire"}):
            circle = self.localization_circle(self.tracks[transition_channel])
            state = self.target_states[transition_channel]
            transition_before = {
                "x": self.client.current_position.x,
                "y": self.client.current_position.y,
                "candidate_distance_m": math.hypot(task.point.x - self.client.current_position.x,
                                                    task.point.y - self.client.current_position.y),
                "radius_m": None if circle is None else circle.radius,
                "area_proxy_m2": None if circle is None else math.pi * circle.radius ** 2,
                "center_x": None if circle is None else circle.center.x,
                "center_y": None if circle is None else circle.center.y,
                "lifecycle": state.lifecycle.value,
                "reacquisition_attempts": state.reacquisition_attempts,
            }
            self.emit("w5pro_transition_before", channel=transition_channel,
                      kind=task.kind, **transition_before)
        super().execute_task(task)
        if transition_before is not None:
            circle = self.localization_circle(self.tracks[transition_channel])
            state = self.target_states[transition_channel]
            self.emit("w5pro_transition_after", channel=transition_channel,
                      kind=task.kind,
                      radius_m=None if circle is None else circle.radius,
                      area_proxy_m2=None if circle is None else math.pi * circle.radius ** 2,
                      center_x=None if circle is None else circle.center.x,
                      center_y=None if circle is None else circle.center.y,
                      lifecycle=state.lifecycle.value,
                      reacquisition_attempts=state.reacquisition_attempts,
                      no_signal_after_measure=state.lifecycle == TargetLifecycle.REACQUIRE,
                      position_x=self.client.current_position.x,
                      position_y=self.client.current_position.y)
        if self.config.identity or not self.config.use_spatial_stop:
            return
        if task.kind == "search":
            return
        pro_kind = {"measure": "REFINE", "clear": "CLEAR",
                    "reacquire": "REACQUIRE"}.get(original_kind, original_kind.upper())
        key = (pro_kind if task.kind != "search" else "SEARCH",
               task.channel if task.kind != "search" else 0, task.search_index,
               round(task.point.x, 6), round(task.point.y, 6))
        stop = self._spatial_bundles.pop(key, None)
        if stop is None and self.config.use_spatial_stop:
            # NBV may replace the legacy task point; recover the spatial
            # bundle by its service type/channel and proximity instead.
            for candidate_key, candidate_stop in list(self._spatial_bundles.items()):
                if (candidate_key[0] == pro_kind
                        and candidate_key[1] == task.channel
                        and math.hypot(candidate_key[3] - task.point.x,
                                       candidate_key[4] - task.point.y) <= 120.0):
                    stop = candidate_stop
                    self._spatial_bundles.pop(candidate_key, None)
                    break
        if stop is None or stop.services < 2:
            return
        executed = {(task.kind.upper(), task.channel, task.search_index,
                     round(task.point.x, 6), round(task.point.y, 6))}
        served_channels = set()
        service_count = 0
        for member in stop.members:
            if service_count >= self.config.spatial_service_budget:
                break
            member_key = (member.kind, member.channel, member.search_index,
                          round(member.point.x, 6), round(member.point.y, 6))
            self._spatial_bundles.pop(member_key, None)
            if member_key in executed:
                continue
            if member.channel in served_channels:
                continue
            if member.channel is not None and self.tracks[member.channel].status.value in {"cleared", "absent"}:
                continue
            from q3.offline_policy import Task
            lower = {"SEARCH": "search", "REFINE": "measure",
                     "REACQUIRE": "reacquire", "CLEAR": "clear"}[member.kind]
            self.emit("w5pro_spatial_service", kind=member.kind,
                      channel=member.channel, point_x=member.point.x,
                      point_y=member.point.y)
            super().execute_task(Task(lower, member.channel or 0, member.point,
                                      search_index=member.search_index))
            served_channels.add(member.channel)
            service_count += 1

    def emit_selected_task(self, task, pool_size: int) -> None:
        super().emit_selected_task(task, pool_size)
        if not self.config.identity:
            self.emit("w5pro_selected_task", kind=task.kind.upper(),
                      channel=task.channel, search_index=task.search_index,
                      task_x=task.point.x, task_y=task.point.y,
                      pool_size=pool_size)

    def emit_exit_state(self) -> None:
        super().emit_exit_state()
        if not self.config.identity:
            self.emit("w5pro_exit_state",
                      termination_reason=self.termination_reason,
                      hard_complete=self.hard_completion(),
                      discovered=self.discovered_count(),
                      cleared=sum(t.status.value == "cleared" for t in self.tracks.values()),
                      statuses={str(c): t.status.value for c, t in self.tracks.items()},
                      remaining_search=len(self.remaining_search_indices),
                      no_progress_streak=self._no_progress_streak)
            self.emit("w5pro_certificate_summary",
                      channels={str(channel): {
                          "no_signal_vertices": len(cert._no_signal.get(channel, set())),
                          "certified_triangles": len(cert.certified_triangles(channel)),
                          "total_triangles": len(cert.triangles),
                          "present": channel in cert.present_channels,
                      } for channel, cert in self.certificates.items()})


def policy_w5pro(runner: Any) -> None:
    W5ProPolicy(runner).run()
