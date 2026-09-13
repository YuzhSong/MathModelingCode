"""Feature gates for the incremental W5Pro migration.

All gates default to ``False`` so the frozen W5 behavior remains the reference
implementation while planner mechanisms are added one at a time.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class W5ProConfig:
    use_hypothesis: bool = False
    adaptive_backbone: bool = False
    use_nbv: bool = False
    use_task_pool: bool = False
    use_wait_for_route: bool = False
    use_spatial_stop: bool = False
    use_future_cost: bool = False
    adaptive_scan: bool = False
    use_tail_rescue: bool = False
    use_intersection: bool = False
    risk_mode: str = "expected"
    cvar_alpha: float = 0.8
    outcome_mode: str = "robust"
    spatial_service_budget: int = 3
    max_macro_steps: int = 2000

    def __post_init__(self) -> None:
        if self.risk_mode not in {"expected", "cvar"}:
            raise ValueError("risk_mode must be 'expected' or 'cvar'")
        if not 0.0 <= self.cvar_alpha < 1.0:
            raise ValueError("cvar_alpha must satisfy 0 <= alpha < 1")
        if self.outcome_mode not in {"robust", "expected"}:
            raise ValueError("outcome_mode must be 'robust' or 'expected'")

    @property
    def identity(self) -> bool:
        return not any(getattr(self, name) for name in (
            "use_hypothesis", "adaptive_backbone", "use_nbv", "use_task_pool",
            "use_wait_for_route", "use_spatial_stop", "use_future_cost",
            "adaptive_scan", "use_tail_rescue", "use_intersection"))


IDENTITY_CONFIG = W5ProConfig()

# The official W5Pro entry point enables the deterministic mechanisms that
# have runtime implementations.  Identity remains available explicitly for
# paired baseline and ablation runs.
PRODUCTION_CONFIG = W5ProConfig(
    use_hypothesis=True,
    adaptive_backbone=True,
    use_nbv=True,
    use_task_pool=True,
    use_wait_for_route=True,
    use_spatial_stop=True,
    use_future_cost=True,
    adaptive_scan=True,
    use_tail_rescue=True,
    use_intersection=True,
)
