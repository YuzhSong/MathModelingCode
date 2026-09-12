from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_stage2_eval import paired_rows, phase_summary_rows
from scripts.run_v5_eval import write_csv


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "results/offline_eval_stage2_200"
MN = ROOT / "results/offline_eval_stage2_mn_200"
AUDIT = ROOT / "results/offline_eval_stage2_v6_audit_200"
BASE = ROOT / "results/offline_eval_v6_n8"
WAY = ROOT / "results/offline_eval_way1_way3_200"
OUT = ROOT / "results/offline_eval_stage2_analysis"
VERSIONS = ["v6", "m1", "m2_b0p1", "n1", "n2", "n3", "mn"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    return 0.0 if value in {None, ""} else float(value)


def integer(row: dict[str, Any], key: str) -> int:
    return int(number(row, key))


def average(rows: Iterable[dict[str, Any]], key: str) -> float:
    values = [number(row, key) for row in rows]
    return statistics.fmean(values) if values else 0.0


def source_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for version in VERSIONS:
        for suite in ("random", "min_reff", "collinear", "overall"):
            subset = [
                row
                for row in rows
                if row["version"] == version and (suite == "overall" or row["suite"] == suite)
            ]
            if not subset:
                continue
            counts = [integer(row, "supplement_measure_count") for row in subset]
            supplemented = [row for row in subset if integer(row, "supplement_measure_count") > 0]
            elapsed = [
                number(row, "clear_time_s") - number(row, "first_found_time_s")
                for row in subset
            ]
            output.append(
                {
                    "version": version,
                    "suite": suite,
                    "sources": len(subset),
                    "mean_found_to_clear_s": statistics.fmean(elapsed),
                    "mean_found_after_move_m": average(subset, "found_after_extra_move_m"),
                    "mean_off_search_supplement_move_m": average(
                        subset, "off_search_supplement_move_m"
                    ),
                    "mean_supplements_per_source": statistics.fmean(counts),
                    "first_supplement_clearable_rate": (
                        sum(integer(row, "first_supplement_clearable") for row in supplemented)
                        / len(supplemented)
                        if supplemented
                        else 0.0
                    ),
                    "supp_ge2_rate": sum(value >= 2 for value in counts) / len(counts),
                    "supp_ge3_rate": sum(value >= 3 for value in counts) / len(counts),
                    "supp_ge4_rate": sum(value >= 4 for value in counts) / len(counts),
                    "off_search_supplement_count": sum(
                        integer(row, "off_search_supplement_count") for row in subset
                    ),
                    "threshold_chasing_20_30_count": sum(
                        integer(row, "threshold_chasing_20_30_count") for row in subset
                    ),
                }
            )
    return output


def decision_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for version in VERSIONS:
        subset = [row for row in rows if row["version"] == version]
        if not subset:
            continue
        families = Counter(row["selected_family"] for row in subset)
        changed = sum(integer(row, "changed_from_v6") for row in subset)
        output.append(
            {
                "version": version,
                "executed_scored_supplements": len(subset),
                "changed_from_v6_count": changed,
                "changed_from_v6_rate": changed / len(subset),
                "selected_near_field_count": families["near_field_85m"],
                "selected_large_angle_count": families["large_angle_perpendicular"],
                "selected_v6_family_count": families["v6"],
            }
        )
    return output


def case_source_map(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, float]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["version"], row["suite"], row["seed"])].append(row)
    output: dict[tuple[str, str, str], dict[str, float]] = {}
    for key, subset in grouped.items():
        output[key] = {
            "supplements": sum(integer(row, "supplement_measure_count") for row in subset),
            "off_search_move_m": sum(number(row, "off_search_supplement_move_m") for row in subset),
            "found_after_move_m": sum(number(row, "found_after_extra_move_m") for row in subset),
            "waited_search": sum(integer(row, "waited_search_supplement_count") for row in subset),
        }
    return output


def phase_map(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], dict[str, float]]:
    return {
        (row["version"], row["suite"], row["seed"], row["phase"]): {
            "move": number(row, "move_time_s"),
            "info": number(row, "measure_time_s") + number(row, "switch_time_s"),
            "service": number(row, "clear_time_s"),
        }
        for row in rows
    }


