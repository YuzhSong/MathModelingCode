from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from q4.geometry import TriangularGridSpec, verify_detection_geometry


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_floats(spec: str) -> list[float]:
    return [float(part) for part in spec.split(",") if part.strip()]


def parse_offsets(spec: str) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for part in spec.split(";"):
        if not part.strip():
            continue
        a, b = part.split(",", 1)
        out.append((float(a), float(b)))
    return out


def render_report(out_dir: Path, rows: list[dict[str, Any]], selected: dict[str, Any]) -> None:
    def fmt(value: Any, digits: int = 2) -> str:
        if isinstance(value, float):
            return f"{value:.{digits}f}"
        return str(value)

    top = sorted(rows, key=lambda r: (int(r["misses"]), int(r["point_count"]), float(r["route_length_m"])))[:15]
    lines = [
        "# Q4 W1 triangular detection geometry scan",
        "",
        "The validation target is directional-source discovery, not routing optimization. A source is counted as covered when at least one candidate detector point is both within 1000m and inside the source's 180 degree effective half-plane.",
        "",
        "Sufficient condition used for design: if every source lies inside the convex hull of candidate detector points within 1000m, then every half-plane through the source contains at least one such detector point. A conservative equilateral triangular lattice with side `s <= 1000m` satisfies this inside each lattice triangle, because every point in a triangle is at most one side length from each of its three vertices. The grid is expanded outside the 1800m arena.",
        "",
        "## Selected baseline geometry",
        "",
        f"- side_m: `{fmt(selected['side_m'])}`",
        f"- rotation_deg: `{fmt(selected['rotation_deg'])}`",
        f"- offset_u / offset_v: `{fmt(selected['offset_u'])}` / `{fmt(selected['offset_v'])}`",
        f"- point_count: `{selected['point_count']}`",
        f"- crop_radius_m: `{fmt(selected['crop_radius_m'])}`",
        f"- theoretical triangle circumradius: `{fmt(selected['theoretical_circumradius_m'])}` m",
        f"- scan miss_rate: `{float(selected['miss_rate']):.6g}` over `{selected['probe_count']}` probes",
        f"- max visible distance: `{fmt(selected['max_visible_distance_m'])}` m",
        f"- worst distance margin: `{fmt(selected['worst_distance_margin_m'])}` m",
        "",
        "## Top candidates",
        "",
        "| side | rot | off_u | off_v | points | route m | misses | miss rate | max visible d | worst margin |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in top:
        lines.append(
            "| "
            + " | ".join(
                [
                    fmt(float(row["side_m"])),
                    fmt(float(row["rotation_deg"])),
                    fmt(float(row["offset_u"])),
                    fmt(float(row["offset_v"])),
                    str(row["point_count"]),
                    fmt(float(row["route_length_m"])),
                    str(row["misses"]),
                    f"{float(row['miss_rate']):.6g}",
                    fmt(float(row["max_visible_distance_m"])),
                    fmt(float(row["worst_distance_margin_m"])),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
        "Interpretation: all zero-miss candidates in this table passed the random and adversarial probe suite. The selected W1 geometry uses the largest tested conservative side with zero misses unless a smaller route with the same point count is available.",
        ]
    )
    (out_dir / "geometry_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan Q4 W1 triangular detection grids")
    parser.add_argument("--sides", default="800,900,950,1000,1050,1100,1200")
    parser.add_argument("--rotations", default="0,10,20,30")
    parser.add_argument("--offsets", default="0,0;0.3333333333,0.3333333333;0.5,0;0,0.5;0.5,0.5")
    parser.add_argument("--random-samples", type=int, default=20000)
    parser.add_argument("--out-dir", default="results/q4/w1_geometry")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for side in parse_floats(args.sides):
        for rotation in parse_floats(args.rotations):
            for offset_u, offset_v in parse_offsets(args.offsets):
                spec = TriangularGridSpec(side_m=side, rotation_deg=rotation, offset_u=offset_u, offset_v=offset_v)
                row = verify_detection_geometry(spec, random_samples=args.random_samples)
                rows.append(row)
                print(
                    f"side={side:.0f} rot={rotation:.0f} off=({offset_u:.3f},{offset_v:.3f}) "
                    f"points={row['point_count']} misses={row['misses']} route={row['route_length_m']:.1f}",
                    flush=True,
                )
    rows.sort(key=lambda r: (int(r["misses"]), int(r["point_count"]), float(r["route_length_m"])))
    selected = next(row for row in rows if int(row["misses"]) == 0)
    write_csv(out_dir / "geometry_scan.csv", rows)
    (out_dir / "selected_geometry.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    render_report(out_dir, rows, selected)
    print(f"selected: side={selected['side_m']}, rot={selected['rotation_deg']}, points={selected['point_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
