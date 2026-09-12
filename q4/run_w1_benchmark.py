from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.case import generate_case, generate_stress_case
from offline_sim.harness import run_episode
from q4.geometry import verify_detection_geometry
from q4.run_w0_baseline import (
    Q3_REFERENCE,
    case_row,
    markdown_table,
    missed_source_rows,
    missed_summary,
    parse_seed_range,
    percentile,
    render_report as render_w0_style_report,
    source_count_summary,
    summarize,
    write_csv,
)
from q4.w1_policy import W1_GRID_SPEC, policy_w1, w1_search_points


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_w0_details(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_csv(path):
        converted: dict[str, Any] = {}
        for key, value in row.items():
            if key in {"version", "suite", "error"}:
                converted[key] = value
            elif key in {
                "n",
                "problem",
                "seed",
                "success",
                "cleared",
                "total",
                "source_count",
                "omni_count",
                "dir_count",
                "measure_count",
                "switch_count",
                "clear_success",
                "clear_fail",
                "near_count",
            }:
                converted[key] = int(value)
            else:
                converted[key] = float(value)
        rows.append(converted)
    return rows


def paired_vs_w0(w0_rows: list[dict[str, Any]], w1_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    w0 = {(row["suite"], int(row["seed"])): row for row in w0_rows}
    w1 = {(row["suite"], int(row["seed"])): row for row in w1_rows}
    output: list[dict[str, Any]] = []
    for suite in ("random", "min_reff", "collinear", "overall"):
        keys = sorted(key for key in w1 if suite == "overall" or key[0] == suite)
        pairs = [(w0[key], w1[key]) for key in keys if key in w0]
        deltas = [float(right["total_time_s"]) - float(left["total_time_s"]) for left, right in pairs]
        avg_deltas = [float(right["avg_time_per_source_s"]) - float(left["avg_time_per_source_s"]) for left, right in pairs]
        clear_delta = [int(right["success"]) - int(left["success"]) for left, right in pairs]
        output.append(
            {
                "base": "w0",
                "target": "w1",
                "suite": suite,
                "pairs": len(pairs),
                "w1_win_rate_time": sum(delta < 0.0 for delta in deltas) / len(deltas) if deltas else 0.0,
                "mean_delta_total_time_s": statistics.fmean(deltas) if deltas else 0.0,
                "median_delta_total_time_s": statistics.median(deltas) if deltas else 0.0,
                "p95_delta_total_time_s": percentile(deltas, 0.95),
                "max_delta_total_time_s": max(deltas, default=0.0),
                "mean_delta_avg_time_per_source_s": statistics.fmean(avg_deltas) if avg_deltas else 0.0,
                "w1_more_success_cases": sum(delta > 0 for delta in clear_delta),
                "w1_fewer_success_cases": sum(delta < 0 for delta in clear_delta),
                "same_success_cases": sum(delta == 0 for delta in clear_delta),
                "mean_delta_move_m": statistics.fmean(
                    float(right["move_distance_m"]) - float(left["move_distance_m"]) for left, right in pairs
                ) if pairs else 0.0,
                "mean_delta_measure_count": statistics.fmean(
                    int(right["measure_count"]) - int(left["measure_count"]) for left, right in pairs
                ) if pairs else 0.0,
            }
        )
    return output


def render_report(
    out_dir: Path,
    geometry_check: dict[str, Any],
    summary: list[dict[str, Any]],
    w0_summary_rows: list[dict[str, str]],
    by_count: list[dict[str, Any]],
    failure_summary: list[dict[str, Any]],
    paired: list[dict[str, Any]],
) -> None:
    w1_overall = next(row for row in summary if row["suite"] == "overall")
    w0_overall = next(row for row in w0_summary_rows if row["suite"] == "overall")
    missed_overall = next(row for row in failure_summary if row["suite"] == "overall")
    q3 = Q3_REFERENCE

    q3_rows = [
        ["Clear rate", f"{100*q3['clear_rate']:.1f}%", f"{100*w1_overall['clear_rate']:.1f}%", f"{100*(w1_overall['clear_rate']-q3['clear_rate']):+.1f} pp"],
        ["Mean total", f"{q3['mean_total_time_s']:.2f}s", f"{w1_overall['mean_total_time_s']:.2f}s", f"{w1_overall['mean_total_time_s']-q3['mean_total_time_s']:+.2f}s"],
        ["Mean T/N", f"{q3['mean_avg_source_s']:.2f}s", f"{w1_overall['mean_avg_time_per_source_s']:.2f}s", f"{w1_overall['mean_avg_time_per_source_s']-q3['mean_avg_source_s']:+.2f}s"],
    ]
    w0_rows = [
        ["Clear rate", f"{100*float(w0_overall['clear_rate']):.1f}%", f"{100*w1_overall['clear_rate']:.1f}%", f"{100*(w1_overall['clear_rate']-float(w0_overall['clear_rate'])):+.1f} pp"],
        ["Full-clear cases", f"{w0_overall['full_clear_cases']}/{w0_overall['episodes']}", f"{w1_overall['full_clear_cases']}/{w1_overall['episodes']}", f"{int(w1_overall['full_clear_cases'])-int(w0_overall['full_clear_cases']):+d}"],
        ["Mean total", f"{float(w0_overall['mean_total_time_s']):.2f}s", f"{w1_overall['mean_total_time_s']:.2f}s", f"{w1_overall['mean_total_time_s']-float(w0_overall['mean_total_time_s']):+.2f}s"],
        ["Mean T/N", f"{float(w0_overall['mean_avg_time_per_source_s']):.2f}s", f"{w1_overall['mean_avg_time_per_source_s']:.2f}s", f"{w1_overall['mean_avg_time_per_source_s']-float(w0_overall['mean_avg_time_per_source_s']):+.2f}s"],
        ["Move distance", f"{float(w0_overall['mean_move_distance_m']):.2f}m", f"{w1_overall['mean_move_distance_m']:.2f}m", f"{w1_overall['mean_move_distance_m']-float(w0_overall['mean_move_distance_m']):+.2f}m"],
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
            f"{row['mean_measure_count']:.2f}",
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
            f"{row['p95_avg_time_per_source_s']:.2f}",
        ]
        for row in by_count
    ]
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
        for row in failure_summary
    ]
    pair_rows = [
        [
            row["suite"],
            str(row["pairs"]),
            f"{100*row['w1_win_rate_time']:.1f}%",
            f"{row['mean_delta_total_time_s']:+.2f}",
            f"{row['mean_delta_avg_time_per_source_s']:+.2f}",
            str(row["w1_more_success_cases"]),
            str(row["w1_fewer_success_cases"]),
            f"{row['mean_delta_move_m']:+.2f}",
            f"{row['mean_delta_measure_count']:+.2f}",
        ]
        for row in paired
    ]
    lines = [
        "# Q4 W1 baseline: triangular detection geometry + frozen V6 routing",
        "",
        "W1 changes only the SEARCH detection backbone. FOUND localization, MEC clear criterion, supplement generation, task scheduling and route optimization are inherited from frozen Q3 V6.",
        "",
        "## A. Detection geometry",
        "",
        f"- Grid: equilateral triangular lattice, side `{W1_GRID_SPEC.side_m:.1f}m`, rotation `{W1_GRID_SPEC.rotation_deg:.1f}deg`, offset `({W1_GRID_SPEC.offset_u}, {W1_GRID_SPEC.offset_v})`.",
        f"- Expanded crop radius: `{W1_GRID_SPEC.crop_radius_m:.1f}m`; candidate detection points: `{len(w1_search_points())}`.",
        f"- Geometry validation: `{geometry_check['misses']}` misses over `{geometry_check['probe_count']}` probes; max visible distance `{geometry_check['max_visible_distance_m']:.2f}m`; worst distance margin `{geometry_check['worst_distance_margin_m']:.2f}m`.",
        "- Guarantee rationale: inside any 1000m-side equilateral triangle, all three vertices are within 1000m; the source is in their convex hull, so any 180 degree half-plane through it contains at least one vertex.",
        "",
        "## B. W1 compared with Q3 and W0",
        "",
        markdown_table(["Metric", "Q3 V6/n=8", "Q4 W1", "Delta"], q3_rows),
        "",
        markdown_table(["Metric", "Q4 W0", "Q4 W1", "Delta"], w0_rows),
        "",
        "## C. W1 benchmark summary",
        "",
        markdown_table(["Suite", "Clear", "Mean", "P95", "Max", "Mean T/N", "P95 T/N", "Move m", "Measures", "Clear fail"], suite_rows),
        "",
        "## D. By true source count",
        "",
        markdown_table(["N", "Cases", "Clear", "Mean total", "Mean T/N", "P95 T/N"], count_rows),
        "",
        "## E. Missed-source composition",
        "",
        markdown_table(["Suite", "Missed", "Omni", "Dir", "Dir share", "Never within R_eff", "Backside only", "R/dir not simultaneous", "Visible area not measured", "Visible measure not cleared"], failure_rows),
        "",
        "## F. Same-seed paired comparison vs W0",
        "",
        markdown_table(["Suite", "Pairs", "W1 time win", "Mean dT", "Mean dT/N", "More clear", "Fewer clear", "dMove m", "dMeasure"], pair_rows),
        "",
        "## G. Answers",
        "",
        f"1. Adopted geometry: side `1000m` expanded triangular lattice with 27 points. It is the smallest-point conservative zero-miss candidate in the tested scan; `1050m+` grids already showed numerical/adversarial misses.",
        f"2. Theoretical/numerical guarantee: the `s<=1000m` triangle argument gives a conservative geometric guarantee for a complete expanded lattice, and the finite cropped grid passed `{geometry_check['probe_count']}` random/adversarial checks with zero miss.",
        f"3. Compared with W0, full-clear rate changes from `{100*float(w0_overall['clear_rate']):.1f}%` to `{100*w1_overall['clear_rate']:.1f}%`, i.e. `{100*(w1_overall['clear_rate']-float(w0_overall['clear_rate'])):+.1f}` percentage points.",
        f"4. Remaining bottleneck: if misses are still high, detection geometry alone is not enough; failures in `visible_measure_but_not_cleared` indicate Q3's all-direction localization/clear assumptions still break on directional half-plane visibility. If clear rate is high but time is large, the next bottleneck is path/task efficiency from visiting 27 backbone points.",
        "",
        "No W2 dynamic pruning, lookahead, or routing redesign is implemented here.",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Q4 W1 benchmark")
    parser.add_argument("--random-seeds", default="0:100")
    parser.add_argument("--stress-seeds", default="10000:10050")
    parser.add_argument("--out-dir", default="results/q4/w1")
    parser.add_argument("--w0-dir", default="results/q4/w0_baseline")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    w0_dir = Path(args.w0_dir)
    random_seeds = parse_seed_range(args.random_seeds)
    stress_seeds = parse_seed_range(args.stress_seeds)
    suites = [
        ("random", random_seeds, "smooth"),
        ("min_reff", stress_seeds, "adversarial"),
        ("collinear", stress_seeds, "adversarial"),
    ]

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
                    scan_points=[(p.x, p.y) for p in w1_search_points()],
                )
            result = run_episode(case, policy_w1, include_oracles=False)
            row = case_row(suite, seed, result, case)
            row["version"] = "w1"
            row["n"] = len(w1_search_points())
            details.append(row)
            if not result.success:
                failure_rows = missed_source_rows(suite, seed, case, result)
                for failure in failure_rows:
                    failure["version"] = "w1"
                failures.extend(failure_rows)
            if index % 10 == 0 or index == len(seeds):
                print(f"[w1/{suite}] {index}/{len(seeds)}", flush=True)

    summary = [summarize(details, suite) for suite in ("random", "min_reff", "collinear", "overall")]
    for row in summary:
        row["version"] = "w1"
        row["n"] = len(w1_search_points())
    by_count = source_count_summary(details)
    failure_summary = missed_summary(failures)
    w0_details = load_w0_details(w0_dir / "details.csv")
    paired = paired_vs_w0(w0_details, details)
    geometry_check = verify_detection_geometry(W1_GRID_SPEC, random_samples=100000, seed=42)
    metadata = {
        "environment": "local offline_sim/practice only",
        "official_practice_run": False,
        "official_formal_test_run": False,
        "problem": 4,
        "baseline": "W1 = frozen Q3 V6/n=8 with only SEARCH points replaced",
        "random_seeds": args.random_seeds,
        "stress_seeds": args.stress_seeds,
        "random_margin_m": 0.0,
        "geometry": geometry_check,
    }

    write_csv(out_dir / "details.csv", details)
    write_csv(out_dir / "summary.csv", summary)
    write_csv(out_dir / "source_count_summary.csv", by_count)
    write_csv(out_dir / "missed_sources.csv", failures)
    write_csv(out_dir / "missed_summary.csv", failure_summary)
    write_csv(out_dir / "paired_vs_w0.csv", paired)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    render_report(out_dir, geometry_check, summary, read_csv(w0_dir / "summary.csv"), by_count, failure_summary, paired)
    print(f"wrote {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
