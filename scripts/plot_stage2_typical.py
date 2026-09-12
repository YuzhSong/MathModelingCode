from __future__ import annotations

import csv
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib as mpl
import matplotlib.pyplot as plt

from offline_sim.harness import EpisodeResult, run_episode
from q3.offline_policy import theoretical_outer_radius
from q3.planner import Q3BaselinePlanner
from q3.stage2_policy import make_policy_m2, policy_n1
from q3.v5_policy import policy_v4_diagnostic
from q3.v6_policy import policy_v6
from scripts.run_v5_eval import write_csv
from scripts.run_way_benchmark import action_components, make_case


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = ROOT / "results/offline_eval_stage2_analysis"
POLICIES: dict[str, Callable] = {
    "v4": policy_v4_diagnostic,
    "v6": policy_v6,
    "m2_b0p1": make_policy_m2(0.10),
    "n1": policy_n1,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def classify_actions(result: EpisodeResult) -> list[dict[str, Any]]:
    found: set[int] = set()
    supplement_number: Counter[int] = Counter()
    rows: list[dict[str, Any]] = []
    for action in action_components(result.action_log):
        channel = int(action["channel"])
        event = action["action"].upper()
        if action["action"] == "measure":
            if channel in found:
                supplement_number[channel] += 1
                event = f"SUPPLEMENT_{supplement_number[channel]}"
            elif action["result"] in {"direction", "near"}:
                found.add(channel)
                event = "FIRST_FOUND"
            else:
                event = "SEARCH_MEASURE"
        elif action["action"] == "clear":
            event = "CLEAR"
        rows.append({**action, "event": event})
    return rows


def focus_channel(rows: list[dict[str, Any]]) -> tuple[int | None, int | None, int | None]:
    first: dict[int, int] = {}
    clear: dict[int, int] = {}
    for index, row in enumerate(rows):
        channel = int(row["channel"])
        if row["event"] == "FIRST_FOUND":
            first.setdefault(channel, index)
        if row["event"] == "CLEAR" and row["result"] == "success":
            clear.setdefault(channel, index)
    complete = [
        (clear[channel] - found_index, channel, found_index, clear[channel])
        for channel, found_index in first.items()
        if channel in clear
    ]
    if not complete:
        return None, None, None
    _, channel, start, stop = max(complete)
    return channel, start, stop


def run_cases(
    cases: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str, int], tuple[Any, EpisodeResult, list[dict[str, Any]]]]]:
    timelines: list[dict[str, Any]] = []
    results: dict[tuple[str, str, int], tuple[Any, EpisodeResult, list[dict[str, Any]]]] = {}
    for case_row in cases:
        suite = case_row["suite"]
        seed = int(case_row["seed"])
        for version in (case_row["base"], case_row["target"]):
            key = (version, suite, seed)
            if key in results:
                continue
            field_kind = "smooth" if suite == "random" else "adversarial"
            case = make_case(suite, seed, field_kind)
            policy = POLICIES[version]
            result = run_episode(
                case,
                lambda runner, selected=policy: selected(runner, n=8),
                include_oracles=False,
            )
            rows = classify_actions(result)
            results[key] = (case, result, rows)
            for row in rows:
                timelines.append(
                    {
                        "version": version,
                        "suite": suite,
                        "seed": seed,
                        "index": row["index"],
                        "time_s": row["virtual_time_s"],
                        "phase": row["phase"],
                        "event": row["event"],
                        "channel": row["channel"],
                        "x": row["x"],
                        "y": row["y"],
                        "result": row["result"],
                        "svd_deg": row["svd_deg"],
                        "move_m": row["move_m"],
                    }
                )
    return timelines, results


def setup_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 7,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "axes.linewidth": 0.8,
            "legend.frameon": False,
        }
    )


