from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.case import generate_case, generate_stress_case
from offline_sim.harness import ActionRecord, EpisodeResult, run_episode
from q3.geometry import distance
from q3.models import Point
from q3.offline_policy import Task
from q4.run_w0_baseline import markdown_table, parse_seed_range, percentile, write_csv
from q4.run_w3_benchmark import _reacquisition_keys
from q4.w1_policy import w1_search_points
from q4.w3_policy import W3CoarseToFinePolicy


LONG_JUMP_M = 500.0
VERY_LONG_JUMP_M = 1000.0
BACKTRACK_MIN_LEG_M = 100.0
BACKTRACK_ANGLE_DEG = 120.0


class W3InstrumentedPolicy(W3CoarseToFinePolicy):
    """Decision-identical W3 with policy-visible task-pool diagnostics."""

    def __init__(self, runner: Any):
        super().__init__(runner, mode="adaptive")
        self._first_clear_ready: set[int] = set()

    def build_dynamic_tasks(self) -> list[Task]:
        tasks = super().build_dynamic_tasks()
        current = self.client.current_position
        for task in tasks:
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
                task_pool_size=len(tasks),
            )
        return tasks

    def execute_task(self, task: Task) -> None:
        current = self.client.current_position
        self.emit(
            "w4a_selected_task",
            time_s=self.client.last_virtual_time_s,
            kind=task.kind,
            channel=task.channel,
            search_index=task.search_index,
            current_x=current.x,
            current_y=current.y,
            task_x=task.point.x,
            task_y=task.point.y,
        )
        super().execute_task(task)


def policy_w3_instrumented(runner: Any) -> None:
    W3InstrumentedPolicy(runner).run()


def action_categories(result: EpisodeResult) -> list[str]:
    search_points = w1_search_points()
    reacquisition = _reacquisition_keys(result)
    categories: list[str] = []
    for action in result.action_log:
        if action.action == "clear":
            categories.append("clear")
            continue
        key = (int(action.channel), round(float(action.virtual_time_s) * 1_000_000))
        if key in reacquisition:
            categories.append("reacquisition")
        elif any(math.hypot(action.x - point.x, action.y - point.y) <= 1e-6 for point in search_points):
            categories.append("backbone")
        else:
            categories.append("localization")
    return categories


def action_movements(actions: list[ActionRecord]) -> list[float]:
    previous = (0.0, 0.0)
    output: list[float] = []
    for action in actions:
        output.append(math.hypot(action.x - previous[0], action.y - previous[1]))
        previous = (action.x, action.y)
    return output


def turn_angle_deg(a: ActionRecord, b: ActionRecord, c: ActionRecord) -> float | None:
    ux, uy = b.x - a.x, b.y - a.y
    vx, vy = c.x - b.x, c.y - b.y
    nu, nv = math.hypot(ux, uy), math.hypot(vx, vy)
    if nu < BACKTRACK_MIN_LEG_M or nv < BACKTRACK_MIN_LEG_M:
        return None
    cosine = max(-1.0, min(1.0, (ux * vx + uy * vy) / (nu * nv)))
    return math.degrees(math.acos(cosine))


def clear_regret_rows(suite: str, seed: int, result: EpisodeResult) -> list[dict[str, Any]]:
    ready = {
        int(row["channel"]): row
        for row in result.policy_diagnostics
        if row.get("event") == "w4a_first_clear_ready"
    }
    actions = result.action_log
    output: list[dict[str, Any]] = []
    for channel, event in ready.items():
        clear_index = next(
            (
                index
                for index, action in enumerate(actions)
                if action.action == "clear"
                and action.channel == channel
                and action.virtual_time_s + 1e-6 >= float(event["time_s"])
            ),
            None,
        )
        if clear_index is None:
            continue
        start = Point(float(event["current_x"]), float(event["current_y"]))
        clear_action = actions[clear_index]
        clear_point = Point(clear_action.x, clear_action.y)
        relevant = [
            action
            for action in actions[: clear_index + 1]
            if action.virtual_time_s + 1e-6 >= float(event["time_s"])
        ]
        actual_path = 0.0
        current = start
        for action in relevant:
            point = Point(action.x, action.y)
            actual_path += distance(current, point)
            current = point
        direct = distance(start, clear_point)
        output.append(
            {
                "suite": suite,
                "seed": seed,
                "channel": channel,
                "ready_time_s": event["time_s"],
                "clear_time_s": clear_action.virtual_time_s,
                "delay_time_s": clear_action.virtual_time_s - float(event["time_s"]),
                "delayed_actions": max(0, len(relevant) - 1),
                "direct_distance_m": direct,
                "actual_path_until_clear_m": actual_path,
                "clear_delay_path_excess_m": max(0.0, actual_path - direct),
                "task_pool_size_at_ready": event["task_pool_size"],
            }
        )
    return output


