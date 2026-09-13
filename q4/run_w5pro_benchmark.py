"""Same-seed W5 versus W5Pro benchmark with auditable traces."""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from dataclasses import replace
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.harness import run_episode
from q4.run_w0_baseline import parse_seed_range
from q4.run_w3_benchmark import source_local_rows, strategy_case_row
from q4.w5_policy import W5SymmetricDetectionPolicy
from q4.w5pro_config import PRODUCTION_CONFIG
from q4.w5pro_diagnostics import collect_diagnostics
from q4.w5pro_experiment_matrix import ERROR_FIELD_NAMES, ExperimentSpec, make_experiment_case
from q4.w5pro_metrics import summarize_sources, write_metrics
from q4.w5pro_policy import W5ProPolicy


def run_one(case, version: str, output: Path, suite: str, seed: int, field_kind: str = "smooth", config=None) -> dict:
    def policy(runner):
        if version == "w5":
            W5SymmetricDetectionPolicy(runner).run()
        else:
            W5ProPolicy(runner, config or PRODUCTION_CONFIG).run()
    result = run_episode(case, policy, include_oracles=False)
    row = strategy_case_row(version, suite, seed, result, case)
    previous = (0.0, 0.0)
    move_m = 0.0
    switches = 0
    measurements = 0
    previous_channel = None
    for action in result.action_log:
        move_m += math.hypot(action.x - previous[0], action.y - previous[1])
        previous = (action.x, action.y)
        if action.action == "measure":
            measurements += 1
            if previous_channel is not None and action.channel != previous_channel:
                switches += 1
            previous_channel = action.channel
    row.update({"error_field": field_kind,
                "move_distance_m": float(result.move_distance_m),
                "move_time_s": float(result.move_time_s),
                "measure_count": measurements,
                "measure_time_s": float(result.measure_action_time_s),
                "clear_time_s": float(result.clear_action_time_s),
                "channel_switch_count": int(result.n_channel_switch),
                "channel_switch_time_s": float(result.channel_switch_time_s)})
    diagnostics = collect_diagnostics(result.policy_diagnostics, decisions=row.get("move_count", 0))
    row.update(diagnostics.counts)
    row["fallback_rate"] = diagnostics.fallback_rate
    event_names = (
        "w5pro_nbv_selected", "w5pro_intersection_attempt",
        "w5pro_intersection_selected", "w5pro_spatial_bundle",
        "w5pro_spatial_service", "w5pro_scan_continue",
        "w5pro_scan_observe", "w5pro_tail_fallback",
        "w5pro_no_progress_guard", "w5pro_route_choice",
        "w5pro_route_repair", "w5pro_corridor_opportunity",
        "w5pro_information_ridge", "w5pro_information_ridge_selected",
        "w5pro_outcome_probabilities",
    )
    event_counts = {name: sum(1 for event in result.policy_diagnostics
                              if event.get("event") == name) for name in event_names}
    row.update({"event_" + name.removeprefix("w5pro_"): count
                for name, count in event_counts.items()})
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{version}_{suite}_{field_kind}_{seed}.json").write_text(
        json.dumps({"details": row, "events": result.policy_diagnostics,
                    "action_log": [asdict(action) for action in result.action_log]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--versions", default="w5,w5pro")
    parser.add_argument("--random-seeds", default="0:3")
    parser.add_argument("--stress-suite", default="min_reff")
    parser.add_argument("--stress-suites", default="")
    parser.add_argument("--stress-seeds", default="10000:10002")
    parser.add_argument("--mode", choices=("formal", "practice"), default="formal")
    parser.add_argument("--output", type=Path, default=Path("results/q4/w5pro_benchmark"))
    parser.add_argument("--max-macro-steps", type=int, default=None)
    parser.add_argument("--error-fields", default="smooth",
                        help="comma-separated error fields; use 'all' for the full required matrix")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    sources = []
    fields = ERROR_FIELD_NAMES if args.error_fields.strip().lower() == "all" else tuple(
        field.strip() for field in args.error_fields.split(",") if field.strip())
    unknown_fields = set(fields) - set(ERROR_FIELD_NAMES)
    if unknown_fields:
        parser.error(f"unknown error fields: {sorted(unknown_fields)}")
    specs = [ExperimentSpec("random", s, field)
             for s in parse_seed_range(args.random_seeds) for field in fields]
    suites = [s.strip() for s in (args.stress_suites or args.stress_suite).split(",") if s.strip()]
    specs += [ExperimentSpec(suite, s, field)
              for suite in suites for s in parse_seed_range(args.stress_seeds)
              for field in fields]
    config = replace(PRODUCTION_CONFIG, max_macro_steps=args.max_macro_steps) if args.max_macro_steps else PRODUCTION_CONFIG
    for version in args.versions.split(","):
        for spec in specs:
            row = run_one(make_experiment_case(spec, mode=args.mode), version, args.output / "traces", spec.suite, spec.seed, spec.field_kind, config)
            rows.append(row)
            # Use the exact action records from this episode; do not fabricate
            # an empty log, otherwise per-source timing is unverifiable.
            trace = json.loads((args.output / "traces" / f"{version}_{spec.suite}_{spec.field_kind}_{spec.seed}.json").read_text(encoding="utf-8"))
            from offline_sim.harness import ActionRecord
            source_rows = source_local_rows(version, spec.suite, spec.seed,
                                            make_experiment_case(spec, mode=args.mode),
                                            type("TraceResult", (), {
                                                "policy_diagnostics": trace["events"],
                                                "action_log": [ActionRecord(**item) for item in trace["action_log"]],
                                            })())
            for source_row in source_rows:
                source_row["error_field"] = spec.field_kind
            sources.extend(source_rows)
            print(f"{version}/{spec.suite}/{spec.field_kind}/{spec.seed}: clear={row['success']} time={row['total_time_s']:.2f}", flush=True)
    import csv
    with (args.output / "details.csv").open("w", newline="", encoding="utf-8") as f:
        fields = sorted({k for row in rows for k in row})
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    versions = sorted({str(r["version"]) for r in rows})
    if "w5" in versions and "w5pro" in versions:
        by_key = {(r["suite"], r.get("error_field", "smooth"), str(r["seed"]), r["version"]): r for r in rows}
        paired = []
        for suite, field, seed in sorted({key[:3] for key in by_key}):
            w5 = by_key.get((suite, field, seed, "w5")); pro = by_key.get((suite, field, seed, "w5pro"))
            if w5 and pro:
                paired.append({"suite": suite, "error_field": field, "seed": seed,
                               "w5_clear": w5["success"], "w5pro_clear": pro["success"],
                               "w5_time_s": w5["total_time_s"],
                               "w5pro_time_s": pro["total_time_s"],
                               "delta_time_s": float(pro["total_time_s"]) - float(w5["total_time_s"])})
        with (args.output / "paired_comparison.csv").open("w", newline="", encoding="utf-8") as f:
            fields = ["suite", "error_field", "seed", "w5_clear", "w5pro_clear", "w5_time_s", "w5pro_time_s", "delta_time_s"]
            writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(paired)
    if sources:
        with (args.output / "source_local.csv").open("w", newline="", encoding="utf-8") as f:
            fields = sorted({k for row in sources for k in row})
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader(); writer.writerows(sources)
    utilization = {}
    for row in rows:
        key = row["version"]
        bucket = utilization.setdefault(key, {"episodes": 0})
        bucket["episodes"] += 1
        for field, value in row.items():
            if field.startswith("event_"):
                bucket[field] = bucket.get(field, 0) + int(value or 0)
    (args.output / "mechanism_utilization.json").write_text(
        json.dumps(utilization, ensure_ascii=False, indent=2), encoding="utf-8")
    write_metrics(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
