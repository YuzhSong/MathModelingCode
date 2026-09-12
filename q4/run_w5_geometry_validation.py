from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Iterable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from q3.models import Point
from q3.routing import optimize_open_point_route
from q4.w5_geometry import (
    ARENA_RADIUS_M,
    MIN_RECEIVE_RADIUS_M,
    W5GeometrySpec,
    analytic_geometry_checks,
    fixed_skeleton_minimum_argument,
    w5_detection_points,
)


NUMERIC_EPS_DEG = 1e-8


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    seen = set(fields)
    for row in rows[1:]:
        for field in row:
            if field not in seen:
                fields.append(field)
                seen.add(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def random_disk_points(count: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    radius = ARENA_RADIUS_M * np.sqrt(rng.random(count))
    angle = 2.0 * math.pi * rng.random(count)
    return np.column_stack((radius * np.cos(angle), radius * np.sin(angle)))


def boundary_points(count: int = 21_600) -> np.ndarray:
    angle = np.linspace(0.0, 2.0 * math.pi, count, endpoint=False)
    return np.column_stack((ARENA_RADIUS_M * np.cos(angle), ARENA_RADIUS_M * np.sin(angle)))


def dense_cap_points(spec: W5GeometrySpec, step_m: float) -> np.ndarray:
    """Sample all six circular caps outside the 19-point hexagon."""

    rows: list[np.ndarray] = []
    x_values = np.arange(spec.apothem_m, ARENA_RADIUS_M + step_m * 0.5, step_m)
    for x in x_values:
        y_limit = math.sqrt(max(0.0, ARENA_RADIUS_M**2 - x**2))
        y_values = np.arange(-y_limit, y_limit + step_m * 0.5, step_m)
        local = np.column_stack((np.full(len(y_values), x), y_values))
        for cap in range(6):
            angle = math.radians(30.0 + 60.0 * cap)
            c, s = math.cos(angle), math.sin(angle)
            rows.append(np.column_stack((local[:, 0] * c - local[:, 1] * s, local[:, 0] * s + local[:, 1] * c)))
    return np.concatenate(rows, axis=0) if rows else np.empty((0, 2))


def cell_boundary_points(spec: W5GeometrySpec, per_edge: int = 101) -> np.ndarray:
    points = w5_detection_points(spec)[:19]
    rows: list[tuple[float, float]] = []
    for left_index, left in enumerate(points):
        for right in points[left_index + 1 :]:
            if abs(math.hypot(left.x - right.x, left.y - right.y) - spec.side_m) > 1e-6:
                continue
            for fraction in np.linspace(0.0, 1.0, per_edge):
                x = left.x + float(fraction) * (right.x - left.x)
                y = left.y + float(fraction) * (right.y - left.y)
                if math.hypot(x, y) <= ARENA_RADIUS_M + 1e-9:
                    rows.append((x, y))
    return np.asarray(rows, dtype=float)


def evaluate_sources(
    spec: W5GeometrySpec,
    source_batches: Iterable[tuple[str, np.ndarray]],
    *,
    direction_seed: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    detectors = np.asarray([(point.x, point.y) for point in w5_detection_points(spec)], dtype=float)
    rng = np.random.default_rng(direction_seed)
    misses = 0
    angular_misses = 0
    sampled_direction_misses = 0
    probe_count = 0
    worst_gap = -1.0
    worst_gap_record: dict[str, Any] = {}
    max_visible_distance = 0.0
    worst_visible_record: dict[str, Any] = {}
    min_nearby = 99

    for probe_kind, sources in source_batches:
        for start in range(0, len(sources), 4096):
            batch = sources[start : start + 4096]
            vectors = detectors[None, :, :] - batch[:, None, :]
            distances_sq = np.sum(vectors * vectors, axis=2)
            directions = rng.uniform(0.0, 2.0 * math.pi, len(batch))
            for index, source in enumerate(batch):
                probe_count += 1
                source_missed = False
                within = distances_sq[index] <= MIN_RECEIVE_RADIUS_M**2 + 1e-7
                nearby_count = int(np.count_nonzero(within))
                min_nearby = min(min_nearby, nearby_count)
                if np.any(distances_sq[index] < 1e-14):
                    gap_deg = 0.0
                else:
                    angles = np.sort(np.arctan2(vectors[index, within, 1], vectors[index, within, 0]))
                    if len(angles) < 2:
                        gap_deg = 360.0
                    else:
                        gap = max(float(np.max(np.diff(angles))), float(angles[0] + 2.0 * math.pi - angles[-1]))
                        gap_deg = math.degrees(gap)
                if gap_deg > worst_gap:
                    worst_gap = gap_deg
                    worst_gap_record = {
                        "record": "worst_angular_gap",
                        "probe_kind": probe_kind,
                        "source_x": float(source[0]),
                        "source_y": float(source[1]),
                        "source_radius_m": float(math.hypot(*source)),
                        "max_angular_gap_deg": gap_deg,
                        "nearby_detector_count": nearby_count,
                    }
                if gap_deg > 180.0 + NUMERIC_EPS_DEG:
                    angular_misses += 1
                    source_missed = True

                unit = np.array((math.cos(float(directions[index])), math.sin(float(directions[index]))))
                visible = within & ((vectors[index] @ unit) >= -1e-9)
                if np.any(visible):
                    nearest_visible = math.sqrt(float(np.min(distances_sq[index, visible])))
                    if nearest_visible > max_visible_distance:
                        max_visible_distance = nearest_visible
                        worst_visible_record = {
                            "record": "worst_sampled_visible_distance",
                            "probe_kind": probe_kind,
                            "source_x": float(source[0]),
                            "source_y": float(source[1]),
                            "source_radius_m": float(math.hypot(*source)),
                            "direction_deg": math.degrees(float(directions[index])),
                            "visible_distance_m": nearest_visible,
                        }
                else:
                    sampled_direction_misses += 1
                    source_missed = True
                misses += int(source_missed)

    route = optimize_open_point_route(Point(0.0, 0.0), w5_detection_points(spec))
    metrics = {
        "side_m": spec.side_m,
        "cap_extension_m": spec.cap_extension_m,
        "supplement_radius_m": spec.supplement_radius_m,
        "point_count": 25,
        "probe_count": probe_count,
        "misses": misses,
        "angular_misses": angular_misses,
        "sampled_direction_misses": sampled_direction_misses,
        "miss_rate": misses / probe_count if probe_count else 0.0,
        "worst_angular_gap_deg": worst_gap,
        "angular_safety_margin_deg": 180.0 - worst_gap,
        "minimum_nearby_detector_count": min_nearby,
        "max_sampled_visible_distance_m": max_visible_distance,
        "distance_safety_margin_m": MIN_RECEIVE_RADIUS_M - max_visible_distance,
        "open_route_proxy_m": route.length_m,
        "open_route_method": route.method,
    }
    return metrics, [worst_gap_record, worst_visible_record]


def scan_specs(samples: np.ndarray, cap_step_m: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = [
        (960.0, 180.0), (970.0, 140.0), (970.0, 180.0),
        (980.0, 120.0), (980.0, 160.0), (990.0, 100.0),
        (990.0, 120.0), (990.0, 160.0), (990.0, 200.0),
        (995.0, 100.0), (997.0, 80.0),
    ]
    rows: list[dict[str, Any]] = []
    worst: list[dict[str, Any]] = []
    for index, (side, extension) in enumerate(candidates):
        spec = W5GeometrySpec(side, extension)
        analytic = analytic_geometry_checks(spec)
        batches = (
            ("scan_random", samples),
            ("scan_boundary", boundary_points(3600)),
            ("scan_caps", dense_cap_points(spec, cap_step_m)),
            ("cell_boundaries", cell_boundary_points(spec, 31)),
        )
        numeric, records = evaluate_sources(spec, batches, direction_seed=9000 + index)
        row = {**analytic, **numeric, "numeric_pass": int(numeric["misses"] == 0)}
        rows.append(row)
        for record in records:
            worst.append({"side_m": side, "cap_extension_m": extension, **record})
        print(f"[geometry {side:.0f}/{extension:.0f}] misses={numeric['misses']} gap={numeric['worst_angular_gap_deg']:.3f} route={numeric['open_route_proxy_m']:.2f}", flush=True)
    return rows, worst


def draw_geometry(spec: W5GeometrySpec, out_dir: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    points = w5_detection_points(spec)
    base = points[:19]
    extra = points[19:]
    limit = max(2200.0, spec.supplement_radius_m + 180.0)
    size = 2400
    margin = 180
    plot_size = size - 2 * margin
    scale = plot_size / (2.0 * limit)

    def pixel(point: Point | tuple[float, float]) -> tuple[float, float]:
        x, y = (point.x, point.y) if isinstance(point, Point) else point
        return margin + (x + limit) * scale, margin + (limit - y) * scale

    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    font = ImageFont.load_default(size=28)
    title_font = ImageFont.load_default(size=34)

    for value in range(-2000, 2001, 500):
        x0, _ = pixel((value, 0.0))
        _, y0 = pixel((0.0, value))
        draw.line((x0, margin, x0, size - margin), fill="#eceff2", width=2)
        draw.line((margin, y0, size - margin, y0), fill="#eceff2", width=2)

    svg_elements: list[str] = [
        f'<rect width="{size}" height="{size}" fill="white"/>',
    ]
    for cap in range(6):
        angle = np.linspace(math.radians(60.0 * cap), math.radians(60.0 * (cap + 1)), 121)
        arc = [Point(ARENA_RADIUS_M * math.cos(value), ARENA_RADIUS_M * math.sin(value)) for value in angle]
        vertex_left = points[7 + cap]
        vertex_right = points[7 + ((cap + 1) % 6)]
        polygon = arc + [vertex_right, vertex_left]
        pixels = [pixel(point) for point in polygon]
        draw.polygon(pixels, fill=(243, 198, 119, 70))
        svg_points = " ".join(f"{x:.2f},{y:.2f}" for x, y in pixels)
        svg_elements.append(f'<polygon points="{svg_points}" fill="#f3c677" fill-opacity="0.28"/>')

    for left_index, left in enumerate(base):
        for right in base[left_index + 1 :]:
            if abs(math.hypot(left.x - right.x, left.y - right.y) - spec.side_m) <= 1e-6:
                x1, y1 = pixel(left)
                x2, y2 = pixel(right)
                draw.line((x1, y1, x2, y2), fill="#b8bec7", width=4)
                svg_elements.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="#b8bec7" stroke-width="4"/>')

    center_x, center_y = pixel((0.0, 0.0))
    radius_px = ARENA_RADIUS_M * scale
    draw.ellipse((center_x - radius_px, center_y - radius_px, center_x + radius_px, center_y + radius_px), outline="#202124", width=6)
    svg_elements.append(f'<circle cx="{center_x:.2f}" cy="{center_y:.2f}" r="{radius_px:.2f}" fill="none" stroke="#202124" stroke-width="6"/>')

    for point in base:
        x, y = pixel(point)
        draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill="#2878b5", outline="white", width=3)
        svg_elements.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="12" fill="#2878b5" stroke="white" stroke-width="3"/>')
    for point in extra:
        x, y = pixel(point)
        diamond = [(x, y - 17), (x + 17, y), (x, y + 17), (x - 17, y)]
        draw.polygon(diamond, fill="#d1495b", outline="white")
        svg_points = " ".join(f"{px:.2f},{py:.2f}" for px, py in diamond)
        svg_elements.append(f'<polygon points="{svg_points}" fill="#d1495b" stroke="white" stroke-width="3"/>')
    draw.ellipse((center_x - 8, center_y - 8, center_x + 8, center_y + 8), fill="#202124")

    title = f"W5 symmetric 25-point geometry: a={spec.side_m:.0f} m, p={spec.cap_extension_m:.0f} m"
    draw.text((margin, 55), title, font=title_font, fill="#202124")
    draw.text((margin, size - 105), "Blue: 19-point skeleton    Red: six cap points    Gold: circular caps", font=font, fill="#202124")
    svg_elements.extend([
        f'<text x="{margin}" y="85" font-family="DejaVu Sans, sans-serif" font-size="34" fill="#202124">{title}</text>',
        f'<text x="{margin}" y="{size-70}" font-family="DejaVu Sans, sans-serif" font-size="28" fill="#202124">Blue: 19-point skeleton   Red: six cap points   Gold: circular caps</text>',
    ])
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">' + "".join(svg_elements) + "</svg>"
    (out_dir / "w5_geometry.svg").write_text(svg, encoding="utf-8")
    image.save(out_dir / "w5_geometry.png", dpi=(400, 400))
    image.save(out_dir / "w5_geometry.tiff", dpi=(600, 600), compression="tiff_lzw")


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    return "\n".join([
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(row) + " |" for row in rows),
    ])


def render_report(out_dir: Path, candidates: list[dict[str, Any]], selected: dict[str, Any], minimum: dict[str, Any]) -> None:
    table = [[
        f"{row['side_m']:.0f}", f"{row['cap_extension_m']:.0f}", str(row["analytical_pass"]),
        str(row["misses"]), f"{row['angular_safety_margin_deg']:.2f}",
        f"{row['cap_side_support_margin_m']:.2f}", f"{row['open_route_proxy_m']:.2f}",
    ] for row in candidates]
    lines = [
        "# Q4 W5 symmetric 25-point geometry validation", "",
        "The design contains the origin, six first-ring points, twelve second-ring points, and six outward cap points. Policy code receives only these fixed coordinates; simulator ground truth is used only by later offline evaluation.", "",
        "## Analytical construction", "",
        f"The cap-apex constraint `a^2 + (1800-sqrt(3)a)^2 <= 1000^2` gives `a in [{selected['side_lower_bound_m']:.6f}, {selected['side_upper_bound_m']:.6f}]m`; the upper root is independently computed rather than hard-coded.",
        "Inside the second-ring hexagon, complete triangular cells have side `a<=1000m`, so each source is in the convex hull of three detectors within reception range. Each circular cap is split into two local triangles by its edge midpoint and outward supplement. The sloping supplement-to-vertex side must support the radius-1800 circle; this is checked by its distance from the origin.", "",
        "## Parameter screen", "", markdown_table(["a m", "p m", "Analytic", "Misses", "Angular margin deg", "Cap support margin m", "Open route m"], table), "",
        f"Selected geometry for policy pilot: `a={selected['side_m']:.0f}m`, `p={selected['cap_extension_m']:.0f}m`, `rho={selected['supplement_radius_m']:.3f}m`. It passed `{selected['probe_count']}` formal probes with zero misses; worst angular gap is `{selected['worst_angular_gap_deg']:.6f}deg` and sampled worst visible distance is `{selected['max_sampled_visible_distance_m']:.3f}m`.", "",
        "The historical hand candidate `a=990,p=200` is retained in the table and validated rather than assumed. Parameter selection is lexicographic: reject any analytic/numeric failure, then expose route length and safety margin separately. No weighted reward is used.", "",
        "## Conditional minimum for the fixed 19-point skeleton", "",
        f"At adjacent outward cap apices, one detector satisfying both outward tangent half-planes has nearest possible distance `{minimum['adjacent_cap_common_detector_distance_m']:.6f}m` to each apex, exceeding the 1000m reception radius. Therefore one added point cannot guarantee both adjacent outward cases. Six distinct caps require at least six supplements, so 25 is a lower bound conditional on retaining this fixed 19-point skeleton.", "",
        "This is not a global proof that every possible detection geometry needs at least 25 points. It proves only the stated 19+cap construction minimum.", "",
        "## Verification scope", "",
        "The selected candidate is checked with one million fixed-seed random disk samples, dense sampling of all six caps, dense arena-boundary points, and triangular-cell edges. The angular-gap test covers every source direction at each sampled source position; sampled direction checks additionally report visible-distance behavior. Numeric zero miss supports the construction but is not presented as an independent formal proof over a continuum.",
    ]
    (out_dir / "geometry_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Q4 W5 symmetric 25-point geometry")
    parser.add_argument("--out-dir", default="results/q4/w5_geometry")
    parser.add_argument("--scan-random", type=int, default=50_000)
    parser.add_argument("--formal-random", type=int, default=1_000_000)
    parser.add_argument("--scan-cap-step", type=float, default=5.0)
    parser.add_argument("--formal-cap-step", type=float, default=0.5)
    parser.add_argument("--selected-a", type=float, default=990.0)
    parser.add_argument("--selected-p", type=float, default=160.0)
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates, worst = scan_specs(random_disk_points(args.scan_random, 20260913), args.scan_cap_step)
    selected_spec = W5GeometrySpec(args.selected_a, args.selected_p)
    formal_batches = (
        ("formal_random", random_disk_points(args.formal_random, 20260913)),
        ("formal_boundary", boundary_points()),
        ("formal_caps", dense_cap_points(selected_spec, args.formal_cap_step)),
        ("formal_cell_boundaries", cell_boundary_points(selected_spec, 401)),
    )
    formal, formal_worst = evaluate_sources(selected_spec, formal_batches, direction_seed=20260914)
    selected = {**analytic_geometry_checks(selected_spec), **formal}
    if not selected["analytical_pass"] or selected["misses"]:
        raise RuntimeError(f"selected W5 geometry failed: {selected}")
    minimum = fixed_skeleton_minimum_argument(selected_spec)
    hand_spec = W5GeometrySpec(990.0, 200.0)
    if hand_spec == selected_spec:
        hand = selected
        hand_worst = formal_worst
    else:
        hand, hand_worst = evaluate_sources(
            hand_spec,
            (
                ("hand_random", random_disk_points(args.formal_random, 20260915)),
                ("hand_boundary", boundary_points()),
                ("hand_caps", dense_cap_points(hand_spec, args.formal_cap_step)),
                ("hand_cell_boundaries", cell_boundary_points(hand_spec, 401)),
            ),
            direction_seed=20260916,
        )
        hand = {**analytic_geometry_checks(hand_spec), **hand}
    if not hand["analytical_pass"] or hand["misses"]:
        raise RuntimeError(f"hand-derived W5 geometry failed: {hand}")
    write_csv(out_dir / "candidate_parameters.csv", candidates)
    write_csv(out_dir / "formal_validation.csv", [selected, hand] if hand_spec != selected_spec else [selected])
    write_csv(out_dir / "worst_cases.csv", worst + [{"side_m": selected_spec.side_m, "cap_extension_m": selected_spec.cap_extension_m, **row} for row in formal_worst] + [{"side_m": hand_spec.side_m, "cap_extension_m": hand_spec.cap_extension_m, **row} for row in hand_worst])
    (out_dir / "selected_geometry.json").write_text(json.dumps({"geometry": selected, "hand_candidate_990_200": hand, "conditional_minimum": minimum}, indent=2), encoding="utf-8")
    draw_geometry(selected_spec, out_dir)
    render_report(out_dir, candidates, selected, minimum)
    print(json.dumps(selected, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