def plot_panel(
    ax: Any,
    case: Any,
    result: EpisodeResult,
    rows: list[dict[str, Any]],
    version: str,
) -> None:
    path_x = [0.0] + [float(row["x"]) for row in rows]
    path_y = [0.0] + [float(row["y"]) for row in rows]
    ax.plot(path_x, path_y, color="#7B8794", linewidth=0.65, alpha=0.75, zorder=1)

    channel, start, stop = focus_channel(rows)
    if start is not None and stop is not None:
        focus = rows[start : stop + 1]
        focus_x = [float(rows[start - 1]["x"]) if start else 0.0] + [
            float(row["x"]) for row in focus
        ]
        focus_y = [float(rows[start - 1]["y"]) if start else 0.0] + [
            float(row["y"]) for row in focus
        ]
        ax.plot(
            focus_x,
            focus_y,
            color="#8E44AD",
            linewidth=1.35,
            alpha=0.75,
            label=f"Longest FOUND-clear segment (ch {channel})",
            zorder=2,
        )

    radius = theoretical_outer_radius(8)
    search_points = Q3BaselinePlanner.make_search_points(radius, 8)
    ax.scatter(
        [point.x for point in search_points],
        [point.y for point in search_points],
        s=14,
        marker="D",
        facecolors="white",
        edgecolors="#2F3E46",
        linewidths=0.7,
        label="Fixed search point",
        zorder=3,
    )

    sources = [(float(source.x), float(source.y), int(source.channel)) for source in case.jammers]
    ax.scatter(
        [x for x, _, _ in sources],
        [y for _, y, _ in sources],
        s=20,
        marker="*",
        color="#C0392B",
        label="True source",
        zorder=5,
    )
    for x, y, source_channel in sources:
        ax.text(x + 18.0, y + 18.0, str(source_channel), fontsize=5.2, color="#8E2B20")

    first_found = [
        (float(row["x"]), float(row["y"]))
        for row in rows
        if row["event"] == "FIRST_FOUND"
    ]
    supplements = [
        (float(row["x"]), float(row["y"]))
        for row in rows
        if str(row["event"]).startswith("SUPPLEMENT")
    ]
    clears = [
        (float(row["x"]), float(row["y"]))
        for row in rows
        if row["event"] == "CLEAR" and row["result"] == "success"
    ]
    if first_found:
        ax.scatter(
            *zip(*first_found),
            s=17,
            marker="o",
            facecolors="none",
            edgecolors="#146C94",
            linewidths=0.8,
            label="First found",
            zorder=4,
        )
    if supplements:
        ax.scatter(
            *zip(*supplements),
            s=12,
            marker="x",
            color="#E67E22",
            linewidths=0.8,
            label="Supplement",
            zorder=4,
        )
    if clears:
        ax.scatter(
            *zip(*clears),
            s=14,
            marker="s",
            color="#2E8B57",
            label="Clear",
            zorder=4,
        )

    theta = [2.0 * math.pi * index / 240 for index in range(241)]
    ax.plot(
        [1800.0 * math.cos(value) for value in theta],
        [1800.0 * math.sin(value) for value in theta],
        color="#B8B8B8",
        linewidth=0.6,
        linestyle="--",
    )
    ax.set_aspect("equal")
    ax.set_title(f"{version}: {result.virtual_time_s:.1f}s, {result.move_distance_m:.0f}m")
    ax.set_xlabel("x (m)")
    ax.grid(color="#E6E8EB", linewidth=0.45, alpha=0.8)


def main() -> int:
    setup_style()
    cases = read_csv(ANALYSIS_DIR / "typical_cases.csv")
    timelines, results = run_cases(cases)
    figure_dir = ANALYSIS_DIR / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    for case_row in cases:
        suite = case_row["suite"]
        seed = int(case_row["seed"])
        versions = [case_row["base"], case_row["target"]]
        fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.55), sharex=True, sharey=True)
        for ax, version in zip(axes, versions):
            case, result, rows = results[(version, suite, seed)]
            expected = float(
                case_row["base_time_s"] if version == case_row["base"] else case_row["target_time_s"]
            )
            if abs(result.virtual_time_s - expected) > 1e-6:
                raise RuntimeError(
                    f"typical replay mismatch for {version}/{suite}/{seed}: "
                    f"{result.virtual_time_s} != {expected}"
                )
            plot_panel(ax, case, result, rows, version)
        axes[0].set_ylabel("y (m)")
        handles, labels = axes[1].get_legend_handles_labels()
        unique = dict(zip(labels, handles))
        fig.legend(
            unique.values(),
            unique.keys(),
            loc="lower center",
            ncol=3,
            bbox_to_anchor=(0.5, -0.015),
        )
        delta = float(case_row["delta_time_s"])
        fig.suptitle(
            f"{case_row['label']} | {suite} seed {seed} | target-base {delta:+.1f}s",
            fontsize=8,
        )
        fig.tight_layout(rect=(0.0, 0.07, 1.0, 0.94))
        stem = f"{case_row['label']}_{suite}_{seed}"
        fig.savefig(figure_dir / f"{stem}.svg", bbox_inches="tight")
        fig.savefig(figure_dir / f"{stem}.pdf", bbox_inches="tight")
        fig.savefig(figure_dir / f"{stem}.png", dpi=600, bbox_inches="tight")
        fig.savefig(figure_dir / f"{stem}.tiff", dpi=600, bbox_inches="tight")
        plt.close(fig)

    write_csv(ANALYSIS_DIR / "typical_timelines.csv", timelines)
    print(figure_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
