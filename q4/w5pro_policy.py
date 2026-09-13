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
        self._visibility_cache = {}
        self._ridge_points = {}
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
            self.tail_fallback = TailFallbackController()

    def hard_completion(self) -> bool:
        if self.config.identity:
            return self.done_w2()
        return all(
            track.status.value == "cleared" or
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
                        and self.certificates[channel].hard_complete(channel)):
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
                route_opportunity=True, no_progress=False, result=result)
            if action:
                self.emit("w5pro_tail_fallback", action=action,
                          no_signal_streak=self.tail_fallback.no_signal_streak)

    def channels_to_scan_search_point(self, search_index: int) -> list[int]:
        channels = super().channels_to_scan_search_point(search_index)
        if self.config.identity or not self.config.adaptive_scan:
            return channels
        clear_ready = {t.channel for t in self.ready_clear_tasks() if t.channel is not None}
        hard_required = {channel for channel, track in self.tracks.items()
                         if track.status.value == "unknown"
                         and not self.certificates[channel].hard_complete(channel)}
        from q4.w5pro_scheduler import BacklogState
        found = {channel for channel, track in self.tracks.items()
                 if track.status.value == "found"}
        clear_ready_channels = {task.channel for task in self.ready_clear_tasks()
                                if task.channel is not None}
        self.scan_session.scheduler.update_mode(
            discovered=self.discovered_count(), hard_complete=self.hard_completion(),
            backlog=BacklogState(len(found), len(clear_ready_channels),
                                 max((self._pro_task_pool.wait_age.get(c, 0) for c in found), default=0),
                                 max((self._pro_task_pool.wait_age.get(c, 0) for c in clear_ready_channels), default=0)))
        # The legacy W2 filter is allowed to optimize soft scans, but it must
        # never remove an unfinished hard-certificate channel before ranking.
        channels = sorted(set(channels) | hard_required)
        ranked = self.scan_session.rank(set(channels), clear_ready=clear_ready_channels,
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
            repair = repair_route(self.client.current_position,
                                  [task.point for task in converted],
                                  locked_macro=None)
            self.emit("w5pro_route_repair", route_size=len(repair.route),
                      total_seconds=repair.total_seconds,
                      locked_macro=False)
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
                            no_progress=True)
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
            priority = {"clear": -100000.0, "search": -1000.0,
                        "reacquire": -500.0, "measure": -250.0}.get(task.kind, 0.0)
            # Backlog pressure suppresses indiscriminate discovery while the
            # nonlinear age term prevents FOUND/CLEAR work from starving.
            pressure = self._pro_task_pool.backlog_pressure()
            search_penalty = pressure * 4.0 if task.kind == "search" else 0.0
            age_bonus = self._pro_task_pool.age_cost(task.channel, task.kind)
            total = priority + distance_s + switch_s + future + search_penalty - age_bonus
            return (total, task.kind, task.channel or -1,
                    task.search_index if task.search_index is not None else -1)

        selected = min(tasks, key=key)
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
        if self.config.use_nbv and selected.kind in {"measure", "reacquire"}:
            from q4.w5pro_nbv import generate_candidates, select_minimax
            candidates = generate_candidates(current, mec_center=selected.point,
                                             ring_radii=(), novelty_distance_m=0.0)
            channel = selected.channel
            if channel is not None:
                nbv = select_minimax(candidates, self.hypotheses, channel, current)
                self.emit("w5pro_nbv_candidates", channel=channel,
                          candidate_count=len(candidates))
                if nbv is not None:
                    self.emit("w5pro_nbv_selected", channel=channel,
                              family=nbv.family, score=nbv.score,
                              information_gain=nbv.information_gain,
                              travel_time_s=nbv.travel_time_s)
                    candidate_time = nbv.travel_time_s
                    original_time = math.hypot(selected.point.x-current.x,
                                               selected.point.y-current.y) / 5.0
                    if candidate_time <= original_time + 1e-9:
                        from q3.offline_policy import Task
                        selected = Task(selected.kind, selected.channel, nbv.point,
                                        search_index=selected.search_index)
        if self.config.use_intersection and selected.kind in {"measure", "reacquire"}:
            from q4.w5pro_nbv import intersection_candidates
            candidates = intersection_candidates((current, selected.point))
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
                if midpoint_time <= original_time:
                    self.emit("w5pro_intersection_selected", channel=selected.channel,
                              point_x=midpoint.point.x, point_y=midpoint.point.y,
                              applied=False)
        self.emit("w5pro_route_choice", kind=selected.kind,
                  channel=selected.channel, search_index=selected.search_index,
                  estimated_move_time_s=math.hypot(selected.point.x-current.x,
                                                   selected.point.y-current.y) / 5.0,
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
        super().execute_task(task)
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
