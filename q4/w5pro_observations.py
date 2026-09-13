"""Public measurement-to-planner observation adapter."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlannerObservation:
    kind: str
    result: str
    bearing_deg: float | None = None


def adapt_measurement(measurement: Any | None, *, clear_result: bool = False) -> PlannerObservation:
    if clear_result:
        return PlannerObservation("CLEAR_RESULT", "clear_result")
    if measurement is None:
        return PlannerObservation("NO_SIGNAL", "no_signal")
    result = str(getattr(measurement, "result", "no_signal"))
    if result == "direction":
        return PlannerObservation("BEARING", result, getattr(measurement, "svd_deg", None))
    if result == "near":
        return PlannerObservation("NEAR", result)
    return PlannerObservation("NO_SIGNAL", "no_signal")
