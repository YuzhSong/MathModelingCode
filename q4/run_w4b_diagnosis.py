from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.case import generate_case, generate_stress_case
from offline_sim.harness import run_episode
from q4.run_w0_baseline import parse_seed_range, write_csv
from q4.run_w3_benchmark import strategy_case_row
from q4.run_w4a_benchmark import write_union_csv
from q4.run_w4a_diagnosis import decompose_episode
from q4.run_w4b_benchmark import continuity_metrics
from q4.w1_policy import w1_search_points
from q4.w4a_policy import policy_w4a


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay W4-A with W4-B continuity metrics")
    parser.add_argument("--random-seeds", default="0:100")
    parser.add_argument("--stress-seeds", default="10000:10050")
    parser.add_argument("--out-dir", default="results/q4/w4b_diagnosis")
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    suites = (("random", parse_seed_range(args.random_seeds), "smooth"), ("min_reff", parse_seed_range(args.stress_seeds), "adversarial"), ("collinear", parse_seed_range(args.stress_seeds), "adversarial"))
    for suite, seeds, field_kind in suites:
        for index, seed in enumerate(seeds, start=1):
            if suite == "random":
                case = generate_case(seed=seed, problem=4, mode="practice", field_kind=field_kind, margin_m=0.0)
            else:
                case = generate_stress_case(
                    suite, seed=seed, problem=4, mode="practice", field_kind=field_kind,
                    scan_points=[(point.x, point.y) for point in w1_search_points()],
                )
            result = run_episode(case, policy_w4a, include_oracles=False)
            row = strategy_case_row("w4a", suite, seed, result, case)
            movement, _ = decompose_episode(suite, seed, result)
            row.update({key: value for key, value in movement.items() if key not in {"suite", "seed", "success", "total_time_s", "move_distance_m"}})
            row.update(continuity_metrics(result))
            rows.append(row)
            if index % 10 == 0 or index == len(seeds):
                print(f"[w4a-continuity/{suite}] {index}/{len(seeds)}", flush=True)
    write_union_csv(out_dir / "w4a_continuity.csv", rows)
    (out_dir / "metadata.json").write_text(json.dumps({
        "environment": "local offline_sim/practice only", "problem": 4, "margin_m": 0.0,
        "policy": "decision-identical frozen W4-A replay", "official_practice_run": False,
        "official_formal_test_run": False,
    }, indent=2), encoding="utf-8")
    print(f"wrote {out_dir / 'w4a_continuity.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
