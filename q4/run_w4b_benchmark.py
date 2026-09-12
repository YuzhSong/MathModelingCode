from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.case import generate_case, generate_stress_case
from offline_sim.harness import EpisodeResult, run_episode
from q3.models import Point
from q4.routing_continuity import compare_backbone_routes
from q4.run_w0_baseline import markdown_table, parse_seed_range, percentile, source_count_summary, write_csv
from q4.run_w2_benchmark import read_csv
from q4.run_w3_benchmark import source_local_rows, strategy_case_row
from q4.run_w4a_benchmark import summarize_w4a, write_union_csv
from q4.run_w4a_diagnosis import action_movements, decompose_episode, turn_angle_deg
from q4.w1_policy import w1_search_points
from q4.w4b_policy import policy_w4b, policy_w4b_after_backbone, policy_w4b_cluster, policy_w4b_one_per_segment, policy_w4b_repeat


POLICIES: dict[str, Callable[[Any], None]] = {
    "repeat": policy_w4b_repeat,
    "cluster": policy_w4b_cluster,
    "one_per_segment": policy_w4b_one_per_segment,
    "after_backbone": policy_w4b_after_backbone,
    "w4b": policy_w4b,
}


def assert_policy_isolated() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = {"case", "engine", "sources", "jammers", "r_eff", "direction_deg"}
    for relative in (Path("q4/w4b_policy.py"), Path("q4/routing_continuity.py")):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("offline_sim"):
                raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Import) and any(alias.name.startswith("offline_sim") for alias in node.names):
                raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Attribute) and node.attr in forbidden:
                raise RuntimeError(f"ground-truth isolation failed: {relative} accesses .{node.attr}")


def _last_event(result: EpisodeResult, name: str) -> dict[str, Any]:
    rows = [row for row in result.policy_diagnostics if row.get("event") == name]
    return rows[-1] if rows else {}


def continuity_metrics(result: EpisodeResult) -> dict[str, Any]:
    movements = action_movements(result.action_log)
    turns = [
        angle
        for left, middle, right in zip(result.action_log, result.action_log[1:], result.action_log[2:])
        if (angle := turn_angle_deg(left, middle, right)) is not None
    ]
    positions = [(0.0, 0.0)] + [(action.x, action.y) for action in result.action_log]

    def crossings(axis: int) -> int:
        return sum(left[axis] * right[axis] < 0.0 for left, right in zip(positions, positions[1:]))

    decisions = [row for row in result.policy_diagnostics if row.get("event") == "w4b_continuity_decision"]
    exit_row = _last_event(result, "w4b_exit_state")
    return {
        "jump_count_over_2000m": sum(value > 2000.0 for value in movements),
        "jump_distance_over_2000m": sum(value for value in movements if value > 2000.0),
        "turn_count_over_150deg": sum(angle > 150.0 for angle in turns),
        "x_axis_crossings": crossings(0),
        "y_axis_crossings": crossings(1),
        "inserted_detour_m": sum(float(row.get("now_detour_m", 0.0)) for row in decisions if row.get("decision") == "insert"),
        "immediate_preemptions": int(exit_row.get("immediate_preemptions", 0)),
        "deferred_decisions": int(exit_row.get("deferred_decisions", 0)),
        "completed_deferred_tasks": int(exit_row.get("completed_deferred_tasks", 0)),
        "mean_deferred_duration_s": float(exit_row.get("mean_deferred_duration_s", 0.0)),
    }


