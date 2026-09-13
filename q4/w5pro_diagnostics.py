"""Runtime event counters required for W5Pro ablation evidence."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable


EVENT_FIELDS = {
    "nbv_selected_count": "w5pro_nbv_selected",
    "nbv_effective_count": "w5pro_nbv_effective",
    "intersection_selected_count": "w5pro_intersection_selected",
    "spatial_stop_selected_count": "w5pro_spatial_stop_selected",
    "information_ridge_selected_count": "w5pro_information_ridge_selected",
    "outcome_probability_count": "w5pro_outcome_probabilities",
    "wait_for_route_success_count": "w5pro_wait_success",
    "corridor_opportunity_count": "w5pro_corridor_opportunity",
    "legacy_backbone_fallback_count": "w5pro_legacy_backbone_fallback",
    "w3_coarse_fallback_count": "w5pro_w3_coarse_fallback",
    "w2_fallback_count": "w5pro_w2_fallback",
    "tail_rescue_count": "w5pro_tail_rescue",
    "tail_fallback_event_count": "w5pro_tail_fallback",
    "route_repair_count": "w5pro_route_repair",
    "no_progress_guard_count": "w5pro_no_progress_guard",
    "exit_state_count": "w5pro_exit_state",
    "certificate_summary_count": "w5pro_certificate_summary",
}


@dataclass(frozen=True)
class PlannerDiagnostics:
    counts: dict[str, int]
    decisions: int

    @property
    def fallback_count(self) -> int:
        return sum(self.counts.get(name, 0) for name in (
            "legacy_backbone_fallback_count", "w3_coarse_fallback_count",
            "w2_fallback_count", "tail_rescue_count"))

    @property
    def fallback_rate(self) -> float:
        return self.fallback_count / self.decisions if self.decisions else 0.0


def collect_diagnostics(events: Iterable[dict], decisions: int | None = None) -> PlannerDiagnostics:
    events = list(events)
    counter = Counter(str(e.get("event", "")) for e in events)
    counts = {field: counter.get(event, 0) for field, event in EVENT_FIELDS.items()}
    counts["nbv_effective_count"] = sum(
        1 for e in events if e.get("event") == "w5pro_nbv_effective"
        and e.get("applied") is True)
    counts["intersection_selected_count"] = sum(
        1 for e in events if e.get("event") == "w5pro_intersection_selected"
        and e.get("applied") is True)
    counts["route_repair_count"] = sum(
        1 for e in events if e.get("event") == "w5pro_route_repair"
        and e.get("repair_needed") is True)
    if decisions is None:
        decisions = counter.get("w5pro_selected_task", 0) or counter.get("w4a_selected_task", 0)
    # The runtime event is named tail_fallback; retain the legacy tail_rescue
    # field for compatibility and expose the actual event count separately.
    return PlannerDiagnostics(counts, int(decisions))
