from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from q3.api_client import RequestIdFactory, SimulatorClient
from q3.logger import JsonlLogger
from q3.planner import Q3BaselinePlanner, Q3Config
from q3.safety import PRACTICE_CONFIRMATION, require_practice_confirmation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Q3 omnidirectional baseline runner.")
    parser.add_argument("--robot-id", default=os.getenv("ROBOT_ID"), help="Current logged-in team/robot id.")
    parser.add_argument("--base-url", default=os.getenv("SIM_BASE_URL", "http://127.0.0.1:2026"))
    parser.add_argument("--log", default="代码/logs/q3_baseline.jsonl")
    parser.add_argument("--search-radius", type=float, default=1150.0)
    parser.add_argument("--max-localization-measures", type=int, default=8)
    parser.add_argument(
        "--confirm-practice",
        help=f"Safety gate. Must equal {PRACTICE_CONFIRMATION!r} after confirming the simulator is in Q3 practice/simulation mode.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.robot_id:
        print("请通过 --robot-id 或环境变量 ROBOT_ID 指定当前登录参赛队号。", file=sys.stderr)
        return 2
    try:
        require_practice_confirmation(args.confirm_practice)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    logger = JsonlLogger(Path(args.log))
    client = SimulatorClient(
        robot_id=args.robot_id,
        base_url=args.base_url,
        request_ids=RequestIdFactory("q3"),
        logger=logger,
    )
    planner = Q3BaselinePlanner(
        client,
        logger=logger,
        config=Q3Config(search_radius=args.search_radius, max_localization_measures=args.max_localization_measures),
    )
    summary = planner.run()
    print("Q3 baseline summary:", summary)
    print(f"log: {Path(args.log).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
