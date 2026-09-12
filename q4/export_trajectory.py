"""Export one local offline_sim episode as an ordered trajectory CSV.

This is an analysis/export helper only. It does not alter W2/W3 policy logic
and never exposes case truth to the policy-facing runner.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.case import generate_case
from offline_sim.harness import run_episode
from q4.w2_policy import policy_w2
from q4.w3_policy import policy_w3


POLICIES = {"w2": policy_w2, "w3": policy_w3}
FIELDS = [
    "step_id",
    "suite",
    "seed",
    "policy",
    "action_type",
    "x",
    "y",
    "channel",
    "virtual_time_s",
    "result",
]


def export_one(policy_name: str, seed: int, output: Path) -> dict[str, float | int]:
    case = generate_case(
        seed=seed,
        problem=4,
        mode="practice",
        field_kind="smooth",
        margin_m=0.0,
    )
    result = run_episode(case, POLICIES[policy_name], include_oracles=False)
    if result.error:
        raise RuntimeError(f"{policy_name} seed={seed} failed: {result.error}")

    output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = [
        {
            "step_id": 0,
            "suite": "random",
            "seed": seed,
            "policy": policy_name,
            "action_type": "enter",
            "x": 0.0,
            "y": 0.0,
            "channel": 1,
            "virtual_time_s": 0.0,
            "result": "accepted",
        }
    ]
    for index, action in enumerate(result.action_log, start=1):
        rows.append(
            {
                "step_id": index,
                "suite": "random",
                "seed": seed,
                "policy": policy_name,
                "action_type": action.action,
                "x": action.x,
                "y": action.y,
                "channel": action.channel,
                "virtual_time_s": action.virtual_time_s,
                "result": action.result,
            }
        )

    last = result.action_log[-1] if result.action_log else None
    rows.append(
        {
            "step_id": len(rows),
            "suite": "random",
            "seed": seed,
            "policy": policy_name,
            "action_type": "exit",
            "x": 0.0 if last is None else last.x,
            "y": 0.0 if last is None else last.y,
            "channel": 1 if last is None else last.channel,
            "virtual_time_s": result.virtual_time_s,
            "result": "user_exit",
        }
    )
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    if rows[0]["action_type"] != "enter" or rows[-1]["action_type"] != "exit":
        raise AssertionError("trajectory endpoint order is invalid")
    if abs(float(rows[-1]["virtual_time_s"]) - result.virtual_time_s) > 1e-9:
        raise AssertionError("trajectory final time does not match episode result")
    if len(rows) != len(result.action_log) + 2:
        raise AssertionError("trajectory row count does not match action log")
    return {
        "rows": len(rows),
        "actions": len(result.action_log),
        "total_time_s": result.virtual_time_s,
        "cleared": result.cleared,
        "total": result.total,
        "move_distance_m": result.move_distance_m,
        "measure_count": result.n_measure,
        "clear_count": result.n_clear,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export one Q4 offline trajectory")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out-dir", default="results/q4/trajectory_plot")
    parser.add_argument("--policies", default="w3,w2")
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    for policy_name in [item.strip() for item in args.policies.split(",") if item.strip()]:
        if policy_name not in POLICIES:
            raise ValueError(f"unknown policy: {policy_name}")
        stats = export_one(
            policy_name,
            args.seed,
            out_dir / f"{policy_name}_seed{args.seed}_trajectory.csv",
        )
        print(policy_name, stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
