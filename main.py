from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from q3.safety import PRACTICE_CONFIRMATION, require_practice_confirmation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Q3 unified entry point (practice/offline only).")
    parser.add_argument("--mode", choices=("official", "offline"), default="official")
    parser.add_argument("--strategy", default="v3", help="Strategy generation for offline evaluation; official uses the HTTP planner.")
    parser.add_argument("--robot-id", default=os.getenv("ROBOT_ID"))
    parser.add_argument("--base-url", default=os.getenv("SIM_BASE_URL", "http://127.0.0.1:2026"))
    parser.add_argument("--confirm-practice", help=f"Required for official practice mode: {PRACTICE_CONFIRMATION}")
    parser.add_argument("--log", default="logs/q3_official.jsonl")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "offline":
        from scripts.run_offline_eval import main as offline_main

        sys.argv = [sys.argv[0], "--versions", args.strategy]
        return offline_main()

    if not args.robot_id:
        print("请通过 --robot-id 或环境变量 ROBOT_ID 指定参赛队号。", file=sys.stderr)
        return 2
    try:
        require_practice_confirmation(args.confirm_practice)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    from q3.api_client import RequestIdFactory, SimulatorClient
    from q3.logger import JsonlLogger
    from q3.planner import Q3BaselinePlanner, Q3Config

    client = SimulatorClient(
        robot_id=args.robot_id,
        base_url=args.base_url,
        request_ids=RequestIdFactory("q3"),
        logger=JsonlLogger(Path(args.log)),
    )
    summary = Q3BaselinePlanner(client, logger=JsonlLogger(Path(args.log)), config=Q3Config()).run()
    print("Q3 practice summary:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
