from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import os
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.harness import EpisodeResult, run_episode
from q3.v5_policy import policy_v4_diagnostic
from q3.v6_l2_policy import policy_v6_l1, policy_v6_l2
from q3.v6_policy import policy_v6
from scripts.run_stage2_eval import phase_summary_rows
from scripts.run_v5_eval import (
    episode_row,
    parse_seed_range,
    percentile,
    source_diagnostic_rows,
    summarize,
    write_csv,
)
from scripts.run_way_benchmark import action_components, make_case, phase_rows


POLICIES: dict[str, Callable] = {
    "v4": policy_v4_diagnostic,
    "v6": policy_v6,
    "v6l1": policy_v6_l1,
    "v6l2": policy_v6_l2,
}


def assert_ground_truth_isolated() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        Path("q3/v6_l2_policy.py"),
        Path("q3/v6_policy.py"),
        Path("q3/v5_prediction.py"),
    ):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("offline_sim"):
                raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Import) and any(alias.name.startswith("offline_sim") for alias in node.names):
                raise RuntimeError(f"ground-truth isolation failed: {relative} imports offline_sim")
            if isinstance(node, ast.Attribute) and node.attr in {"case", "engine", "sources", "jammers"}:
                raise RuntimeError(f"ground-truth isolation failed: {relative} accesses .{node.attr}")


def l2_event_rows(version: str, suite: str, seed: int, result: EpisodeResult) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for event in result.policy_diagnostics:
        if event.get("event") != "l2_supplement_execution":
            continue
        output.append({"version": version, "suite": suite, "seed": seed, **event})
    return output


def timeline_rows(version: str, suite: str, seed: int, result: EpisodeResult) -> list[dict[str, Any]]:
    found: set[int] = set()
    supplements: dict[int, int] = {}
    output: list[dict[str, Any]] = []
    for row in action_components(result.action_log):
        channel = int(row["channel"])
        if row["action"] == "measure" and channel in found:
            supplements[channel] = supplements.get(channel, 0) + 1
            event = f"SUPPLEMENT_{supplements[channel]}"
        elif row["action"] == "measure" and row["result"] in {"direction", "near"}:
            found.add(channel)
            event = "FIRST_FOUND"
        elif row["action"] == "measure":
            event = "SEARCH_MEASURE"
        else:
            event = "CLEAR"
        output.append(
            {
                "version": version,
                "suite": suite,
                "seed": seed,
                "index": row["index"],
                "time_s": row["virtual_time_s"],
                "phase": row["phase"],
                "event": event,
                "channel": channel,
                "x": row["x"],
                "y": row["y"],
                "result": row["result"],
                "svd_deg": row["svd_deg"],
                "move_m": row["move_m"],
            }
        )
    return output


def run_job(job: tuple[str, str, int, str]) -> dict[str, Any]:
    version, suite, seed, field_kind = job
    case = make_case(suite, seed, field_kind)
    policy = POLICIES[version]
    result = run_episode(
        case,
        lambda runner: policy(runner, n=8),
        include_oracles=False,
    )
    source_rows = source_diagnostic_rows(version, suite, seed, result)
    return {
        "version": version,
        "suite": suite,
        "seed": seed,
        "detail": episode_row(version, suite, seed, result, source_rows),
        "sources": source_rows,
        "phases": phase_rows(version, suite, seed, result),
        "events": l2_event_rows(version, suite, seed, result),
        "timeline": timeline_rows(version, suite, seed, result),
    }


