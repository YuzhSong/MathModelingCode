"""Offline ordering oracle for a frozen W5Pro random/2 task trace.

The oracle keeps the selected task points fixed and only reorders them.  It is
diagnostic: it does not replay the simulator and must not be treated as a
valid policy result because observations are order-dependent.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def length(start: tuple[float, float], points: list[tuple[float, float]]) -> float:
    total = 0.0
    cursor = start
    for point in points:
        total += distance(cursor, point)
        cursor = point
    return total


def nearest_neighbor(start: tuple[float, float], points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pending = list(points)
    result: list[tuple[float, float]] = []
    cursor = start
    while pending:
        point = min(pending, key=lambda p: (distance(cursor, p), p[0], p[1]))
        result.append(point)
        pending.remove(point)
        cursor = point
    return result


def two_opt(start: tuple[float, float], points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    best = list(points)
    changed = True
    while changed:
        changed = False
        best_length = length(start, best)
        for i in range(len(best)):
            for j in range(i + 1, len(best)):
                candidate = best[:i] + list(reversed(best[i:j + 1])) + best[j + 1:]
                candidate_length = length(start, candidate)
                if candidate_length + 1e-9 < best_length:
                    best, best_length, changed = candidate, candidate_length, True
                    break
            if changed:
                break
    return best


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--speed-mps", type=float, default=5.0)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if args.speed_mps <= 0:
        parser.error("--speed-mps must be positive")
    trace = json.loads(args.trace.read_text(encoding="utf-8"))
    actions = trace["action_log"]
    selected = [event for event in trace["events"]
                if event.get("event") == "w5pro_selected_task"]
    points = [(float(event["task_x"]), float(event["task_y"])) for event in selected]
    if not points:
        raise SystemExit("trace contains no w5pro_selected_task events")
    start = (0.0, 0.0)
    actual = [(float(action["x"]), float(action["y"])) for action in actions]
    actual_distance = length(start, actual)
    oracle_order = two_opt(start, nearest_neighbor(start, points))
    oracle_distance = length(start, oracle_order)
    result = {
        "trace": str(args.trace),
        "selected_task_count": len(points),
        "actual_action_distance_m": actual_distance,
        "selected_task_path_distance_m": length(start, points),
        "oracle_task_path_distance_m": oracle_distance,
        "oracle_saving_m": length(start, points) - oracle_distance,
        "oracle_saving_s_at_speed": (length(start, points) - oracle_distance) / args.speed_mps,
        "actual_total_time_s": trace.get("details", {}).get("total_time_s"),
        "warning": "diagnostic lower-bound style reorder; not an executable policy result",
    }
    output = args.output or args.trace.with_name("refinement_oracle.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
