from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.case import (
    ARENA_RADIUS_M,
    DIRECTIONAL_HALF_ANGLE_DEG,
    Case,
    Jammer,
    ang_diff,
    generate_case,
    generate_stress_case,
    norm_deg,
)
from offline_sim.engine import CLEAR_RADIUS_M, Engine
from offline_sim.harness import ActionRecord, EpisodeResult, run_episode
from q3.offline_policy import theoretical_outer_radius
from q3.planner import Q3BaselinePlanner
from q4.w0_policy import policy_w0


Q3_REFERENCE = {
    "clear_rate": 1.0,
    "mean_total_time_s": 3496.68684313,
    "p95_total_time_s": 4244.8281959,
    "max_total_time_s": 4817.500183,
    "mean_avg_source_s": 278.6922540054254,
    "mean_move_distance_m": 13554.134210713679,
    "clear_fail_total": 0,
}


def parse_seed_range(spec: str) -> list[int]:
    if ":" in spec:
        start, stop = spec.split(":", 1)
        return list(range(int(start), int(stop)))
    return [int(part) for part in spec.split(",") if part.strip()]


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    pos = q * (len(values) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return values[lo]
    frac = pos - lo
    return values[lo] * (1.0 - frac) + values[hi] * frac


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def source_to_point_deg(jammer: Jammer, x: float, y: float) -> float:
    return norm_deg(math.degrees(math.atan2(y - jammer.y, x - jammer.x)))


def in_directional_halfplane(jammer: Jammer, x: float, y: float) -> bool:
    if jammer.kind == "omni":
        return True
    if jammer.direction_deg is None:
        return False
    return ang_diff(source_to_point_deg(jammer, x, y), jammer.direction_deg) <= DIRECTIONAL_HALF_ANGLE_DEG + 1e-9


def action_points(action_log: list[ActionRecord]) -> list[tuple[float, float]]:
    points = [(0.0, 0.0)]
    points.extend((float(row.x), float(row.y)) for row in action_log)
    return points


def case_row(suite: str, seed: int, result: EpisodeResult, case: Case) -> dict[str, Any]:
    move_time = result.move_distance_m / 5.0
    measure_time = result.n_measure * 5.0
    switch_time = float(result.n_channel_switch)
    clear_success = result.n_clear - result.n_clear_fail
    clear_time = clear_success * 5.0 + result.n_clear_fail * 3.0
    return {
        "version": "w0",
        "n": 8,
        "problem": 4,
        "suite": suite,
        "seed": seed,
        "success": int(result.success),
        "cleared": result.cleared,
        "total": result.total,
        "source_count": case.total,
        "omni_count": case.n_omni,
        "dir_count": case.n_dir,
        "total_time_s": result.virtual_time_s,
        "avg_time_per_source_s": result.virtual_time_s / case.total if case.total else 0.0,
        "move_distance_m": result.move_distance_m,
        "move_time_s": move_time,
        "measure_count": result.n_measure,
        "measure_time_s": measure_time,
        "switch_count": result.n_channel_switch,
        "switch_time_s": switch_time,
        "clear_success": clear_success,
        "clear_fail": result.n_clear_fail,
        "clear_time_s": clear_time,
        "near_count": result.n_near,
        "time_component_delta_s": result.virtual_time_s - (move_time + measure_time + switch_time + clear_time),
        "policy_runtime_s": result.policy_runtime_s,
        "error": result.error or "",
    }


def summarize(rows: list[dict[str, Any]], suite: str) -> dict[str, Any]:
    subset = [row for row in rows if suite == "overall" or row["suite"] == suite]
    times = [float(row["total_time_s"]) for row in subset]
    avg_sources = [float(row["avg_time_per_source_s"]) for row in subset]
    return {
        "version": "w0",
        "n": 8,
        "problem": 4,
        "suite": suite,
        "episodes": len(subset),
        "clear_rate": sum(int(row["success"]) for row in subset) / len(subset) if subset else 0.0,
        "full_clear_cases": sum(int(row["success"]) for row in subset),
        "clear_fail_total": sum(int(row["clear_fail"]) for row in subset),
        "error_count": sum(1 for row in subset if row["error"]),
        "mean_total_time_s": statistics.fmean(times) if times else 0.0,
        "median_total_time_s": statistics.median(times) if times else 0.0,
        "p95_total_time_s": percentile(times, 0.95),
        "max_total_time_s": max(times, default=0.0),
        "mean_avg_time_per_source_s": statistics.fmean(avg_sources) if avg_sources else 0.0,
        "median_avg_time_per_source_s": statistics.median(avg_sources) if avg_sources else 0.0,
        "p95_avg_time_per_source_s": percentile(avg_sources, 0.95),
        "mean_move_distance_m": statistics.fmean(float(row["move_distance_m"]) for row in subset) if subset else 0.0,
        "mean_measure_count": statistics.fmean(int(row["measure_count"]) for row in subset) if subset else 0.0,
        "mean_switch_count": statistics.fmean(int(row["switch_count"]) for row in subset) if subset else 0.0,
        "mean_source_count": statistics.fmean(int(row["source_count"]) for row in subset) if subset else 0.0,
        "mean_omni_count": statistics.fmean(int(row["omni_count"]) for row in subset) if subset else 0.0,
        "mean_dir_count": statistics.fmean(int(row["dir_count"]) for row in subset) if subset else 0.0,
        "mean_policy_runtime_s": statistics.fmean(float(row["policy_runtime_s"]) for row in subset) if subset else 0.0,
        "max_abs_time_component_delta_s": max((abs(float(row["time_component_delta_s"])) for row in subset), default=0.0),
    }


def source_count_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for count in range(10, 17):
        subset = [row for row in rows if int(row["source_count"]) == count]
        times = [float(row["total_time_s"]) for row in subset]
        avg_sources = [float(row["avg_time_per_source_s"]) for row in subset]
        output.append(
            {
                "source_count": count,
                "case_count": len(subset),
                "full_clear_cases": sum(int(row["success"]) for row in subset),
                "clear_rate": sum(int(row["success"]) for row in subset) / len(subset) if subset else 0.0,
                "mean_total_time_s": statistics.fmean(times) if times else 0.0,
                "mean_avg_time_per_source_s": statistics.fmean(avg_sources) if avg_sources else 0.0,
                "median_avg_time_per_source_s": statistics.median(avg_sources) if avg_sources else 0.0,
                "p95_avg_time_per_source_s": percentile(avg_sources, 0.95),
            }
        )
    return output


def missed_source_rows(suite: str, seed: int, case: Case, result: EpisodeResult) -> list[dict[str, Any]]:
    points = action_points(result.action_log)
    last_x, last_y = points[-1]
    rows: list[dict[str, Any]] = []
    for jammer in sorted(case.jammers, key=lambda item: item.channel):
        if jammer.cleared:
            continue
        distances = [math.hypot(x - jammer.x, y - jammer.y) for x, y in points]
        halfplane_flags = [in_directional_halfplane(jammer, x, y) for x, y in points]
        within_reff_flags = [dist <= jammer.r_eff + 1e-9 for dist in distances]
        visible_flags = [inside and near for inside, near in zip(halfplane_flags, within_reff_flags)]
        same_channel_visible_measures = [
            row
            for row in result.action_log
            if row.action == "measure"
            and row.channel == jammer.channel
            and math.hypot(row.x - jammer.x, row.y - jammer.y) <= jammer.r_eff + 1e-9
            and in_directional_halfplane(jammer, row.x, row.y)
        ]
        if not any(within_reff_flags):
            failure_mode = "never_within_receive_radius"
        elif jammer.kind == "dir" and not any(halfplane_flags):
            failure_mode = "directional_backside_only"
        elif not any(visible_flags):
            failure_mode = "radius_or_direction_never_simultaneous"
        elif not same_channel_visible_measures:
            failure_mode = "visible_area_not_measured_on_channel"
        else:
            failure_mode = "visible_measure_but_not_cleared"
        rows.append(
            {
                "version": "w0",
                "suite": suite,
                "seed": seed,
                "channel": jammer.channel,
                "kind": jammer.kind,
                "x": jammer.x,
                "y": jammer.y,
                "radius_from_origin_m": math.hypot(jammer.x, jammer.y),
                "r_eff_m": jammer.r_eff,
                "direction_deg": "" if jammer.direction_deg is None else jammer.direction_deg,
                "last_robot_distance_m": math.hypot(last_x - jammer.x, last_y - jammer.y),
                "closest_robot_distance_m": min(distances) if distances else math.inf,
                "ever_within_receive_radius": int(any(within_reff_flags)),
                "ever_in_effective_halfplane": int(any(halfplane_flags)),
                "ever_visible_distance_and_halfplane": int(any(visible_flags)),
                "same_channel_visible_measure_count": len(same_channel_visible_measures),
                "failure_mode": failure_mode,
            }
        )
    return rows


def missed_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for suite in ("random", "min_reff", "collinear", "overall"):
        subset = [row for row in rows if suite == "overall" or row["suite"] == suite]
        total = len(subset)
        by_mode: dict[str, int] = {}
        for row in subset:
            by_mode[row["failure_mode"]] = by_mode.get(row["failure_mode"], 0) + 1
        output.append(
            {
                "suite": suite,
                "missed_sources": total,
                "missed_omni": sum(row["kind"] == "omni" for row in subset),
                "missed_dir": sum(row["kind"] == "dir" for row in subset),
                "dir_share": (sum(row["kind"] == "dir" for row in subset) / total) if total else 0.0,
                "never_within_receive_radius": by_mode.get("never_within_receive_radius", 0),
                "directional_backside_only": by_mode.get("directional_backside_only", 0),
                "radius_or_direction_never_simultaneous": by_mode.get("radius_or_direction_never_simultaneous", 0),
                "visible_area_not_measured_on_channel": by_mode.get("visible_area_not_measured_on_channel", 0),
                "visible_measure_but_not_cleared": by_mode.get("visible_measure_but_not_cleared", 0),
            }
        )
    return output


def verify_q4_physics() -> dict[str, Any]:
    from offline_sim.case import ErrorField

    case = Case(
        [Jammer(8, 0.0, 0.0, 1200.0, "dir", direction_deg=0.0)],
        ErrorField(123),
        seed=123,
        mode="practice",
    )
    east = Engine(case)
    east.enter()
    _, east_out = east.measure(500.0, 0.0, 8)
    north = Engine(case)
    north.enter()
    _, north_out = north.measure(0.0, 500.0, 8)
    west = Engine(case)
    west.enter()
    _, west_out = west.measure(-500.0, 0.0, 8)
    clear = Engine(case)
    clear.enter()
    _, clear_out = clear.clear(-10.0, 0.0, 8)
    ok = (
        east_out is not None
        and east_out.result == "direction"
        and north_out is not None
        and north_out.result == "direction"
        and west_out is not None
        and west_out.result == "no_signal"
        and clear_out is not None
        and clear_out.result == "success"
        and CLEAR_RADIUS_M == 20.0
        and DIRECTIONAL_HALF_ANGLE_DEG == 90.0
    )
    return {
        "directional_half_angle_deg": DIRECTIONAL_HALF_ANGLE_DEG,
        "direction_east_result": None if east_out is None else east_out.result,
        "direction_boundary_north_result": None if north_out is None else north_out.result,
        "direction_backside_west_result": None if west_out is None else west_out.result,
        "clear_from_backside_result": None if clear_out is None else clear_out.result,
        "clear_radius_m": CLEAR_RADIUS_M,
        "ok": ok,
    }


def assert_w0_ground_truth_isolated() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (Path("q4/w0_policy.py"), Path("q3/v6_policy.py"), Path("q3/v5_prediction.py")):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("offline_sim"):
                raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Import) and any(alias.name.startswith("offline_sim") for alias in node.names):
                raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Attribute) and node.attr in {"case", "engine", "sources", "jammers"}:
                raise RuntimeError(f"ground-truth isolation failed: {relative} accesses .{node.attr}")


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def render_report(
    out_dir: Path,
    summary: list[dict[str, Any]],
    by_count: list[dict[str, Any]],
    missed: list[dict[str, Any]],
    missed_by_suite: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    overall = next(row for row in summary if row["suite"] == "overall")
    random = next(row for row in summary if row["suite"] == "random")
    q3 = Q3_REFERENCE
    q3_drop_rows = [
        ["Clear rate", f"{100*q3['clear_rate']:.1f}%", f"{100*overall['clear_rate']:.1f}%", f"{100*(overall['clear_rate']-q3['clear_rate']):+.1f} pp"],
        ["Mean total", f"{q3['mean_total_time_s']:.2f}s", f"{overall['mean_total_time_s']:.2f}s", f"{overall['mean_total_time_s']-q3['mean_total_time_s']:+.2f}s"],
        ["P95 total", f"{q3['p95_total_time_s']:.2f}s", f"{overall['p95_total_time_s']:.2f}s", f"{overall['p95_total_time_s']-q3['p95_total_time_s']:+.2f}s"],
        ["Mean T/N", f"{q3['mean_avg_source_s']:.2f}s", f"{overall['mean_avg_time_per_source_s']:.2f}s", f"{overall['mean_avg_time_per_source_s']-q3['mean_avg_source_s']:+.2f}s"],
        ["Move distance", f"{q3['mean_move_distance_m']:.2f}m", f"{overall['mean_move_distance_m']:.2f}m", f"{overall['mean_move_distance_m']-q3['mean_move_distance_m']:+.2f}m"],
    ]
    suite_rows = [
        [
            row["suite"],
            f"{100*row['clear_rate']:.1f}% ({row['full_clear_cases']}/{row['episodes']})",
            f"{row['mean_total_time_s']:.2f}",
            f"{row['p95_total_time_s']:.2f}",
            f"{row['max_total_time_s']:.2f}",
            f"{row['mean_avg_time_per_source_s']:.2f}",
            f"{row['p95_avg_time_per_source_s']:.2f}",
            f"{row['mean_move_distance_m']:.2f}",
            str(row["clear_fail_total"]),
        ]
        for row in summary
    ]
    count_rows = [
        [
            str(row["source_count"]),
            str(row["case_count"]),
            f"{100*row['clear_rate']:.1f}%",
            f"{row['mean_total_time_s']:.2f}",
            f"{row['mean_avg_time_per_source_s']:.2f}",
            f"{row['median_avg_time_per_source_s']:.2f}",
            f"{row['p95_avg_time_per_source_s']:.2f}",
        ]
        for row in by_count
    ]
    simple_count_rows = [
        [str(row["source_count"]), f"{row['mean_total_time_s']:.2f}s", f"{row['mean_avg_time_per_source_s']:.2f}s"]
        for row in by_count
    ]
    missed_overall = next(row for row in missed_by_suite if row["suite"] == "overall")
    failure_rows = [
        [
            row["suite"],
            str(row["missed_sources"]),
            str(row["missed_omni"]),
            str(row["missed_dir"]),
            f"{100*row['dir_share']:.1f}%",
            str(row["never_within_receive_radius"]),
            str(row["directional_backside_only"]),
            str(row["radius_or_direction_never_simultaneous"]),
            str(row["visible_area_not_measured_on_channel"]),
            str(row["visible_measure_but_not_cleared"]),
        ]
        for row in missed_by_suite
    ]
    top_missed = sorted(missed, key=lambda row: float(row["closest_robot_distance_m"]))[:12]
    missed_rows = [
        [
            row["suite"],
            str(row["seed"]),
            str(row["channel"]),
            row["kind"],
            f"{float(row['radius_from_origin_m']):.1f}",
            f"{float(row['r_eff_m']):.1f}",
            "" if row["direction_deg"] == "" else f"{float(row['direction_deg']):.1f}",
            f"{float(row['closest_robot_distance_m']):.1f}",
            str(row["ever_within_receive_radius"]),
            str(row["ever_in_effective_halfplane"]),
            str(row["ever_visible_distance_and_halfplane"]),
            row["failure_mode"],
        ]
        for row in top_missed
    ]

    lines = [
        "# Q4 W0 baseline: frozen Q3 V6/n=8 on problem=4",
        "",
        "W0 does not change the Q3 frozen V6/n=8 algorithm. It only runs that policy against local `offline_sim` with `problem=4` and records post-episode failure diagnostics.",
        "",
        "## A. Environment checks",
        "",
        f"- Local-only: `{metadata['environment']}`; official practice/formal HTTP was not called.",
        f"- Q4 physics check: `{metadata['q4_physics_check']}`.",
        f"- Random Q4 cases use `generate_case(..., problem=4, margin_m=0)`. Stress cases reuse `generate_stress_case(..., problem=4)`; that generator has no `margin_m` parameter.",
        f"- Arena radius: `{ARENA_RADIUS_M}` m; directional half angle: `{DIRECTIONAL_HALF_ANGLE_DEG}` deg; clear radius: `{CLEAR_RADIUS_M}` m.",
        "",
        "## B. Q3 to Q4 drop",
        "",
        markdown_table(["Metric", "Q3 V6/n=8", "Q4 W0", "Delta"], q3_drop_rows),
        "",
        "## C. W0 benchmark summary",
        "",
        markdown_table(["Suite", "Clear", "Mean", "P95", "Max", "Mean T/N", "P95 T/N", "Move m", "Clear fail"], suite_rows),
        "",
        "## D. By true source count",
        "",
        markdown_table(["N", "Cases", "Clear", "Mean total", "Mean T/N", "Median T/N", "P95 T/N"], count_rows),
        "",
        "简洁表格：",
        "",
        markdown_table(["干扰源数量", "平均总时间", "平均单源时间"], simple_count_rows),
        "",
        "## E. Missed-source failure modes",
        "",
        markdown_table(
            [
                "Suite",
                "Missed",
                "Omni",
                "Dir",
                "Dir share",
                "Never within R_eff",
                "Backside only",
                "R/dir not simultaneous",
                "Visible area not measured",
                "Visible measure not cleared",
            ],
            failure_rows,
        ),
        "",
        "Closest missed sources, for spot checking:",
        "",
        markdown_table(
            ["Suite", "Seed", "Ch", "Kind", "r0", "R_eff", "dir", "closest", "withinR", "half", "visible", "mode"],
            missed_rows,
        ),
        "",
        "## F. Answers",
        "",
        f"1. Performance drop: full-clear rate changes from Q3 `100.0%` to Q4 W0 `{100*overall['clear_rate']:.1f}%` ({overall['full_clear_cases']}/{overall['episodes']}). Mean total time changes by `{overall['mean_total_time_s']-q3['mean_total_time_s']:+.2f}s`, but this mean includes failed runs and is not a success metric by itself.",
        f"2. Missed-source type: W0 missed `{missed_overall['missed_sources']}` sources overall; `{missed_overall['missed_dir']}` are directional and `{missed_overall['missed_omni']}` are omni, so directional share is `{100*missed_overall['dir_share']:.1f}%`.",
        f"3. Main failure cause: between the two requested mechanisms, pure distance non-coverage is larger than backside-only (`{missed_overall['never_within_receive_radius']}` vs `{missed_overall['directional_backside_only']}`). However the largest bucket is `{missed_overall['visible_measure_but_not_cleared']}` `visible_measure_but_not_cleared` sources: W0 sometimes receives directional-source measurements, but then applies the Q3 all-direction localization/clear logic to a half-plane visibility process, so the source remains uncleared. `{missed_overall['radius_or_direction_never_simultaneous']}` more sources had distance and direction not simultaneous, and `visible_area_not_measured_on_channel` means the robot entered a point that could see the source but did not measure that channel there.",
        "",
        "No W1 or Q4-specific optimization is implemented in this stage.",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Q4 W0 baseline: frozen Q3 V6/n=8 in problem=4 offline_sim")
    parser.add_argument("--random-seeds", default="0:100")
    parser.add_argument("--stress-seeds", default="10000:10050")
    parser.add_argument("--out-dir", default="results/q4/w0_baseline")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    assert_w0_ground_truth_isolated()
    physics = verify_q4_physics()
    if not physics["ok"]:
        raise RuntimeError(f"Q4 physics check failed: {physics}")

    random_seeds = parse_seed_range(args.random_seeds)
    stress_seeds = parse_seed_range(args.stress_seeds)
    radius = theoretical_outer_radius(8)
    scan_points = [(point.x, point.y) for point in Q3BaselinePlanner.make_search_points(radius, 8)]
    suites = [
        ("random", random_seeds, "smooth"),
        ("min_reff", stress_seeds, "adversarial"),
        ("collinear", stress_seeds, "adversarial"),
    ]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    details: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
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
                    scan_points=scan_points,
                )
            result = run_episode(case, lambda runner: policy_w0(runner, n=8), include_oracles=False)
            details.append(case_row(suite, seed, result, case))
            if not result.success:
                failures.extend(missed_source_rows(suite, seed, case, result))
            if index % 10 == 0 or index == len(seeds):
                print(f"[w0/{suite}] {index}/{len(seeds)}", flush=True)

    summary = [summarize(details, suite) for suite in ("random", "min_reff", "collinear", "overall")]
    by_count = source_count_summary(details)
    failure_summary = missed_summary(failures)
    metadata = {
        "environment": "local offline_sim/practice only",
        "official_practice_run": False,
        "official_formal_test_run": False,
        "problem": 4,
        "baseline": "W0 = frozen Q3 V6/n=8 unchanged",
        "random_seeds": args.random_seeds,
        "stress_seeds": args.stress_seeds,
        "random_margin_m": 0.0,
        "stress_margin_m": None,
        "stress_margin_note": "generate_stress_case has no margin_m argument; stress layouts are unchanged except problem=4.",
        "q4_physics_check": physics,
        "q3_reference": Q3_REFERENCE,
    }

    write_csv(out_dir / "details.csv", details)
    write_csv(out_dir / "summary.csv", summary)
    write_csv(out_dir / "source_count_summary.csv", by_count)
    write_csv(out_dir / "missed_sources.csv", failures)
    write_csv(out_dir / "missed_summary.csv", failure_summary)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    render_report(out_dir, summary, by_count, failures, failure_summary, metadata)
    print(f"wrote {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
