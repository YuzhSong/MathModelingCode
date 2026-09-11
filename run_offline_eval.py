from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from itertools import combinations
from pathlib import Path
from typing import Callable

from offline_sim.case import generate_case, generate_stress_case
from offline_sim.harness import EpisodeResult, aggregate, run_episode
from q3.offline_policy import policy_v0, policy_v1, policy_v2, policy_v3, policy_v4, theoretical_outer_radius, theoretical_route_length
from q3.planner import Q3BaselinePlanner


POLICIES: dict[str, Callable] = {
    "v0": policy_v0,
    "v1": policy_v1,
    "v2": policy_v2,
    "v3": policy_v3,
    "v4": policy_v4,
}


def parse_seed_range(spec: str) -> list[int]:
    if ":" in spec:
        start, stop = spec.split(":", 1)
        return list(range(int(start), int(stop)))
    return [int(part) for part in spec.split(",") if part.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline Q3 policy evaluation on fixed practice/simulation cases.")
    parser.add_argument("--versions", default="v0", help="Comma-separated versions: v0,v1,v2,v3.")
    parser.add_argument("--rings", default="6,7,8,9", help="Comma-separated outer ring point counts.")
    parser.add_argument("--random-seeds", default="0:100", help="Fixed random seeds, e.g. 0:100 or 1,2,3.")
    parser.add_argument("--stress-seeds", default="10000:10050", help="Fixed stress seeds.")
    parser.add_argument("--stress-types", default="min_reff,collinear", help="Comma-separated stress case types.")
    parser.add_argument("--field-kind", default="smooth", help="Random case error field.")
    parser.add_argument("--stress-field-kind", default="adversarial", help="Stress case error field.")
    parser.add_argument("--out-dir", default="results/offline_eval")
    return parser.parse_args()


def result_row(version: str, n: int, suite: str, seed: int, result: EpisodeResult) -> dict:
    move_time = result.move_distance_m / 5.0
    measure_time = 5.0 * result.n_measure
    switch_time = 1.0 * result.n_channel_switch
    clear_success = result.n_clear - result.n_clear_fail
    clear_time = 5.0 * clear_success + 3.0 * result.n_clear_fail
    component_sum = move_time + measure_time + switch_time + clear_time
    return {
        "version": version,
        "n": n,
        "outer_radius_m": theoretical_outer_radius(n),
        "search_route_length_m": theoretical_route_length(n),
        "suite": suite,
        "seed": seed,
        "success": int(result.success),
        "cleared": result.cleared,
        "total": result.total,
        "virtual_time_s": result.virtual_time_s,
        "avg_time_per_source_s": result.virtual_time_s / result.cleared if result.cleared else 0.0,
        "move_distance_m": result.move_distance_m,
        "move_time_s": move_time,
        "n_measure": result.n_measure,
        "measure_time_s": measure_time,
        "n_channel_switch": result.n_channel_switch,
        "switch_time_s": switch_time,
        "n_clear": result.n_clear,
        "clear_success": clear_success,
        "n_clear_fail": result.n_clear_fail,
        "clear_time_s": clear_time,
        "time_component_sum_s": component_sum,
        "time_component_delta_s": result.virtual_time_s - component_sum,
        "conditional_route_oracle_time_s": result.conditional_route_oracle_time_s,
        "conditional_route_oracle_method": result.conditional_route_oracle_method or "",
        "conditional_route_oracle_exact": int(result.conditional_route_oracle_exact),
        "conditional_route_oracle_gap": result.conditional_route_oracle_gap,
        "full_oracle_proxy_time_s": result.full_oracle_proxy_time_s,
        "full_oracle_proxy_method": result.full_oracle_proxy_method or "",
        "full_oracle_proxy_exact_route": int(result.full_oracle_proxy_exact_route),
        "full_oracle_proxy_gap": result.full_oracle_proxy_gap,
        "n_near": result.n_near,
        "finished_reason": result.finished_reason or "",
        "error": result.error or "",
    }


def metrics_dict(metrics) -> dict:
    return {
        "episodes": metrics.n_episodes,
        "success_rate": metrics.success_rate,
        "success_count": metrics.n_success,
        "error_count": metrics.n_error,
        "time_mean_s": metrics.time_mean,
        "time_p50_s": metrics.time_p50,
        "time_p90_s": metrics.time_p90,
        "time_p95_s": metrics.time_p95,
        "time_max_s": metrics.time_max,
        "time_success_mean_s": metrics.time_mean_success,
        "time_success_p95_s": metrics.time_p95_success,
        "time_success_max_s": metrics.time_max_success,
        "mean_avg_time_per_source_s": metrics.avg_time_per_source_mean,
        "pooled_avg_time_per_source_s": metrics.pooled_avg_time_per_source,
        "move_mean_m": metrics.move_mean,
        "move_time_mean_s": metrics.move_time_mean,
        "measure_mean": metrics.measure_mean,
        "measure_time_mean_s": metrics.measure_time_mean,
        "channel_switch_mean": metrics.switch_mean,
        "channel_switch_time_mean_s": metrics.switch_time_mean,
        "clear_mean": metrics.clear_mean,
        "clear_success_mean": metrics.clear_success_mean,
        "clear_fail_mean": metrics.clear_fail_mean,
        "clear_time_mean_s": metrics.clear_time_mean,
        "near_mean": metrics.near_mean,
        "time_component_delta_mean_s": metrics.time_component_delta_mean,
        "time_component_delta_abs_max_s": metrics.time_component_delta_abs_max,
        "conditional_route_oracle_time_mean_s": metrics.conditional_route_oracle_time_mean,
        "conditional_route_oracle_gap_mean": metrics.conditional_route_oracle_gap_mean,
        "full_oracle_proxy_time_mean_s": metrics.full_oracle_proxy_time_mean,
        "full_oracle_proxy_gap_mean": metrics.full_oracle_proxy_gap_mean,
    }


def run_suite(version: str, policy: Callable, n: int, suite: str, seeds: list[int], field_kind: str) -> list[dict]:
    rows = []
    radius = theoretical_outer_radius(n)
    scan_points = [(p.x, p.y) for p in Q3BaselinePlanner.make_search_points(radius, n)]
    policy_for_n = lambda runner: policy(runner, n=n)
    for seed in seeds:
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
        rows.append(result_row(version, n, suite, seed, run_episode(case, policy_for_n)))
    return rows


def ring_theory_rows(ns: list[int]) -> list[dict]:
    return [
        {
            "n": n,
            "outer_radius_m": theoretical_outer_radius(n),
            "search_route_length_m": theoretical_route_length(n),
        }
        for n in ns
    ]


def percentile(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    sorted_vals = sorted(vals)
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = q * (len(sorted_vals) - 1)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def paired_comparisons(rows: list[dict]) -> list[dict]:
    by_key: dict[tuple[str, int, str, int], dict] = {}
    versions = sorted({row["version"] for row in rows})
    ns = sorted({int(row["n"]) for row in rows})
    suites = sorted({row["suite"] for row in rows})
    for row in rows:
        by_key[(row["version"], int(row["n"]), row["suite"], int(row["seed"]))] = row

    comparisons: list[dict] = []
    for n in ns:
        for suite in suites:
            seeds = sorted({int(row["seed"]) for row in rows if int(row["n"]) == n and row["suite"] == suite})
            for base, target in combinations(versions, 2):
                deltas = []
                for seed in seeds:
                    left = by_key.get((base, n, suite, seed))
                    right = by_key.get((target, n, suite, seed))
                    if left is None or right is None:
                        continue
                    deltas.append(float(right["virtual_time_s"]) - float(left["virtual_time_s"]))
                if not deltas:
                    continue
                comparisons.append(
                    {
                        "n": n,
                        "suite": suite,
                        "base_version": base,
                        "target_version": target,
                        "delta_definition": "target_time_minus_base_time_s",
                        "pairs": len(deltas),
                        "target_win_rate": sum(1 for d in deltas if d < 0.0) / len(deltas),
                        "mean_delta_s": statistics.fmean(deltas),
                        "median_delta_s": statistics.median(deltas),
                        "p95_delta_s": percentile(deltas, 0.95),
                        "max_delta_s": max(deltas),
                    }
                )
    return comparisons


def main() -> int:
    args = parse_args()
    versions = [v.strip() for v in args.versions.split(",") if v.strip()]
    ns = [int(n.strip()) for n in args.rings.split(",") if n.strip()]
    random_seeds = parse_seed_range(args.random_seeds)
    stress_seeds = parse_seed_range(args.stress_seeds)
    stress_types = [s.strip() for s in args.stress_types.split(",") if s.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    summary_rows: list[dict] = []
    for n in ns:
        for version in versions:
            if version not in POLICIES:
                raise SystemExit(f"unknown version {version!r}; available: {sorted(POLICIES)}")
            policy = POLICIES[version]
            suite_defs = [("random", random_seeds, args.field_kind)]
            suite_defs.extend((stress, stress_seeds, args.stress_field_kind) for stress in stress_types)
            for suite, seeds, field_kind in suite_defs:
                rows = run_suite(version, policy, n, suite, seeds, field_kind)
                all_rows.extend(rows)
                metrics = aggregate([row_to_result(row) for row in rows])
                summary = {
                    "version": version,
                    "n": n,
                    "outer_radius_m": theoretical_outer_radius(n),
                    "search_route_length_m": theoretical_route_length(n),
                    "suite": suite,
                    "field_kind": field_kind,
                    **metrics_dict(metrics),
                }
                summary_rows.append(summary)
                print(f"\n[{version} / n={n} / {suite} / {field_kind}]")
                print(json.dumps(summary, ensure_ascii=False, indent=2))

    details_path = out_dir / "details.csv"
    summary_path = out_dir / "summary.csv"
    json_path = out_dir / "summary.json"
    ring_path = out_dir / "ring_theory.csv"
    ring_json_path = out_dir / "ring_theory.json"
    paired_path = out_dir / "paired_comparison.csv"
    paired_json_path = out_dir / "paired_comparison.json"
    rings = ring_theory_rows(ns)
    pairs = paired_comparisons(all_rows)
    write_csv(details_path, all_rows)
    write_csv(summary_path, summary_rows)
    write_csv(ring_path, rings)
    write_csv(paired_path, pairs)
    json_path.write_text(json.dumps(summary_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    ring_json_path.write_text(json.dumps(rings, ensure_ascii=False, indent=2), encoding="utf-8")
    paired_json_path.write_text(json.dumps(pairs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {details_path}")
    print(f"wrote {summary_path}")
    print(f"wrote {json_path}")
    print(f"wrote {ring_path}")
    print(f"wrote {paired_path}")
    return 0


def row_to_result(row: dict) -> EpisodeResult:
    return EpisodeResult(
        cleared=int(row["cleared"]),
        total=int(row["total"]),
        success=bool(row["success"]),
        virtual_time_s=float(row["virtual_time_s"]),
        move_distance_m=float(row["move_distance_m"]),
        move_time_s=float(row["move_time_s"]),
        channel_switch_time_s=float(row["switch_time_s"]),
        measure_action_time_s=float(row["measure_time_s"]),
        clear_action_time_s=float(row["clear_time_s"]),
        n_measure=int(row["n_measure"]),
        n_channel_switch=int(row["n_channel_switch"]),
        n_clear=int(row["n_clear"]),
        n_clear_fail=int(row["n_clear_fail"]),
        n_near=int(row["n_near"]),
        conditional_route_oracle_time_s=(None if row.get("conditional_route_oracle_time_s") in {None, ""} else float(row["conditional_route_oracle_time_s"])),
        conditional_route_oracle_method=row.get("conditional_route_oracle_method") or None,
        conditional_route_oracle_exact=bool(int(row.get("conditional_route_oracle_exact") or 0)),
        conditional_route_oracle_gap=(None if row.get("conditional_route_oracle_gap") in {None, ""} else float(row["conditional_route_oracle_gap"])),
        full_oracle_proxy_time_s=(None if row.get("full_oracle_proxy_time_s") in {None, ""} else float(row["full_oracle_proxy_time_s"])),
        full_oracle_proxy_method=row.get("full_oracle_proxy_method") or None,
        full_oracle_proxy_exact_route=bool(int(row.get("full_oracle_proxy_exact_route") or 0)),
        full_oracle_proxy_gap=(None if row.get("full_oracle_proxy_gap") in {None, ""} else float(row["full_oracle_proxy_gap"])),
        finished_reason=str(row["finished_reason"]),
        error=str(row["error"]),
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