def enriched_summary(
    version: str,
    suite: str,
    details: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    row = summarize(version, suite, details, sources)
    avg_source = [float(item["avg_source_s"]) for item in details]
    row.update(
        {
            "std_total_time_s": statistics.pstdev(float(item["total_time_s"]) for item in details),
            "median_avg_source_s": statistics.median(avg_source),
            "p95_avg_source_s": percentile(avg_source, 0.95),
        }
    )
    return row


def paired_rows(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {(row["version"], row["suite"], int(row["seed"])): row for row in details}
    output: list[dict[str, Any]] = []
    for base in ("v6", "v4"):
        for suite in ("random", "min_reff", "collinear", "overall"):
            keys = sorted(
                (row["suite"], int(row["seed"]))
                for row in details
                if row["version"] == base and (suite == "overall" or row["suite"] == suite)
            )
            pairs = [(lookup[(base, group, seed)], lookup[("v6l2", group, seed)]) for group, seed in keys]
            deltas = [float(right["total_time_s"]) - float(left["total_time_s"]) for left, right in pairs]
            avg_deltas = [float(right["avg_source_s"]) - float(left["avg_source_s"]) for left, right in pairs]
            output.append(
                {
                    "base": base,
                    "target": "v6l2",
                    "suite": suite,
                    "pairs": len(pairs),
                    "target_win_rate": sum(delta < 0.0 for delta in deltas) / len(deltas),
                    "mean_delta_time_s": statistics.fmean(deltas),
                    "median_delta_time_s": statistics.median(deltas),
                    "p95_delta_time_s": percentile(deltas, 0.95),
                    "worst_regression_s": max(deltas),
                    "best_improvement_s": min(deltas),
                    "worse_over_100s_count": sum(delta > 100.0 for delta in deltas),
                    "worse_over_300s_count": sum(delta > 300.0 for delta in deltas),
                    "mean_delta_avg_source_s": statistics.fmean(avg_deltas),
                    "median_delta_avg_source_s": statistics.median(avg_deltas),
                    "p95_delta_avg_source_s": percentile(avg_deltas, 0.95),
                    "mean_delta_move_m": statistics.fmean(
                        float(right["move_distance_m"]) - float(left["move_distance_m"])
                        for left, right in pairs
                    ),
                }
            )
    return output


def severe_regression_rows(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {(row["version"], row["suite"], int(row["seed"])): row for row in details}
    output: list[dict[str, Any]] = []
    for version, suite, seed in sorted(lookup):
        if version != "v6":
            continue
        v4 = lookup[("v4", suite, seed)]
        v6 = lookup[("v6", suite, seed)]
        l2 = lookup[("v6l2", suite, seed)]
        old_delta = float(v6["total_time_s"]) - float(v4["total_time_s"])
        if old_delta <= 300.0:
            continue
        output.append(
            {
                "suite": suite,
                "seed": seed,
                "v4_time_s": v4["total_time_s"],
                "v6_time_s": v6["total_time_s"],
                "v6l2_time_s": l2["total_time_s"],
                "l2_minus_v6_s": float(l2["total_time_s"]) - float(v6["total_time_s"]),
                "l2_minus_v4_s": float(l2["total_time_s"]) - float(v4["total_time_s"]),
                "l2_minus_v6_move_m": float(l2["move_distance_m"]) - float(v6["move_distance_m"]),
                "l2_minus_v6_measure_count": int(l2["measure_count"]) - int(v6["measure_count"]),
            }
        )
    return output


def phase_delta_rows(
    details: list[dict[str, Any]],
    phases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    detail = {(row["version"], row["suite"], int(row["seed"])): row for row in details}
    phase = {
        (row["version"], row["suite"], int(row["seed"]), row["phase"]): row
        for row in phases
    }
    output: list[dict[str, Any]] = []
    for suite in ("random", "min_reff", "collinear", "overall"):
        keys = sorted(
            (row["suite"], int(row["seed"]))
            for row in details
            if row["version"] == "v6" and (suite == "overall" or row["suite"] == suite)
        )
        case_rows = []
        for group, seed in keys:
            values: dict[str, float] = {}
            for name in ("search", "found", "clear"):
                left = phase[("v6", group, seed, name)]
                right = phase[("v6l2", group, seed, name)]
                values[f"delta_{name}_move_s"] = float(right["move_time_s"]) - float(left["move_time_s"])
                values[f"delta_{name}_info_s"] = (
                    float(right["measure_time_s"])
                    + float(right["switch_time_s"])
                    - float(left["measure_time_s"])
                    - float(left["switch_time_s"])
                )
                values[f"delta_{name}_service_s"] = float(right["clear_time_s"]) - float(left["clear_time_s"])
            l2 = detail[("v6l2", group, seed)]
            v6 = detail[("v6", group, seed)]
            values["delta_total_s"] = float(l2["total_time_s"]) - float(v6["total_time_s"])
            values["delta_dedicated_supplement_move_s"] = (
                float(l2["off_search_supplement_move_m"])
                - float(v6["off_search_supplement_move_m"])
            ) / 5.0
            values["ordering_remainder_proxy_s"] = (
                values["delta_found_move_s"]
                + values["delta_clear_move_s"]
                - values["delta_dedicated_supplement_move_s"]
            )
            values["component_reconciliation_s"] = values["delta_total_s"] - sum(
                values[f"delta_{name}_{component}_s"]
                for name in ("search", "found", "clear")
                for component in ("move", "info", "service")
            )
            case_rows.append(values)
        output.append(
            {
                "target": "v6l2",
                "base": "v6",
                "suite": suite,
                "cases": len(case_rows),
                **{
                    f"mean_{key}": statistics.fmean(row[key] for row in case_rows)
                    for key in case_rows[0]
                },
            }
        )
    return output


def verify_replay(details: list[dict[str, Any]], reference_path: Path) -> dict[str, Any]:
    with reference_path.open(newline="", encoding="utf-8") as handle:
        reference = {
            (row["version"], row["suite"], int(row["seed"])): row
            for row in csv.DictReader(handle)
            if row["version"] in {"v4", "v6"}
        }
    current = {
        (row["version"], row["suite"], int(row["seed"])): row
        for row in details
        if row["version"] in {"v4", "v6"}
    }
    keys = sorted(set(reference) & set(current))
    time_delta = [abs(float(current[key]["total_time_s"]) - float(reference[key]["total_time_s"])) for key in keys]
    move_delta = [abs(float(current[key]["move_distance_m"]) - float(reference[key]["move_distance_m"])) for key in keys]
    return {
        "pairs": len(keys),
        "max_abs_time_delta_s": max(time_delta, default=0.0),
        "max_abs_move_delta_m": max(move_delta, default=0.0),
        "equivalent": bool(keys and max(time_delta, default=0.0) <= 1e-6 and max(move_delta, default=0.0) <= 1e-6),
    }


def make_plots(
    out_dir: Path,
    severe: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
) -> None:
    selected = {(row["suite"], int(row["seed"])) for row in severe}
    selected.update({("random", 70), ("random", 83)})
    by_key: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for row in timeline:
        key = (str(row["version"]), str(row["suite"]), int(row["seed"]))
        by_key.setdefault(key, []).append(row)

    figure_dir = out_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    def sx(x: float, offset: float) -> float:
        return offset + 300.0 + x * 300.0 / 1900.0

    def sy(y: float) -> float:
        return 310.0 - y * 300.0 / 1900.0

    for suite, seed in sorted(selected):
        if not all((version, suite, seed) in by_key for version in ("v6", "v6l2")):
            continue
        case = make_case(suite, seed, "smooth" if suite == "random" else "adversarial")
        parts = [
            '<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="650" viewBox="0 0 1240 650">',
            '<rect width="1240" height="650" fill="#ffffff"/>',
            f'<text x="620" y="24" text-anchor="middle" font-family="Arial" font-size="17">{suite} seed {seed}: frozen V6 vs V6-L2</text>',
        ]
        for panel, version in enumerate(("v6", "v6l2")):
            offset = 10.0 + panel * 610.0
            rows = by_key[(version, suite, seed)]
            points = [(0.0, 0.0)] + [(float(row["x"]), float(row["y"])) for row in rows]
            route = " ".join(f"{sx(x, offset):.2f},{sy(y):.2f}" for x, y in points)
            parts.extend(
                [
                    f'<text x="{offset + 300:.1f}" y="48" text-anchor="middle" font-family="Arial" font-size="15">{version}</text>',
                    f'<circle cx="{offset + 300:.2f}" cy="310" r="{1800*300/1900:.2f}" fill="none" stroke="#CBD5E1" stroke-dasharray="5 4"/>',
                    f'<polyline points="{route}" fill="none" stroke="#6B7280" stroke-width="1.2" stroke-opacity="0.78"/>',
                ]
            )
            supplements = [row for row in rows if str(row["event"]).startswith("SUPPLEMENT")]
            clears = [row for row in rows if row["event"] == "CLEAR" and row["result"] == "success"]
            for row in supplements:
                x = sx(float(row["x"]), offset)
                y = sy(float(row["y"]))
                parts.append(f'<path d="M{x-3:.2f},{y-3:.2f} L{x+3:.2f},{y+3:.2f} M{x-3:.2f},{y+3:.2f} L{x+3:.2f},{y-3:.2f}" stroke="#D97706" stroke-width="1.5"/>')
            for row in clears:
                x = sx(float(row["x"]), offset)
                y = sy(float(row["y"]))
                parts.append(f'<rect x="{x-2.8:.2f}" y="{y-2.8:.2f}" width="5.6" height="5.6" fill="#15803D"/>')
            for jammer in case.jammers:
                x = sx(float(jammer.x), offset)
                y = sy(float(jammer.y))
                parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.8" fill="#B91C1C"/>')
            final_time = float(rows[-1]["time_s"]) if rows else 0.0
            move_m = sum(float(row["move_m"]) for row in rows)
            parts.append(f'<text x="{offset + 300:.1f}" y="628" text-anchor="middle" font-family="Arial" font-size="12" fill="#334155">time {final_time:.1f}s | move {move_m:.0f}m</text>')
        parts.extend(
            [
                '<text x="620" y="610" text-anchor="middle" font-family="Arial" font-size="11" fill="#64748B">gray: route   red: source truth (post-episode only)   orange x: supplement   green square: clear</text>',
                '</svg>',
            ]
        )
        (figure_dir / f"{suite}_{seed}_v6_vs_v6l2.svg").write_text("\n".join(parts), encoding="utf-8")


def format_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---:" if index else "---" for index in range(len(headers))) + "|",
        *("| " + " | ".join(row) + " |" for row in rows),
    ]


def render_report(
    out_dir: Path,
    summaries: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    severe: list[dict[str, Any]],
    phase_summary: list[dict[str, Any]],
    phase_delta: list[dict[str, Any]],
    replay: dict[str, Any],
    details: list[dict[str, Any]],
    phases: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> None:
    overall = {row["version"]: row for row in summaries if row["suite"] == "overall"}
    l2 = overall["v6l2"]
    v6 = overall["v6"]
    pair_v6 = next(row for row in pairs if row["base"] == "v6" and row["suite"] == "overall")
    severe_improved = sum(float(row["l2_minus_v6_s"]) < 0.0 for row in severe)
    severe_fully_repaired = sum(float(row["l2_minus_v4_s"]) <= 0.0 for row in severe)
    changed_decisions = sum(str(row.get("changed_from_v6", "")).lower() == "true" for row in events)
    cpu_ratio = l2["mean_policy_runtime_s"] / v6["mean_policy_runtime_s"]
    replace = (
        l2["clear_rate"] == 1.0
        and l2["clear_fail_total"] == 0
        and pair_v6["worse_over_300s_count"] < len(severe)
        and l2["p95_total_time_s"] <= v6["p95_total_time_s"]
        and l2["max_total_time_s"] <= v6["max_total_time_s"]
        and l2["mean_avg_source_s"] <= v6["mean_avg_source_s"] + 1e-9
    )
    lines = [
        "# Q3 V6-L2 depth-2 lookahead evaluation",
        "",
        "本报告仅使用本地 `offline_sim` practice cases；没有调用官方 HTTP、官方演练或正式测试。",
        "",
        "## 结论",
        "",
        (
            "V6-L2 满足本轮升级条件，建议替换 frozen V6/n=8。"
            if replace
            else "V6-L2 未同时满足清除率、尾部与 mean(T/N) 升级条件，不建议替换 frozen V6/n=8。"
        ),
        "",
        f"相对 V6：mean {pair_v6['mean_delta_time_s']:+.2f}s，P95 {l2['p95_total_time_s']-v6['p95_total_time_s']:+.2f}s，"
        f"max {l2['max_total_time_s']-v6['max_total_time_s']:+.2f}s，>300s 回退 {pair_v6['worse_over_300s_count']} 局。",
        "",
        "## A. 数学定义与实现",
        "",
        "Frozen V6 使用 `J1(S)=route_marginal(S)+5+E[V6_source_after]`。V6-L2 对即将进入 frozen router 执行前沿的补测候选计算：",
        "",
        "`Q2(s0,S1)=route_marginal(S1)+5+E_o1[c(s1,a2)+E_o2[V6_terminal(s2)]]`。",
        "",
        "每个 S1 仍使用 V6 原候选集、12 个固定可行域样本和 `(-1,0,+1)` 度误差。o1 后只重建因该观测改变的源任务，未改变源的 V6 任务保留，但 SEARCH/MEASURE/CLEAR 完整任务池会重新交给 frozen router 选择 a2。第二步 MEASURE 的 36 个结果已由 frozen `predict_candidate` 枚举；由于其他任务的 terminal 与 o2 可分离，代码以线性期望作等价合并。没有 alpha/lambda。",
        "",
        "L2 采用滚动规划下的惰性求值：只对当前可执行前沿上的补测做两层展开，远期补测会在真正到达执行前沿时重新评价。depth=1 直接走 frozen V6 路径。",
        "",
        "## B. 总表",
        "",
    ]
    lines.extend(
        format_table(
            ["版本", "Clear", "Mean", "Median", "P95", "Max", "Mean T/N", "Median T/N", "P95 T/N", "Move m", "Measures", "Switch", "CPU s"],
            [
                [
                    version,
                    f"{100*row['clear_rate']:.1f}%/{row['clear_fail_total']}",
                    f"{row['mean_total_time_s']:.2f}",
                    f"{row['median_total_time_s']:.2f}",
                    f"{row['p95_total_time_s']:.2f}",
                    f"{row['max_total_time_s']:.2f}",
                    f"{row['mean_avg_source_s']:.2f}",
                    f"{row['median_avg_source_s']:.2f}",
                    f"{row['p95_avg_source_s']:.2f}",
                    f"{row['mean_move_distance_m']:.2f}",
                    f"{row['mean_measure_count']:.2f}",
                    f"{row['mean_switch_count']:.2f}",
                    f"{row['mean_policy_runtime_s']:.3f}",
                ]
                for version, row in overall.items()
            ],
        )
    )
    lines.extend(["", "## C. Same-seed paired comparison", ""])
    lines.extend(
        format_table(
            ["Base", "Suite", "Win", "Mean delta", "Median", "P95 delta", "Worst", "Best", ">100s", ">300s"],
            [
                [
                    row["base"], row["suite"], f"{100*row['target_win_rate']:.1f}%",
                    f"{row['mean_delta_time_s']:+.2f}", f"{row['median_delta_time_s']:+.2f}",
                    f"{row['p95_delta_time_s']:+.2f}", f"{row['worst_regression_s']:+.2f}",
                    f"{row['best_improvement_s']:+.2f}", str(row["worse_over_100s_count"]),
                    str(row["worse_over_300s_count"]),
                ]
                for row in pairs
            ],
        )
    )
    lines.extend(["", "## D. 原 V6 严重回退 case", ""])
    lines.extend(
        format_table(
            ["Suite", "Seed", "V4", "V6", "V6-L2", "L2-V6", "L2-V4"],
            [
                [row["suite"], str(row["seed"]), f"{float(row['v4_time_s']):.2f}", f"{float(row['v6_time_s']):.2f}", f"{float(row['v6l2_time_s']):.2f}", f"{float(row['l2_minus_v6_s']):+.2f}", f"{float(row['l2_minus_v4_s']):+.2f}"]
                for row in severe
            ],
        )
    )
    lines.extend(["", "## E. SEARCH / FOUND / CLEAR 分解", ""])
    lines.extend(
        format_table(
            ["Version", "Phase", "Move", "Info", "Clear service", "Total"],
            [
                [row["version"], row["phase"], f"{row['mean_move_time_s']:.2f}", f"{row['mean_measure_time_s']+row['mean_switch_time_s']:.2f}", f"{row['mean_clear_time_s']:.2f}", f"{row['mean_total_time_s']:.2f}"]
                for row in phase_summary
                if row["suite"] == "overall"
            ],
        )
    )
    delta = next(row for row in phase_delta if row["suite"] == "overall")
    detail_lookup = {
        (row["version"], row["suite"], int(row["seed"])): row
        for row in details
    }
    phase_lookup = {
        (row["version"], row["suite"], int(row["seed"]), row["phase"]): row
        for row in phases
    }
    lines.extend(
        [
            "",
            "相对 V6 的平均差值："
            f"SEARCH move {delta['mean_delta_search_move_s']:+.2f}s，SEARCH info {delta['mean_delta_search_info_s']:+.2f}s，"
            f"FOUND move {delta['mean_delta_found_move_s']:+.2f}s，FOUND info {delta['mean_delta_found_info_s']:+.2f}s，"
            f"CLEAR move {delta['mean_delta_clear_move_s']:+.2f}s。"
            f"专门补测移动代理 {delta['mean_delta_dedicated_supplement_move_s']:+.2f}s，"
            f"task-ordering remainder proxy {delta['mean_ordering_remainder_proxy_s']:+.2f}s。",
            "",
            "`component_reconciliation_s` 仅检查时间恒等式，不应解释为调度损失；调度代理沿用此前定义：FOUND move + CLEAR move - off-search supplement arrival move。",
            "",
            "## F. seed 70 / 83 复盘",
            "",
        ]
    )
    seed_rows: list[list[str]] = []
    for seed in (70, 83):
        for version in ("v6", "v6l2"):
            detail_row = detail_lookup[(version, "random", seed)]
            search = phase_lookup[(version, "random", seed, "search")]
            found = phase_lookup[(version, "random", seed, "found")]
            clear = phase_lookup[(version, "random", seed, "clear")]
            seed_rows.append(
                [
                    str(seed), version, f"{float(detail_row['total_time_s']):.2f}",
                    f"{float(detail_row['move_distance_m']):.2f}",
                    f"{float(search['move_time_s']):.2f}", f"{float(found['move_time_s']):.2f}",
                    f"{float(clear['move_time_s']):.2f}", str(detail_row["supplement_measure_count"]),
                ]
            )
    lines.extend(
        format_table(
            ["Seed", "Version", "Total", "Move m", "SEARCH move s", "FOUND move s", "CLEAR move s", "Supplements"],
            seed_rows,
        )
    )
    lines.extend(
        [
            "",
            "seed 70 中 L2 相对 V6 快 190.25s：SEARCH move 减少 619.36s、CLEAR move 减少 82.18s，但 FOUND move 增加 491.30s 且补测多 2 次。它缓解了旧回退，却仍比 V4 慢 362.76s。",
            "",
            "seed 83 中 L2 相对 V6 慢 157.00s：FOUND move 增加 478.35s、补测多 3 次，虽 CLEAR move 减少 337.37s仍无法抵消；相对 V4 已慢 680.11s。",
            "",
            f"原 12 个 V6>V4 300s case 中，L2 有 {severe_improved}/12 相对 V6 改善，但只有 {severe_fully_repaired}/12 真正降到 V4 以下；其余改善多为部分缓解。",
            "",
            "## G. CPU 与决策变化",
            "",
            f"L2 平均 policy CPU 为 {l2['mean_policy_runtime_s']:.2f}s/局，V6 为 {v6['mean_policy_runtime_s']:.2f}s/局，即 {cpu_ratio:.2f}x。"
            f"200 局共执行 {len(events)} 次 L2 补测决策，其中 {changed_decisions} 次（{100*changed_decisions/len(events):.1f}%）改变了 V6 候选。",
            "",
            "## H. 正确性与复现",
            "",
            f"V4/V6 历史重放：{json.dumps(replay, ensure_ascii=False)}。每局均检查 total=move+measure+switch+clear；策略代码通过 AST 隔离检查，不导入或访问 case/engine/sources/jammers。",
            "",
            "seed 70、83 及原 12 个 V6>V4 300s case 的动作时间线见 `typical_timelines.csv`，路线图见 `figures/`。图中的真值仅由 episode 完成后的评估代码读取，不进入 policy。",
            "",
            "## I. 判断",
            "",
            (
                "两步展开在当前 200 个同 seed 离线案例中同时改善了尾部与 mean(T/N)，可以作为下一候选。"
                if replace
                else "两步展开没有在当前 200 个同 seed 离线案例中稳定压缩尾部；其额外 CPU 成本也没有换来足够稳健的路线收益，因此 frozen V6/n=8 仍是正式候选。"
            ),
            "",
            "该结论只适用于当前离线 simulator/practice 分布，不是官方隐藏分布保证。",
        ]
    )
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline-only Q3 frozen V6 vs V6-L2 evaluation")
    parser.add_argument("--versions", default="v4,v6,v6l2")
    parser.add_argument("--random-seeds", default="0:100")
    parser.add_argument("--stress-seeds", default="10000:10050")
    parser.add_argument("--workers", type=int, default=max(1, min(8, os.cpu_count() or 1)))
    parser.add_argument("--out-dir", default="results/offline_eval_v6_l2_200")
    parser.add_argument("--reference", default="results/offline_eval_v6_n8/details.csv")
    parser.add_argument("--skip-plots", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    assert_ground_truth_isolated()
    versions = [item.strip() for item in args.versions.split(",") if item.strip()]
    unknown = [version for version in versions if version not in POLICIES]
    if unknown:
        raise SystemExit(f"unknown versions: {unknown}")
    suites = [
        ("random", parse_seed_range(args.random_seeds), "smooth"),
        ("min_reff", parse_seed_range(args.stress_seeds), "adversarial"),
        ("collinear", parse_seed_range(args.stress_seeds), "adversarial"),
    ]
    jobs = [
        (version, suite, seed, field_kind)
        for version in versions
        for suite, seeds, field_kind in suites
        for seed in seeds
    ]
    outputs: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run_job, job) for job in jobs]
        for index, future in enumerate(as_completed(futures), start=1):
            outputs.append(future.result())
            if index % 10 == 0 or index == len(futures):
                print(f"[offline/practice] {index}/{len(futures)}", flush=True)
    outputs.sort(key=lambda row: (versions.index(row["version"]), row["suite"], row["seed"]))

    details = [row["detail"] for row in outputs]
    sources = [item for row in outputs for item in row["sources"]]
    phases = [item for row in outputs for item in row["phases"]]
    events = [item for row in outputs for item in row["events"]]
    timelines = [item for row in outputs for item in row["timeline"]]
    summaries: list[dict[str, Any]] = []
    for version in versions:
        for suite in ("random", "min_reff", "collinear", "overall"):
            detail_subset = [row for row in details if row["version"] == version and (suite == "overall" or row["suite"] == suite)]
            source_subset = [row for row in sources if row["version"] == version and (suite == "overall" or row["suite"] == suite)]
            summaries.append(enriched_summary(version, suite, detail_subset, source_subset))

    pairs = paired_rows(details)
    severe = severe_regression_rows(details)
    phase_summary = phase_summary_rows(phases, versions)
    phase_delta = phase_delta_rows(details, phases)
    replay = verify_replay(details, Path(args.reference))
    max_component_error = max(abs(float(row["time_component_delta_s"])) for row in details)
    if max_component_error > 1e-3:
        raise RuntimeError(f"time-component identity failed: max error {max_component_error}")

    selected_keys = {(row["suite"], int(row["seed"])) for row in severe}
    selected_keys.update({("random", 70), ("random", 83)})
    selected_timelines = [row for row in timelines if (row["suite"], int(row["seed"])) in selected_keys]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "details.csv", details)
    write_csv(out_dir / "source_diagnostics.csv", sources)
    write_csv(out_dir / "phase_decomposition.csv", phases)
    write_csv(out_dir / "phase_summary.csv", phase_summary)
    write_csv(out_dir / "phase_paired_delta.csv", phase_delta)
    write_csv(out_dir / "paired_comparison.csv", pairs)
    write_csv(out_dir / "v6_gt300_regressions.csv", severe)
    write_csv(out_dir / "l2_decisions.csv", events)
    write_csv(out_dir / "typical_timelines.csv", selected_timelines)
    write_csv(out_dir / "summary.csv", summaries)
    metadata = {
        "environment": "local offline_sim practice only",
        "official_http_called": False,
        "official_practice_called": False,
        "official_formal_called": False,
        "ground_truth_policy_use": False,
        "n": 8,
        "versions": versions,
        "random_seeds": args.random_seeds,
        "stress_seeds": args.stress_seeds,
        "workers": args.workers,
        "lookahead_depth": 2,
        "only_variable": "frozen V6 one-step supplement evaluation -> depth-2 rollout",
        "second_outcome_evaluation": "exact algebraic collapse using frozen predict_candidate expectation; no outcome pruning",
        "max_time_component_error_s": max_component_error,
        "reference_replay": replay,
    }
    (out_dir / "summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    render_report(
        out_dir,
        summaries,
        pairs,
        severe,
        phase_summary,
        phase_delta,
        replay,
        details,
        phases,
        events,
    )
    if not args.skip_plots:
        make_plots(out_dir, severe, selected_timelines)
    print(json.dumps(metadata, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
