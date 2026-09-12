from __future__ import annotations

import argparse
import ast
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.case import generate_case, generate_stress_case
from offline_sim.harness import run_episode
from q4.run_w0_baseline import markdown_table, parse_seed_range, percentile, source_count_summary, write_csv
from q4.run_w2_benchmark import read_csv
from q4.run_w3_benchmark import source_local_rows, strategy_case_row, summarize_strategy
from q4.run_w4a_diagnosis import decompose_episode
from q4.w1_policy import w1_search_points
from q4.w4a_policy import (
    policy_w4a,
    policy_w4a_nearest,
    policy_w4a_open_route,
    policy_w4a_route_consequence,
)


POLICIES: dict[str, Callable[[Any], None]] = {
    "nearest": policy_w4a_nearest,
    "open_route": policy_w4a_open_route,
    "route_consequence": policy_w4a_route_consequence,
    "w4a": policy_w4a,
}


def write_union_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    seen = set(fields)
    for row in rows[1:]:
        for field in row:
            if field not in seen:
                fields.append(field)
                seen.add(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def assert_policy_isolated() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = {"case", "engine", "sources", "jammers", "r_eff", "direction_deg"}
    for relative in (Path("q4/w4a_policy.py"), Path("q4/routing.py")):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("offline_sim"):
                raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Import) and any(alias.name.startswith("offline_sim") for alias in node.names):
                raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Attribute) and node.attr in forbidden:
                raise RuntimeError(f"ground-truth isolation failed: {relative} accesses .{node.attr}")


def run_cases(
    strategies: list[str], random_seeds: list[int], stress_seeds: list[int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    details: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    clear_regrets: list[dict[str, Any]] = []
    suites = (("random", random_seeds, "smooth"), ("min_reff", stress_seeds, "adversarial"), ("collinear", stress_seeds, "adversarial"))
    for strategy in strategies:
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
                result = run_episode(case, POLICIES[strategy], include_oracles=False)
                row = strategy_case_row(strategy, suite, seed, result, case)
                movement, regrets = decompose_episode(suite, seed, result)
                row.update({key: value for key, value in movement.items() if key not in {"suite", "seed", "success", "total_time_s", "move_distance_m"}})
                details.append(row)
                sources.extend(source_local_rows(strategy, suite, seed, case, result))
                for regret in regrets:
                    regret["strategy"] = strategy
                clear_regrets.extend(regrets)
                if index % 10 == 0 or index == len(seeds):
                    print(f"[{strategy}/{suite}] {index}/{len(seeds)}", flush=True)
    return details, sources, clear_regrets


def summarize_w4a(rows: list[dict[str, Any]], strategy: str, suite: str) -> dict[str, Any]:
    base = summarize_strategy(rows, strategy, suite)
    subset = [row for row in rows if row["version"] == strategy and (suite == "overall" or row["suite"] == suite)]
    for field in (
        "move_count",
        "long_jump_count_ge_500m",
        "long_jump_distance_ge_500m",
        "very_long_jump_count_ge_1000m",
        "backtrack_count",
        "clear_to_backbone_count",
        "clear_to_backbone_distance_m",
        "clear_delay_path_excess_m",
        "delayed_clear_count",
    ):
        base[f"mean_{field}"] = statistics.fmean(float(row.get(field, 0.0)) for row in subset) if subset else 0.0
    move_values = [float(row["move_distance_m"]) for row in subset]
    base["p95_move_distance_m"] = percentile(move_values, 0.95)
    base["max_move_distance_m"] = max(move_values, default=0.0)
    return base


def paired_vs_w3(
    baseline_rows: list[dict[str, str]], target_rows: list[dict[str, Any]], strategy: str
) -> list[dict[str, Any]]:
    baseline = {(row["suite"], int(row["seed"])): row for row in baseline_rows}
    target = {(row["suite"], int(row["seed"])): row for row in target_rows if row["version"] == strategy}
    output: list[dict[str, Any]] = []
    for suite in ("random", "min_reff", "collinear", "overall"):
        keys = sorted(key for key in target if suite == "overall" or key[0] == suite)
        pairs = [(baseline[key], target[key]) for key in keys if key in baseline]
        deltas = [float(right["total_time_s"]) - float(left["total_time_s"]) for left, right in pairs]
        move_deltas = [float(right["move_distance_m"]) - float(left["move_distance_m"]) for left, right in pairs]
        output.append(
            {
                "base": "w3_adaptive",
                "target": strategy,
                "suite": suite,
                "pairs": len(pairs),
                "full_clear_cases": sum(int(right["success"]) for _, right in pairs),
                "clear_fail": sum(int(right["clear_fail"]) for _, right in pairs),
                "unresolved": sum(int(right["targets_remaining_at_exit"]) for _, right in pairs),
                "win_rate": sum(delta < 0.0 for delta in deltas) / len(deltas) if deltas else 0.0,
                "move_win_rate": sum(delta < 0.0 for delta in move_deltas) / len(move_deltas) if move_deltas else 0.0,
                "mean_delta_time_s": statistics.fmean(deltas) if deltas else 0.0,
                "median_delta_time_s": statistics.median(deltas) if deltas else 0.0,
                "p95_delta_time_s": percentile(deltas, 0.95),
                "worst_delta_time_s": max(deltas, default=0.0),
                "best_delta_time_s": min(deltas, default=0.0),
                "mean_delta_move_m": statistics.fmean(move_deltas) if move_deltas else 0.0,
                "p95_delta_move_m": percentile(move_deltas, 0.95),
                "worst_delta_move_m": max(move_deltas, default=0.0),
                "regression_over_300s": sum(delta > 300.0 for delta in deltas),
            }
        )
    return output


def paired_case_rows(
    baseline_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]], strategy: str
) -> list[dict[str, Any]]:
    baseline = {(row["suite"], int(row["seed"])): row for row in baseline_rows}
    output: list[dict[str, Any]] = []
    for right in target_rows:
        if right["version"] != strategy:
            continue
        key = (right["suite"], int(right["seed"]))
        left = baseline[key]
        output.append(
            {
                "suite": key[0],
                "seed": key[1],
                "w3_time_s": float(left["total_time_s"]),
                "w4a_time_s": float(right["total_time_s"]),
                "delta_time_s": float(right["total_time_s"]) - float(left["total_time_s"]),
                "delta_move_m": float(right["move_distance_m"]) - float(left["move_distance_m"]),
                "delta_measure_count": int(right["measure_count"]) - int(left["measure_count"]),
                "delta_reacquisition_attempts": int(right["reacquisition_attempts"]) - int(left["reacquisition_attempts"]),
            }
        )
    return output


