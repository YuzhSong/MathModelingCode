from __future__ import annotations

from typing import Any

from q3.models import ChannelStatus
from q3.offline_policy import Task
from q4.routing import select_task
from q4.w2_policy import TargetLifecycle
from q4.w3_policy import W3CoarseToFinePolicy


class W4AUnifiedRoutingPolicy(W3CoarseToFinePolicy):
    """W3 local behavior with a unified, rolling global task pool."""

    def __init__(self, runner: Any, routing_method: str = "open_route"):
        super().__init__(runner, mode="adaptive")
        self.routing_method = routing_method
        self.variant = f"w4a_{routing_method}"
        self._first_clear_ready: set[int] = set()
        self.task_selection_count = 0

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
                        self.emit("w2_stalled_reactivated", channels=unresolved)
                        tasks = self.build_dynamic_tasks()
                    if not tasks:
                        self.termination_reason = "stalled_without_task"
                        return

                task = select_task(self.client.current_position, tasks, self.routing_method)
                self.emit_selected_task(task, len(tasks))
                self.execute_task(task)

            self.termination_reason = "max_steps"
        finally:
            self.update_unknown_state()
            self.emit_exit_state()
            self.client.exit()

    def build_dynamic_tasks(self) -> list[Task]:
        self._wait_assignments = {}
        self._selected_decisions = {}

        search_tasks: list[Task] = []
        if self.discovered_count() < 16:
            for index in sorted(self.remaining_search_indices):
                if self.channels_to_scan_search_point(index):
                    search_tasks.append(Task("search", 0, self.search_points[index], search_index=index))

        clear_tasks = self.ready_clear_tasks()
        clear_channels = {task.channel for task in clear_tasks}
        reacquire_tasks: list[Task] = []
        normal_candidates: dict[int, Task] = {}
        for track in self.tracks.values():
            if track.status != ChannelStatus.FOUND or track.channel in clear_channels:
                continue
            state = self.target_states[track.channel]
            if state.lifecycle == TargetLifecycle.DEFERRED and self.remaining_search_indices:
                continue
            if state.lifecycle in {TargetLifecycle.REACQUIRE, TargetLifecycle.DEFERRED}:
                point = self.reacquisition_point(track, state)
                if point is not None:
                    reacquire_tasks.append(Task("reacquire", track.channel, point))
                continue
            point = self.localization_candidate(track)
            if point is not None:
                normal_candidates[track.channel] = Task("measure", track.channel, point)

        selected_tasks = search_tasks + clear_tasks + reacquire_tasks
        provisional = selected_tasks + list(normal_candidates.values())
        for channel, base_task in normal_candidates.items():
            track = self.tracks[channel]
            region, circle = self.localization_state(track)
            if not region or circle is None:
                selected_tasks.append(base_task)
                continue
            context = [
                task
                for task in provisional
                if not (task.kind == "measure" and task.channel == channel)
            ]
            decision = self.route_aware_decision(track, region, base_task.point, context)
            self._selected_decisions[channel] = decision
            if decision.selected.search_index is not None:
                self._wait_assignments[channel] = decision.selected.search_index
            else:
                selected_tasks.append(Task("measure", channel, decision.selected.point))

        current = self.client.current_position
        for task in selected_tasks:
            if task.kind != "clear" or task.channel in self._first_clear_ready:
                continue
            self._first_clear_ready.add(task.channel)
            self.emit(
                "w4a_first_clear_ready",
                channel=task.channel,
                time_s=self.client.last_virtual_time_s,
                current_x=current.x,
                current_y=current.y,
                clear_x=task.point.x,
                clear_y=task.point.y,
                task_pool_size=len(selected_tasks),
            )
        return selected_tasks

    def emit_selected_task(self, task: Task, pool_size: int) -> None:
        current = self.client.current_position
        self.task_selection_count += 1
        self.emit(
            "w4a_selected_task",
            time_s=self.client.last_virtual_time_s,
            routing_method=self.routing_method,
            pool_size=pool_size,
            kind=task.kind,
            channel=task.channel,
            search_index=task.search_index,
            current_x=current.x,
            current_y=current.y,
            task_x=task.point.x,
            task_y=task.point.y,
        )

    def emit_exit_state(self) -> None:
        super().emit_exit_state()
        self.emit(
            "w4a_exit_state",
            routing_method=self.routing_method,
            task_selection_count=self.task_selection_count,
        )


def policy_w4a_nearest(runner: Any) -> None:
    W4AUnifiedRoutingPolicy(runner, routing_method="nearest").run()


def policy_w4a_open_route(runner: Any) -> None:
    W4AUnifiedRoutingPolicy(runner, routing_method="open_route").run()


def policy_w4a_route_consequence(runner: Any) -> None:
    W4AUnifiedRoutingPolicy(runner, routing_method="route_consequence").run()


def policy_w4a(runner: Any) -> None:
    """Selected W4-A entry point; set after same-seed controlled evaluation."""

    policy_w4a_open_route(runner)
