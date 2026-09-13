"""Offline-only benchmark for the new W6 persistent-bearing certificate."""
from __future__ import annotations

import argparse
import ast
import csv
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.case import generate_case, generate_stress_case
from offline_sim.harness import run_episode
from q4.run_w0_baseline import parse_seed_range, write_csv
from q4.run_w3_benchmark import source_local_rows, strategy_case_row, summarize_strategy
from q4.run_w4a_benchmark import write_union_csv
from q4.w1_policy import w1_search_points
from q4.w6_policy import policy_w6


def assert_policy_isolated() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = {"case", "engine", "sources", "jammers", "r_eff", "direction_deg"}
    for relative in (Path("q4/w6_policy.py"), Path("q4/w6_feasible_region.py")):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("offline_sim"):
                raise RuntimeError(f"ground-truth isolation failed: {relative}")
            if isinstance(node, ast.Import) and any(alias.name.startswith("offline_sim") for alias in node.names):
                raise RuntimeError(f"ground-truth isolation failed: {relative}")
            if isinstance(node, ast.Attribute) and node.attr in forbidden:
                raise RuntimeError(f"ground-truth isolation failed: {relative} accesses .{node.attr}")


def run_cases(random_seeds: list[int], stress_seeds: list[int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    details: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    suites = (("random", random_seeds, "smooth"), ("min_reff", stress_seeds, "adversarial"), ("collinear", stress_seeds, "adversarial"))
    for suite, seeds, field_kind in suites:
        for index, seed in enumerate(seeds, 1):
            if suite == "random":
                case = generate_case(seed=seed, problem=4, mode="practice", field_kind=field_kind, margin_m=0.0)
            else:
                case = generate_stress_case(
                    suite, seed=seed, problem=4, mode="practice", field_kind=field_kind,
                    scan_points=[(point.x, point.y) for point in w1_search_points()],
                )
            result = run_episode(case, policy_w6, include_oracles=False)
            row = strategy_case_row("w6_persistent_bearing", suite, seed, result, case)
            # summarize_strategy inherits the shared W1 helper's n=27 default;
            # the actual W6 policy always uses the frozen W5 25-point backbone.
            row["n"] = 25
            exit_rows = [item for item in result.policy_diagnostics if item.get("event") == "w6_exit_state"]
            exit_row = exit_rows[-1] if exit_rows else {}
            row.update({
                "guaranteed_clear_attempts": int(exit_row.get("guaranteed_clear_attempts", 0)),
                "guaranteed_clear_successes": int(exit_row.get("guaranteed_clear_successes", 0)),
                "guaranteed_clear_failures": int(exit_row.get("guaranteed_clear_failures", 0)),
                "certificate_ready_channels_at_exit": json.dumps(exit_row.get("certificate_ready_channels", [])),
            })
            details.append(row)
            sources.extend(source_local_rows("w6_persistent_bearing", suite, seed, case, result))
            if index % 10 == 0 or index == len(seeds):
                print(f"[w6/{suite}] {index}/{len(seeds)}", flush=True)
    return details, sources


def main() -> int:
    parser = argparse.ArgumentParser(description="Q4 W6 persistent-bearing offline benchmark")
    parser.add_argument("--pilot", action="store_true", help="run 30 cases: 10 random + 10+10 stress")
    parser.add_argument("--random-seeds", default=None)
    parser.add_argument("--stress-seeds", default=None)
    parser.add_argument("--out-dir", default="results/q4/w6/feasible_region")
    args = parser.parse_args()
    assert_policy_isolated()
    random_spec = args.random_seeds or ("0:10" if args.pilot else "0:50")
    stress_spec = args.stress_seeds or ("10000:10010" if args.pilot else "10000:10050")
    random_seeds = parse_seed_range(random_spec)
    stress_seeds = parse_seed_range(stress_spec)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    details, sources = run_cases(random_seeds, stress_seeds)
    write_union_csv(out_dir / "details.csv", details)
    write_union_csv(out_dir / "source_local.csv", sources)
    summaries = [summarize_strategy(details, "w6_persistent_bearing", suite) for suite in ("random", "min_reff", "collinear", "overall")]
    for summary in summaries:
        summary["n"] = 25
        summary["mean_guaranteed_clear_attempts"] = sum(int(row["guaranteed_clear_attempts"]) for row in details if summary["suite"] == "overall" or row["suite"] == summary["suite"]) / max(1, sum(1 for row in details if summary["suite"] == "overall" or row["suite"] == summary["suite"]))
        summary["mean_guaranteed_clear_failures"] = sum(int(row["guaranteed_clear_failures"]) for row in details if summary["suite"] == "overall" or row["suite"] == summary["suite"]) / max(1, sum(1 for row in details if summary["suite"] == "overall" or row["suite"] == summary["suite"]))
    write_csv(out_dir / "summary.csv", summaries)
    (out_dir / "metadata.json").write_text(json.dumps({
        "policy": "25G-ASR base W5 + persistent bearing certificate (experimental W6)",
        "environment": "local offline_sim/practice only",
        "random_seeds": random_seeds, "stress_seeds": stress_seeds,
        "case_count": len(details), "official_interface_used": False,
        "historical_results_overwritten": False,
    }, indent=2), encoding="utf-8")
    print(f"wrote {out_dir} ({len(details)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
