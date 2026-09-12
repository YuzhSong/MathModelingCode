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

from offline_sim.harness import EpisodeResult, run_episode
from q3.stage2_policy import (
    make_policy_m2,
    policy_m1,
    policy_mn,
    policy_n1,
    policy_n2,
    policy_n3,
    policy_v6_audit,
)
from q3.v6_policy import policy_v6
from scripts.run_v5_eval import (
    episode_row,
    percentile,
    source_diagnostic_rows,
    summarize,
    write_csv,
)
from scripts.run_way_benchmark import action_components, make_case, phase_rows


STATIC_POLICIES: dict[str, Callable] = {
    "v6": policy_v6,
    "v6audit": policy_v6_audit,
    "m1": policy_m1,
    "mn": policy_mn,
    "n1": policy_n1,
    "n2": policy_n2,
    "n3": policy_n3,
}


def parse_seed_range(spec: str) -> list[int]:
    if ":" in spec:
        start, stop = spec.split(":", 1)
        return list(range(int(start), int(stop)))
    return [int(part) for part in spec.split(",") if part.strip()]


def policy_for(version: str) -> Callable:
    if version in STATIC_POLICIES:
        return STATIC_POLICIES[version]
    if version.startswith("m2_b"):
        beta = float(version.removeprefix("m2_b").replace("p", "."))
        return make_policy_m2(beta)
    raise ValueError(f"unknown stage-2 version: {version}")


