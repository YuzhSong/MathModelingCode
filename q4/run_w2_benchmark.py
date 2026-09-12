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

from offline_sim.case import Case, generate_case, generate_stress_case
from offline_sim.harness import EpisodeResult, run_episode
from q4.run_w0_baseline import (
    action_points,
    case_row,
    in_directional_halfplane,
    markdown_table,
    parse_seed_range,
    percentile,
    source_count_summary,
    summarize,
    write_csv,
)
from q4.w1_policy import w1_search_points
from q4.w2_policy import DEFER_AFTER_CONSECUTIVE_FAILURES, policy_w2


FAILURE_CLASSES = (
    "never_visible",
    "visible_but_never_registered",
    "discovered_but_localization_failed",
    "discovered_but_reacquisition_failed",
    "localized_but_not_cleared",
    "other",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def exit_diagnostic(result: EpisodeResult) -> dict[str, Any]:
    rows = [row for row in result.policy_diagnostics if row.get("event") == "w2_exit_state"]
    return rows[-1] if rows else {}


def discovered_channels(result: EpisodeResult) -> set[int]:
    return {
        int(row["channel"])
        for row in result.policy_diagnostics
        if row.get("event") == "w2_target_discovered"
    }


def cleared_channels(result: EpisodeResult) -> set[int]:
    return {
        int(row.channel)
        for row in result.action_log
        if row.action == "clear" and row.result == "success"
    }


def w2_case_row(suite: str, seed: int, result: EpisodeResult, case: Case) -> dict[str, Any]:
    row = case_row(suite, seed, result, case)
    row["version"] = "w2"
    row["n"] = len(w1_search_points())
    exit_row = exit_diagnostic(result)
    discovered = discovered_channels(result)
    cleared = cleared_channels(result)
    row.update(
        {
            "number_discovered": len(discovered),
            "number_cleared": len(cleared),
            "discovered_but_not_cleared": len(discovered - cleared),
            "never_discovered": case.total - len(discovered),
            "reacquisition_attempts": int(exit_row.get("reacquisition_attempts", 0)),
            "reacquisition_successes": int(exit_row.get("reacquisition_successes", 0)),
            "no_signal_after_found": int(exit_row.get("no_signal_after_found", 0)),
            "deferred_targets": int(exit_row.get("ever_deferred_targets", 0)),
            "targets_remaining_at_exit": len(exit_row.get("unresolved_channels", [])),
            "completed_search_points": int(exit_row.get("completed_search_points", 0)),
            "remaining_search_points": int(exit_row.get("remaining_search_points", 0)),
            "termination_reason": str(exit_row.get("termination_reason", "missing_exit_diagnostic")),
        }
    )
    return row


def _channel_events(result: EpisodeResult, channel: int) -> list[dict[str, Any]]:
    return [
        row
        for row in result.policy_diagnostics
        if int(row.get("channel", -1)) == channel
    ]


def missed_source_rows(suite: str, seed: int, case: Case, result: EpisodeResult) -> list[dict[str, Any]]:
    points = action_points(result.action_log)
    discovered = discovered_channels(result)
    rows: list[dict[str, Any]] = []
    for jammer in sorted(case.jammers, key=lambda item: item.channel):
        if jammer.cleared:
            continue
        channel = int(jammer.channel)
        events = _channel_events(result, channel)
        visible_flags = [
            math.hypot(x - jammer.x, y - jammer.y) <= jammer.r_eff + 1e-9
            and in_directional_halfplane(jammer, x, y)
            for x, y in points
        ]
        registered = any(
            row.action == "measure"
            and row.channel == channel
            and row.result in {"direction", "near"}
            for row in result.action_log
        )
        reacq_attempts = sum(
            row.get("event") == "w2_reacquisition_success"
            or (
                row.get("event") == "w2_no_signal_after_found"
                and row.get("role") in {"reacquire", "search_reacquire"}
            )
            for row in events
        )
        reacq_successes = sum(row.get("event") == "w2_reacquisition_success" for row in events)
        clear_attempts = sum(
            row.action == "clear" and row.channel == channel
            for row in result.action_log
        )
        mec_values = [
            float(row["mec_radius_m"])
            for row in events
            if row.get("event") == "w2_direction_update" and row.get("mec_radius_m") is not None
        ]
        final_mec = mec_values[-1] if mec_values else None

        if not any(visible_flags):
            failure_class = "never_visible"
        elif not registered or channel not in discovered:
            failure_class = "visible_but_never_registered"
        elif clear_attempts > 0 or (final_mec is not None and final_mec <= 20.0):
            failure_class = "localized_but_not_cleared"
        elif reacq_attempts > 0 and reacq_successes == 0:
            failure_class = "discovered_but_reacquisition_failed"
        elif registered:
            failure_class = "discovered_but_localization_failed"
        else:
            failure_class = "other"

        rows.append(
            {
                "version": "w2",
                "suite": suite,
                "seed": seed,
                "channel": channel,
                "kind": jammer.kind,
                "x": jammer.x,
                "y": jammer.y,
                "radius_from_origin_m": math.hypot(jammer.x, jammer.y),
                "r_eff_m": jammer.r_eff,
                "direction_deg": "" if jammer.direction_deg is None else jammer.direction_deg,
                "ever_visible_at_action_endpoint": int(any(visible_flags)),
                "registered": int(registered),
                "reacquisition_attempts": reacq_attempts,
                "reacquisition_successes": reacq_successes,
                "clear_attempts": clear_attempts,
                "final_mec_radius_m": "" if final_mec is None else final_mec,
                "failure_class": failure_class,
            }
        )
    return rows


def missed_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for suite in ("random", "min_reff", "collinear", "overall"):
        subset = [row for row in rows if suite == "overall" or row["suite"] == suite]
        counts = {name: 0 for name in FAILURE_CLASSES}
        for row in subset:
            counts[str(row["failure_class"])] += 1
        if sum(counts.values()) != len(subset):
            raise RuntimeError(f"non-exclusive failure taxonomy for {suite}")
        output.append(
            {
                "suite": suite,
                "missed_sources": len(subset),
                "missed_omni": sum(row["kind"] == "omni" for row in subset),
                "missed_dir": sum(row["kind"] == "dir" for row in subset),
                **counts,
                "taxonomy_total": sum(counts.values()),
            }
        )
    return output


def lifecycle_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "number_discovered",
        "number_cleared",
        "discovered_but_not_cleared",
        "never_discovered",
        "reacquisition_attempts",
        "reacquisition_successes",
        "no_signal_after_found",
        "deferred_targets",
        "targets_remaining_at_exit",
    )
    output: list[dict[str, Any]] = []
    for suite in ("random", "min_reff", "collinear", "overall"):
        subset = [row for row in rows if suite == "overall" or row["suite"] == suite]
        record: dict[str, Any] = {"suite": suite, "episodes": len(subset)}
        for field in fields:
            values = [int(row[field]) for row in subset]
            record[f"total_{field}"] = sum(values)
            record[f"mean_{field}"] = statistics.fmean(values) if values else 0.0
        attempts = record["total_reacquisition_attempts"]
        record["reacquisition_success_rate"] = (
            record["total_reacquisition_successes"] / attempts if attempts else 0.0
        )
        output.append(record)
    return output