def decompose_episode(suite: str, seed: int, result: EpisodeResult) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    categories = action_categories(result)
    movements = action_movements(result.action_log)
    transitions: defaultdict[str, float] = defaultdict(float)
    transition_counts: Counter[str] = Counter()
    previous_category = "origin"
    for category, movement in zip(categories, movements):
        key = f"{previous_category}->{category}"
        transitions[key] += movement
        transition_counts[key] += int(movement > 1e-6)
        previous_category = category

    positive_movements = [value for value in movements if value > 1e-6]
    angles = [
        angle
        for left, middle, right in zip(result.action_log, result.action_log[1:], result.action_log[2:])
        if (angle := turn_angle_deg(left, middle, right)) is not None
    ]
    clear_regrets = clear_regret_rows(suite, seed, result)
    row: dict[str, Any] = {
        "suite": suite,
        "seed": seed,
        "success": int(result.success),
        "total_time_s": result.virtual_time_s,
        "move_distance_m": result.move_distance_m,
        "move_count": len(positive_movements),
        "mean_positive_jump_m": statistics.fmean(positive_movements) if positive_movements else 0.0,
        "p95_positive_jump_m": percentile(positive_movements, 0.95),
        "max_jump_m": max(positive_movements, default=0.0),
        "long_jump_count_ge_500m": sum(value >= LONG_JUMP_M for value in movements),
        "long_jump_distance_ge_500m": sum(value for value in movements if value >= LONG_JUMP_M),
        "very_long_jump_count_ge_1000m": sum(value >= VERY_LONG_JUMP_M for value in movements),
        "backtrack_count": sum(angle >= BACKTRACK_ANGLE_DEG for angle in angles),
        "clear_to_backbone_count": transition_counts["clear->backbone"],
        "clear_to_backbone_distance_m": transitions["clear->backbone"],
        "clear_delay_path_excess_m": sum(float(row["clear_delay_path_excess_m"]) for row in clear_regrets),
        "delayed_clear_count": sum(int(row["delayed_actions"]) > 0 for row in clear_regrets),
    }
    for key, value in sorted(transitions.items()):
        row[f"distance_{key}"] = value
        row[f"count_{key}"] = transition_counts[key]
    return row, clear_regrets