def regression_cases() -> list[dict[str, Any]]:
    details = {
        (row["version"], row["suite"], row["seed"]): row
        for row in read_csv(BASE / "details.csv")
        if row["version"] in {"v4", "v6"}
    }
    phases = phase_map(read_csv(WAY / "phase_decomposition.csv"))
    sources = case_source_map(read_csv(BASE / "source_diagnostics.csv"))
    abandoned: Counter[tuple[str, str]] = Counter()
    for row in read_csv(BASE / "route_decisions.csv"):
        if row["version"] == "v6" and integer(row, "abandoned_high_p_clear"):
            abandoned[(row["suite"], row["seed"])] += 1

    output: list[dict[str, Any]] = []
    for version, suite, seed in sorted(details):
        if version != "v6":
            continue
        v4 = details[("v4", suite, seed)]
        v6 = details[("v6", suite, seed)]
        components: dict[str, float] = {}
        for phase in ("search", "found", "clear"):
            left = phases[("v4", suite, seed, phase)]
            right = phases[("v6", suite, seed, phase)]
            components[f"{phase}_move_delta_s"] = right["move"] - left["move"]
            components[f"{phase}_info_delta_s"] = right["info"] - left["info"]
            components[f"{phase}_service_delta_s"] = right["service"] - left["service"]

        v4_source = sources[("v4", suite, seed)]
        v6_source = sources[("v6", suite, seed)]
        delta_supp = v6_source["supplements"] - v4_source["supplements"]
        delta_off_move = v6_source["off_search_move_m"] - v4_source["off_search_move_m"]
        delta_wait = v6_source["waited_search"] - v4_source["waited_search"]
        delta_total = number(v6, "total_time_s") - number(v4, "total_time_s")
        non_dedicated = (
            components["found_move_delta_s"]
            + components["clear_move_delta_s"]
            - delta_off_move / 5.0
        )
        positive = {
            "search_move": components["search_move_delta_s"],
            "search_info": components["search_info_delta_s"],
            "found_move": components["found_move_delta_s"],
            "found_info": components["found_info_delta_s"],
            "clear_move": components["clear_move_delta_s"],
        }
        largest = max(positive, key=positive.get)
        r1 = delta_supp > 0 and abandoned[(suite, seed)] > 0
        r2 = delta_wait > 0 and components["search_move_delta_s"] > 0
        r3 = delta_off_move > 0 and components["found_move_delta_s"] > 0
        r4 = delta_supp > 0
        r5 = non_dedicated > 0
        if largest == "search_move" and r2:
            primary = "R2_over_wait_search"
        elif largest == "found_info" and r4:
            primary = "R4_insufficient_measurement"
        elif largest == "found_move" and r3 and delta_off_move / 5.0 >= 0.5 * max(
            positive["found_move"], 1e-9
        ):
            primary = "R3_dedicated_detour"
        elif largest == "found_move" and r1:
            primary = "R1_route_info_tradeoff"
        elif largest in {"search_move", "found_move", "clear_move"} and r5:
            primary = "R5_task_ordering"
        else:
            primary = "R6_other"
        output.append(
            {
                "suite": suite,
                "seed": int(seed),
                "delta_total_s": delta_total,
                "v4_time_s": number(v4, "total_time_s"),
                "v6_time_s": number(v6, "total_time_s"),
                "delta_move_m": number(v6, "move_distance_m") - number(v4, "move_distance_m"),
                "delta_supplements": delta_supp,
                "delta_off_search_supplement_move_m": delta_off_move,
                "delta_waited_search_supplements": delta_wait,
                "abandoned_high_p_clear_count": abandoned[(suite, seed)],
                "non_dedicated_route_remainder_s": non_dedicated,
                "flag_r1": int(r1),
                "flag_r2": int(r2),
                "flag_r3": int(r3),
                "flag_r4": int(r4),
                "flag_r5": int(r5),
                "primary_class": primary,
                **components,
                "component_reconciliation_s": delta_total - sum(components.values()),
            }
        )
    return output


