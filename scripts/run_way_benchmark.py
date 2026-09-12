from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.case import generate_case, generate_stress_case
from offline_sim.harness import ActionRecord, EpisodeResult, run_episode
from q3.external_policies import policy_way1, policy_way3
from q3.geometry import localization_region, minimum_enclosing_circle
from q3.models import Measurement, Point
from q3.offline_policy import theoretical_outer_radius
from q3.planner import Q3BaselinePlanner
from q3.v5_policy import policy_v4_diagnostic
from q3.v6_policy import policy_v6


POLICIES: dict[str, Callable] = {
    "v4": policy_v4_diagnostic,
    "v6": policy_v6,
    "way1": policy_way1,
    "way3": policy_way3,
}

LB_CACHE: dict[tuple[str, int], dict[str, float]] = {}


def parse_seed_range(text: str) -> list[int]:
    if ":" in text:
        start, end = text.split(":", 1)
        return list(range(int(start), int(end)))
    return [int(part) for part in text.split(",") if part.strip()]


def percentile(vals: Iterable[float], q: float) -> float:
    data = sorted(float(v) for v in vals)
    if not data:
        return 0.0
    if len(data) == 1:
        return data[0]
    idx = q * (len(data) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return data[lo]
    frac = idx - lo
    return data[lo] * (1.0 - frac) + data[hi] * frac


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def action_components(actions: list[ActionRecord]) -> list[dict[str, Any]]:
    current = (0.0, 0.0)
    current_channel = 1
    rows: list[dict[str, Any]] = []
    found_channels: set[int] = set()
    for idx, action in enumerate(actions):
        point = (float(action.x), float(action.y))
        move_m = dist(current, point)
        switch_s = 0.0
        measure_s = 0.0
        clear_s = 0.0
        phase = "unknown"
        if action.action == "measure":
            switch_s = 1.0 if int(action.channel) != current_channel else 0.0
            measure_s = 5.0
            phase = "found" if int(action.channel) in found_channels else "search"
            if action.result in {"direction", "near"}:
                found_channels.add(int(action.channel))
            current_channel = int(action.channel)
        elif action.action == "clear":
            phase = "clear"
            clear_s = 5.0 if action.result == "success" else 3.0
        rows.append(
            {
                "index": idx,
                "action": action.action,
                "channel": int(action.channel),
                "x": point[0],
                "y": point[1],
                "result": action.result,
                "svd_deg": getattr(action, "svd_deg", None),
                "phase": phase,
                "virtual_time_s": float(getattr(action, "virtual_time_s", 0.0)),
                "move_m": move_m,
                "move_s": move_m / 5.0,
                "measure_s": measure_s,
                "switch_s": switch_s,
                "clear_s": clear_s,
            }
        )
        current = point
    return rows


def mec_radius(measurements: list[Measurement]) -> float | None:
    dirs = [m for m in measurements if m.result == "direction"]
    if len(dirs) < 2:
        return None
    region = localization_region(dirs)
    if not region:
        return None
    return float(minimum_enclosing_circle(region).radius)


def source_rows(version: str, suite: str, seed: int, result: EpisodeResult) -> list[dict[str, Any]]:
    actions = action_components(result.action_log)
    by_channel: dict[int, dict[str, Any]] = {}
    measurements: dict[int, list[Measurement]] = {}
    last_point = (0.0, 0.0)
    for row in actions:
        ch = int(row["channel"])
        state = by_channel.setdefault(
            ch,
            {
                "first_found_time_s": None,
                "clear_time_s": None,
                "supplement_measure_count": 0,
                "supplement_move_m": 0.0,
                "found_after_move_m": 0.0,
                "clear_attempt_count": 0,
                "mec_before_values": [],
                "mec_after_values": [],
                "first_found_mec_m": None,
                "final_clear_mec_m": None,
                "threshold_chasing_20_30": 0,
                "off_search_supplements": 0,
            },
        )
        if row["action"] == "measure":
            before_mec = mec_radius(measurements.get(ch, []))
            if row["result"] == "direction":
                measurements.setdefault(ch, []).append(
                    Measurement(
                        Point(float(row["x"]), float(row["y"])),
                        ch,
                        "direction",
                        None if row["svd_deg"] is None else float(row["svd_deg"]),
                        float(row["virtual_time_s"]),
                    )
                )
            after_mec = mec_radius(measurements.get(ch, []))
            if row["result"] in {"direction", "near"} and state["first_found_time_s"] is None:
                state["first_found_time_s"] = float(row["virtual_time_s"])
                state["first_found_mec_m"] = 0.0 if row["result"] == "near" else after_mec
            elif state["first_found_time_s"] is not None and state["clear_time_s"] is None:
                state["supplement_measure_count"] += 1
                state["supplement_move_m"] += float(row["move_m"])
                state["found_after_move_m"] += float(row["move_m"])
                state["mec_before_values"].append(before_mec)
                state["mec_after_values"].append(0.0 if row["result"] == "near" else after_mec)
                if row["phase"] != "search":
                    state["off_search_supplements"] += 1
                if before_mec is not None and 20.0 < before_mec <= 30.0:
                    state["threshold_chasing_20_30"] += 1
        elif row["action"] == "clear" and state["first_found_time_s"] is not None:
            state["clear_attempt_count"] += 1
            state["found_after_move_m"] += float(row["move_m"])
            if row["result"] == "success" and state["clear_time_s"] is None:
                state["clear_time_s"] = float(row["virtual_time_s"])
                state["final_clear_mec_m"] = mec_radius(measurements.get(ch, []))
        last_point = (float(row["x"]), float(row["y"]))

    out: list[dict[str, Any]] = []
    for ch, state in sorted(by_channel.items()):
        if state["first_found_time_s"] is None:
            continue
        cleared = state["clear_time_s"] is not None
        out.append(
            {
                "version": version,
                "suite": suite,
                "seed": seed,
                "channel": ch,
                "cleared": int(cleared),
                "first_found_time_s": state["first_found_time_s"],
                "clear_time_s": state["clear_time_s"],
                "found_to_clear_elapsed_s": (
                    float(state["clear_time_s"]) - float(state["first_found_time_s"]) if cleared else None
                ),
                "supplement_measure_count": state["supplement_measure_count"],
                "supplement_measure_time_s": 5.0 * int(state["supplement_measure_count"]),
                "supplement_move_m": state["supplement_move_m"],
                "supplement_move_time_s": float(state["supplement_move_m"]) / 5.0,
                "found_after_move_m": state["found_after_move_m"],
                "found_after_move_time_s": float(state["found_after_move_m"]) / 5.0,
                "clear_attempt_count": state["clear_attempt_count"],
                "off_search_supplements": state["off_search_supplements"],
                "threshold_chasing_20_30": state["threshold_chasing_20_30"],
                "first_found_mec_m": state["first_found_mec_m"],
                "final_clear_mec_m": state["final_clear_mec_m"],
                "first_supplement_mec_before_m": state["mec_before_values"][0] if state["mec_before_values"] else None,
                "first_supplement_mec_after_m": state["mec_after_values"][0] if state["mec_after_values"] else None,
                "min_supplement_mec_after_m": (
                    min(v for v in state["mec_after_values"] if v is not None)
                    if any(v is not None for v in state["mec_after_values"])
                    else None
                ),
            }
        )
    return out


def phase_rows(version: str, suite: str, seed: int, result: EpisodeResult) -> list[dict[str, Any]]:
    rows = action_components(result.action_log)
    out: list[dict[str, Any]] = []
    for phase in ("search", "found", "clear"):
        part = [row for row in rows if row["phase"] == phase]
        out.append(
            {
                "version": version,
                "suite": suite,
                "seed": seed,
                "phase": phase,
                "move_time_s": sum(float(row["move_s"]) for row in part),
                "move_distance_m": sum(float(row["move_m"]) for row in part),
                "measure_time_s": sum(float(row["measure_s"]) for row in part),
                "switch_time_s": sum(float(row["switch_s"]) for row in part),
                "clear_time_s": sum(float(row["clear_s"]) for row in part),
                "measure_count": sum(1 for row in part if row["action"] == "measure"),
                "clear_count": sum(1 for row in part if row["action"] == "clear"),
            }
        )
    return out


def disc_lower_bound(case: Any) -> dict[str, float]:
    pts = [(float(j.x), float(j.y)) for j in case.jammers]
    n = len(pts)
    if n == 0:
        return {"move_lb_m": 0.0, "time_abs_lb_s": 0.0, "center_route_m": 0.0}
    w0 = [max(0.0, math.hypot(x, y) - 20.0) for x, y in pts]
    wij = [
        [max(0.0, math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]) - 40.0) for j in range(n)]
        for i in range(n)
    ]
    dp: dict[tuple[int, int], float] = {}
    for i in range(n):
        dp[(1 << i, i)] = w0[i]
    for mask in range(1, 1 << n):
        for last in range(n):
            base = dp.get((mask, last))
            if base is None:
                continue
            remain = ((1 << n) - 1) ^ mask
            bits = remain
            while bits:
                bit = bits & -bits
                nxt = bit.bit_length() - 1
                key = (mask | bit, nxt)
                cand = base + wij[last][nxt]
                if cand < dp.get(key, math.inf):
                    dp[key] = cand
                bits ^= bit
    full = (1 << n) - 1
    lb_m = min(dp[(full, last)] for last in range(n))
    return {
        "move_lb_m": lb_m,
        "time_abs_lb_s": lb_m / 5.0 + 5.0 * n,
    }


