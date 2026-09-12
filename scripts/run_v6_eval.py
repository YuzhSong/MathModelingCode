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
from q3.offline_policy import theoretical_outer_radius
from q3.planner import Q3BaselinePlanner
from q3.v5_policy import policy_v4_diagnostic, policy_v5b
from q3.v5_prediction import V5PredictionConfig
from q3.v6_policy import policy_v6
from scripts.run_v5_eval import (
    episode_row,
    parse_seed_range,
    percentile,
    source_diagnostic_rows,
    summarize,
    verify_frozen_v4,
    write_csv,
)


POLICIES: dict[str, Callable] = {
    "v4": policy_v4_diagnostic,
    "v5b": policy_v5b,
    "v6": policy_v6,
}


def route_event_rows(version: str, suite: str, seed: int, diagnostics: list[dict]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in diagnostics:
        if event.get("event") != "route_supplement_execution":
            continue
        rows.append(
            {
                "version": version,
                "suite": suite,
                "seed": seed,
                "channel": event["channel"],
                "time_s": event["time_s"],
                "selected_x": event["selected_x"],
                "selected_y": event["selected_y"],
                "selected_search_index": event["selected_search_index"],
                "selected_p_clear": event["selected_p_clear"],
                "selected_route_marginal_s": event["selected_route_marginal_s"],
                "selected_expected_future_cost_s": event["selected_expected_future_cost_s"],
                "selected_objective_s": event["selected_objective_s"],
                "highest_p_clear_x": event["highest_p_clear_x"],
                "highest_p_clear_y": event["highest_p_clear_y"],
                "highest_p_clear": event["highest_p_clear"],
                "highest_p_clear_route_marginal_s": event["highest_p_clear_route_marginal_s"],
                "highest_p_clear_objective_s": event["highest_p_clear_objective_s"],
                "abandoned_high_p_clear": int(event["abandoned_high_p_clear"]),
            }
        )
    return rows


def add_route_case_metrics(row: dict[str, Any], route_rows: list[dict[str, Any]]) -> None:
    abandoned = [item for item in route_rows if int(item["abandoned_high_p_clear"])]
    row.update(
        {
            "route_scored_supplement_count": len(route_rows),
            "mean_selected_route_marginal_s": (
                statistics.fmean(float(item["selected_route_marginal_s"]) for item in route_rows)
                if route_rows
                else 0.0
            ),
            "abandoned_high_p_clear_count": len(abandoned),
            "mean_rejected_high_p_clear_route_marginal_s": (
                statistics.fmean(float(item["highest_p_clear_route_marginal_s"]) for item in abandoned)
                if abandoned
                else 0.0
            ),
            "mean_selected_route_marginal_when_abandon_s": (
                statistics.fmean(float(item["selected_route_marginal_s"]) for item in abandoned)
                if abandoned
                else 0.0
            ),
        }
    )


def add_route_summary_metrics(summary: dict[str, Any], route_rows: list[dict[str, Any]]) -> None:
    abandoned = [item for item in route_rows if int(item["abandoned_high_p_clear"])]
    summary.update(
        {
            "route_scored_supplement_count": len(route_rows),
            "mean_selected_route_marginal_s": (
                statistics.fmean(float(item["selected_route_marginal_s"]) for item in route_rows)
                if route_rows
                else 0.0
            ),
            "abandoned_high_p_clear_count": len(abandoned),
            "abandoned_high_p_clear_rate": len(abandoned) / len(route_rows) if route_rows else 0.0,
            "mean_rejected_high_p_clear_route_marginal_s": (
                statistics.fmean(float(item["highest_p_clear_route_marginal_s"]) for item in abandoned)
                if abandoned
                else 0.0
            ),
            "mean_selected_route_marginal_when_abandon_s": (
                statistics.fmean(float(item["selected_route_marginal_s"]) for item in abandoned)
                if abandoned
                else 0.0
            ),
        }
    )


def paired_comparisons(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {(row["version"], row["suite"], int(row["seed"])): row for row in details}
    output: list[dict[str, Any]] = []
    for base in ("v4", "v5b"):
        for suite in ("random", "min_reff", "collinear", "overall"):
            keys = sorted(
                (row["suite"], int(row["seed"]))
                for row in details
                if row["version"] == base and (suite == "overall" or row["suite"] == suite)
            )
            pairs = [(lookup[(base, group, seed)], lookup[("v6", group, seed)]) for group, seed in keys]
            deltas = [float(target["total_time_s"]) - float(left["total_time_s"]) for left, target in pairs]
            output.append(
                {
                    "base": base,
                    "target": "v6",
                    "suite": suite,
                    "pairs": len(pairs),
                    "target_win_rate": sum(delta < 0.0 for delta in deltas) / len(deltas),
                    "mean_delta_time_s": statistics.fmean(deltas),
                    "median_delta_time_s": statistics.median(deltas),
                    "p95_delta_time_s": percentile(deltas, 0.95),
                    "max_delta_time_s": max(deltas),
                    "worse_over_300s_count": sum(delta > 300.0 for delta in deltas),
                    "mean_delta_move_m": statistics.fmean(
                        float(target["move_distance_m"]) - float(left["move_distance_m"])
                        for left, target in pairs
                    ),
                    "mean_delta_supplements": statistics.fmean(
                        int(target["supplement_measure_count"]) - int(left["supplement_measure_count"])
                        for left, target in pairs
                    ),
                    "mean_delta_found_after_move_m": statistics.fmean(
                        float(target["found_after_extra_move_m"]) - float(left["found_after_extra_move_m"])
                        for left, target in pairs
                    ),
                }
            )
    return output


def abandonment_effect(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {(row["version"], row["suite"], int(row["seed"])): row for row in details}
    output: list[dict[str, Any]] = []
    for suite in ("random", "min_reff", "collinear", "overall"):
        v6_rows = [
            row
            for row in details
            if row["version"] == "v6"
            and int(row["abandoned_high_p_clear_count"]) > 0
            and (suite == "overall" or row["suite"] == suite)
        ]
        deltas = [
            float(row["total_time_s"])
            - float(lookup[("v5b", row["suite"], int(row["seed"]))]["total_time_s"])
            for row in v6_rows
        ]
        output.append(
            {
                "suite": suite,
                "cases_with_abandonment": len(v6_rows),
                "v6_win_rate_vs_v5b": sum(delta < 0.0 for delta in deltas) / len(deltas) if deltas else 0.0,
                "mean_v6_minus_v5b_s": statistics.fmean(deltas) if deltas else 0.0,
                "median_v6_minus_v5b_s": statistics.median(deltas) if deltas else 0.0,
                "total_v6_minus_v5b_s": sum(deltas),
                "p95_v6_minus_v5b_s": percentile(deltas, 0.95),
                "max_v6_minus_v5b_s": max(deltas, default=0.0),
            }
        )
    return output


def typical_cases(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {(row["version"], row["suite"], int(row["seed"])): row for row in details}
    output: list[dict[str, Any]] = []
    keys = [(row["suite"], int(row["seed"])) for row in details if row["version"] == "v6"]
    for base in ("v4", "v5b"):
        cases = []
        for suite, seed in keys:
            left = lookup[(base, suite, seed)]
            target = lookup[("v6", suite, seed)]
            delta = float(target["total_time_s"]) - float(left["total_time_s"])
            cases.append((delta, left, target))
        selected = sorted(cases, key=lambda item: item[0])[:3] + sorted(cases, key=lambda item: item[0], reverse=True)[:3]
        for rank, (delta, left, target) in enumerate(selected):
            output.append(
                {
                    "base": base,
                    "kind": "success" if rank < 3 else "failure",
                    "suite": left["suite"],
                    "seed": left["seed"],
                    "delta_time_s": delta,
                    "base_time_s": left["total_time_s"],
                    "v6_time_s": target["total_time_s"],
                    "delta_move_m": float(target["move_distance_m"]) - float(left["move_distance_m"]),
                    "delta_supplements": int(target["supplement_measure_count"]) - int(left["supplement_measure_count"]),
                    "v6_abandoned_high_p_clear_count": target["abandoned_high_p_clear_count"],
                }
            )
    return output


def assert_v6_ground_truth_isolated() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (Path("q3/v6_policy.py"), Path("q3/v5_prediction.py")):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("offline_sim"):
                raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Import) and any(alias.name.startswith("offline_sim") for alias in node.names):
                raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Attribute) and node.attr in {"case", "engine", "sources", "jammers"}:
                raise RuntimeError(f"ground-truth isolation failed: {relative} accesses .{node.attr}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline-only Q3 V6 route-aware supplement evaluation.")
    parser.add_argument("--versions", default="v4,v5b,v6")
    parser.add_argument("--random-seeds", default="0:100")
    parser.add_argument("--stress-seeds", default="10000:10050")
    parser.add_argument("--out-dir", default="results/offline_eval_v6_n8")
    parser.add_argument(
        "--frozen-v4-details",
        default="frozen/v4_n8_20260911/results/offline_eval_v4_n8_n9/details.csv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    assert_v6_ground_truth_isolated()
    versions = [value.strip() for value in args.versions.split(",") if value.strip()]
    for version in versions:
        if version not in POLICIES:
            raise SystemExit(f"unknown version {version!r}")
    random_seeds = parse_seed_range(args.random_seeds)
    stress_seeds = parse_seed_range(args.stress_seeds)
    suites = [
        ("random", random_seeds, "smooth"),
        ("min_reff", stress_seeds, "adversarial"),
        ("collinear", stress_seeds, "adversarial"),
    ]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    radius = theoretical_outer_radius(8)
    scan_points = [(point.x, point.y) for point in Q3BaselinePlanner.make_search_points(radius, 8)]

    details: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    route_events: list[dict[str, Any]] = []
    for version in versions:
        policy = POLICIES[version]
        for suite, seeds, field_kind in suites:
            for index, seed in enumerate(seeds, start=1):
                if suite == "random":
                    case = generate_case(seed=seed, problem=3, mode="practice", field_kind=field_kind)
                else:
                    case = generate_stress_case(
                        suite,
                        seed=seed,
                        problem=3,
                        mode="practice",
                        field_kind=field_kind,
                        scan_points=scan_points,
                    )
                result = run_episode(case, lambda runner, selected=policy: selected(runner, n=8), include_oracles=False)
                source_rows = source_diagnostic_rows(version, suite, seed, result)
                current_route_events = route_event_rows(version, suite, seed, result.policy_diagnostics)
                row = episode_row(version, suite, seed, result, source_rows)
                add_route_case_metrics(row, current_route_events)
                details.append(row)
                sources.extend(source_rows)
                route_events.extend(current_route_events)
                if index % 10 == 0 or index == len(seeds):
                    print(f"[{version}/{suite}] {index}/{len(seeds)}", flush=True)

    summaries: list[dict[str, Any]] = []
    for version in versions:
        for suite in ("random", "min_reff", "collinear", "overall"):
            episode_subset = [row for row in details if row["version"] == version and (suite == "overall" or row["suite"] == suite)]
            source_subset = [row for row in sources if row["version"] == version and (suite == "overall" or row["suite"] == suite)]
            route_subset = [row for row in route_events if row["version"] == version and (suite == "overall" or row["suite"] == suite)]
            summary = summarize(version, suite, episode_subset, source_subset)
            add_route_summary_metrics(summary, route_subset)
            summaries.append(summary)

    pairs = paired_comparisons(details) if "v6" in versions and {"v4", "v5b"}.issubset(versions) else []
    abandon = abandonment_effect(details) if "v6" in versions and "v5b" in versions else []
    typical = typical_cases(details) if "v6" in versions and {"v4", "v5b"}.issubset(versions) else []
    frozen_check = verify_frozen_v4(details, Path(args.frozen_v4_details)) if "v4" in versions else {}
    config = V5PredictionConfig()
    metadata = {
        "environment": "local offline_sim practice only",
        "official_formal_test_run": False,
        "n": 8,
        "random_seeds": args.random_seeds,
        "stress_seeds": args.stress_seeds,
        "route_cost_definition": "frozen V4 open-route travel length / 5 m/s",
        "route_marginal_definition": "max(0, C_with_candidate - C_before); clamp removes heuristic non-monotonicity",
        "objective": "route_marginal_s + 5s measure service + V5 fixed-sample expected future localization/clear cost",
        "future_cost_approximation": "V5 visible-geometry outcome model with frozen V4-style fallback point; not full outcome rerouting",
        "prediction_config": {
            "sample_seed": config.sample_seed,
            "sample_count": config.sample_count,
            "bearing_error_offsets_deg": config.bearing_error_offsets_deg,
            "candidate_radii_m": config.candidate_radii_m,
            "candidate_angle_step_deg": config.candidate_angle_step_deg,
            "lambda_alpha": None,
        },
        "frozen_v4_equivalence": frozen_check,
    }

    write_csv(out_dir / "details.csv", details)
    write_csv(out_dir / "source_diagnostics.csv", sources)
    write_csv(out_dir / "route_decisions.csv", route_events)
    write_csv(out_dir / "summary.csv", summaries)
    write_csv(out_dir / "paired_comparison.csv", pairs)
    write_csv(out_dir / "abandonment_effect.csv", abandon)
    write_csv(out_dir / "typical_cases.csv", typical)
    (out_dir / "summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