def stage2_event_rows(version: str, suite: str, seed: int, result: EpisodeResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in result.policy_diagnostics:
        if event.get("event") != "stage2_supplement_execution":
            continue
        rows.append(
            {
                "version": version,
                "suite": suite,
                "seed": seed,
                "channel": int(event["channel"]),
                "time_s": event.get("time_s"),
                "selected_family": event.get("selected_family"),
                "selected_worst_mec_after_m": event.get("selected_worst_mec_after_m"),
                "selected_stage2_objective_s": event.get("selected_stage2_objective_s"),
                "selected_v6_objective_s": event.get("selected_v6_objective_s"),
                "v6_selected_x": event.get("v6_selected_x"),
                "v6_selected_y": event.get("v6_selected_y"),
                "v6_selected_family": event.get("v6_selected_family"),
                "v6_selected_worst_mec_after_m": event.get("v6_selected_worst_mec_after_m"),
                "v6_selected_objective_s": event.get("v6_selected_objective_s"),
                "changed_from_v6": int(bool(event.get("changed_from_v6"))),
                "minimax_mode": event.get("minimax_mode"),
                "minimax_beta_s_per_m": event.get("minimax_beta_s_per_m"),
            }
        )
    return rows


def v6_audit_rows(version: str, suite: str, seed: int, result: EpisodeResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in result.policy_diagnostics:
        if event.get("event") != "v6_decision_audit":
            continue
        rows.append(
            {
                "version": version,
                "suite": suite,
                "seed": seed,
                "channel": int(event["channel"]),
                "time_s": event.get("time_s"),
                "selected_is_dedicated": int(bool(event.get("selected_is_dedicated"))),
                "selected_route_marginal_s": event.get("selected_route_marginal_s"),
                "selected_p_clear": event.get("selected_p_clear"),
                "selected_objective_s": event.get("selected_objective_s"),
                "remaining_search_count": event.get("remaining_search_count"),
                "legal_future_search_count": event.get("legal_future_search_count"),
                "nearest_future_search_to_selected_m": event.get("nearest_future_search_to_selected_m"),
                "best_future_search_objective_s": event.get("best_future_search_objective_s"),
                "best_future_search_route_marginal_s": event.get("best_future_search_route_marginal_s"),
                "best_future_search_p_clear": event.get("best_future_search_p_clear"),
            }
        )
    return rows


def phase_summary_rows(phases: list[dict[str, Any]], versions: list[str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for version in versions:
        for suite in ("random", "min_reff", "collinear", "overall"):
            for phase in ("search", "found", "clear"):
                subset = [
                    row
                    for row in phases
                    if row["version"] == version
                    and row["phase"] == phase
                    and (suite == "overall" or row["suite"] == suite)
                ]
                if not subset:
                    continue
                output.append(
                    {
                        "version": version,
                        "suite": suite,
                        "phase": phase,
                        "cases": len(subset),
                        "mean_move_time_s": statistics.fmean(float(row["move_time_s"]) for row in subset),
                        "mean_move_distance_m": statistics.fmean(float(row["move_distance_m"]) for row in subset),
                        "mean_measure_time_s": statistics.fmean(float(row["measure_time_s"]) for row in subset),
                        "mean_switch_time_s": statistics.fmean(float(row["switch_time_s"]) for row in subset),
                        "mean_clear_time_s": statistics.fmean(float(row["clear_time_s"]) for row in subset),
                        "mean_total_time_s": statistics.fmean(
                            float(row["move_time_s"])
                            + float(row["measure_time_s"])
                            + float(row["switch_time_s"])
                            + float(row["clear_time_s"])
                            for row in subset
                        ),
                        "mean_measure_count": statistics.fmean(int(row["measure_count"]) for row in subset),
                    }
                )
    return output


def paired_rows(details: list[dict[str, Any]], versions: list[str]) -> list[dict[str, Any]]:
    lookup = {(str(row["version"]), str(row["suite"]), int(row["seed"])): row for row in details}
    base_keys = sorted((str(row["suite"]), int(row["seed"])) for row in details if row["version"] == "v6")
    output: list[dict[str, Any]] = []
    for version in versions:
        if version == "v6":
            continue
        for suite in ("random", "min_reff", "collinear", "overall"):
            keys = [key for key in base_keys if suite == "overall" or key[0] == suite]
            pairs = [(lookup[("v6", group, seed)], lookup[(version, group, seed)]) for group, seed in keys]
            deltas = [float(target["total_time_s"]) - float(base["total_time_s"]) for base, target in pairs]
            if not deltas:
                continue
            output.append(
                {
                    "base": "v6",
                    "target": version,
                    "suite": suite,
                    "pairs": len(pairs),
                    "target_win_rate": sum(delta < 0.0 for delta in deltas) / len(deltas),
                    "mean_delta_time_s": statistics.fmean(deltas),
                    "median_delta_time_s": statistics.median(deltas),
                    "p95_delta_time_s": percentile(deltas, 0.95),
                    "worst_regression_s": max(deltas),
                    "best_improvement_s": min(deltas),
                    "worse_over_300s_count": sum(delta > 300.0 for delta in deltas),
                    "mean_delta_move_m": statistics.fmean(
                        float(target["move_distance_m"]) - float(base["move_distance_m"])
                        for base, target in pairs
                    ),
                    "mean_delta_measure_count": statistics.fmean(
                        int(target["measure_count"]) - int(base["measure_count"])
                        for base, target in pairs
                    ),
                    "mean_delta_found_after_move_m": statistics.fmean(
                        float(target["found_after_extra_move_m"]) - float(base["found_after_extra_move_m"])
                        for base, target in pairs
                    ),
                    "mean_delta_off_search_supplement_move_m": statistics.fmean(
                        float(target["off_search_supplement_move_m"])
                        - float(base["off_search_supplement_move_m"])
                        for base, target in pairs
                    ),
                }
            )
    return output


def verify_v6_replay(details: list[dict[str, Any]], reference_path: Path) -> dict[str, Any]:
    with reference_path.open(newline="", encoding="utf-8") as handle:
        reference = {
            (row["suite"], int(row["seed"])): row
            for row in csv.DictReader(handle)
            if row["version"] == "v6"
        }
    current = {
        (str(row["suite"]), int(row["seed"])): row
        for row in details
        if row["version"] == "v6"
    }
    common = sorted(set(reference) & set(current))
    time_delta = [abs(float(current[key]["total_time_s"]) - float(reference[key]["total_time_s"])) for key in common]
    move_delta = [abs(float(current[key]["move_distance_m"]) - float(reference[key]["move_distance_m"])) for key in common]
    return {
        "pairs": len(common),
        "max_abs_time_delta_s": max(time_delta, default=0.0),
        "max_abs_move_delta_m": max(move_delta, default=0.0),
        "equivalent": bool(common and max(time_delta, default=0.0) <= 1e-6 and max(move_delta, default=0.0) <= 1e-6),
    }


def assert_policy_ground_truth_isolated() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (Path("q3/stage2_policy.py"), Path("q3/v6_policy.py"), Path("q3/v5_prediction.py")):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("offline_sim"):
                raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Import) and any(alias.name.startswith("offline_sim") for alias in node.names):
                raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Attribute) and node.attr in {"case", "engine", "sources", "jammers"}:
                raise RuntimeError(f"ground-truth isolation failed: {relative} accesses .{node.attr}")


def render_brief_report(out_dir: Path, summaries: list[dict[str, Any]], pairs: list[dict[str, Any]]) -> None:
    overall = {row["version"]: row for row in summaries if row["suite"] == "overall"}
    lines = [
        "# Q3 Stage-2 Controlled Ablation",
        "",
        "Local `offline_sim` practice-only. No official HTTP or formal test was called.",
        "",
        "| Version | Clear rate | Mean s | Median s | P95 s | Max s | Move m | Measures | Clear fail |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for version, row in overall.items():
        lines.append(
            f"| {version} | {100*row['clear_rate']:.1f}% | {row['mean_total_time_s']:.2f} | "
            f"{row['median_total_time_s']:.2f} | {row['p95_total_time_s']:.2f} | "
            f"{row['max_total_time_s']:.2f} | {row['mean_move_distance_m']:.2f} | "
            f"{row['mean_measure_count']:.2f} | {row['clear_fail_total']} |"
        )
    lines.extend(
        [
            "",
            "| Target vs V6 | Win rate | Mean delta s | Median | P95 delta | Worst | Best | >300s |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in pairs:
        if row["suite"] != "overall":
            continue
        lines.append(
            f"| {row['target']} | {100*row['target_win_rate']:.1f}% | {row['mean_delta_time_s']:.2f} | "
            f"{row['median_delta_time_s']:.2f} | {row['p95_delta_time_s']:.2f} | "
            f"{row['worst_regression_s']:.2f} | {row['best_improvement_s']:.2f} | "
            f"{row['worse_over_300s_count']} |"
        )
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Q3 stage-2 controlled offline ablations.")
    parser.add_argument("--versions", default="v6,m1,m2_b0p25,n1,n2,n3")
    parser.add_argument("--random-seeds", default="0:100")
    parser.add_argument("--stress-seeds", default="10000:10050")
    parser.add_argument("--out-dir", default="results/offline_eval_stage2")
    parser.add_argument("--reference-v6", default="results/offline_eval_v6_n8/details.csv")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    assert_policy_ground_truth_isolated()
    versions = [item.strip() for item in args.versions.split(",") if item.strip()]
    policies = {version: policy_for(version) for version in versions}
    suites = [
        ("random", parse_seed_range(args.random_seeds), "smooth"),
        ("min_reff", parse_seed_range(args.stress_seeds), "adversarial"),
        ("collinear", parse_seed_range(args.stress_seeds), "adversarial"),
    ]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    details: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    phases: list[dict[str, Any]] = []
    stage2_events: list[dict[str, Any]] = []
    audit_events: list[dict[str, Any]] = []
    for version in versions:
        policy = policies[version]
        for suite, seeds, field_kind in suites:
            for index, seed in enumerate(seeds, start=1):
                case = make_case(suite, seed, field_kind)
                result = run_episode(case, lambda runner, selected=policy: selected(runner, n=8), include_oracles=False)
                source_rows = source_diagnostic_rows(version, suite, seed, result)
                details.append(episode_row(version, suite, seed, result, source_rows))
                sources.extend(source_rows)
                phases.extend(phase_rows(version, suite, seed, result))
                stage2_events.extend(stage2_event_rows(version, suite, seed, result))
                audit_events.extend(v6_audit_rows(version, suite, seed, result))
                if index % 10 == 0 or index == len(seeds):
                    print(f"[{version}/{suite}] {index}/{len(seeds)}", flush=True)

    summaries: list[dict[str, Any]] = []
    for version in versions:
        for suite in ("random", "min_reff", "collinear", "overall"):
            detail_subset = [
                row for row in details if row["version"] == version and (suite == "overall" or row["suite"] == suite)
            ]
            source_subset = [
                row for row in sources if row["version"] == version and (suite == "overall" or row["suite"] == suite)
            ]
            if not detail_subset:
                continue
            summary = summarize(version, suite, detail_subset, source_subset)
            summary["std_total_time_s"] = statistics.pstdev(float(row["total_time_s"]) for row in detail_subset)
            summaries.append(summary)

    pairs = paired_rows(details, versions) if "v6" in versions else []
    phase_summary = phase_summary_rows(phases, versions)
    reference_check = (
        verify_v6_replay(details, Path(args.reference_v6))
        if "v6" in versions and Path(args.reference_v6).exists()
        else {}
    )
    metadata = {
        "environment": "local offline_sim practice only",
        "official_formal_test_run": False,
        "ground_truth_policy_use": False,
        "n": 8,
        "versions": versions,
        "random_seeds": args.random_seeds,
        "stress_seeds": args.stress_seeds,
        "m1": "same V6 candidates; lexicographic minimum sampled worst-after MEC, then V6 objective",
        "m2": "V6 objective seconds + beta[s/m] * sampled worst-after MEC[m]",
        "n1": "V6 candidates plus 85m near-field ring after one supplement still leaves MEC>20m",
        "n2": "V6 candidates plus exact perpendicular large-angle points after one supplement still leaves MEC>20m",
        "n3": "union of N1 and N2 candidates under the same difficulty gate",
        "v6_reference_equivalence": reference_check,
    }

    write_csv(out_dir / "details.csv", details)
    write_csv(out_dir / "source_diagnostics.csv", sources)
    write_csv(out_dir / "phase_decomposition.csv", phases)
    write_csv(out_dir / "phase_summary.csv", phase_summary)
    write_csv(out_dir / "stage2_decisions.csv", stage2_events)
    write_csv(out_dir / "v6_audit.csv", audit_events)
    write_csv(out_dir / "summary.csv", summaries)
    write_csv(out_dir / "paired_vs_v6.csv", pairs)
    (out_dir / "summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    render_brief_report(out_dir, summaries, pairs)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