def episode_row(version: str, suite: str, seed: int, case: Any, result: EpisodeResult) -> dict[str, Any]:
    lb_key = (suite, seed)
    if lb_key not in LB_CACHE:
        LB_CACHE[lb_key] = disc_lower_bound(case)
    lb = LB_CACHE[lb_key]
    source_count = int(result.total)
    total = float(result.virtual_time_s)
    component_sum = (
        float(result.move_time_s)
        + float(result.measure_action_time_s)
        + float(result.channel_switch_time_s)
        + float(result.clear_action_time_s)
    )
    return {
        "version": version,
        "suite": suite,
        "seed": seed,
        "success": int(result.success),
        "error": result.error or "",
        "cleared": int(result.cleared),
        "source_count": source_count,
        "total_time_s": total,
        "avg_source_s": total / result.cleared if result.cleared else 0.0,
        "move_distance_m": float(result.move_distance_m),
        "move_time_s": float(result.move_time_s),
        "measure_count": int(result.n_measure),
        "measure_time_s": float(result.measure_action_time_s),
        "switch_count": int(result.n_channel_switch),
        "switch_time_s": float(result.channel_switch_time_s),
        "clear_count": int(result.n_clear),
        "clear_success": int(result.n_clear - result.n_clear_fail),
        "clear_fail": int(result.n_clear_fail),
        "clear_time_s": float(result.clear_action_time_s),
        "near_count": int(result.n_near),
        "std_component_delta_s": total - component_sum,
        "policy_runtime_s": float(result.policy_runtime_s),
        "move_lb_m": lb["move_lb_m"],
        "time_abs_lb_s": lb["time_abs_lb_s"],
        "actual_over_abs_lb": total / lb["time_abs_lb_s"] if lb["time_abs_lb_s"] else 0.0,
        "move_regret_s": float(result.move_time_s) - lb["move_lb_m"] / 5.0,
        "info_regret_s": float(result.measure_action_time_s) + float(result.channel_switch_time_s) - 119.0,
        "full_oracle_proxy_time_s": result.full_oracle_proxy_time_s if result.full_oracle_proxy_time_s is not None else lb["time_abs_lb_s"],
        "full_oracle_proxy_gap": result.full_oracle_proxy_gap if result.full_oracle_proxy_gap is not None else (total - lb["time_abs_lb_s"]) / lb["time_abs_lb_s"],
        "conditional_oracle_time_s": result.conditional_route_oracle_time_s if result.conditional_route_oracle_time_s is not None else total,
        "conditional_oracle_gap": result.conditional_route_oracle_gap if result.conditional_route_oracle_gap is not None else 0.0,
    }