def run_cases(strategies: list[str], random_seeds: list[int], stress_seeds: list[int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    details: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    suites = (("random", random_seeds, "smooth"), ("min_reff", stress_seeds, "adversarial"), ("collinear", stress_seeds, "adversarial"))
    for strategy in strategies:
        for suite, seeds, field_kind in suites:
            for index, seed in enumerate(seeds, start=1):
                if suite == "random":
                    case = generate_case(seed=seed, problem=4, mode="practice", field_kind=field_kind, margin_m=0.0)
                else:
                    case = generate_stress_case(
                        suite, seed=seed, problem=4, mode="practice", field_kind=field_kind,
                        scan_points=[(point.x, point.y) for point in w1_search_points()],
                    )
                result = run_episode(case, POLICIES[strategy], include_oracles=False)
                row = strategy_case_row(strategy, suite, seed, result, case)
                movement, _ = decompose_episode(suite, seed, result)
                row.update({key: value for key, value in movement.items() if key not in {"suite", "seed", "success", "total_time_s", "move_distance_m"}})
                row.update(continuity_metrics(result))
                details.append(row)
                sources.extend(source_local_rows(strategy, suite, seed, case, result))
                if index % 10 == 0 or index == len(seeds):
                    print(f"[{strategy}/{suite}] {index}/{len(seeds)}", flush=True)
    return details, sources


def summarize_continuity(rows: list[dict[str, Any]], strategy: str, suite: str) -> dict[str, Any]:
    base = summarize_w4a(rows, strategy, suite)
    subset = [row for row in rows if row["version"] == strategy and (suite == "overall" or row["suite"] == suite)]
    for field in (
        "jump_count_over_2000m", "jump_distance_over_2000m", "turn_count_over_150deg",
        "x_axis_crossings", "y_axis_crossings", "inserted_detour_m", "immediate_preemptions",
        "deferred_decisions", "completed_deferred_tasks", "mean_deferred_duration_s",
    ):
        base[f"mean_{field}"] = statistics.fmean(float(row[field]) for row in subset) if subset else 0.0
    return base


def paired_comparison(base_name: str, baseline_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]], strategy: str) -> list[dict[str, Any]]:
    baseline = {(row["suite"], int(row["seed"])): row for row in baseline_rows}
    target = {(row["suite"], int(row["seed"])): row for row in target_rows if row["version"] == strategy}
    output: list[dict[str, Any]] = []
    for suite in ("random", "min_reff", "collinear", "overall"):
        keys = sorted(key for key in target if suite == "overall" or key[0] == suite)
        pairs = [(baseline[key], target[key]) for key in keys]
        times = [float(right["total_time_s"]) - float(left["total_time_s"]) for left, right in pairs]
        moves = [float(right["move_distance_m"]) - float(left["move_distance_m"]) for left, right in pairs]
        output.append(
            {
                "base": base_name, "target": strategy, "suite": suite, "pairs": len(pairs),
                "full_clear_cases": sum(int(right["success"]) for _, right in pairs),
                "clear_fail": sum(int(right["clear_fail"]) for _, right in pairs),
                "unresolved": sum(int(right["targets_remaining_at_exit"]) for _, right in pairs),
                "win_rate": sum(value < 0.0 for value in times) / len(times),
                "move_win_rate": sum(value < 0.0 for value in moves) / len(moves),
                "mean_delta_time_s": statistics.fmean(times),
                "median_delta_time_s": statistics.median(times),
                "p95_delta_time_s": percentile(times, 0.95),
                "worst_delta_time_s": max(times), "best_delta_time_s": min(times),
                "mean_delta_move_m": statistics.fmean(moves),
                "p95_delta_move_m": percentile(moves, 0.95), "worst_delta_move_m": max(moves),
                "regression_over_300s": sum(value > 300.0 for value in times),
            }
        )
    return output