def paired_comparison(base_rows: list[dict[str, str]], target_rows: list[dict[str, Any]], base: str) -> list[dict[str, Any]]:
    lookup = {(row["suite"], int(row["seed"])): row for row in base_rows}
    target = {(row["suite"], int(row["seed"])): row for row in target_rows}
    output: list[dict[str, Any]] = []
    for suite in ("random", "min_reff", "collinear", "overall"):
        keys = sorted(key for key in target if suite == "overall" or key[0] == suite)
        pairs = [(lookup[key], target[key]) for key in keys if key in lookup]
        deltas = [float(right["total_time_s"]) - float(left["total_time_s"]) for left, right in pairs]
        success_delta = [int(right["success"]) - int(left["success"]) for left, right in pairs]
        output.append(
            {
                "base": base,
                "target": "w2",
                "suite": suite,
                "pairs": len(pairs),
                "w2_time_win_rate": sum(delta < 0.0 for delta in deltas) / len(deltas) if deltas else 0.0,
                "mean_delta_total_time_s": statistics.fmean(deltas) if deltas else 0.0,
                "median_delta_total_time_s": statistics.median(deltas) if deltas else 0.0,
                "p95_delta_total_time_s": percentile(deltas, 0.95),
                "max_delta_total_time_s": max(deltas, default=0.0),
                "w2_more_success_cases": sum(delta > 0 for delta in success_delta),
                "w2_fewer_success_cases": sum(delta < 0 for delta in success_delta),
                "same_success_cases": sum(delta == 0 for delta in success_delta),
                "mean_delta_move_m": statistics.fmean(
                    float(right["move_distance_m"]) - float(left["move_distance_m"])
                    for left, right in pairs
                ) if pairs else 0.0,
                "mean_delta_measure_count": statistics.fmean(
                    int(right["measure_count"]) - int(left["measure_count"])
                    for left, right in pairs
                ) if pairs else 0.0,
            }
        )
    return output