def summarize(version: str, suite: str, rows: list[dict[str, Any]], src_rows: list[dict[str, Any]]) -> dict[str, Any]:
    times = [float(row["total_time_s"]) for row in rows]
    if not rows:
        return {"version": version, "suite": suite}
    cleared = sum(int(row["cleared"]) for row in rows)
    supp_counts = [int(row["supplement_measure_count"]) for row in src_rows]
    return {
        "version": version,
        "suite": suite,
        "cases": len(rows),
        "success_rate": sum(int(row["success"]) for row in rows) / len(rows),
        "clear_fail_total": sum(int(row["clear_fail"]) for row in rows),
        "mean_time_s": statistics.fmean(times),
        "median_time_s": statistics.median(times),
        "p95_time_s": percentile(times, 0.95),
        "max_time_s": max(times),
        "std_time_s": statistics.pstdev(times),
        "mean_move_distance_m": statistics.fmean(float(row["move_distance_m"]) for row in rows),
        "mean_move_time_s": statistics.fmean(float(row["move_time_s"]) for row in rows),
        "mean_measure_count": statistics.fmean(int(row["measure_count"]) for row in rows),
        "mean_clear_count": statistics.fmean(int(row["clear_count"]) for row in rows),
        "mean_switch_count": statistics.fmean(int(row["switch_count"]) for row in rows),
        "mean_source_count": statistics.fmean(int(row["source_count"]) for row in rows),
        "mean_avg_source_s": statistics.fmean(float(row["avg_source_s"]) for row in rows),
        "pooled_avg_source_s": sum(times) / cleared if cleared else 0.0,
        "mean_move_regret_s": statistics.fmean(float(row["move_regret_s"]) for row in rows),
        "mean_info_regret_s": statistics.fmean(float(row["info_regret_s"]) for row in rows),
        "mean_actual_over_abs_lb": statistics.fmean(float(row["actual_over_abs_lb"]) for row in rows),
        "mean_full_oracle_gap": statistics.fmean(float(row["full_oracle_proxy_gap"]) for row in rows),
        "mean_conditional_oracle_gap": statistics.fmean(float(row["conditional_oracle_gap"]) for row in rows),
        "mean_supplements_per_source": statistics.fmean(supp_counts) if supp_counts else 0.0,
        "supp_0_rate": sum(v == 0 for v in supp_counts) / len(supp_counts) if supp_counts else 0.0,
        "supp_1_rate": sum(v == 1 for v in supp_counts) / len(supp_counts) if supp_counts else 0.0,
        "supp_2_rate": sum(v == 2 for v in supp_counts) / len(supp_counts) if supp_counts else 0.0,
        "supp_3_rate": sum(v == 3 for v in supp_counts) / len(supp_counts) if supp_counts else 0.0,
        "supp_ge4_rate": sum(v >= 4 for v in supp_counts) / len(supp_counts) if supp_counts else 0.0,
        "mean_found_to_clear_elapsed_s": statistics.fmean(
            float(row["found_to_clear_elapsed_s"]) for row in src_rows if row["found_to_clear_elapsed_s"] not in {"", None}
        ) if src_rows else 0.0,
        "mean_found_after_move_m": statistics.fmean(float(row["found_after_move_m"]) for row in src_rows) if src_rows else 0.0,
        "threshold_chasing_20_30_total": sum(int(row["threshold_chasing_20_30"]) for row in src_rows),
    }