def regression_decomposition(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    populations = {
        "all": rows,
        "v6_wins": [row for row in rows if number(row, "delta_total_s") < 0],
        "v6_losses": [row for row in rows if number(row, "delta_total_s") > 0],
        "regression_gt300": [row for row in rows if number(row, "delta_total_s") > 300],
    }
    output = []
    for name, subset in populations.items():
        output.append(
            {
                "population": name,
                "cases": len(subset),
                "mean_delta_total_s": average(subset, "delta_total_s"),
                "mean_search_move_delta_s": average(subset, "search_move_delta_s"),
                "mean_search_info_delta_s": average(subset, "search_info_delta_s"),
                "mean_found_move_delta_s": average(subset, "found_move_delta_s"),
                "mean_found_info_delta_s": average(subset, "found_info_delta_s"),
                "mean_clear_move_delta_s": average(subset, "clear_move_delta_s"),
                "mean_dedicated_detour_proxy_delta_s": average(
                    subset, "delta_off_search_supplement_move_m"
                )
                / 5.0,
                "mean_task_ordering_remainder_s": average(
                    subset, "non_dedicated_route_remainder_s"
                ),
                "mean_delta_supplements": average(subset, "delta_supplements"),
            }
        )
    return output


def regression_classes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    losses = [row for row in rows if number(row, "delta_total_s") > 0]
    output: list[dict[str, Any]] = []
    for label, count in Counter(row["primary_class"] for row in losses).most_common():
        subset = [row for row in losses if row["primary_class"] == label]
        output.append(
            {
                "classification": label,
                "case_count": count,
                "share_of_v6_losses": count / len(losses),
                "mean_loss_s": average(subset, "delta_total_s"),
                "max_loss_s": max(number(row, "delta_total_s") for row in subset),
            }
        )
    for flag in ("flag_r1", "flag_r2", "flag_r3", "flag_r4", "flag_r5"):
        subset = [row for row in losses if integer(row, flag)]
        output.append(
            {
                "classification": f"overlap_{flag[5:].upper()}",
                "case_count": len(subset),
                "share_of_v6_losses": len(subset) / len(losses),
                "mean_loss_s": average(subset, "delta_total_s"),
                "max_loss_s": max((number(row, "delta_total_s") for row in subset), default=0.0),
            }
        )
    return output


def audit_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dedicated = [row for row in rows if integer(row, "selected_is_dedicated")]
    legal = [row for row in dedicated if integer(row, "legal_future_search_count") > 0]
    output = [
        {"metric": "executed_supplements", "value": len(rows)},
        {"metric": "dedicated_supplements", "value": len(dedicated)},
        {"metric": "dedicated_with_legal_future_search", "value": len(legal)},
    ]
    for threshold in (100, 250, 500, 1000):
        output.append(
            {
                "metric": f"dedicated_legal_search_within_{threshold}m",
                "value": sum(
                    number(row, "nearest_future_search_to_selected_m") <= threshold
                    for row in legal
                ),
            }
        )
    output.extend(
        [
            {
                "metric": "mean_dedicated_route_marginal_s",
                "value": average(dedicated, "selected_route_marginal_s"),
            },
            {
                "metric": "mean_future_search_objective_minus_selected_s",
                "value": statistics.fmean(
                    number(row, "best_future_search_objective_s")
                    - number(row, "selected_objective_s")
                    for row in legal
                )
                if legal
                else 0.0,
            },
        ]
    )
    return output


def audit_by_population(
    audit_rows: list[dict[str, Any]], regression_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    populations = {
        "all": {(row["suite"], str(row["seed"])) for row in regression_rows},
        "v6_wins": {
            (row["suite"], str(row["seed"]))
            for row in regression_rows
            if number(row, "delta_total_s") < 0
        },
        "v6_losses": {
            (row["suite"], str(row["seed"]))
            for row in regression_rows
            if number(row, "delta_total_s") > 0
        },
        "regression_gt300": {
            (row["suite"], str(row["seed"]))
            for row in regression_rows
            if number(row, "delta_total_s") > 300
        },
    }
    output: list[dict[str, Any]] = []
    for name, keys in populations.items():
        subset = [row for row in audit_rows if (row["suite"], row["seed"]) in keys]
        dedicated = [row for row in subset if integer(row, "selected_is_dedicated")]
        legal = [row for row in dedicated if integer(row, "legal_future_search_count") > 0]
        output.append(
            {
                "population": name,
                "cases": len(keys),
                "executed_supplements": len(subset),
                "dedicated_supplements": len(dedicated),
                "dedicated_with_legal_future_search": len(legal),
                "legal_future_search_share_of_dedicated": (
                    len(legal) / len(dedicated) if dedicated else 0.0
                ),
                "within_250m_count": sum(
                    number(row, "nearest_future_search_to_selected_m") <= 250.0
                    for row in legal
                ),
                "within_500m_count": sum(
                    number(row, "nearest_future_search_to_selected_m") <= 500.0
                    for row in legal
                ),
                "mean_selected_route_marginal_s": average(
                    dedicated, "selected_route_marginal_s"
                ),
                "mean_future_search_objective_minus_selected_s": (
                    statistics.fmean(
                        number(row, "best_future_search_objective_s")
                        - number(row, "selected_objective_s")
                        for row in legal
                    )
                    if legal
                    else 0.0
                ),
            }
        )
    return output


def top_sources() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = [
        row
        for row in read_csv(WAY / "source_found_clear.csv")
        if row["version"] == "v6"
    ]
    expensive = sorted(
        rows, key=lambda row: number(row, "found_to_clear_elapsed_s"), reverse=True
    )[:20]
    supplement_heavy = sorted(
        rows,
        key=lambda row: (
            integer(row, "supplement_measure_count"),
            number(row, "found_after_move_m"),
        ),
        reverse=True,
    )[:20]
    return expensive, supplement_heavy


def pair_against(
    details: list[dict[str, Any]], base: str, target: str
) -> list[dict[str, Any]]:
    renamed = []
    for row in details:
        if row["version"] == base:
            renamed.append(dict(row, version="v6"))
        elif row["version"] == target:
            renamed.append(row)
    rows = paired_rows(renamed, ["v6", target])
    for row in rows:
        row["base"] = base
    return rows


def typical_cases(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {
        (row["version"], row["suite"], row["seed"]): row
        for row in details
    }
    keys = [(row["suite"], row["seed"]) for row in details if row["version"] == "v6"]

    def extreme(target: str, base: str, maximum: bool) -> tuple[str, str, float]:
        values = [
            (
                suite,
                seed,
                number(lookup[(target, suite, seed)], "total_time_s")
                - number(lookup[(base, suite, seed)], "total_time_s"),
            )
            for suite, seed in keys
        ]
        return (max if maximum else min)(values, key=lambda item: item[2])

    specs = [
        ("v6_big_win_v4", "v6", "v4", False),
        ("v6_big_loss_v4", "v6", "v4", True),
        ("m2_best_improvement", "m2_b0p1", "v6", False),
        ("n1_best_improvement", "n1", "v6", False),
        ("n1_worst_regression", "n1", "v6", True),
    ]
    output = []
    for label, target, base, maximum in specs:
        suite, seed, delta = extreme(target, base, maximum)
        output.append(
            {
                "label": label,
                "suite": suite,
                "seed": int(seed),
                "base": base,
                "target": target,
                "delta_time_s": delta,
                "base_time_s": number(lookup[(base, suite, seed)], "total_time_s"),
                "target_time_s": number(lookup[(target, suite, seed)], "total_time_s"),
            }
        )
    return output


def typical_decomposition(
    cases: list[dict[str, Any]],
    details: list[dict[str, Any]],
    phases: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    detail_lookup = {
        (row["version"], row["suite"], row["seed"]): row for row in details
    }
    phase_lookup = phase_map(phases)
    source_lookup = case_source_map(sources)
    output: list[dict[str, Any]] = []
    for case in cases:
        suite = str(case["suite"])
        seed = str(case["seed"])
        base = str(case["base"])
        target = str(case["target"])
        left = detail_lookup[(base, suite, seed)]
        right = detail_lookup[(target, suite, seed)]
        left_source = source_lookup[(base, suite, seed)]
        right_source = source_lookup[(target, suite, seed)]
        row: dict[str, Any] = {
            **case,
            "delta_move_time_s": number(right, "move_time_s") - number(left, "move_time_s"),
            "delta_measure_time_s": number(right, "measure_time_s") - number(left, "measure_time_s"),
            "delta_switch_time_s": number(right, "switch_time_s") - number(left, "switch_time_s"),
            "delta_clear_time_s": number(right, "clear_time_s") - number(left, "clear_time_s"),
            "delta_supplements": right_source["supplements"] - left_source["supplements"],
            "delta_found_after_move_m": (
                right_source["found_after_move_m"] - left_source["found_after_move_m"]
            ),
            "delta_off_search_move_m": (
                right_source["off_search_move_m"] - left_source["off_search_move_m"]
            ),
        }
        for phase in ("search", "found", "clear"):
            before = phase_lookup[(base, suite, seed, phase)]
            after = phase_lookup[(target, suite, seed, phase)]
            row[f"delta_{phase}_total_s"] = (
                after["move"] + after["info"] + after["service"]
                - before["move"] - before["info"] - before["service"]
            )
        output.append(row)
    return output


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    details = read_csv(MAIN / "details.csv") + read_csv(MN / "details.csv")
    sources = read_csv(MAIN / "source_diagnostics.csv") + read_csv(MN / "source_diagnostics.csv")
    phases = read_csv(MAIN / "phase_decomposition.csv") + read_csv(MN / "phase_decomposition.csv")
    decisions_raw = read_csv(MAIN / "stage2_decisions.csv") + read_csv(MN / "stage2_decisions.csv")
    summaries = read_csv(MAIN / "summary.csv") + read_csv(MN / "summary.csv")
    pairs = paired_rows(details, VERSIONS) + pair_against(details, "n1", "mn")
    phase_summaries = phase_summary_rows(phases, VERSIONS)
    source_summaries = source_summary(sources)
    decisions = decision_summary(decisions_raw)
    regressions = regression_cases()
    decomposition = regression_decomposition(regressions)
    classes = regression_classes(regressions)
    audit_rows = read_csv(AUDIT / "v6_audit.csv")
    audit = audit_summary(audit_rows)
    audit_populations = audit_by_population(audit_rows, regressions)
    expensive, supplement_heavy = top_sources()
    v4 = [row for row in read_csv(BASE / "details.csv") if row["version"] == "v4"]
    typical = typical_cases(details + v4)
    baseline_phases = read_csv(WAY / "phase_decomposition.csv")
    baseline_sources = read_csv(BASE / "source_diagnostics.csv")
    typical_breakdown = typical_decomposition(
        typical,
        details + v4,
        phases + [row for row in baseline_phases if row["version"] == "v4"],
        sources + [row for row in baseline_sources if row["version"] == "v4"],
    )

    write_csv(OUT / "summary.csv", summaries)
    write_csv(OUT / "paired_vs_v6_and_n1.csv", pairs)
    write_csv(OUT / "phase_summary.csv", phase_summaries)
    write_csv(OUT / "source_summary.csv", source_summaries)
    write_csv(OUT / "candidate_decision_summary.csv", decisions)
    write_csv(OUT / "v6_regression_cases.csv", regressions)
    write_csv(OUT / "v6_regression_decomposition.csv", decomposition)
    write_csv(OUT / "v6_regression_classification.csv", classes)
    write_csv(OUT / "v6_dedicated_search_audit.csv", audit)
    write_csv(OUT / "v6_dedicated_search_audit_by_population.csv", audit_populations)
    write_csv(OUT / "v6_expensive_sources.csv", expensive)
    write_csv(OUT / "v6_supplement_heavy_sources.csv", supplement_heavy)
    write_csv(OUT / "typical_cases.csv", typical)
    write_csv(OUT / "typical_case_decomposition.csv", typical_breakdown)
    (OUT / "metadata.json").write_text(
        json.dumps(
            {
                "environment": "local offline_sim practice only",
                "official_formal_test_run": False,
                "policy_ground_truth_use": False,
                "m2_pilot_selection": "beta=0.10 s/m selected on fixed 40-case pilot",
                "regression_classification": (
                    "heuristic log-based attribution; primary classes are mutually exclusive; "
                    "overlap flags are not"
                ),
                "v6_audit_equivalence": json.loads(
                    (AUDIT / "metadata.json").read_text(encoding="utf-8")
                )["v6_reference_equivalence"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