def assert_w2_ground_truth_isolated() -> None:
    root = Path(__file__).resolve().parents[1]
    policy_files = (Path("q4/w2_policy.py"), Path("q4/w1_policy.py"), Path("q3/v6_policy.py"))
    forbidden_attrs = {"case", "engine", "sources", "jammers", "r_eff", "direction_deg"}
    for relative in policy_files:
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("offline_sim"):
                raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Import) and any(alias.name.startswith("offline_sim") for alias in node.names):
                raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
                raise RuntimeError(f"ground-truth isolation failed: {relative} accesses .{node.attr}")


def _summary_lookup(rows: list[dict[str, str]], suite: str = "overall") -> dict[str, str]:
    return next(row for row in rows if row["suite"] == suite)


def render_report(
    out_dir: Path,
    summary: list[dict[str, Any]],
    by_count: list[dict[str, Any]],
    lifecycle: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    w0_summary: list[dict[str, str]],
    w1_summary: list[dict[str, str]],
    paired: list[dict[str, Any]],
) -> None:
    overall = next(row for row in summary if row["suite"] == "overall")
    life = next(row for row in lifecycle if row["suite"] == "overall")
    missed = next(row for row in failures if row["suite"] == "overall")
    w0 = _summary_lookup(w0_summary)
    w1 = _summary_lookup(w1_summary)

    strategy_rows: list[list[str]] = []
    for name, row in (("W0", w0), ("W1", w1)):
        strategy_rows.append(
            [
                name,
                str(row["full_clear_cases"]),
                f"{100*float(row['clear_rate']):.1f}%",
                f"{float(row['mean_total_time_s']):.2f}",
                f"{float(row['p95_total_time_s']):.2f}",
                f"{float(row['max_total_time_s']):.2f}",
                f"{float(row['mean_avg_time_per_source_s']):.2f}",
                f"{float(row['mean_move_distance_m']):.2f}",
                f"{float(row['mean_measure_count']):.2f}",
            ]
        )
    strategy_rows.append(
        [
            "W2",
            str(overall["full_clear_cases"]),
            f"{100*overall['clear_rate']:.1f}%",
            f"{overall['mean_total_time_s']:.2f}",
            f"{overall['p95_total_time_s']:.2f}",
            f"{overall['max_total_time_s']:.2f}",
            f"{overall['mean_avg_time_per_source_s']:.2f}",
            f"{overall['mean_move_distance_m']:.2f}",
            f"{overall['mean_measure_count']:.2f}",
        ]
    )
    suite_rows = [
        [
            row["suite"],
            f"{row['full_clear_cases']}/{row['episodes']}",
            f"{100*row['clear_rate']:.1f}%",
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
            f"{row['full_clear_cases']}/{row['case_count']}",
            f"{100*row['clear_rate']:.1f}%",
            f"{row['mean_total_time_s']:.2f}",
            f"{row['mean_avg_time_per_source_s']:.2f}",
            f"{row['p95_avg_time_per_source_s']:.2f}",
        ]
        for row in by_count
    ]
    failure_rows = [
        [row["suite"], str(row["missed_sources"])]
        + [str(row[name]) for name in FAILURE_CLASSES]
        + [str(row["taxonomy_total"])]
        for row in failures
    ]
    lifecycle_rows = [
        [
            row["suite"],
            f"{row['mean_number_discovered']:.2f}",
            f"{row['mean_number_cleared']:.2f}",
            f"{row['mean_discovered_but_not_cleared']:.2f}",
            f"{row['mean_never_discovered']:.2f}",
            f"{row['mean_reacquisition_attempts']:.2f}",
            f"{100*row['reacquisition_success_rate']:.1f}%",
            f"{row['mean_no_signal_after_found']:.2f}",
            f"{row['mean_deferred_targets']:.2f}",
            f"{row['mean_targets_remaining_at_exit']:.2f}",
        ]
        for row in lifecycle
    ]
    pair_rows = [
        [
            row["base"],
            row["suite"],
            str(row["pairs"]),
            str(row["w2_more_success_cases"]),
            str(row["w2_fewer_success_cases"]),
            f"{row['mean_delta_total_time_s']:+.2f}",
            f"{row['mean_delta_move_m']:+.2f}",
            f"{row['mean_delta_measure_count']:+.2f}",
        ]
        for row in paired
    ]

    lines = [
        "# Q4 W2: persistent target lifecycle and direction-aware reacquisition",
        "",
        "W2 keeps W1's 27-point triangular detection backbone and the frozen V6 route optimizer. It changes only post-discovery target persistence, no-signal handling, reacquisition, and termination semantics.",
        "",
        "## A. Frozen state-machine audit",
        "",
        "- The current offline simulator generates distinct source channels and resolves a channel through `Case.jammer_on_channel`; W2 preserves that existing model and adds no stronger multiplicity assumption.",
        "- In frozen V6, a `direction` changes a channel from `UNKNOWN` to `FOUND`, so it leaves the UNKNOWN discovery scan set.",
        "- A later `no_signal` is returned without adding a measurement or changing the track. The localization cache key therefore stays unchanged.",
        "- V6 can consequently select the same cached supplement point again. W1 random seed 0 exhibited repeated zero-movement `no_signal` measurements at one coordinate until the 1000-step loop ended.",
        "- Frozen completion is task-driven: an empty task pool or the step cap exits through `finally`; neither path proves every confirmed target was cleared.",
        "- This is the direct state-transition mechanism behind much of W1's `visible_measure_but_not_cleared` class.",
        "",
        "## B. W2 state transitions",
        "",
        "```text",
        "UNKNOWN --direction/near--> ACTIVE",
        "ACTIVE --no_signal--> REACQUIRE",
        "REACQUIRE --direction--> REACQUIRE (new bearing, new anchor)",
        "REACQUIRE --repeated no_signal--> DEFERRED --one SEARCH completion--> REACQUIRE",
        "ACTIVE/REACQUIRE --MEC<=20 or near; clear success--> RESOLVED",
        "clear failure --> REACQUIRE (target remains persistent)",
        "```",
        "",
        "A post-FOUND `no_signal` is stored as a visibility observation and prevents silent target deletion or identical-point retry. It does not clip the source-position polygon: without knowing omni/directional type, receive radius, or directional orientation, such clipping would be unsound. Reacquisition probes start 5m from the last visible point along the reported bearing and its fixed +/-1.005-degree uncertainty edges, then expand through a deterministic angle fan. This uses API-visible bearings only.",
        "",
        "## C. W0 / W1 / W2",
        "",
        markdown_table(["Strategy", "Full Clear", "Clear Rate", "Mean", "P95", "Max", "Mean T/N", "Move m", "Measures"], strategy_rows),
        "",
        "## D. W2 by suite",
        "",
        markdown_table(["Suite", "Full Clear", "Rate", "Mean", "P95", "Max", "Mean T/N", "P95 T/N", "Move m", "Measures", "Clear fail"], suite_rows),
        "",
        "## E. W2 by source count",
        "",
        markdown_table(["Sources", "Cases", "Full Clear", "Rate", "Mean", "Mean T/N", "P95 T/N"], count_rows),
        "",
        "## F. Persistent-lifecycle diagnostics",
        "",
        markdown_table(["Suite", "Discovered/ep", "Cleared/ep", "Discovered not cleared/ep", "Never discovered/ep", "Reacq attempts/ep", "Reacq success", "No signal after found/ep", "Deferred targets/ep", "Remaining at exit/ep"], lifecycle_rows),
        "",
        "## G. Exclusive missed-source taxonomy",
        "",
        markdown_table(["Suite", "Missed", *FAILURE_CLASSES, "Check total"], failure_rows),
        "",
        "The six classes are mutually exclusive by construction and `Check total` must equal `Missed`. Visibility is audited at recorded action endpoints; it does not infer visibility along continuous movement segments.",
        "",
        "## H. Same-seed comparison",
        "",
        markdown_table(["Base", "Suite", "Pairs", "W2 more full-clear", "W2 fewer full-clear", "Mean dT", "Mean dMove m", "Mean dMeasures"], pair_rows),
        "",
        "## I. Answers",
        "",
        f"1. Frozen V6/W1 lost progress because post-FOUND `no_signal` left the feasible-region/cache state unchanged, permitting repeated selection of the same ineffective point while the target was no longer part of UNKNOWN scanning.",
        f"2. W2 adds persistent `ACTIVE/REACQUIRE/DEFERRED/RESOLVED` lifecycle states, no-signal memory, deterministic direction-aware local reacquisition, clear-failure persistence, and an explicit all-search-complete/all-discovered-resolved exit condition.",
        f"3. `no_signal after FOUND` records an unavailable viewpoint, keeps the target unresolved, changes it to `REACQUIRE`, and selects a different probe from the last valid bearing. It never means that the target disappeared.",
        f"4. W2 full-clear rate is `{100*overall['clear_rate']:.1f}%`, versus W1 `{100*float(w1['clear_rate']):.1f}%`, a change of `{100*(overall['clear_rate']-float(w1['clear_rate'])):+.1f}` percentage points.",
        f"5. Remaining misses: `never_visible + visible_but_never_registered = {missed['never_visible'] + missed['visible_but_never_registered']}`; discovered-but-not-cleared classes total `{missed['discovered_but_localization_failed'] + missed['discovered_but_reacquisition_failed'] + missed['localized_but_not_cleared'] + missed['other']}`.",
        f"6. Readiness for path optimization/pruning: {'yes within this tested 200-case offline benchmark, because every episode reached full clearance with no remaining target; this is not a proof for every hidden distribution' if overall['clear_rate'] == 1.0 and overall['clear_fail_total'] == 0 else 'not yet; the failure taxonomy above must be addressed before optimizing speed'}.",
        "",
        f"Time-component identity maximum absolute residual: `{overall['max_abs_time_component_delta_s']:.9f}s`.",
        "",
        "No W3, detection-point pruning, lookahead, or router redesign is included.",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Q4 W2 persistent-lifecycle benchmark")
    parser.add_argument("--random-seeds", default="0:100")
    parser.add_argument("--stress-seeds", default="10000:10050")
    parser.add_argument("--out-dir", default="results/q4/w2")
    parser.add_argument("--w0-dir", default="results/q4/w0_baseline")
    parser.add_argument("--w1-dir", default="results/q4/w1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    assert_w2_ground_truth_isolated()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    random_seeds = parse_seed_range(args.random_seeds)
    stress_seeds = parse_seed_range(args.stress_seeds)
    suites = (
        ("random", random_seeds, "smooth"),
        ("min_reff", stress_seeds, "adversarial"),
        ("collinear", stress_seeds, "adversarial"),
    )

    details: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []
    for suite, seeds, field_kind in suites:
        for index, seed in enumerate(seeds, start=1):
            if suite == "random":
                case = generate_case(
                    seed=seed,
                    problem=4,
                    mode="practice",
                    field_kind=field_kind,
                    margin_m=0.0,
                )
            else:
                case = generate_stress_case(
                    suite,
                    seed=seed,
                    problem=4,
                    mode="practice",
                    field_kind=field_kind,
                    scan_points=[(point.x, point.y) for point in w1_search_points()],
                )
            result = run_episode(case, policy_w2, include_oracles=False)
            details.append(w2_case_row(suite, seed, result, case))
            if not result.success:
                missed.extend(missed_source_rows(suite, seed, case, result))
            if index % 10 == 0 or index == len(seeds):
                print(f"[w2/{suite}] {index}/{len(seeds)}", flush=True)

    summary = [summarize(details, suite) for suite in ("random", "min_reff", "collinear", "overall")]
    for row in summary:
        row["version"] = "w2"
        row["n"] = len(w1_search_points())
    by_count = source_count_summary(details)
    life = lifecycle_summary(details)
    failure_summary = missed_summary(missed)

    w0_dir = Path(args.w0_dir)
    w1_dir = Path(args.w1_dir)
    w0_details = read_csv(w0_dir / "details.csv")
    w1_details = read_csv(w1_dir / "details.csv")
    paired = paired_comparison(w0_details, details, "w0") + paired_comparison(w1_details, details, "w1")

    metadata = {
        "environment": "local offline_sim/practice only",
        "official_practice_run": False,
        "official_formal_test_run": False,
        "problem": 4,
        "random_seeds": args.random_seeds,
        "stress_seeds": args.stress_seeds,
        "random_margin_m": 0.0,
        "detection_backbone": "frozen W1 27-point triangular grid",
        "router": "frozen V4/V6 optimize_open_route",
        "policy_ground_truth_isolation": "AST checked and PolicyRunnerProxy enforced",
        "bearing_total_bound_deg": 1.005,
        "reacquire_step_m": 5.0,
        "defer_after_consecutive_failures": DEFER_AFTER_CONSECUTIVE_FAILURES,
    }

    write_csv(out_dir / "details.csv", details)
    write_csv(out_dir / "summary.csv", summary)
    write_csv(out_dir / "source_count_summary.csv", by_count)
    write_csv(out_dir / "lifecycle_summary.csv", life)
    write_csv(out_dir / "missed_sources.csv", missed)
    write_csv(out_dir / "missed_summary.csv", failure_summary)
    write_csv(out_dir / "paired_comparison.csv", paired)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    render_report(
        out_dir,
        summary,
        by_count,
        life,
        failure_summary,
        read_csv(w0_dir / "summary.csv"),
        read_csv(w1_dir / "summary.csv"),
        paired,
    )
    print(f"wrote {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