def paired(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {(row["version"], row["suite"], int(row["seed"])): row for row in details}
    out: list[dict[str, Any]] = []
    for target in ("way1", "way3"):
        for base in ("v4", "v6"):
            for suite in ("random", "min_reff", "collinear", "overall"):
                keys = sorted(
                    (row["suite"], int(row["seed"]))
                    for row in details
                    if row["version"] == base and (suite == "overall" or row["suite"] == suite)
                )
                deltas = [
                    float(lookup[(target, group, seed)]["total_time_s"]) - float(lookup[(base, group, seed)]["total_time_s"])
                    for group, seed in keys
                ]
                if not deltas:
                    continue
                out.append(
                    {
                        "target": target,
                        "base": base,
                        "suite": suite,
                        "pairs": len(deltas),
                        "target_win_rate": sum(delta < 0.0 for delta in deltas) / len(deltas),
                        "mean_delta_s": statistics.fmean(deltas),
                        "median_delta_s": statistics.median(deltas),
                        "p95_delta_s": percentile(deltas, 0.95),
                        "worst_regression_s": max(deltas),
                        "best_improvement_s": min(deltas),
                    }
                )
    return out


def timeline_rows(version: str, suite: str, seed: int, result: EpisodeResult, limit: int = 260) -> list[dict[str, Any]]:
    rows = action_components(result.action_log)
    return [
        {
            "version": version,
            "suite": suite,
            "seed": seed,
            "index": row["index"],
            "time_s": row["virtual_time_s"],
            "phase": row["phase"],
            "action": row["action"],
            "channel": row["channel"],
            "x": row["x"],
            "y": row["y"],
            "result": row["result"],
            "move_m": row["move_m"],
        }
        for row in rows[:limit]
    ]


def choose_typical(details: list[dict[str, Any]]) -> list[tuple[str, str, int, str]]:
    lookup = {(row["version"], row["suite"], int(row["seed"])): row for row in details}
    out: list[tuple[str, str, int, str]] = []
    for target in ("way1", "way3"):
        cases = []
        for row in details:
            if row["version"] != target:
                continue
            key = (row["suite"], int(row["seed"]))
            delta = float(row["total_time_s"]) - float(lookup[("v6", *key)]["total_time_s"])
            cases.append((delta, row["suite"], int(row["seed"])))
        best = min(cases, key=lambda item: item[0])
        worst = max(cases, key=lambda item: item[0])
        out.append((target, best[1], best[2], "fast_vs_v6"))
        out.append((target, worst[1], worst[2], "slow_vs_v6"))
    leads = []
    for row in details:
        if row["version"] != "v6":
            continue
        key = (row["suite"], int(row["seed"]))
        best_external = min(float(lookup[(v, *key)]["total_time_s"]) for v in ("way1", "way3"))
        leads.append((float(row["total_time_s"]) - best_external, row["suite"], int(row["seed"])))
    lead = min(leads, key=lambda item: item[0])
    out.append(("v6", lead[1], lead[2], "v6_leads_external"))
    return out


def make_case(suite: str, seed: int, field_kind: str):
    if suite == "random":
        return generate_case(seed=seed, problem=3, mode="practice", field_kind=field_kind)
    radius = theoretical_outer_radius(8)
    scan_points = [(p.x, p.y) for p in Q3BaselinePlanner.make_search_points(radius, 8)]
    return generate_stress_case(
        suite,
        seed=seed,
        problem=3,
        mode="practice",
        field_kind=field_kind,
        scan_points=scan_points,
    )


def render_report(out_dir: Path, summaries: list[dict[str, Any]], pairs: list[dict[str, Any]]) -> None:
    overall = [row for row in summaries if row["suite"] == "overall"]
    lines = [
        "# Q3 Way1 / Way3 Unified Offline Benchmark",
        "",
        "Environment: local `offline_sim` practice-only. No official formal test was run.",
        "",
        "## Overall Summary",
        "",
        "| version | success | mean | median | P95 | max | move m | measure | clear fail | move regret | info regret |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in overall:
        lines.append(
            f"| {row['version']} | {100*row['success_rate']:.1f}% | {row['mean_time_s']:.2f} | "
            f"{row['median_time_s']:.2f} | {row['p95_time_s']:.2f} | {row['max_time_s']:.2f} | "
            f"{row['mean_move_distance_m']:.2f} | {row['mean_measure_count']:.2f} | "
            f"{row['clear_fail_total']} | {row['mean_move_regret_s']:.2f} | {row['mean_info_regret_s']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Paired Comparison",
            "",
            "| target | base | suite | win rate | mean delta | median | P95 | worst | best |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in pairs:
        if row["suite"] == "overall":
            lines.append(
                f"| {row['target']} | {row['base']} | {row['suite']} | {100*row['target_win_rate']:.1f}% | "
                f"{row['mean_delta_s']:.2f} | {row['median_delta_s']:.2f} | {row['p95_delta_s']:.2f} | "
                f"{row['worst_regression_s']:.2f} | {row['best_improvement_s']:.2f} |"
            )
    lines.extend(
        [
            "",
            "## Adaptation Notes",
            "",
            "- Way1 is run through its original `Controller` and Q3 feasible-set stack, with a runner-to-response adapter. Its run-script defaults are used: safe coverage radius 980m, 6 outer points, clear certificate 19m, coarse/fine 40m/15m.",
            "- Way3 is run through its original `Hunter(problem=3)` and `RunnerWorld` adapter. It keeps its 7-point coverage search, stage-style scan then homing/clear design, clear margin 14m, prune radius 30m.",
            "- The simulator, seeds, source generation, fixed location bearing error, movement, measure, switch, clear, and termination rules are our unified local `offline_sim`.",
            "- Lower-bound regret uses the evaluate branch's strict disc-distance Held-Karp movement lower bound. The SLSQP TSPN upper bound was not used because scipy is unavailable in this environment.",
            "",
            "See CSV files in this directory for group tables, phase decomposition, source-level FOUND-to-CLEAR statistics, and timelines.",
        ]
    )
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Q3 Way1/Way3 unified offline benchmark.")
    parser.add_argument("--versions", default="v4,v6,way1,way3")
    parser.add_argument("--random-seeds", default="0:100")
    parser.add_argument("--stress-seeds", default="10000:10050")
    parser.add_argument("--out-dir", default="results/offline_eval_way1_way3")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    versions = [item.strip() for item in args.versions.split(",") if item.strip()]
    for version in versions:
        if version not in POLICIES:
            raise SystemExit(f"unknown version {version}")
    suites = [
        ("random", parse_seed_range(args.random_seeds), "smooth"),
        ("min_reff", parse_seed_range(args.stress_seeds), "adversarial"),
        ("collinear", parse_seed_range(args.stress_seeds), "adversarial"),
    ]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    details: list[dict[str, Any]] = []
    src: list[dict[str, Any]] = []
    phases: list[dict[str, Any]] = []
    saved_results: dict[tuple[str, str, int], EpisodeResult] = {}
    for version in versions:
        for suite, seeds, field_kind in suites:
            for i, seed in enumerate(seeds, start=1):
                case = make_case(suite, seed, field_kind)
                policy = POLICIES[version]
                if version in {"v4", "v6"}:
                    result = run_episode(case, lambda runner, p=policy: p(runner, n=8), include_oracles=False)
                else:
                    result = run_episode(case, policy, include_oracles=False)
                details.append(episode_row(version, suite, seed, case, result))
                sr = source_rows(version, suite, seed, result)
                src.extend(sr)
                phases.extend(phase_rows(version, suite, seed, result))
                saved_results[(version, suite, seed)] = result
                if i % 10 == 0 or i == len(seeds):
                    print(f"[{version}/{suite}] {i}/{len(seeds)}", flush=True)

    summaries: list[dict[str, Any]] = []
    for version in versions:
        for suite in ("random", "min_reff", "collinear", "overall"):
            dsub = [row for row in details if row["version"] == version and (suite == "overall" or row["suite"] == suite)]
            ssub = [row for row in src if row["version"] == version and (suite == "overall" or row["suite"] == suite)]
            summaries.append(summarize(version, suite, dsub, ssub))
    pairs = paired(details)

    typical_keys = choose_typical(details)
    typical_meta = [
        {"version": v, "suite": s, "seed": seed, "kind": kind}
        for v, s, seed, kind in typical_keys
    ]
    timelines: list[dict[str, Any]] = []
    for version, suite, seed, _ in typical_keys:
        timelines.extend(timeline_rows(version, suite, seed, saved_results[(version, suite, seed)]))

    write_csv(out_dir / "details.csv", details)
    write_csv(out_dir / "summary.csv", summaries)
    write_csv(out_dir / "paired_comparison.csv", pairs)
    write_csv(out_dir / "phase_decomposition.csv", phases)
    write_csv(out_dir / "source_found_clear.csv", src)
    write_csv(out_dir / "typical_cases.csv", typical_meta)
    write_csv(out_dir / "typical_timelines.csv", timelines)
    (out_dir / "summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "metadata.json").write_text(
        json.dumps(
            {
                "environment": "local offline_sim practice only",
                "official_formal_test_run": False,
                "versions": versions,
                "random_seeds": args.random_seeds,
                "stress_seeds": args.stress_seeds,
                "ground_truth_policy_use": False,
                "lower_bound": "disc-distance exact Held-Karp movement lower bound; no scipy SLSQP upper-bound refinement",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    render_report(out_dir, summaries, pairs)
    print(out_dir / "report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
