"""Reproducible Q4 stress/error-field matrix used by W5Pro acceptance."""
from __future__ import annotations

from dataclasses import dataclass

from offline_sim.case import Case, STRESS_TYPES, generate_case, generate_stress_case
from offline_sim.fields import FIELD_KINDS
from q4.w1_policy import w1_search_points


@dataclass(frozen=True)
class ExperimentSpec:
    suite: str
    seed: int
    field_kind: str


STRESS_SUITE_NAMES = tuple(STRESS_TYPES)
ERROR_FIELD_NAMES = tuple(FIELD_KINDS)


def make_experiment_case(spec: ExperimentSpec, problem: int = 4, mode: str = "formal") -> Case:
    if spec.field_kind not in ERROR_FIELD_NAMES:
        raise ValueError(f"unknown error field: {spec.field_kind}")
    if spec.suite == "random":
        return generate_case(seed=spec.seed, problem=problem, mode=mode,
                             field_kind=spec.field_kind, margin_m=0.0)
    if spec.suite not in STRESS_SUITE_NAMES:
        raise ValueError(f"unknown Q4 stress suite: {spec.suite}")
    return generate_stress_case(spec.suite, seed=spec.seed, problem=problem,
                                mode=mode, field_kind=spec.field_kind,
                                scan_points=[(p.x, p.y) for p in w1_search_points()])


def full_matrix(seed: int = 0, mode: str = "formal") -> list[tuple[ExperimentSpec, Case]]:
    specs = [ExperimentSpec("random", seed, field) for field in ERROR_FIELD_NAMES]
    specs += [ExperimentSpec(suite, seed, field) for suite in STRESS_SUITE_NAMES for field in ERROR_FIELD_NAMES]
    return [(spec, make_experiment_case(spec, mode=mode)) for spec in specs]
