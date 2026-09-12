from __future__ import annotations

from collections.abc import Sequence

from q3.geometry import distance
from q3.models import Point
from q3.offline_policy import Task
from q3.routing import optimize_open_point_route, optimize_open_route


def nearest_task(current: Point, tasks: Sequence[Task]) -> Task:
    return min(tasks, key=lambda task: distance(current, task.point))


def open_route_first(current: Point, tasks: Sequence[Task]) -> Task:
    return optimize_open_route(current, tasks)[0]


def one_step_route_consequence(current: Point, tasks: Sequence[Task]) -> Task:
    """Choose the first task minimizing an approximate complete open route.

    Every term is physical route length in metres. There are no category weights:
    the candidate's immediate leg and the optimized route through all other
    currently known tasks are evaluated together.
    """

    if len(tasks) <= 1:
        return tasks[0]
    best_task = tasks[0]
    best_length = float("inf")
    for index, task in enumerate(tasks):
        remaining = [other.point for pos, other in enumerate(tasks) if pos != index]
        tail = optimize_open_point_route(task.point, remaining).length_m
        total = distance(current, task.point) + tail
        if total < best_length - 1e-6:
            best_length = total
            best_task = task
    return best_task


def select_task(current: Point, tasks: Sequence[Task], method: str) -> Task:
    if not tasks:
        raise ValueError("cannot route an empty task pool")
    if method == "nearest":
        return nearest_task(current, tasks)
    if method == "open_route":
        return open_route_first(current, tasks)
    if method == "route_consequence":
        return one_step_route_consequence(current, tasks)
    raise ValueError(f"unknown W4-A routing method: {method}")
