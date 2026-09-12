from __future__ import annotations

from typing import Any

from q3.v6_policy import policy_v6


def policy_w0(runner: Any, n: int = 8) -> None:
    """W0: run frozen Q3 V6 unchanged in the problem=4 simulator."""

    policy_v6(runner, n=n)