def run_diagnosis(random_seeds: list[int], stress_seeds: list[int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    episodes: list[dict[str, Any]] = []
    clears: list[dict[str, Any]] = []
    suites = (("random", random_seeds, "smooth"), ("min_reff", stress_seeds, "adversarial"), ("collinear", stress_seeds, "adversarial"))
    for suite, seeds, field_kind in suites:
        for index, seed in enumerate(seeds, start=1):
            if suite == "random":
                case = generate_case(seed=seed, problem=4, mode="practice", field_kind=field_kind, margin_m=0.0)
            else:
                case = generate_stress_case(
                    suite,
                    seed=seed,
                    problem=4,
                    mode="practice",
                    field_kind=field_kind,
                    scan_points=[(point.x, point.y) for point in w1_search_points()],
                )
            result = run_episode(case, policy_w3_instrumented, include_oracles=False)
            row, clear_rows = decompose_episode(suite, seed, result)
            episodes.append(row)
            clears.extend(clear_rows)
            if index % 10 == 0 or index == len(seeds):
                print(f"[diagnosis/{suite}] {index}/{len(seeds)}", flush=True)
    return episodes, clears


def summarize_transitions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted({key.removeprefix("distance_") for row in rows for key in row if key.startswith("distance_")})
    mean_total = statistics.fmean(float(row["move_distance_m"]) for row in rows)
    output: list[dict[str, Any]] = []
    for key in keys:
        distances = [float(row.get(f"distance_{key}", 0.0)) for row in rows]
        counts = [int(row.get(f"count_{key}", 0)) for row in rows]
        mean_distance = statistics.fmean(distances)
        output.append(
            {
                "transition": key,
                "mean_distance_m": mean_distance,
                "share_of_total_move": mean_distance / mean_total,
                "mean_nonzero_transition_count": statistics.fmean(counts),
                "p95_episode_distance_m": percentile(distances, 0.95),
                "max_episode_distance_m": max(distances),
            }
        )
    return sorted(output, key=lambda row: float(row["mean_distance_m"]), reverse=True)


def render_report(out_dir: Path, episodes: list[dict[str, Any]], clears: list[dict[str, Any]], transitions: list[dict[str, Any]]) -> None:
    mean_move = statistics.fmean(float(row["move_distance_m"]) for row in episodes)
    transition_table = [
        [
            row["transition"],
            f"{row['mean_distance_m']:.2f}",
            f"{100*row['share_of_total_move']:.1f}%",
            f"{row['mean_nonzero_transition_count']:.2f}",
            f"{row['p95_episode_distance_m']:.2f}",
        ]
        for row in transitions
    ]
    clear_excess = [float(row["clear_delay_path_excess_m"]) for row in clears]
    lines = [
        "# Q4 W4-A pre-optimization movement diagnosis",
        "",
        "This is a decision-identical replay of frozen W3-adaptive. Instrumentation records only policy-visible task pools and action logs; it does not alter routing or read ground truth during policy execution.",
        "",
        f"Episodes: `{len(episodes)}`; full clear: `{sum(int(row['success']) for row in episodes)}/{len(episodes)}`; mean movement: `{mean_move:.2f}m`.",
        "",
        "## Movement transition decomposition",
        "",
        markdown_table(["Transition", "Mean distance m", "Share", "Mean count", "P95 episode m"], transition_table),
        "",
        "Categories are action destinations: backbone is any measure at one of the fixed 27 search points; reacquisition is a W3/W2 lifecycle probe; localization is another non-backbone measure; clear is a clear action. Movement is assigned from the previous action category to the next.",
        "",
        "## Route-shape diagnostics",
        "",
        f"- Mean >=500m jumps: `{statistics.fmean(float(row['long_jump_count_ge_500m']) for row in episodes):.2f}` per episode; their mean summed distance is `{statistics.fmean(float(row['long_jump_distance_ge_500m']) for row in episodes):.2f}m`.",
        f"- Mean >=1000m jumps: `{statistics.fmean(float(row['very_long_jump_count_ge_1000m']) for row in episodes):.2f}` per episode.",
        f"- Mean geometric backtracks: `{statistics.fmean(float(row['backtrack_count']) for row in episodes):.2f}` per episode, defined as consecutive >100m legs with a turn >=120 degrees.",
        f"- Clear -> backbone transitions: `{statistics.fmean(float(row['clear_to_backbone_count']) for row in episodes):.2f}` per episode, `{statistics.fmean(float(row['clear_to_backbone_distance_m']) for row in episodes):.2f}m`.",
        "",
        "## Clear-delay path-excess proxy",
        "",
        f"For `{len(clears)}` targets whose MEC clear task became visible to the router, mean/median/P95 path excess from first readiness until actual clear is `{statistics.fmean(clear_excess) if clear_excess else 0.0:.2f}` / `{statistics.median(clear_excess) if clear_excess else 0.0:.2f}` / `{percentile(clear_excess, 0.95):.2f}m`. This is a scheduling-regret proxy, not a strict avoidable-distance lower bound, because intervening tasks may themselves be mandatory.",
        "",
        "The diagnosis intentionally precedes W4-A policy changes. Detection-point pruning is not performed.",
    ]
    (out_dir / "routing_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Decision-identical W3 movement diagnosis")
    parser.add_argument("--random-seeds", default="0:100")
    parser.add_argument("--stress-seeds", default="10000:10050")
    parser.add_argument("--out-dir", default="results/q4/w4a_diagnosis")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.report_only:
        with (out_dir / "episode_movement.csv").open(newline="", encoding="utf-8") as handle:
            episodes = list(csv.DictReader(handle))
        with (out_dir / "clear_delay_regret.csv").open(newline="", encoding="utf-8") as handle:
            clears = list(csv.DictReader(handle))
    else:
        episodes, clears = run_diagnosis(parse_seed_range(args.random_seeds), parse_seed_range(args.stress_seeds))
        write_csv(out_dir / "episode_movement.csv", episodes)
        write_csv(out_dir / "clear_delay_regret.csv", clears)
    transitions = summarize_transitions(episodes)
    write_csv(out_dir / "movement_decomposition.csv", transitions)
    metadata = {
        "environment": "local offline_sim/practice only",
        "problem": 4,
        "margin_m": 0.0,
        "policy": "decision-identical W3-adaptive instrumentation",
        "official_practice_run": False,
        "official_formal_test_run": False,
        "thresholds_are_diagnostic_only": {
            "long_jump_m": LONG_JUMP_M,
            "very_long_jump_m": VERY_LONG_JUMP_M,
            "backtrack_min_leg_m": BACKTRACK_MIN_LEG_M,
            "backtrack_angle_deg": BACKTRACK_ANGLE_DEG,
        },
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    render_report(out_dir, episodes, clears, transitions)
    print(f"wrote {out_dir / 'routing_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
