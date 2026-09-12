from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.case import generate_case, generate_stress_case
from offline_sim.harness import run_episode
from q4.run_w0_baseline import parse_seed_range, write_csv
from q4.run_w2_benchmark import read_csv
from q4.run_w5_benchmark import decompose_episode
from q4.w1_policy import w1_search_points
from q4.w4a_policy import policy_w4a


def main() -> int:
    parser = argparse.ArgumentParser(description="Decision-identical W4-A replay for W5 geometry diagnostics")
    parser.add_argument("--random-seeds", default="0:100")
    parser.add_argument("--stress-seeds", default="10000:10050")
    parser.add_argument("--out-dir", default="results/q4/w5")
    args = parser.parse_args()
    points = w1_search_points()
    historical = {(row["suite"], int(row["seed"])): row for row in read_csv(Path("results/q4/w4a/details.csv"))}
    rows = []
    suites = (("random", parse_seed_range(args.random_seeds), "smooth"), ("min_reff", parse_seed_range(args.stress_seeds), "adversarial"), ("collinear", parse_seed_range(args.stress_seeds), "adversarial"))
    for suite, seeds, field_kind in suites:
        for index, seed in enumerate(seeds, start=1):
            if suite == "random":
                case = generate_case(seed=seed, problem=4, mode="practice", field_kind=field_kind, margin_m=0.0)
            else:
                case = generate_stress_case(suite, seed=seed, problem=4, mode="practice", field_kind=field_kind, scan_points=[(point.x, point.y) for point in points])
            result = run_episode(case, policy_w4a, include_oracles=False)
            metrics, _ = decompose_episode(suite, seed, result, points)
            old = historical[(suite, seed)]
            rows.append({
                "suite": suite, "seed": seed,
                "total_time_s": result.virtual_time_s,
                "move_distance_m": result.move_distance_m,
                "time_replay_delta_s": result.virtual_time_s - float(old["total_time_s"]),
                "move_replay_delta_m": result.move_distance_m - float(old["move_distance_m"]),
                "backbone_points_visited": metrics["backbone_points_visited"],
                "backbone_measure_count": metrics["backbone_measure_count"],
                "search_move_distance_m": metrics["search_move_distance_m"],
                "backbone_to_backbone_m": metrics.get("distance_backbone->backbone", 0.0),
            })
            if index % 10 == 0 or index == len(seeds):
                print(f"[w4a-replay/{suite}] {index}/{len(seeds)}", flush=True)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "w4a_geometry_diagnostics.csv", rows)
    summary = {
        "episodes": len(rows),
        "mean_backbone_points_visited": statistics.fmean(row["backbone_points_visited"] for row in rows),
        "mean_backbone_measure_count": statistics.fmean(row["backbone_measure_count"] for row in rows),
        "mean_search_move_distance_m": statistics.fmean(row["search_move_distance_m"] for row in rows),
        "mean_backbone_to_backbone_m": statistics.fmean(row["backbone_to_backbone_m"] for row in rows),
        "max_abs_time_replay_delta_s": max(abs(row["time_replay_delta_s"]) for row in rows),
        "max_abs_move_replay_delta_m": max(abs(row["move_replay_delta_m"]) for row in rows),
    }
    (out_dir / "w4a_geometry_diagnostics_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
