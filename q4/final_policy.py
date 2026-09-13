"""Single Q4 production entry point for the frozen W6-25PFR strategy."""
from __future__ import annotations

from typing import Any

from q4.w6_policy import W6PersistentBearingPolicy


def policy_q4_final(runner: Any) -> None:
    """Run W6-25PFR without duplicating the policy implementation."""
    W6PersistentBearingPolicy(runner).run()