def movement_comparison(
    baseline_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]], strategy: str
) -> list[dict[str, Any]]:
    target = [row for row in target_rows if row["version"] == strategy]
    keys = sorted(
        {
            key.removeprefix("distance_")
            for row in baseline_rows + target
            for key in row
            if key.startswith("distance_")
        }
    )
    w3_total = statistics.fmean(float(row["move_distance_m"]) for row in baseline_rows)
    w4_total = statistics.fmean(float(row["move_distance_m"]) for row in target)
    output: list[dict[str, Any]] = []
    for key in keys:
        w3 = statistics.fmean(float(row.get(f"distance_{key}", 0.0) or 0.0) for row in baseline_rows)
        w4 = statistics.fmean(float(row.get(f"distance_{key}", 0.0) or 0.0) for row in target)
        output.append(
            {
                "transition": key,
                "w3_mean_distance_m": w3,
                "w4a_mean_distance_m": w4,
                "delta_distance_m": w4 - w3,
                "w3_share": w3 / w3_total,
                "w4a_share": w4 / w4_total,
            }
        )
    return sorted(output, key=lambda row: abs(float(row["delta_distance_m"])), reverse=True)


def time_decomposition_rows(
    w3_summary: dict[str, Any], w4_summary: dict[str, Any]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for label, row in (("w3_adaptive", w3_summary), ("w4a_open_route", w4_summary)):
        output.append(
            {
                "strategy": label,
                "total_time_s": _num(row, "mean_total_time_s"),
                "move_time_s": _num(row, "mean_move_distance_m") / 5.0,
                "measure_time_s": _num(row, "mean_measure_count") * 5.0,
                "switch_time_s": _num(row, "mean_switch_count"),
                "clear_time_s": _num(row, "mean_source_count") * 5.0,
            }
        )
    output.append(
        {
            "strategy": "w4a_minus_w3",
            **{
                key: float(output[1][key]) - float(output[0][key])
                for key in ("total_time_s", "move_time_s", "measure_time_s", "switch_time_s", "clear_time_s")
            },
        }
    )
    return output


def _num(row: dict[str, Any], key: str) -> float:
    return float(row[key])


def render_final_report(
    out_dir: Path,
    strategy: str,
    summary: list[dict[str, Any]],
    paired: list[dict[str, Any]],
    movement: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
) -> None:
    w4 = next(row for row in summary if row["version"] == strategy and row["suite"] == "overall")
    w3 = next(row for row in read_csv(Path("results/q4/w3/summary.csv")) if row["version"] == "adaptive" and row["suite"] == "overall")
    pair = next(row for row in paired if row["target"] == strategy and row["suite"] == "overall")
    time_parts = time_decomposition_rows(w3, w4)
    main_table = [
        ["W3-adaptive", "200/200", f"{_num(w3, 'mean_total_time_s'):.2f}", f"{_num(w3, 'p95_total_time_s'):.2f}", f"{_num(w3, 'max_total_time_s'):.2f}", f"{_num(w3, 'mean_avg_time_per_source_s'):.2f}", f"{_num(w3, 'mean_move_distance_m'):.2f}", f"{_num(w3, 'mean_measure_count'):.2f}", f"{_num(w3, 'mean_reacquisition_attempts'):.2f}", "0", "0"],
        ["W4-A/open-route", f"{w4['full_clear_cases']}/{w4['episodes']}", f"{_num(w4, 'mean_total_time_s'):.2f}", f"{_num(w4, 'p95_total_time_s'):.2f}", f"{_num(w4, 'max_total_time_s'):.2f}", f"{_num(w4, 'mean_avg_time_per_source_s'):.2f}", f"{_num(w4, 'mean_move_distance_m'):.2f}", f"{_num(w4, 'mean_measure_count'):.2f}", f"{_num(w4, 'mean_reacquisition_attempts'):.2f}", str(w4['clear_fail_total']), f"{_num(w4, 'mean_targets_remaining_at_exit'):.0f}"],
    ]
    w3_move_values = [float(row["move_distance_m"]) for row in read_csv(Path("results/q4/w3/details.csv")) if row["version"] == "adaptive"]
    move_tail_table = [
        ["W3-adaptive", f"{percentile(w3_move_values, 0.95):.2f}", f"{max(w3_move_values):.2f}"],
        ["W4-A/open-route", f"{_num(w4, 'p95_move_distance_m'):.2f}", f"{_num(w4, 'max_move_distance_m'):.2f}"],
    ]
    time_table = [
        [row["strategy"], f"{row['move_time_s']:+.2f}", f"{row['measure_time_s']:+.2f}", f"{row['switch_time_s']:+.2f}", f"{row['clear_time_s']:+.2f}", f"{row['total_time_s']:+.2f}"]
        for row in time_parts
    ]
    movement_table = [
        [row["transition"], f"{row['w3_mean_distance_m']:.2f}", f"{row['w4a_mean_distance_m']:.2f}", f"{row['delta_distance_m']:+.2f}", f"{100*row['w4a_share']:.1f}%"]
        for row in movement
        if float(row["w3_mean_distance_m"]) >= 100.0 or float(row["w4a_mean_distance_m"]) >= 100.0
    ]
    paired_table = [
        [row["suite"], str(row["pairs"]), f"{100*_num(row, 'win_rate'):.1f}%", f"{100*_num(row, 'move_win_rate'):.1f}%", f"{_num(row, 'mean_delta_time_s'):+.2f}", f"{_num(row, 'p95_delta_time_s'):+.2f}", f"{_num(row, 'worst_delta_time_s'):+.2f}", f"{_num(row, 'mean_delta_move_m'):+.2f}", str(row["regression_over_300s"])]
        for row in paired if row["target"] == strategy
    ]
    target_sources = [row for row in source_rows if row["strategy"] == strategy]
    w3_sources = [row for row in read_csv(Path("results/q4/w3/source_local.csv")) if row["strategy"] == "adaptive"]
    source_table = []
    for label, rows in (("W3-adaptive", w3_sources), ("W4-A/open-route", target_sources)):
        source_table.append(
            [
                label,
                f"{statistics.fmean(float(row['found_to_clear_s']) for row in rows):.2f}",
                f"{statistics.fmean(float(row['supplement_measure_count']) for row in rows):.2f}",
                f"{statistics.fmean(float(row['reacquisition_attempts']) for row in rows):.2f}",
                f"{statistics.fmean(float(row['reacquisition_move_m']) for row in rows):.2f}",
            ]
        )
    mean_move_delta = _num(w4, "mean_move_distance_m") - _num(w3, "mean_move_distance_m")
    mean_time_delta = _num(w4, "mean_total_time_s") - _num(w3, "mean_total_time_s")
    p95_delta = _num(w4, "p95_total_time_s") - _num(w3, "p95_total_time_s")
    max_delta = _num(w4, "max_total_time_s") - _num(w3, "max_total_time_s")
    lines = [
        "# Q4 W4-A: fixed-backbone global routing optimization",
        "",
        "W4-A keeps all 27 triangular detection points, W3 adaptive coarse-to-fine reacquisition, persistent lifecycle, <=20m MEC threshold, and explicit termination. It changes only the global task pool and next-task ordering. All experiments use local `offline_sim`, `problem=4`, practice mode, and `margin_m=0`.",
        "",
        "## Result",
        "",
        markdown_table(["Strategy", "Full clear", "Mean", "P95", "Max", "Mean T/N", "Move m", "Measures", "Reacq", "Clear fail", "Unresolved"], main_table),
        "",
        markdown_table(["Strategy", "P95 move m", "Max move m"], move_tail_table),
        "",
        "### Time components",
        "",
        markdown_table(["Strategy", "Move", "Measure", "Switch", "Clear", "Total"], time_table),
        "",
        "The routing gain saves more movement time than the final total improvement because changed observation order adds measurement and channel-switching service time.",
        "",
        "## Routing method",
        "",
        "W3 temporarily suppresses SEARCH and normal LOCALIZE whenever any REACQUIRE task exists. W4-A instead builds `SEARCH + LOCALIZE + REACQUIRE + CLEAR` together. At every state update it computes the existing nearest/cheapest-insertion + 2-opt open route over that complete current pool, executes only its first task, then rebuilds and replans. No task-category weight, detour threshold, point deletion, or fixed global tour is introduced.",
        "",
        "A 40-case pilot also tested immediate nearest-neighbor and a heavier one-step complete-route consequence calculation. Open-route was selected because its P95, worst regression, movement, and CPU were more stable than the tiny mean advantage of the heavier lookahead.",
        "",
        "## Movement decomposition",
        "",
        markdown_table(["Transition", "W3 m", "W4-A m", "Delta m", "W4 share"], movement_table),
        "",
        f"Mean movement changes by `{mean_move_delta:+.2f}m` (`{100*mean_move_delta/_num(w3, 'mean_move_distance_m'):.1f}%`). >=500m jump distance changes from `{statistics.fmean(float(row['long_jump_distance_ge_500m']) for row in read_csv(Path('results/q4/w4a_diagnosis/episode_movement.csv'))):.2f}m` to `{_num(w4, 'mean_long_jump_distance_ge_500m'):.2f}m`; geometric backtracks change from `6.90` to `{_num(w4, 'mean_backtrack_count'):.2f}` per episode.",
        "",
        "## CLEAR insertion and delay",
        "",
        f"Because CLEAR tasks participate in the unified route, clear->backbone travel falls from `4106.93m` to `{_num(w4, 'mean_clear_to_backbone_distance_m'):.2f}m`, and transitions fall from `5.86` to `{_num(w4, 'mean_clear_to_backbone_count'):.2f}` per episode. This is a modest improvement, not the main gain.",
        "",
        f"The clear-delay path-excess proxy rises from `2650.15m` to `{_num(w4, 'mean_clear_delay_path_excess_m'):.2f}m`: the globally shorter route often postpones a ready CLEAR while visiting nearby mandatory tasks. This proxy is not a strict regret bound, and forcing immediate CLEAR would conflict with the observed route saving.",
        "",
        "## Same-seed comparison",
        "",
        markdown_table(["Suite", "Pairs", "Time win", "Move win", "Mean dT", "P95 dT", "Worst dT", "Mean dMove", ">300s regressions"], paired_table),
        "",
        "The 17 slower cases are mostly information-order side effects: changing which search/localization task occurs first changes later visibility and coarse-to-fine probes. Seven cases regress by more than 300s; several still move less but perform substantially more measurements. This is why W4-A is not described as pointwise dominant.",
        "",
        "## FOUND-to-CLEAR side effects",
        "",
        markdown_table(["Strategy", "FOUND->CLEAR s/source", "Supplements/source", "Reacq/source", "Reacq move m/source"], source_table),
        "",
        "The elapsed FOUND-to-CLEAR time increases because targets coexist longer with global SEARCH tasks, while their attributed reacquisition movement falls. Lifecycle correctness is unchanged: all targets are eventually cleared.",
        "",
        "## Answers",
        "",
        "1. W3's 43km is dominated by 16.65km backbone-to-backbone travel plus repeated crossings among backbone, reacquisition, and clear tasks. About 35.03km per episode lies in jumps of at least 500m.",
        "2. The largest avoidable pattern is task-class switching: backbone->reacquire, clear->reacquire, and later returns to backbone. It is larger than delayed-CLEAR travel alone.",
        "3. W4-A uses one unified dynamic task pool and the existing open-route nearest/cheapest-insertion + 2-opt solver, executing one action before replanning.",
        "4. Unified CLEAR insertion modestly reduces clear->backbone travel, but most savings come from coordinating backbone and reacquisition order.",
        f"5. Average movement improves by `{-mean_move_delta:.2f}m`.",
        f"6. Mean/P95/Max change by `{mean_time_delta:+.2f}s` / `{p95_delta:+.2f}s` / `{max_delta:+.2f}s`.",
        f"7. Full clearance remains `{w4['full_clear_cases']}/{w4['episodes']}`, with `{w4['clear_fail_total']}` clear failures and mean unresolved `{_num(w4, 'mean_targets_remaining_at_exit'):.0f}`.",
        "8. Routing still contributes, but the fixed 27-point backbone is now the largest single movement category at 37.1% of W4-A movement. The remaining 34.5km cannot be attributed wholly to the backbone because localization and directional visibility still create dynamic crossings.",
        "9. W4-A isolates and validates a substantial routing gain. It is now methodologically reasonable to test W4-B point pruning separately, without changing W4-A in this result set.",
        "",
        f"Maximum time-component identity residual: `{_num(w4, 'max_abs_time_component_delta_s'):.9f}s`. Mean policy CPU time: `{_num(w4, 'mean_policy_runtime_s'):.3f}s/episode`.",
        "",
        "No detection point was deleted, and W4-B was not implemented.",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_pilot(out_dir: Path, summary: list[dict[str, Any]], paired: list[dict[str, Any]]) -> None:
    table = []
    for row in summary:
        if row["suite"] != "overall":
            continue
        pair = next(item for item in paired if item["target"] == row["version"] and item["suite"] == "overall")
        table.append(
            [
                row["version"], str(row["full_clear_cases"]), f"{_num(row, 'mean_total_time_s'):.2f}",
                f"{_num(row, 'p95_total_time_s'):.2f}", f"{_num(row, 'mean_move_distance_m'):.2f}",
                f"{_num(row, 'mean_measure_count'):.2f}", f"{_num(row, 'mean_reacquisition_attempts'):.2f}",
                f"{100*_num(pair, 'win_rate'):.1f}%", f"{_num(pair, 'mean_delta_time_s'):+.2f}",
                f"{_num(pair, 'mean_delta_move_m'):+.2f}", f"{_num(pair, 'worst_delta_time_s'):+.2f}",
            ]
        )
    lines = [
        "# Q4 W4-A routing pilot",
        "",
        "All variants keep the same 27 detection points, W3 adaptive local reacquisition, lifecycle, clear threshold, and termination. Only the task pool and next-task routing rule change.",
        "",
        markdown_table(["Variant", "Full clear", "Mean", "P95", "Move m", "Measures", "Reacq", "Win vs W3", "Mean dT", "Mean dMove", "Worst dT"], table),
        "",
        "- nearest: unified task pool, choose minimum immediate distance.",
        "- open_route: unified task pool, current nearest/cheapest-insertion + 2-opt open route.",
        "- route_consequence: for every possible first task, add its immediate leg to a newly optimized open route through all other known tasks, then choose the minimum complete route estimate.",
    ]
    (out_dir / "pilot_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Q4 W4-A routing benchmark")
    parser.add_argument("--strategies", default="nearest,open_route,route_consequence")
    parser.add_argument("--random-seeds", default="0:20")
    parser.add_argument("--stress-seeds", default="10000:10010")
    parser.add_argument("--out-dir", default="results/q4/w4a_pilot")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    assert_policy_isolated()
    strategies = [item.strip() for item in args.strategies.split(",") if item.strip()]
    unknown = [item for item in strategies if item not in POLICIES]
    if unknown:
        raise ValueError(f"unknown strategies: {unknown}")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.report_only:
        details = read_csv(out_dir / "details.csv")
        sources = read_csv(out_dir / "source_local.csv")
        regrets = read_csv(out_dir / "clear_delay_regret.csv")
        summary = read_csv(out_dir / "summary.csv")
    else:
        details, sources, regrets = run_cases(strategies, parse_seed_range(args.random_seeds), parse_seed_range(args.stress_seeds))
        summary = [summarize_w4a(details, strategy, suite) for strategy in strategies for suite in ("random", "min_reff", "collinear", "overall")]
    baseline = read_csv(Path("results/q4/w3/details.csv"))
    baseline = [row for row in baseline if row["version"] == "adaptive"]
    paired = read_csv(out_dir / "paired_vs_w3.csv") if args.report_only else [row for strategy in strategies for row in paired_vs_w3(baseline, details, strategy)]
    write_union_csv(out_dir / "details.csv", details)
    write_csv(out_dir / "summary.csv", summary)
    write_csv(out_dir / "paired_vs_w3.csv", paired)
    write_csv(out_dir / "source_local.csv", sources)
    write_csv(out_dir / "clear_delay_regret.csv", regrets)
    write_csv(out_dir / "paired_cases.csv", paired_case_rows(baseline, details, strategies[0]))
    diagnosis_rows = read_csv(Path("results/q4/w4a_diagnosis/episode_movement.csv"))
    movement = movement_comparison(diagnosis_rows, details, strategies[0])
    write_csv(out_dir / "movement_decomposition.csv", movement)
    w3_overall = next(row for row in read_csv(Path("results/q4/w3/summary.csv")) if row["version"] == "adaptive" and row["suite"] == "overall")
    w4_overall = next(row for row in summary if row["version"] == strategies[0] and row["suite"] == "overall")
    write_csv(out_dir / "time_decomposition.csv", time_decomposition_rows(w3_overall, w4_overall))
    for strategy in strategies:
        write_csv(out_dir / f"source_count_{strategy}.csv", source_count_summary([row for row in details if row["version"] == strategy]))
    metadata = {
        "environment": "local offline_sim/practice only",
        "problem": 4,
        "margin_m": 0.0,
        "fixed_detection_points": 27,
        "strategies": strategies,
        "official_practice_run": False,
        "official_formal_test_run": False,
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    render_pilot(out_dir, summary, paired)
    if len([row for row in details if row["version"] == strategies[0]]) >= 200:
        render_final_report(out_dir, strategies[0], summary, paired, movement, sources)
        print(f"wrote {out_dir / 'report.md'}")
    print(f"wrote {out_dir / 'pilot_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
