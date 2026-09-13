"""Acceptance metrics for W5Pro experiments."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import fmean


CORE_FIELDS = ("clear_ratio", "mean_localization_clear_time_s", "total_localization_clear_time_s")
DIAGNOSTIC_FIELDS = ("nbv_selected_count", "nbv_effective_count", "intersection_selected_count",
                     "spatial_stop_selected_count", "information_ridge_selected_count",
                     "wait_for_route_success_count", "legacy_backbone_fallback_count",
                     "w3_coarse_fallback_count", "w2_fallback_count", "tail_rescue_count")


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def summarize_sources(source_rows: list[dict[str, str]], detail_rows: list[dict[str, str]] | None = None) -> dict[str, object]:
    """Compute the two core metrics from per-source and per-episode evidence."""
    total = len(source_rows)
    cleared = [r for r in source_rows if str(r.get("cleared", "0")) in {"1", "True", "true"}]
    times = [float(r["found_to_clear_s"]) for r in cleared if r.get("found_to_clear_s") not in (None, "")]
    # Episode total_time_s includes movement, switching, sensing, localization,
    # and clear dwell; this is the requested drill-test denominator.
    details = detail_rows or []
    episode_time = sum(float(r["total_time_s"]) for r in details)
    return {
        "source_total": total,
        "source_cleared": len(cleared),
        "clear_ratio": len(cleared) / total if total else 0.0,
        "total_localization_clear_time_s": sum(times),
        "mean_localization_clear_time_s": fmean(times) if times else None,
        "episode_total_time_s": episode_time,
        "episode_time_per_cleared_source_s": episode_time / len(cleared) if cleared else None,
    }


def summarize_directory(directory: str | Path) -> dict[str, dict[str, object]]:
    directory = Path(directory)
    details = _read(directory / "details.csv")
    source_path = directory / "source_tail.csv"
    if not source_path.exists():
        source_path = directory / "source_local.csv"
    sources = _read(source_path)
    versions = sorted({r["version"] for r in details} | {r["strategy"] for r in sources})
    return {version: summarize_sources([r for r in sources if r["strategy"] == version],
                                       [r for r in details if r["version"] == version])
            for version in versions}


def write_metrics(directory: str | Path, output: str | Path | None = None) -> Path:
    result = summarize_directory(directory)
    target = Path(output) if output else Path(directory) / "core_metrics.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