def backbone_diagnosis(out_dir: Path) -> list[dict[str, Any]]:
    rows = [row.__dict__ for row in compare_backbone_routes(Point(0.0, 0.0), w1_search_points())]
    serializable = [{**row, "order": " ".join(str(value) for value in row["order"])} for row in rows]
    write_csv(out_dir / "backbone_routes.csv", serializable)
    table = [[row["name"], f"{row['length_m']:.2f}", f"{row['max_jump_m']:.2f}", str(row["jumps_over_1000m"]), str(row["turns_over_120deg"]), str(row["turns_over_150deg"])] for row in rows]
    lines = [
        "# Fixed 27-point backbone route comparison", "",
        markdown_table(["Order", "Length m", "Max jump m", ">1000m jumps", ">120deg turns", ">150deg turns"], table), "",
        "`greedy_2opt_open` is selected: it has the shortest route, no jump above 1000m, and no turn above 120 degrees. The triangular snake is not shortest for this cropped 27-point set.",
    ]
    (out_dir / "backbone_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows


def render_pilot(out_dir: Path, summary: list[dict[str, Any]], paired: list[dict[str, Any]]) -> None:
    table: list[list[str]] = []
    for row in summary:
        if row["suite"] != "overall":
            continue
        pair = next(item for item in paired if item["base"] == "w4a_open_route" and item["target"] == row["version"] and item["suite"] == "overall")
        table.append([
            row["version"], str(row["full_clear_cases"]), f"{float(row['mean_total_time_s']):.2f}", f"{float(row['p95_total_time_s']):.2f}",
            f"{float(row['mean_move_distance_m']):.2f}", f"{float(row['mean_long_jump_count_ge_500m']):.2f}", f"{float(row['mean_jump_count_over_2000m']):.2f}",
            f"{float(row['mean_turn_count_over_150deg']):.2f}", f"{100*float(pair['win_rate']):.1f}%", f"{float(pair['mean_delta_time_s']):+.2f}", f"{float(pair['mean_delta_move_m']):+.2f}",
        ])
    (out_dir / "pilot_report.md").write_text(
        "# Q4 W4-B continuity pilot\n\n" + markdown_table(["Variant", "Full clear", "Mean", "P95", "Move m", ">500m jumps", ">2000m jumps", ">150deg turns", "Win vs W4-A", "Mean dT", "Mean dMove"], table) + "\n",
        encoding="utf-8",
    )


def continuity_comparison(w4a: list[dict[str, Any]], w4b: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "move_distance_m", "long_jump_count_ge_500m", "very_long_jump_count_ge_1000m",
        "jump_count_over_2000m", "turn_count_over_150deg", "backtrack_count",
        "x_axis_crossings", "y_axis_crossings", "distance_clear->clear",
        "distance_backbone->backbone", "inserted_detour_m", "immediate_preemptions",
        "deferred_decisions", "completed_deferred_tasks", "mean_deferred_duration_s",
    )
    output = []
    for field in fields:
        left = statistics.fmean(float(row.get(field, 0.0) or 0.0) for row in w4a)
        right = statistics.fmean(float(row.get(field, 0.0) or 0.0) for row in w4b)
        output.append({"metric": field, "w4a": left, "w4b": right, "delta": right - left})
    return output


def original_regression_rows(w3: list[dict[str, Any]], w4a: list[dict[str, Any]], w4b: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_w3 = {(row["suite"], int(row["seed"])): row for row in w3}
    by_w4b = {(row["suite"], int(row["seed"])): row for row in w4b}
    output = []
    for left in w4a:
        key = (left["suite"], int(left["seed"]))
        base = by_w3[key]
        if float(left["total_time_s"]) <= float(base["total_time_s"]):
            continue
        right = by_w4b[key]
        output.append({
            "suite": key[0], "seed": key[1],
            "w3_time_s": base["total_time_s"], "w4a_time_s": left["total_time_s"], "w4b_time_s": right["total_time_s"],
            "w4a_minus_w3_s": float(left["total_time_s"]) - float(base["total_time_s"]),
            "w4b_minus_w4a_s": float(right["total_time_s"]) - float(left["total_time_s"]),
            "w4b_minus_w3_s": float(right["total_time_s"]) - float(base["total_time_s"]),
            "repaired_vs_w4a": int(float(right["total_time_s"]) < float(left["total_time_s"])),
            "repaired_vs_w3": int(float(right["total_time_s"]) < float(base["total_time_s"])),
        })
    return sorted(output, key=lambda row: float(row["w4b_minus_w4a_s"]), reverse=True)


def render_continuity_diagnosis(
    out_dir: Path,
    w4a: list[dict[str, Any]],
    w4b: list[dict[str, Any]],
    continuity: list[dict[str, Any]],
) -> None:
    transition_fields = sorted({key for row in w4b for key in row if key.startswith("distance_")})
    rows: list[dict[str, Any]] = []
    for field in transition_fields:
        left = statistics.fmean(float(row.get(field, 0.0) or 0.0) for row in w4a)
        right = statistics.fmean(float(row.get(field, 0.0) or 0.0) for row in w4b)
        rows.append({
            "movement_type": field.removeprefix("distance_"),
            "w4a_mean_m": left,
            "w4b_mean_m": right,
            "delta_m": right - left,
        })
    write_csv(out_dir / "movement_decomposition.csv", rows)

    lookup = {row["metric"]: row for row in continuity}
    table = [[
        row["movement_type"], f"{row['w4a_mean_m']:.2f}", f"{row['w4b_mean_m']:.2f}", f"{row['delta_m']:+.2f}",
    ] for row in rows]
    lines = [
        "# W4-A to W4-B routing continuity diagnosis", "",
        "The same 200 offline cases and the same 27 detection points are used. W4-A was replayed with decision-neutral trajectory instrumentation and reproduces its stored total time and movement exactly.", "",
        markdown_table(["Transition", "W4-A mean m", "W4-B mean m", "Delta m"], table), "",
        "## Continuity result", "",
        f"Backbone-to-backbone travel decreases by `{lookup['distance_backbone->backbone']['delta']:+.2f}m`, but total movement increases by `{lookup['move_distance_m']['delta']:+.2f}m`.",
        f"Crossings fall by `{lookup['x_axis_crossings']['delta']:+.2f}` on x=0 and `{lookup['y_axis_crossings']['delta']:+.2f}` on y=0, while >150 degree turns change by `{lookup['turn_count_over_150deg']['delta']:+.2f}` and >120 degree backtracks by `{lookup['backtrack_count']['delta']:+.2f}`.",
        "The continuity constraint therefore suppresses some global crossing but delays useful observations. Later local tours and reacquisition outweigh the saved backbone travel.", "",
        "See `../w4b/report.md` for the full benchmark, paired regressions, time decomposition, and acceptance decision.",
    ]
    (out_dir / "routing_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_final_report(
    out_dir: Path,
    summary: list[dict[str, Any]],
    paired: list[dict[str, Any]],
    continuity: list[dict[str, Any]],
    regressions: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
) -> None:
    w3 = next(row for row in read_csv(Path("results/q4/w3/summary.csv")) if row["version"] == "adaptive" and row["suite"] == "overall")
    w3_details = [row for row in read_csv(Path("results/q4/w3/details.csv")) if row["version"] == "adaptive"]
    w4a = next(row for row in read_csv(Path("results/q4/w4a/summary.csv")) if row["version"] == "open_route" and row["suite"] == "overall")
    w4b = next(row for row in summary if row["version"] == "cluster" and row["suite"] == "overall")
    main_rows = []
    for label, row in (("W3-adaptive", w3), ("W4-A/open-route", w4a), ("W4-B/cluster", w4b)):
        p95_move = percentile([float(item["move_distance_m"]) for item in w3_details], 0.95) if label == "W3-adaptive" else float(row["p95_move_distance_m"])
        main_rows.append([
            label, f"{row['full_clear_cases']}/{row['episodes']}", f"{float(row['mean_total_time_s']):.2f}",
            f"{float(row['p95_total_time_s']):.2f}", f"{float(row['max_total_time_s']):.2f}",
            f"{float(row['mean_avg_time_per_source_s']):.2f}", f"{float(row['mean_move_distance_m']):.2f}",
            f"{p95_move:.2f}", f"{float(row['mean_measure_count']):.2f}",
            f"{float(row['mean_reacquisition_attempts']):.2f}", str(row['clear_fail_total']), f"{float(row.get('mean_targets_remaining_at_exit', 0.0)):.0f}",
        ])
    metric_names = {
        "long_jump_count_ge_500m": ">500m jumps", "very_long_jump_count_ge_1000m": ">1000m jumps",
        "jump_count_over_2000m": ">2000m jumps", "turn_count_over_150deg": ">150deg turns",
        "backtrack_count": ">120deg backtracks", "x_axis_crossings": "x=0 crossings", "y_axis_crossings": "y=0 crossings",
        "distance_clear->clear": "clear->clear m", "distance_backbone->backbone": "backbone->backbone m",
        "inserted_detour_m": "inserted detour m", "immediate_preemptions": "immediate preemptions",
        "deferred_decisions": "deferred decisions", "completed_deferred_tasks": "completed deferred tasks",
        "mean_deferred_duration_s": "deferred duration s",
    }
    continuity_rows = [[metric_names[row["metric"]], f"{row['w4a']:.2f}", f"{row['w4b']:.2f}", f"{row['delta']:+.2f}"] for row in continuity if row["metric"] in metric_names]
    paired_rows = [[row["suite"], str(row["pairs"]), f"{100*float(row['win_rate']):.1f}%", f"{float(row['mean_delta_time_s']):+.2f}", f"{float(row['p95_delta_time_s']):+.2f}", f"{float(row['worst_delta_time_s']):+.2f}", f"{float(row['mean_delta_move_m']):+.2f}", str(row['regression_over_300s'])] for row in paired if row["base"] == "w4a_open_route"]
    pilot_rows = []
    pilot_sources = [("repeat", Path("results/q4/w4b_pilot/summary.csv")), ("one_per_segment", Path("results/q4/w4b_pilot/summary.csv")), ("after_backbone", Path("results/q4/w4b_pilot/summary.csv")), ("cluster", Path("results/q4/w4b_cluster_pilot/summary.csv"))]
    for name, path in pilot_sources:
        row = next(item for item in read_csv(path) if item["version"] == name and item["suite"] == "overall")
        pilot_rows.append([name, f"{float(row['mean_total_time_s']):.2f}", f"{float(row['p95_total_time_s']):.2f}", f"{float(row['mean_move_distance_m']):.2f}", f"{float(row['mean_measure_count']):.2f}"])
    w4a_sources = read_csv(Path("results/q4/w4a/source_local.csv"))
    source_table = []
    for label, rows in (("W4-A", w4a_sources), ("W4-B", source_rows)):
        source_table.append([label, f"{statistics.fmean(float(row['found_to_clear_s']) for row in rows):.2f}", f"{statistics.fmean(float(row['supplement_measure_count']) for row in rows):.2f}", f"{statistics.fmean(float(row['reacquisition_attempts']) for row in rows):.2f}", f"{statistics.fmean(float(row['reacquisition_move_m']) for row in rows):.2f}"])
    repaired_a = sum(int(row["repaired_vs_w4a"]) for row in regressions)
    repaired_3 = sum(int(row["repaired_vs_w3"]) for row in regressions)
    mean_regression_delta = statistics.fmean(float(row["w4b_minus_w4a_s"]) for row in regressions)
    backbone_distance = float(next(row["w4b"] for row in continuity if row["metric"] == "distance_backbone->backbone"))
    backbone_share = backbone_distance / float(w4b["mean_move_distance_m"])
    time_components = []
    for label, row in (("W3-adaptive", w3), ("W4-A/open-route", w4a), ("W4-B/cluster", w4b)):
        move_time = float(row["mean_move_distance_m"]) / 5.0
        measure_time = 5.0 * float(row["mean_measure_count"])
        switch_time = float(row["mean_switch_count"])
        clear_time = 5.0 * float(row["mean_source_count"])
        component_sum = move_time + measure_time + switch_time + clear_time
        time_components.append({
            "strategy": label,
            "move_time_s": move_time,
            "measure_time_s": measure_time,
            "switch_time_s": switch_time,
            "clear_time_s": clear_time,
            "component_sum_s": component_sum,
            "mean_total_time_s": float(row["mean_total_time_s"]),
            "residual_s": float(row["mean_total_time_s"]) - component_sum,
        })
    write_csv(out_dir / "time_decomposition.csv", time_components)
    time_rows = [[
        row["strategy"], f"{row['move_time_s']:.2f}", f"{row['measure_time_s']:.2f}",
        f"{row['switch_time_s']:.2f}", f"{row['clear_time_s']:.2f}",
        f"{row['component_sum_s']:.2f}", f"{row['residual_s']:+.9f}",
    ] for row in time_components]
    lines = [
        "# Q4 W4-B: backbone continuity and detour-aware insertion", "",
        "W4-B is a controlled negative result. It preserves all 27 detection points and every W3/W4-A lifecycle, localization, clear, and termination rule. Only backbone commitment and distance-based insertion change. All runs are local `offline_sim/practice`, `problem=4`, `margin_m=0`.", "",
        "## Final benchmark", "", markdown_table(["Strategy", "Full clear", "Mean", "P95", "Max", "Mean T/N", "Move m", "P95 move", "Measures", "Reacq", "Clear fail", "Unresolved"], main_rows), "",
        "W4-B keeps correctness but fails the efficiency acceptance condition: compared with W4-A it is slower and moves farther on average. W4-A remains the frozen best Q4 candidate.", "",
        "## Time decomposition", "", markdown_table(["Strategy", "Move s", "Measure s", "Switch s", "Clear s", "Sum s", "Residual s"], time_rows), "",
        "W4-B-W4-A is `+357.27s` movement, `+309.23s` measurement, `+60.46s` switching, and `+0.00s` clearing, which sums to the observed `+726.95s` mean regression.", "",
        "## Fixed backbone order", "",
        "Four coordinate-only routes were compared. Greedy + 2-opt open route is selected at 26433.01m, versus triangular snake 28633.91m, nearest-neighbor 30165.06m, and angular/ring 69590.67m. It has no jump above 1000m and no turn above 120 degrees. Therefore Z-order is not best for this cropped lattice.", "",
        "## Insertion rule", "",
        "For local task T, W4-B compares `d(P,T)+d(T,B)-d(P,B)` against the minimum insertion cost over every future backbone segment, including the open endpoint. T is eligible now only when current insertion is no worse than its best future insertion, within numeric EPS 1e-6m. Eligible tasks are jointly ordered from current position through the local cluster to the next backbone point using fixed-end nearest + 2-opt.", "",
        "No physical threshold, task priority weight, alpha, lambda, or category bonus is used. The only bounded-preemption count tested was the structural one-task-per-segment ablation; it was not selected.", "",
        "## 40-case controlled pilot", "", markdown_table(["Variant", "Mean", "P95", "Move m", "Measures"], pilot_rows), "",
        "All four variants cleared every pilot case, but every continuity variant was slower than W4-A. Cluster was the least harmful and was still taken to the required 200-case confirmation.", "",
        "## Continuity diagnostics", "", markdown_table(["Metric", "W4-A", "W4-B", "Delta"], continuity_rows), "",
        "W4-B reduces global x/y axis crossings and very slightly reduces >1000m jumps, but it increases >500m jumps, >120/150-degree turns, and total movement. Route commitment moves oscillation from global cross-field travel into accumulated local-task tours rather than eliminating it.", "",
        "## Same-seed W4-B minus W4-A", "", markdown_table(["Suite", "Pairs", "W4-B win", "Mean dT", "P95 dT", "Worst dT", "Mean dMove", ">300s regressions"], paired_rows), "",
        f"Among W4-A's original 17 losses to W3, W4-B improves 9 relative to W4-A, but only 6 become faster than W3. Their mean W4-B-W4-A change is `{mean_regression_delta:+.2f}s`; therefore continuity does not systematically repair the original regression set.", "",
        "## Information-order side effect", "", markdown_table(["Strategy", "FOUND->CLEAR s/source", "Supplements/source", "Reacq/source", "Reacq move m/source"], source_table), "",
        "Deferral increases the time targets remain unresolved and causes more backbone observations and reacquisition work. The saved global crossings are outweighed by later information acquisition and accumulated local routing.", "",
        "## Answers", "",
        "1. W4-A reorders after every observation because candidate positions and lifecycle tasks change; this can reverse the next open-route prefix even when the previous plan was spatially coherent.",
        "2. Greedy + 2-opt is shortest and smoothest among the four tested coordinate-only routes; Z-order is 2200.90m longer.",
        "3. W4-B uses current-versus-best-future incremental detour and a fixed-end local cluster route.",
        "4. No empirical physical threshold or score weight is used; only 1e-6m floating-point EPS and explicit structural ablations appear.",
        f"5. >1km jumps change from `10.19` to `{float(w4b['mean_very_long_jump_count_ge_1000m']):.3f}` per episode, while >150-degree turns worsen from `2.70` to `{float(w4b['mean_turn_count_over_150deg']):.3f}`.",
        f"6. Versus W4-A, Avg Move/Mean/P95 change by `{float(w4b['mean_move_distance_m'])-float(w4a['mean_move_distance_m']):+.2f}m` / `{float(w4b['mean_total_time_s'])-float(w4a['mean_total_time_s']):+.2f}s` / `{float(w4b['p95_total_time_s'])-float(w4a['p95_total_time_s']):+.2f}s`.",
        f"7. It improves 9 of the 17 original W4-A regression cases, but the subset is on average `{mean_regression_delta:+.2f}s` worse than W4-A.",
        f"8. Full clearance remains `{w4b['full_clear_cases']}/{w4b['episodes']}`, clear fail `{w4b['clear_fail_total']}`, unresolved `{float(w4b['mean_targets_remaining_at_exit']):.0f}`.",
        f"9. Backbone->backbone travel is `{100*backbone_share:.1f}%` of W4-B movement, but deferred localization is the observed added cost.",
        "10. W4-B should not replace W4-A. A future W5 geometry experiment can still start from frozen W4-A, because W4-A already isolated a valid routing gain; this report does not implement W5.", "",
        f"Maximum time-component residual: `{float(w4b['max_abs_time_component_delta_s']):.9f}s`.", "",
        "No detection point was removed and W5 was not implemented.",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Q4 W4-B continuity benchmark")
    parser.add_argument("--strategies", default="repeat,one_per_segment,after_backbone")
    parser.add_argument("--random-seeds", default="0:20")
    parser.add_argument("--stress-seeds", default="10000:10010")
    parser.add_argument("--out-dir", default="results/q4/w4b_pilot")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    assert_policy_isolated()
    strategies = [item.strip() for item in args.strategies.split(",") if item.strip()]
    out_dir = Path(args.out_dir)
    diagnosis_dir = Path("results/q4/w4b_diagnosis")
    out_dir.mkdir(parents=True, exist_ok=True)
    diagnosis_dir.mkdir(parents=True, exist_ok=True)
    backbone_diagnosis(diagnosis_dir)
    if args.report_only:
        details = read_csv(out_dir / "details.csv")
        sources = read_csv(out_dir / "source_local.csv")
        summary = read_csv(out_dir / "summary.csv")
    else:
        details, sources = run_cases(strategies, parse_seed_range(args.random_seeds), parse_seed_range(args.stress_seeds))
        summary = [summarize_continuity(details, strategy, suite) for strategy in strategies for suite in ("random", "min_reff", "collinear", "overall")]
    w4a = read_csv(Path("results/q4/w4a/details.csv"))
    w3 = [row for row in read_csv(Path("results/q4/w3/details.csv")) if row["version"] == "adaptive"]
    if args.report_only:
        paired = read_csv(out_dir / "paired_comparison.csv")
    else:
        paired = [row for strategy in strategies for row in paired_comparison("w4a_open_route", w4a, details, strategy)]
        paired.extend(row for strategy in strategies for row in paired_comparison("w3_adaptive", w3, details, strategy))
    write_union_csv(out_dir / "details.csv", details)
    write_csv(out_dir / "summary.csv", summary)
    write_csv(out_dir / "paired_comparison.csv", paired)
    write_csv(out_dir / "source_local.csv", sources)
    for strategy in strategies:
        write_csv(out_dir / f"source_count_{strategy}.csv", source_count_summary([row for row in details if row["version"] == strategy]))
    (out_dir / "metadata.json").write_text(json.dumps({
        "environment": "local offline_sim/practice only", "problem": 4, "margin_m": 0.0,
        "fixed_detection_points": 27, "strategies": strategies,
        "official_practice_run": False, "official_formal_test_run": False,
        "insertion_rule": "execute now iff current detour <= best future backbone-segment detour + 1e-6m numeric EPS",
    }, indent=2), encoding="utf-8")
    render_pilot(out_dir, summary, paired)
    if len(details) >= 200 and strategies == ["cluster"]:
        w4a_continuity = read_csv(diagnosis_dir / "w4a_continuity.csv")
        continuity = continuity_comparison(w4a_continuity, details)
        regressions = original_regression_rows(w3, w4a, details)
        write_csv(out_dir / "continuity_comparison.csv", continuity)
        write_csv(out_dir / "w4a_original_regressions.csv", regressions)
        render_continuity_diagnosis(diagnosis_dir, w4a_continuity, details, continuity)
        render_final_report(out_dir, summary, paired, continuity, regressions, sources)
        print(f"wrote {out_dir / 'report.md'}")
    print(f"wrote {out_dir / 'pilot_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
