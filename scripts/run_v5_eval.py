from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.case import generate_case, generate_stress_case
from offline_sim.harness import EpisodeResult, run_episode
from q3.planner import Q3BaselinePlanner
from q3.offline_policy import theoretical_outer_radius
from q3.v5_policy import policy_v4_diagnostic, policy_v5_final, policy_v5a, policy_v5b
from q3.v5_prediction import V5PredictionConfig


POLICIES: dict[str, Callable] = {
    "v4": policy_v4_diagnostic,
    "v5a": policy_v5a,
    "v5b": policy_v5b,
    "v5final": policy_v5_final,
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
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def first_supplement_bucket(event: dict[str, Any]) -> str:
    if event.get("clearable_after"):
        return "le20_or_near"
    radius = event.get("mec_after_m")
    if radius is None:
        return "unknown"
    radius = float(radius)
    if radius <= 25.0:
        return "20_25"
    if radius <= 30.0:
        return "25_30"
    if radius <= 50.0:
        return "30_50"
    return "gt50"


def source_diagnostic_rows(
    version: str,
    suite: str,
    seed: int,
    result: EpisodeResult,
) -> list[dict[str, Any]]:
    by_channel: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in result.policy_diagnostics:
        channel = event.get("channel")
        if channel is not None:
            by_channel[int(channel)].append(event)

    rows: list[dict[str, Any]] = []
    for channel, events in sorted(by_channel.items()):
        found = next((event for event in events if event.get("event") == "first_found"), None)
        if found is None:
            continue
        supplements = [event for event in events if event.get("event") == "supplement_measure"]
        clear = next(
            (event for event in events if event.get("event") == "clear" and event.get("result") == "success"),
            None,
        )
        off_search = [event for event in supplements if not event.get("at_mandatory_search")]
        threshold_chasing = [
            event
            for event in off_search
            if event.get("mec_before_m") is not None and 20.0 < float(event["mec_before_m"]) <= 30.0
        ]
        wait_realized = [event for event in supplements if event.get("waited_for_search")]
        wait_saved_proxy = [event for event in wait_realized if event.get("clearable_after")]
        attributed_extra_move = sum(float(event.get("arrival_move_m") or 0.0) for event in off_search)
        off_search_move = attributed_extra_move
        if clear is not None:
            attributed_extra_move += float(clear.get("arrival_move_m") or 0.0)
        first_supplement = supplements[0] if supplements else None

        rows.append(
            {
                "version": version,
                "suite": suite,
                "seed": seed,
                "channel": channel,
                "first_found_time_s": found.get("time_s"),
                "clear_time_s": None if clear is None else clear.get("time_s"),
                "supplement_measure_count": len(supplements),
                "supplement_measure_points_json": json.dumps(
                    [[event.get("x"), event.get("y")] for event in supplements], separators=(",", ":")
                ),
                "supplement_measure_times_json": json.dumps(
                    [event.get("time_s") for event in supplements], separators=(",", ":")
                ),
                "supplement_mec_before_json": json.dumps(
                    [event.get("mec_before_m") for event in supplements], separators=(",", ":")
                ),
                "supplement_mec_after_json": json.dumps(
                    [event.get("mec_after_m") for event in supplements], separators=(",", ":")
                ),
                "supplement_arrival_move_json": json.dumps(
                    [event.get("arrival_move_m") for event in supplements], separators=(",", ":")
                ),
                "supplement_at_search_json": json.dumps(
                    [bool(event.get("at_mandatory_search")) for event in supplements], separators=(",", ":")
                ),
                "final_clear_mec_m": None if clear is None else clear.get("final_mec_m"),
                "found_after_extra_move_m": attributed_extra_move,
                "off_search_supplement_move_m": off_search_move,
                "off_search_supplement_count": len(off_search),
                "threshold_chasing_20_30_count": len(threshold_chasing),
                "first_supplement_clearable": int(bool(first_supplement and first_supplement.get("clearable_after"))),
                "first_supplement_bucket": "none" if first_supplement is None else first_supplement_bucket(first_supplement),
                "waited_search_supplement_count": len(wait_realized),
                "wait_saved_dedicated_proxy_count": len(wait_saved_proxy),
            }
        )
    return rows


def episode_row(
    version: str,
    suite: str,
    seed: int,
    result: EpisodeResult,
    source_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    move_time = result.move_distance_m / 5.0
    measure_time = result.n_measure * 5.0
    switch_time = float(result.n_channel_switch)
    clear_success = result.n_clear - result.n_clear_fail
    clear_time = clear_success * 5.0 + result.n_clear_fail * 3.0
    supplement_sources = [row for row in source_rows if int(row["supplement_measure_count"]) > 0]
    return {
        "version": version,
        "n": 8,
        "suite": suite,
        "seed": seed,
        "success": int(result.success),
        "cleared": result.cleared,
        "total": result.total,
        "total_time_s": result.virtual_time_s,
        "avg_source_s": result.virtual_time_s / result.cleared if result.cleared else 0.0,
        "move_distance_m": result.move_distance_m,
        "move_time_s": move_time,
        "measure_count": result.n_measure,
        "measure_time_s": measure_time,
        "switch_count": result.n_channel_switch,
        "switch_time_s": switch_time,
        "clear_success": clear_success,
        "clear_fail": result.n_clear_fail,
        "clear_time_s": clear_time,
        "time_component_delta_s": result.virtual_time_s - (move_time + measure_time + switch_time + clear_time),
        "policy_runtime_s": result.policy_runtime_s,
        "found_source_count": len(source_rows),
        "supplement_measure_count": sum(int(row["supplement_measure_count"]) for row in source_rows),
        "supplement_source_count": len(supplement_sources),
        "first_supplement_clearable_count": sum(int(row["first_supplement_clearable"]) for row in supplement_sources),
        "off_search_supplement_count": sum(int(row["off_search_supplement_count"]) for row in source_rows),
        "found_after_extra_move_m": sum(float(row["found_after_extra_move_m"]) for row in source_rows),
        "off_search_supplement_move_m": sum(float(row["off_search_supplement_move_m"]) for row in source_rows),
        "threshold_chasing_20_30_count": sum(int(row["threshold_chasing_20_30_count"]) for row in source_rows),
        "waited_search_supplement_count": sum(int(row["waited_search_supplement_count"]) for row in source_rows),
        "wait_saved_dedicated_proxy_count": sum(int(row["wait_saved_dedicated_proxy_count"]) for row in source_rows),
        "error": result.error or "",
    }


def summarize(version: str, suite: str, rows: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    times = [float(row["total_time_s"]) for row in rows]
    cleared = sum(int(row["cleared"]) for row in rows)
    supplement_sources = [row for row in sources if int(row["supplement_measure_count"]) > 0]
    buckets = ["le20_or_near", "20_25", "25_30", "30_50", "gt50", "unknown"]
    summary: dict[str, Any] = {
        "version": version,
        "n": 8,
        "suite": suite,
        "episodes": len(rows),
        "clear_rate": sum(int(row["success"]) for row in rows) / len(rows),
        "mean_total_time_s": statistics.fmean(times),
        "median_total_time_s": statistics.median(times),
        "p95_total_time_s": percentile(times, 0.95),
        "max_total_time_s": max(times),
        "mean_avg_source_s": statistics.fmean(float(row["avg_source_s"]) for row in rows),
        "pooled_avg_source_s": sum(times) / cleared if cleared else 0.0,
        "mean_move_distance_m": statistics.fmean(float(row["move_distance_m"]) for row in rows),
        "mean_move_time_s": statistics.fmean(float(row["move_time_s"]) for row in rows),
        "mean_measure_count": statistics.fmean(int(row["measure_count"]) for row in rows),
        "mean_measure_time_s": statistics.fmean(float(row["measure_time_s"]) for row in rows),
        "mean_switch_count": statistics.fmean(int(row["switch_count"]) for row in rows),
        "mean_switch_time_s": statistics.fmean(float(row["switch_time_s"]) for row in rows),
        "mean_clear_success": statistics.fmean(int(row["clear_success"]) for row in rows),
        "mean_clear_time_s": statistics.fmean(float(row["clear_time_s"]) for row in rows),
        "clear_fail_total": sum(int(row["clear_fail"]) for row in rows),
        "max_abs_time_component_delta_s": max(abs(float(row["time_component_delta_s"])) for row in rows),
        "mean_policy_runtime_s": statistics.fmean(float(row["policy_runtime_s"]) for row in rows),
        "p95_policy_runtime_s": percentile([float(row["policy_runtime_s"]) for row in rows], 0.95),
        "max_policy_runtime_s": max(float(row["policy_runtime_s"]) for row in rows),
        "source_count": len(sources),
        "mean_supplement_measures_per_source": (
            sum(int(row["supplement_measure_count"]) for row in sources) / len(sources) if sources else 0.0
        ),
        "first_supplement_clearable_rate": (
            sum(int(row["first_supplement_clearable"]) for row in supplement_sources) / len(supplement_sources)
            if supplement_sources
            else 0.0
        ),
        "off_search_supplement_total": sum(int(row["off_search_supplement_count"]) for row in sources),
        "off_search_supplement_per_source": (
            sum(int(row["off_search_supplement_count"]) for row in sources) / len(sources) if sources else 0.0
        ),
        "found_after_extra_move_total_m": sum(float(row["found_after_extra_move_m"]) for row in sources),
        "found_after_extra_move_per_source_m": (
            sum(float(row["found_after_extra_move_m"]) for row in sources) / len(sources) if sources else 0.0
        ),
        "off_search_supplement_move_total_m": sum(float(row["off_search_supplement_move_m"]) for row in sources),
        "off_search_supplement_move_per_source_m": (
            sum(float(row["off_search_supplement_move_m"]) for row in sources) / len(sources) if sources else 0.0
        ),
        "threshold_chasing_20_30_total": sum(int(row["threshold_chasing_20_30_count"]) for row in sources),
        "waited_search_supplement_total": sum(int(row["waited_search_supplement_count"]) for row in sources),
        "wait_saved_dedicated_proxy_total": sum(int(row["wait_saved_dedicated_proxy_count"]) for row in sources),
    }
    denominator = len(supplement_sources)
    for bucket in buckets:
        count = sum(row["first_supplement_bucket"] == bucket for row in supplement_sources)
        summary[f"first_supplement_{bucket}_count"] = count
        summary[f"first_supplement_{bucket}_rate"] = count / denominator if denominator else 0.0
    return summary


def paired_rows(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {(row["version"], row["suite"], int(row["seed"])): row for row in details}
    output: list[dict[str, Any]] = []
    present_versions = sorted({str(row["version"]) for row in details})
    for target in [version for version in present_versions if version != "v4"]:
        for suite in ["random", "min_reff", "collinear", "overall"]:
            keys = sorted(
                (row["suite"], int(row["seed"]))
                for row in details
                if row["version"] == "v4" and (suite == "overall" or row["suite"] == suite)
            )
            pairs = [(lookup[("v4", group, seed)], lookup[(target, group, seed)]) for group, seed in keys]
            deltas = [float(right["total_time_s"]) - float(left["total_time_s"]) for left, right in pairs]
            supplement_deltas = [
                int(right["supplement_measure_count"]) - int(left["supplement_measure_count"]) for left, right in pairs
            ]
            move_deltas = [
                float(right["found_after_extra_move_m"]) - float(left["found_after_extra_move_m"])
                for left, right in pairs
            ]
            off_search_move_deltas = [
                float(right["off_search_supplement_move_m"]) - float(left["off_search_supplement_move_m"])
                for left, right in pairs
            ]
            output.append(
                {
                    "base": "v4",
                    "target": target,
                    "suite": suite,
                    "pairs": len(pairs),
                    "target_win_rate": sum(delta < 0.0 for delta in deltas) / len(deltas),
                    "mean_delta_time_s": statistics.fmean(deltas),
                    "median_delta_time_s": statistics.median(deltas),
                    "p95_delta_time_s": percentile(deltas, 0.95),
                    "max_delta_time_s": max(deltas),
                    "mean_delta_supplement_count": statistics.fmean(supplement_deltas),
                    "total_delta_supplement_count": sum(supplement_deltas),
                    "mean_delta_found_after_move_m": statistics.fmean(move_deltas),
                    "total_delta_found_after_move_m": sum(move_deltas),
                    "mean_delta_off_search_supplement_move_m": statistics.fmean(off_search_move_deltas),
                    "total_delta_off_search_supplement_move_m": sum(off_search_move_deltas),
                    "tail_worse_over_300s_count": sum(delta > 300.0 for delta in deltas),
                    "tail_worse_over_300s_rate": sum(delta > 300.0 for delta in deltas) / len(deltas),
                }
            )
    return output


def typical_case_rows(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {(row["version"], row["suite"], int(row["seed"])): row for row in details}
    output: list[dict[str, Any]] = []
    base_keys = [(row["suite"], int(row["seed"])) for row in details if row["version"] == "v4"]
    present_versions = sorted({str(row["version"]) for row in details})
    for target in [version for version in present_versions if version != "v4"]:
        cases = []
        for suite, seed in base_keys:
            left = lookup[("v4", suite, seed)]
            right = lookup[(target, suite, seed)]
            cases.append((float(right["total_time_s"]) - float(left["total_time_s"]), left, right))
        selected = sorted(cases, key=lambda item: item[0])[:3] + sorted(cases, key=lambda item: item[0], reverse=True)[:3]
        for rank, (delta, left, right) in enumerate(selected):
            output.append(
                {
                    "target": target,
                    "kind": "success" if rank < 3 else "failure",
                    "suite": left["suite"],
                    "seed": left["seed"],
                    "delta_time_s": delta,
                    "v4_time_s": left["total_time_s"],
                    "target_time_s": right["total_time_s"],
                    "delta_move_m": float(right["move_distance_m"]) - float(left["move_distance_m"]),
                    "delta_supplements": int(right["supplement_measure_count"]) - int(left["supplement_measure_count"]),
                    "delta_found_after_move_m": float(right["found_after_extra_move_m"]) - float(left["found_after_extra_move_m"]),
                }
            )
    return output


def verify_frozen_v4(details: list[dict[str, Any]], frozen_path: Path) -> dict[str, Any]:
    with frozen_path.open(newline="", encoding="utf-8") as handle:
        frozen = {
            (row["suite"], int(row["seed"])): row
            for row in csv.DictReader(handle)
            if row["version"] == "v4" and int(row["n"]) == 8
        }
    current = {(row["suite"], int(row["seed"])): row for row in details if row["version"] == "v4"}
    common = sorted(set(frozen) & set(current))
    time_deltas = [abs(float(current[key]["total_time_s"]) - float(frozen[key]["virtual_time_s"])) for key in common]
    move_deltas = [abs(float(current[key]["move_distance_m"]) - float(frozen[key]["move_distance_m"])) for key in common]
    count_mismatches = sum(
        int(current[key]["measure_count"]) != int(frozen[key]["n_measure"])
        or int(current[key]["switch_count"]) != int(frozen[key]["n_channel_switch"])
        or int(current[key]["clear_fail"]) != int(frozen[key]["n_clear_fail"])
        for key in common
    )
    return {
        "pairs": len(common),
        "max_abs_time_delta_s": max(time_deltas, default=0.0),
        "max_abs_move_delta_m": max(move_deltas, default=0.0),
        "count_mismatch_cases": count_mismatches,
        "equivalent": bool(common and max(time_deltas, default=0.0) <= 1e-6 and max(move_deltas, default=0.0) <= 1e-6 and count_mismatches == 0),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline-only Q3 V5 task-generation evaluation.")
    parser.add_argument("--versions", default="v4,v5a,v5b,v5final")
    parser.add_argument("--random-seeds", default="0:100")
    parser.add_argument("--stress-seeds", default="10000:10050")
    parser.add_argument("--out-dir", default="results/offline_eval_v5_n8")
    parser.add_argument(
        "--frozen-v4-details",
        default="frozen/v4_n8_20260911/results/offline_eval_v4_n8_n9/details.csv",
    )
    return parser.parse_args()


def assert_policy_ground_truth_isolated() -> None:
    """Reject direct simulator-internal references in the V5 policy modules."""
    root = Path(__file__).resolve().parents[1]
    for relative in [Path("q3/v5_policy.py"), Path("q3/v5_prediction.py")]:
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]
                module = node.module or "" if isinstance(node, ast.ImportFrom) else ""
                if module.startswith("offline_sim") or any(name.startswith("offline_sim") for name in names):
                    raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Attribute) and node.attr in {"case", "engine", "sources", "jammers"}:
                raise RuntimeError(f"ground-truth isolation failed: {relative} accesses .{node.attr}")


def main() -> int:
    args = parse_args()
    assert_policy_ground_truth_isolated()
    versions = [value.strip() for value in args.versions.split(",") if value.strip()]
    random_seeds = parse_seed_range(args.random_seeds)
    stress_seeds = parse_seed_range(args.stress_seeds)
    suites = [
        ("random", random_seeds, "smooth"),
        ("min_reff", stress_seeds, "adversarial"),
        ("collinear", stress_seeds, "adversarial"),
    ]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    details: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    radius = theoretical_outer_radius(8)
    scan_points = [(point.x, point.y) for point in Q3BaselinePlanner.make_search_points(radius, 8)]
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
                result = run_episode(case, lambda runner, p=policy: p(runner, n=8), include_oracles=False)
                source_rows = source_diagnostic_rows(version, suite, seed, result)
                sources.extend(source_rows)
                details.append(episode_row(version, suite, seed, result, source_rows))
                if index % 10 == 0 or index == len(seeds):
                    print(f"[{version}/{suite}] {index}/{len(seeds)}")

    summaries: list[dict[str, Any]] = []
    for version in versions:
        for suite in ["random", "min_reff", "collinear", "overall"]:
            episode_subset = [row for row in details if row["version"] == version and (suite == "overall" or row["suite"] == suite)]
            source_subset = [row for row in sources if row["version"] == version and (suite == "overall" or row["suite"] == suite)]
            summaries.append(summarize(version, suite, episode_subset, source_subset))

    pairs = paired_rows(details)
    typical = typical_case_rows(details)
    frozen_check = verify_frozen_v4(details, Path(args.frozen_v4_details)) if "v4" in versions else {}
    config = V5PredictionConfig()
    metadata = {
        "environment": "local offline_sim practice only",
        "official_formal_test_run": False,
        "n": 8,
        "random_seeds": args.random_seeds,
        "stress_seeds": args.stress_seeds,
        "prediction_config": {
            "sample_seed": config.sample_seed,
            "sample_count": config.sample_count,
            "bearing_error_offsets_deg": config.bearing_error_offsets_deg,
            "candidate_radii_m": config.candidate_radii_m,
            "candidate_angle_step_deg": config.candidate_angle_step_deg,
            "v5a_objective": "minimum expected incremental completion time; mandatory-search movement costs zero",
            "v5b_objective": "maximum predicted P_clear, then minimum expected incremental completion time",
            "v5final_objective": "V5-B dedicated point plus wait only when search P_clear is no lower and expected time is no higher",
            "lambda_alpha": None,
        },
        "found_after_move_definition": "off-search supplement arrival segments plus final-clear arrival segment",
        "wait_saved_proxy_definition": "waited mandatory-search supplement that immediately became clearable",
        "frozen_v4_equivalence": frozen_check,
    }

    write_csv(out_dir / "details.csv", details)
    write_csv(out_dir / "source_diagnostics.csv", sources)
    write_csv(out_dir / "summary.csv", summaries)
    write_csv(out_dir / "paired_v5_minus_v4.csv", pairs)
    write_csv(out_dir / "typical_cases.csv", typical)
    (out_dir / "summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
