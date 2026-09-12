from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.case import generate_case, generate_stress_case
from offline_sim.harness import EpisodeResult, run_episode
from q3.offline_policy import policy_v4, theoretical_outer_radius, theoretical_route_length
from q3.planner import Q3BaselinePlanner
from q3.v6_policy import policy_v6
from scripts.run_way_benchmark import action_components, phase_rows


POLICIES: dict[str, Callable] = {
    "v4": policy_v4,
    "v6": policy_v6,
}


def parse_seed_range(text: str) -> list[int]:
    if ":" in text:
        start, end = text.split(":", 1)
        return list(range(int(start), int(end)))
    return [int(part) for part in text.split(",") if part.strip()]


def percentile(values: Iterable[float], q: float) -> float:
    data = sorted(float(v) for v in values)
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
    fields = list(rows[0].keys())
    extra = sorted({key for row in rows for key in row} - set(fields))
    fields.extend(extra)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def ring_row(n: int) -> dict[str, Any]:
    radius = theoretical_outer_radius(n)
    route_m = theoretical_route_length(n)
    points = n + 1
    full_measure_s = 20 * points * 5.0
    full_switch_s = 19 * points * 1.0
    return {
        "n": n,
        "outer_radius_m": radius,
        "outer_points": n,
        "search_points_total": points,
        "theoretical_outer_route_m": route_m,
        "theoretical_outer_route_time_s": route_m / 5.0,
        "full_unknown_scan_measure_time_s": full_measure_s,
        "full_unknown_scan_switch_time_s": full_switch_s,
        "full_unknown_scan_proxy_s": route_m / 5.0 + full_measure_s + full_switch_s,
        "formula": "a_n=1800*cos(pi/n)-sqrt(1000^2-1800^2*sin(pi/n)^2)",
    }


def build_case(suite: str, seed: int, field_kind: str, n: int):
    if suite == "random":
        return generate_case(seed=seed, problem=3, mode="practice", field_kind=field_kind)
    radius = theoretical_outer_radius(n)
    scan_points = [(p.x, p.y) for p in Q3BaselinePlanner.make_search_points(radius, n)]
    return generate_stress_case(
        suite,
        seed=seed,
        problem=3,
        mode="practice",
        field_kind=field_kind,
        scan_points=scan_points,
    )


def episode_row(
    version: str,
    n: int,
    suite: str,
    seed: int,
    result: EpisodeResult,
) -> dict[str, Any]:
    total = float(result.virtual_time_s)
    component_sum = (
        float(result.move_time_s)
        + float(result.measure_action_time_s)
        + float(result.channel_switch_time_s)
        + float(result.clear_action_time_s)
    )
    return {
        "version": version,
        "n": n,
        "suite": suite,
        "seed": seed,
        "success": int(result.success),
        "error": result.error or "",
        "cleared": int(result.cleared),
        "source_count": int(result.total),
        "total_time_s": total,
        "avg_source_time_s": total / int(result.total) if result.total else 0.0,
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
        "policy_cpu_time_s": float(result.policy_runtime_s),
        "time_component_sum_s": component_sum,
        "time_component_delta_s": total - component_sum,
        "finished_reason": result.finished_reason or "",
    }


