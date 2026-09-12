from __future__ import annotations

from typing import Any

from q3.models import Point
from q3.offline_policy import Task
from q3.routing import optimize_open_route
from q4.routing_continuity import compare_backbone_routes, fixed_end_route_order, insertion_decisions
from q4.w4a_policy import W4AUnifiedRoutingPolicy
from q4.w2_policy import TargetLifecycle


class W4BBackboneContinuityPolicy(W4AUnifiedRoutingPolicy):
    """Stable backbone route with distance-only local task insertion."""

    def __init__(self, runner: Any, insertion_mode: str = "one_per_segment"):
        if insertion_mode not in {"repeat", "cluster", "one_per_segment", "after_backbone"}:
            raise ValueError(f"unknown W4-B insertion mode: {insertion_mode}")
        super().__init__(runner, routing_method="open_route")
        self.insertion_mode = insertion_mode
        self.variant = f"w4b_{insertion_mode}"
        metrics = compare_backbone_routes(Point(0.0, 0.0), self.search_points)
        self.backbone_metrics = {row.name: row for row in metrics}
        self.backbone_order = list(self.backbone_metrics["greedy_2opt_open"].order)
        self.insertions_since_backbone = 0
        self.immediate_preemptions = 0
        self.deferred_decisions = 0
        self.deferred_first_time: dict[tuple[str, int], float] = {}
        self.deferred_durations_s: list[float] = []

    def _remaining_backbone_tasks(self, tasks: list[Task]) -> list[Task]:
        by_index = {
            task.search_index: task
            for task in tasks
            if task.kind == "search" and task.search_index is not None
        }
        return [by_index[index] for index in self.backbone_order if index in by_index]

    def _record_deferred(self, tasks: list[Task]) -> None:
        now = self.client.last_virtual_time_s
        for task in tasks:
            key = (task.kind, task.channel)
            self.deferred_decisions += 1
            self.deferred_first_time.setdefault(key, now)

    def _record_execution(self, task: Task) -> None:
        key = (task.kind, task.channel)
        started = self.deferred_first_time.pop(key, None)
        if started is not None:
            self.deferred_durations_s.append(self.client.last_virtual_time_s - started)

    def select_continuous_task(self, tasks: list[Task]) -> tuple[Task, dict[str, float | int | str]]:
        backbone = self._remaining_backbone_tasks(tasks)
        local = [task for task in tasks if task.kind != "search"]
        if not backbone:
            task = optimize_open_route(self.client.current_position, local)[0]
            return task, {"decision": "post_backbone"}

        next_backbone = backbone[0]
        if not local or self.insertion_mode == "after_backbone":
            self._record_deferred(local)
            return next_backbone, {"decision": "backbone"}
        if self.insertion_mode == "one_per_segment" and self.insertions_since_backbone >= 1:
            self._record_deferred(local)
            return next_backbone, {"decision": "bounded_backbone"}

        points = [task.point for task in backbone]
        decisions = insertion_decisions(
            self.client.current_position,
            next_backbone.point,
            points,
            local,
        )
        eligible = [decision for decision in decisions if decision.ready_now]
        if not eligible:
            self._record_deferred(local)
            best = min(decisions, key=lambda decision: decision.best_future_detour_m)
            return next_backbone, {
                "decision": "defer_to_backbone",
                "best_deferred_now_detour_m": best.now_detour_m,
                "best_deferred_future_detour_m": best.best_future_detour_m,
            }

        if self.insertion_mode == "cluster":
            route = fixed_end_route_order(
                self.client.current_position,
                next_backbone.point,
                [decision.task for decision in eligible],
            )
            selected = next(decision for decision in eligible if decision.task is route[0])
        else:
            selected = min(eligible, key=lambda decision: decision.now_detour_m)
        self._record_deferred([decision.task for decision in decisions if decision.task is not selected.task])
        return selected.task, {
            "decision": "insert",
            "now_detour_m": selected.now_detour_m,
            "best_future_detour_m": selected.best_future_detour_m,
            "best_future_segment": selected.best_future_segment,
        }

    def run(self) -> None:
        self.client.enter()
        self.termination_reason = "running"
        try:
            for _ in range(self.max_steps):
                self.update_unknown_state()
                if self.done_w2():
                    self.termination_reason = "all_resolved"
                    return
                tasks = self.build_dynamic_tasks()
                if not tasks:
                    unresolved = self.unresolved_channels()
                    if unresolved:
                        for channel in unresolved:
                            self.target_states[channel].lifecycle = TargetLifecycle.REACQUIRE
                        tasks = self.build_dynamic_tasks()
                    if not tasks:
                        self.termination_reason = "stalled_without_task"
                        return

                task, decision = self.select_continuous_task(tasks)
                self._record_execution(task)
                if task.kind == "search":
                    self.insertions_since_backbone = 0
                else:
                    self.insertions_since_backbone += 1
                    if decision["decision"] == "insert":
                        self.immediate_preemptions += 1
                self.emit_selected_task(task, len(tasks))
                self.emit(
                    "w4b_continuity_decision",
                    time_s=self.client.last_virtual_time_s,
                    insertion_mode=self.insertion_mode,
                    task_kind=task.kind,
                    channel=task.channel,
                    **decision,
                )
                self.execute_task(task)
            self.termination_reason = "max_steps"
        finally:
            self.update_unknown_state()
            self.emit_exit_state()
            self.client.exit()

    def emit_exit_state(self) -> None:
        super().emit_exit_state()
        mean_deferred = (
            sum(self.deferred_durations_s) / len(self.deferred_durations_s)
            if self.deferred_durations_s
            else 0.0
        )
        self.emit(
            "w4b_exit_state",
            insertion_mode=self.insertion_mode,
            immediate_preemptions=self.immediate_preemptions,
            deferred_decisions=self.deferred_decisions,
            completed_deferred_tasks=len(self.deferred_durations_s),
            mean_deferred_duration_s=mean_deferred,
        )


def policy_w4b_repeat(runner: Any) -> None:
    W4BBackboneContinuityPolicy(runner, insertion_mode="repeat").run()


def policy_w4b_one_per_segment(runner: Any) -> None:
    W4BBackboneContinuityPolicy(runner, insertion_mode="one_per_segment").run()


def policy_w4b_cluster(runner: Any) -> None:
    W4BBackboneContinuityPolicy(runner, insertion_mode="cluster").run()


def policy_w4b_after_backbone(runner: Any) -> None:
    W4BBackboneContinuityPolicy(runner, insertion_mode="after_backbone").run()


def policy_w4b(runner: Any) -> None:
    """Best tested W4-B experiment; it is not promoted over frozen W4-A."""

    policy_w4b_cluster(runner)
