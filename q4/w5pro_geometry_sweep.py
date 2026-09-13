"""Reproducible constrained geometry sweep for W5Pro (production stays frozen)."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from q4.w5_geometry import W5GeometrySpec, analytic_geometry_checks


def constrained_sweep(sides: Iterable[float], extensions: Iterable[float]) -> list[dict]:
    rows = []
    for side in sides:
        for extension in extensions:
            spec = W5GeometrySpec(float(side), float(extension))
            checks = analytic_geometry_checks(spec)
            rows.append({"side_m": spec.side_m, "cap_extension_m": spec.cap_extension_m,
                         "analytical_pass": checks["analytical_pass"],
                         "side_margin_m": spec.receive_radius_m - spec.side_m,
                         "cap_side_support_margin_m": checks["cap_side_support_margin_m"]})
    return rows


def write_sweep(path: Path, sides: Iterable[float], extensions: Iterable[float]) -> list[dict]:
    rows = constrained_sweep(sides, extensions)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else
                                ["side_m", "cap_extension_m", "analytical_pass",
                                 "side_margin_m", "cap_side_support_margin_m"])
        writer.writeheader()
        writer.writerows(rows)
    return rows