def summarize_rows(version: str, n: int, suite: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    times = [float(row["total_time_s"]) for row in rows]
    avg_source = [float(row["avg_source_time_s"]) for row in rows]
    return {
        "version": version,
        "n": n,
        "suite": suite,
        "cases": len(rows),
        "success_rate": sum(int(row["success"]) for row in rows) / len(rows) if rows else 0.0,
        "clear_fail_total": sum(int(row["clear_fail"]) for row in rows),
        "error_count": sum(1 for row in rows if row["error"]),
        "mean_total_time_s": statistics.fmean(times) if times else 0.0,
        "median_total_time_s": statistics.median(times) if times else 0.0,
        "p95_total_time_s": percentile(times, 0.95),
        "max_total_time_s": max(times, default=0.0),
        "std_total_time_s": statistics.pstdev(times) if len(times) > 1 else 0.0,
        "mean_avg_source_time_s": statistics.fmean(avg_source) if avg_source else 0.0,
        "median_avg_source_time_s": statistics.median(avg_source) if avg_source else 0.0,
        "p95_avg_source_time_s": percentile(avg_source, 0.95),
        "max_avg_source_time_s": max(avg_source, default=0.0),
        "pooled_avg_source_time_s": (
            sum(times) / sum(int(row["source_count"]) for row in rows) if rows else 0.0
        ),
        "mean_source_count": statistics.fmean(int(row["source_count"]) for row in rows) if rows else 0.0,
        "mean_move_distance_m": statistics.fmean(float(row["move_distance_m"]) for row in rows) if rows else 0.0,
        "mean_move_time_s": statistics.fmean(float(row["move_time_s"]) for row in rows) if rows else 0.0,
        "mean_measure_count": statistics.fmean(int(row["measure_count"]) for row in rows) if rows else 0.0,
        "mean_switch_count": statistics.fmean(int(row["switch_count"]) for row in rows) if rows else 0.0,
        "mean_clear_count": statistics.fmean(int(row["clear_count"]) for row in rows) if rows else 0.0,
        "mean_policy_cpu_time_s": statistics.fmean(float(row["policy_cpu_time_s"]) for row in rows) if rows else 0.0,
        "p95_policy_cpu_time_s": percentile((float(row["policy_cpu_time_s"]) for row in rows), 0.95),
        "time_component_delta_abs_max_s": max((abs(float(row["time_component_delta_s"])) for row in rows), default=0.0),
    }


def source_count_rows(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    versions = sorted({str(row["version"]) for row in details})
    ns = sorted({int(row["n"]) for row in details})
    for version in versions:
        for n in ns:
            for count in range(10, 17):
                rows = [
                    row
                    for row in details
                    if row["version"] == version
                    and int(row["n"]) == n
                    and int(row["source_count"]) == count
                ]
                if not rows:
                    continue
                avg_source = [float(row["avg_source_time_s"]) for row in rows]
                output.append(
                    {
                        "version": version,
                        "n": n,
                        "source_count": count,
                        "case_count": len(rows),
                        "mean_total_time_s": statistics.fmean(float(row["total_time_s"]) for row in rows),
                        "mean_avg_source_time_s": statistics.fmean(avg_source),
                        "median_avg_source_time_s": statistics.median(avg_source),
                        "p95_avg_source_time_s": percentile(avg_source, 0.95),
                    }
                )
    return output


def phase_summary_rows(phases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    versions = sorted({str(row["version"]) for row in phases})
    ns = sorted({int(row["n"]) for row in phases})
    for version in versions:
        for n in ns:
            for suite in ("random", "min_reff", "collinear", "overall"):
                for phase in ("search", "found", "clear"):
                    rows = [
                        row
                        for row in phases
                        if row["version"] == version
                        and int(row["n"]) == n
                        and row["phase"] == phase
                        and (suite == "overall" or row["suite"] == suite)
                    ]
                    if not rows:
                        continue
                    output.append(
                        {
                            "version": version,
                            "n": n,
                            "suite": suite,
                            "phase": phase,
                            "cases": len(rows),
                            "mean_total_phase_time_s": statistics.fmean(
                                float(row["move_time_s"])
                                + float(row["measure_time_s"])
                                + float(row["switch_time_s"])
                                + float(row["clear_time_s"])
                                for row in rows
                            ),
                            "mean_move_time_s": statistics.fmean(float(row["move_time_s"]) for row in rows),
                            "mean_move_distance_m": statistics.fmean(float(row["move_distance_m"]) for row in rows),
                            "mean_measure_time_s": statistics.fmean(float(row["measure_time_s"]) for row in rows),
                            "mean_switch_time_s": statistics.fmean(float(row["switch_time_s"]) for row in rows),
                            "mean_clear_time_s": statistics.fmean(float(row["clear_time_s"]) for row in rows),
                            "mean_measure_count": statistics.fmean(int(row["measure_count"]) for row in rows),
                            "mean_clear_count": statistics.fmean(int(row["clear_count"]) for row in rows),
                        }
                    )
    return output


def paired_vs_n8_rows(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {
        (row["version"], int(row["n"]), row["suite"], int(row["seed"])): row
        for row in details
    }
    output: list[dict[str, Any]] = []
    for version in sorted({str(row["version"]) for row in details}):
        ns = sorted({int(row["n"]) for row in details if row["version"] == version})
        for n in ns:
            if n == 8:
                continue
            for suite in ("random", "min_reff", "collinear", "overall"):
                keys = sorted(
                    (row["suite"], int(row["seed"]))
                    for row in details
                    if row["version"] == version
                    and int(row["n"]) == 8
                    and (suite == "overall" or row["suite"] == suite)
                )
                pairs = [
                    (lookup[(version, 8, group, seed)], lookup[(version, n, group, seed)])
                    for group, seed in keys
                    if (version, n, group, seed) in lookup
                ]
                if not pairs:
                    continue
                total_deltas = [
                    float(right["total_time_s"]) - float(left["total_time_s"])
                    for left, right in pairs
                ]
                avg_deltas = [
                    float(right["avg_source_time_s"]) - float(left["avg_source_time_s"])
                    for left, right in pairs
                ]
                output.append(
                    {
                        "version": version,
                        "base_n": 8,
                        "target_n": n,
                        "suite": suite,
                        "pairs": len(pairs),
                        "target_win_rate_total": sum(delta < 0.0 for delta in total_deltas) / len(total_deltas),
                        "target_win_rate_avg_source": sum(delta < 0.0 for delta in avg_deltas) / len(avg_deltas),
                        "mean_delta_total_time_s": statistics.fmean(total_deltas),
                        "mean_delta_avg_source_time_s": statistics.fmean(avg_deltas),
                        "median_delta_total_time_s": statistics.median(total_deltas),
                        "median_delta_avg_source_time_s": statistics.median(avg_deltas),
                        "p95_delta_total_time_s": percentile(total_deltas, 0.95),
                        "p95_delta_avg_source_time_s": percentile(avg_deltas, 0.95),
                        "worst_regression_total_time_s": max(total_deltas),
                        "worst_regression_avg_source_time_s": max(avg_deltas),
                        "regression_over_300s_count": sum(delta > 300.0 for delta in total_deltas),
                    }
                )
    return output


def make_plots(out_dir: Path, summary: list[dict[str, Any]], by_count: list[dict[str, Any]], candidate: tuple[str, int]) -> None:
    plot_dir = out_dir / "figures"
    plot_dir.mkdir(parents=True, exist_ok=True)

    def svg_line_chart(
        path: Path,
        series: list[tuple[str, list[tuple[float, float]], str]],
        xlabel: str,
        ylabel: str,
        title: str,
    ) -> None:
        width, height = 760, 460
        left, right, top, bottom = 78, 30, 42, 70
        xs = [x for _, data, _ in series for x, _ in data]
        ys = [y for _, data, _ in series for _, y in data]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if math.isclose(ymin, ymax):
            ymin -= 1.0
            ymax += 1.0
        ypad = (ymax - ymin) * 0.08
        ymin -= ypad
        ymax += ypad

        def sx(x: float) -> float:
            return left + (x - xmin) / (xmax - xmin or 1.0) * (width - left - right)

        def sy(y: float) -> float:
            return top + (ymax - y) / (ymax - ymin or 1.0) * (height - top - bottom)

        tick_lines: list[str] = []
        for i in range(6):
            value = ymin + (ymax - ymin) * i / 5
            y = sy(value)
            tick_lines.append(
                f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}" stroke="#e5e7eb"/>'
            )
            tick_lines.append(
                f'<text x="{left-10}" y="{y+4:.2f}" text-anchor="end" font-size="12" fill="#374151">{value:.1f}</text>'
            )
        x_values = sorted(set(xs))
        for xval in x_values:
            x = sx(xval)
            tick_lines.append(
                f'<line x1="{x:.2f}" y1="{height-bottom}" x2="{x:.2f}" y2="{height-bottom+5}" stroke="#374151"/>'
            )
            tick_lines.append(
                f'<text x="{x:.2f}" y="{height-bottom+22}" text-anchor="middle" font-size="12" fill="#374151">{xval:g}</text>'
            )

        line_parts: list[str] = []
        legend_parts: list[str] = []
        for idx, (label, data, color) in enumerate(series):
            pts = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in data)
            line_parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>')
            for x, y in data:
                line_parts.append(f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="4" fill="{color}"/>')
            lx = left + idx * 120
            ly = height - 24
            legend_parts.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+24}" y2="{ly}" stroke="{color}" stroke-width="2.5"/>')
            legend_parts.append(f'<text x="{lx+32}" y="{ly+4}" font-size="13" fill="#111827">{label}</text>')

        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="white"/>
  <text x="{width/2}" y="24" text-anchor="middle" font-size="18" font-family="Arial, sans-serif" fill="#111827">{title}</text>
  {''.join(tick_lines)}
  <line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#374151"/>
  <line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#374151"/>
  {''.join(line_parts)}
  <text x="{width/2}" y="{height-38}" text-anchor="middle" font-size="14" font-family="Arial, sans-serif" fill="#111827">{xlabel}</text>
  <text x="22" y="{height/2}" text-anchor="middle" font-size="14" font-family="Arial, sans-serif" fill="#111827" transform="rotate(-90 22 {height/2})">{ylabel}</text>
  {''.join(legend_parts)}
</svg>
'''
        path.write_text(svg, encoding="utf-8")

    overall = [row for row in summary if row["suite"] == "overall"]
    series = []
    for version, marker in (("v4", "o"), ("v6", "s")):
        rows = sorted((row for row in overall if row["version"] == version), key=lambda row: int(row["n"]))
        color = "#d62728" if version == "v4" else "#1f77b4"
        series.append(
            (
                version.upper(),
                [(int(row["n"]), float(row["mean_avg_source_time_s"])) for row in rows],
                color,
            )
        )
    svg_line_chart(
        plot_dir / "mean_avg_source_vs_n.svg",
        series,
        "Outer search point count n",
        "Mean T/N (s/source)",
        "Q3 n Sweep: Mean Per-Source Time",
    )

    version, n = candidate
    rows = sorted(
        (
            row
            for row in by_count
            if row["version"] == version and int(row["n"]) == n
        ),
        key=lambda row: int(row["source_count"]),
    )
    svg_line_chart(
        plot_dir / "final_candidate_avg_source_by_count.svg",
        [
            (
                f"{version.upper()} n={n}",
                [(int(row["source_count"]), float(row["mean_avg_source_time_s"])) for row in rows],
                "#1f77b4",
            )
        ],
        "True source count",
        "Mean T/N (s/source)",
        "Final Candidate: Per-Source Time by Source Count",
    )


def markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str, str]], limit: int | None = None) -> str:
    subset = rows[:limit] if limit else rows
    header = "| " + " | ".join(label for _, label, _ in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, sep]
    for row in subset:
        vals = []
        for key, _, fmt in columns:
            value = row.get(key, "")
            if fmt == "i":
                vals.append(str(int(float(value))))
            elif fmt == "pct":
                vals.append(f"{100.0 * float(value):.1f}%")
            elif fmt:
                vals.append(format(float(value), fmt))
            else:
                vals.append(str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def best_n(summary: list[dict[str, Any]], version: str) -> dict[str, Any]:
    rows = [row for row in summary if row["version"] == version and row["suite"] == "overall"]
    return min(rows, key=lambda row: (float(row["mean_avg_source_time_s"]), float(row["p95_avg_source_time_s"])))


def render_report(
    out_dir: Path,
    ns: list[int],
    ring_rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    by_count: list[dict[str, Any]],
    paired: list[dict[str, Any]],
    phase_summary: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    v4_best = best_n(summary, "v4")
    v6_best = best_n(summary, "v6")
    final = v6_best if float(v6_best["mean_avg_source_time_s"]) <= float(v4_best["mean_avg_source_time_s"]) else v4_best
    final_version = str(final["version"])
    final_n = int(final["n"])
    lines: list[str] = []
    lines.extend(
        [
            "# Q3 Outer Search Point Count Sweep",
            "",
            "This is an offline_sim/practice-only single-variable experiment. The only changed variable is the number of uniformly spaced outer SEARCH points `n`; V4/V6 policy logic, UNKNOWN scanning, FOUND supplement logic, routing, `MEC <= 20m`, candidate generation/scoring, and the 16-source early stop rule are left unchanged.",
            "",
            f"Seeds: random `{metadata['random_seeds']}`, stress `{metadata['stress_seeds']}` for min_reff and collinear. Official HTTP/practice/formal endpoints were not called.",
            "",
            "Primary metric: per episode `T_i / N_i`, then averaged as `MeanAvgSource = mean_i(T_i / N_i)`. This is not `mean(T)/mean(N)`.",
            "",
            "## A. Design And Only Variable",
            "",
            f"Compared versions: `v4`, `v6`. Tested n values: {', '.join(str(n) for n in ns)}. Radius uses the theoretical formula exactly: `a_n = 1800*cos(pi/n) - sqrt(1000^2 - 1800^2*sin(pi/n)^2)`.",
            "",
            "The fixed scan proxy is `L_n/5 + 20*(n+1)*5 + 19*(n+1)`, i.e. all 20 channels at every SEARCH point with snake-like channel order. Actual policy time can be lower because FOUND channels leave UNKNOWN scanning and search can stop after 16 discovered sources.",
            "",
            "## B. Theoretical Search Structure",
            "",
            markdown_table(
                ring_rows,
                [
                    ("n", "n", "i"),
                    ("outer_radius_m", "a_n m", ".6f"),
                    ("theoretical_outer_route_m", "L_n m", ".2f"),
                    ("theoretical_outer_route_time_s", "L_n/5 s", ".2f"),
                    ("full_unknown_scan_proxy_s", "Full scan proxy s", ".2f"),
                ],
            ),
            "",
            "## C. V4 Summary By n",
            "",
            markdown_table(
                [row for row in summary if row["version"] == "v4" and row["suite"] == "overall"],
                [
                    ("n", "n", "i"),
                    ("success_rate", "ClearRate", "pct"),
                    ("clear_fail_total", "Clear fail", "i"),
                    ("mean_total_time_s", "Mean T", ".2f"),
                    ("median_total_time_s", "Median T", ".2f"),
                    ("p95_total_time_s", "P95 T", ".2f"),
                    ("max_total_time_s", "Max T", ".2f"),
                    ("mean_avg_source_time_s", "Mean T/N", ".2f"),
                    ("median_avg_source_time_s", "Median T/N", ".2f"),
                    ("p95_avg_source_time_s", "P95 T/N", ".2f"),
                    ("mean_move_distance_m", "Move m", ".2f"),
                    ("mean_measure_count", "Measure", ".2f"),
                    ("mean_switch_count", "Switch", ".2f"),
                    ("mean_policy_cpu_time_s", "CPU s", ".4f"),
                ],
            ),
            "",
            "## D. V6 Summary By n",
            "",
            markdown_table(
                [row for row in summary if row["version"] == "v6" and row["suite"] == "overall"],
                [
                    ("n", "n", "i"),
                    ("success_rate", "ClearRate", "pct"),
                    ("clear_fail_total", "Clear fail", "i"),
                    ("mean_total_time_s", "Mean T", ".2f"),
                    ("median_total_time_s", "Median T", ".2f"),
                    ("p95_total_time_s", "P95 T", ".2f"),
                    ("max_total_time_s", "Max T", ".2f"),
                    ("mean_avg_source_time_s", "Mean T/N", ".2f"),
                    ("median_avg_source_time_s", "Median T/N", ".2f"),
                    ("p95_avg_source_time_s", "P95 T/N", ".2f"),
                    ("mean_move_distance_m", "Move m", ".2f"),
                    ("mean_measure_count", "Measure", ".2f"),
                    ("mean_switch_count", "Switch", ".2f"),
                    ("mean_policy_cpu_time_s", "CPU s", ".4f"),
                ],
            ),
            "",
            "## E. Primary Mean(T/N) Comparison",
            "",
            f"Within the tested n range, V4 is best at n={int(v4_best['n'])} with Mean(T/N)={float(v4_best['mean_avg_source_time_s']):.2f}s/source. V6 is best at n={int(v6_best['n'])} with Mean(T/N)={float(v6_best['mean_avg_source_time_s']):.2f}s/source.",
            "",
            f"The best overall candidate within the tested n range is `{final_version}/n={final_n}` with Mean(T/N)={float(final['mean_avg_source_time_s']):.2f}s/source, mean total={float(final['mean_total_time_s']):.2f}s, P95(T/N)={float(final['p95_avg_source_time_s']):.2f}s/source, max total={float(final['max_total_time_s']):.2f}s.",
            "",
            "![Mean T/N vs n](figures/mean_avg_source_vs_n.svg)",
            "",
            "## F. Source Count Groups",
            "",
            f"Final candidate source-count curve: `{final_version}/n={final_n}`.",
            "",
            markdown_table(
                [row for row in by_count if row["version"] == final_version and int(row["n"]) == final_n],
                [
                    ("source_count", "N", "i"),
                    ("case_count", "Cases", "i"),
                    ("mean_total_time_s", "Mean T", ".2f"),
                    ("mean_avg_source_time_s", "Mean T/N", ".2f"),
                    ("median_avg_source_time_s", "Median T/N", ".2f"),
                    ("p95_avg_source_time_s", "P95 T/N", ".2f"),
                ],
            ),
            "",
            "![Final candidate T/N by source count](figures/final_candidate_avg_source_by_count.svg)",
            "",
            "The grouped T/N trend need not be strictly monotone: fixed SEARCH cost is amortized over more sources, while the 16-source early stop can shorten UNKNOWN scanning when many true channels are discovered early.",
            "",
            "Full version x n x source-count grouped table:",
            "",
            markdown_table(
                by_count,
                [
                    ("version", "Version", ""),
                    ("n", "n", "i"),
                    ("source_count", "N", "i"),
                    ("case_count", "Cases", "i"),
                    ("mean_total_time_s", "Mean T", ".2f"),
                    ("mean_avg_source_time_s", "Mean T/N", ".2f"),
                    ("median_avg_source_time_s", "Median T/N", ".2f"),
                    ("p95_avg_source_time_s", "P95 T/N", ".2f"),
                ],
            ),
            "",
            "## G. Same-Seed Paired Comparison vs n=8",
            "",
            markdown_table(
                [row for row in paired if row["suite"] == "overall"],
                [
                    ("version", "Version", ""),
                    ("target_n", "n", "i"),
                    ("target_win_rate_avg_source", "Win T/N", "pct"),
                    ("mean_delta_total_time_s", "Mean dT", ".2f"),
                    ("mean_delta_avg_source_time_s", "Mean dT/N", ".2f"),
                    ("median_delta_avg_source_time_s", "Median dT/N", ".2f"),
                    ("p95_delta_avg_source_time_s", "P95 dT/N", ".2f"),
                    ("worst_regression_total_time_s", "Worst dT", ".2f"),
                    ("regression_over_300s_count", ">300s", "i"),
                ],
            ),
            "",
            "## H. Phase Effects",
            "",
            markdown_table(
                [
                    row
                    for row in phase_summary
                    if row["suite"] == "overall" and row["phase"] in {"search", "found", "clear"}
                ],
                [
                    ("version", "Version", ""),
                    ("n", "n", "i"),
                    ("phase", "Phase", ""),
                    ("mean_total_phase_time_s", "Mean phase s", ".2f"),
                    ("mean_move_time_s", "Move s", ".2f"),
                    ("mean_measure_time_s", "Measure s", ".2f"),
                    ("mean_switch_time_s", "Switch s", ".2f"),
                    ("mean_clear_time_s", "Clear s", ".2f"),
                ],
            ),
            "",
            "## I/J/K. Best n And Recommendation",
            "",
            f"- V4 best n within the tested range: `n={int(v4_best['n'])}` by Mean(T/N).",
            f"- V6 best n within the tested range: `n={int(v6_best['n'])}` by Mean(T/N).",
            f"- Recommended Q3 candidate within the tested n range: `{final_version}/n={final_n}`.",
            "",
            "This is an empirical offline_sim conclusion over the tested n range, not a mathematical global optimum.",
            "",
            "## L. Can Q3 Algorithm Development End?",
            "",
        ]
    )
    if final_version == "v6" and final_n == 8:
        lines.append("Yes: this sweep supports keeping the existing frozen V6/n=8 as the final offline candidate, because changing only n did not produce a better tested configuration under the primary Mean(T/N) metric and tail checks.")
    else:
        lines.append("The n sweep identifies a better tested configuration than the prior V6/n=8 under the primary metric. Before ending Q3 development, freeze this exact configuration and replay the official practice-only harness; do not add new algorithm variables.")

    report = "\n".join(lines) + "\n"
    (out_dir / "report.md").write_text(report, encoding="utf-8")


def run_for_n_values(
    versions: list[str],
    ns: list[int],
    suites: list[tuple[str, list[int], str]],
    out_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    details: list[dict[str, Any]] = []
    phases: list[dict[str, Any]] = []
    for n in ns:
        for version in versions:
            policy = POLICIES[version]
            for suite, seeds, field_kind in suites:
                for index, seed in enumerate(seeds, start=1):
                    case = build_case(suite, seed, field_kind, n)
                    result = run_episode(case, lambda runner, p=policy, nn=n: p(runner, n=nn), include_oracles=False)
                    details.append(episode_row(version, n, suite, seed, result))
                    for row in phase_rows(version, suite, seed, result):
                        row["n"] = n
                        phases.append(row)
                    if index % 25 == 0 or index == len(seeds):
                        print(f"[{version}/n={n}/{suite}] {index}/{len(seeds)}")
    return details, phases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Q3 offline-only single-variable outer-ring n sweep.")
    parser.add_argument("--versions", default="v4,v6")
    parser.add_argument("--rings", default="6,7,8,9,10,11,12")
    parser.add_argument("--random-seeds", default="0:100")
    parser.add_argument("--stress-seeds", default="10000:10050")
    parser.add_argument("--out-dir", default="results/offline_eval_ring_count_200")
    parser.add_argument("--auto-extend-boundary", action="store_true")
    parser.add_argument("--max-n", type=int, default=18)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    versions = [value.strip() for value in args.versions.split(",") if value.strip()]
    for version in versions:
        if version not in POLICIES:
            raise SystemExit(f"unknown version {version!r}; available={sorted(POLICIES)}")
    ns = sorted({int(value.strip()) for value in args.rings.split(",") if value.strip()})
    random_seeds = parse_seed_range(args.random_seeds)
    stress_seeds = parse_seed_range(args.stress_seeds)
    suites = [
        ("random", random_seeds, "smooth"),
        ("min_reff", stress_seeds, "adversarial"),
        ("collinear", stress_seeds, "adversarial"),
    ]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    details, phases = run_for_n_values(versions, ns, suites, out_dir)
    completed_ns = set(ns)

    while args.auto_extend_boundary:
        summary_tmp: list[dict[str, Any]] = []
        for version in versions:
            for n in sorted(completed_ns):
                rows = [row for row in details if row["version"] == version and int(row["n"]) == n]
                summary_tmp.append(summarize_rows(version, n, "overall", rows))
        boundary_is_best = False
        current_max = max(completed_ns)
        for version in versions:
            row = best_n(summary_tmp, version)
            if int(row["n"]) == current_max:
                boundary_is_best = True
        if not boundary_is_best or current_max >= args.max_n:
            break
        next_n = current_max + 1
        print(f"Boundary n={current_max} is still best for at least one version; extending to n={next_n}.")
        more_details, more_phases = run_for_n_values(versions, [next_n], suites, out_dir)
        details.extend(more_details)
        phases.extend(more_phases)
        completed_ns.add(next_n)

    ns = sorted(completed_ns)
    ring_rows = [ring_row(n) for n in ns]
    summary: list[dict[str, Any]] = []
    for version in versions:
        for n in ns:
            for suite in ("random", "min_reff", "collinear", "overall"):
                rows = [
                    row
                    for row in details
                    if row["version"] == version
                    and int(row["n"]) == n
                    and (suite == "overall" or row["suite"] == suite)
                ]
                summary.append(summarize_rows(version, n, suite, rows))
    by_count = source_count_rows(details)
    phase_summary = phase_summary_rows(phases)
    paired = paired_vs_n8_rows(details)
    v6_best = best_n(summary, "v6")
    v4_best = best_n(summary, "v4")
    final = v6_best if float(v6_best["mean_avg_source_time_s"]) <= float(v4_best["mean_avg_source_time_s"]) else v4_best
    metadata = {
        "environment": "local offline_sim practice only",
        "official_http_called": False,
        "official_formal_test_run": False,
        "only_variable": "number of uniformly spaced outer SEARCH points n",
        "versions": versions,
        "rings": ns,
        "random_seeds": args.random_seeds,
        "stress_seeds": args.stress_seeds,
        "suites": ["random", "min_reff", "collinear"],
        "oracle_benchmarks_enabled": False,
        "primary_metric": "mean_i(total_time_i / true_source_count_i)",
        "time_identity_abs_max_s": max((abs(float(row["time_component_delta_s"])) for row in details), default=0.0),
    }

    write_csv(out_dir / "details.csv", details)
    write_csv(out_dir / "phase_decomposition.csv", phases)
    write_csv(out_dir / "ring_theory.csv", ring_rows)
    write_csv(out_dir / "summary.csv", summary)
    write_csv(out_dir / "source_count_summary.csv", by_count)
    write_csv(out_dir / "phase_summary.csv", phase_summary)
    write_csv(out_dir / "paired_vs_n8.csv", paired)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    make_plots(out_dir, summary, by_count, (str(final["version"]), int(final["n"])))
    render_report(out_dir, ns, ring_rows, summary, by_count, paired, phase_summary, metadata)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    print(f"wrote {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
