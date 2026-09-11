from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from q3.api_client import RequestIdFactory, SimulatorClient
from q3.logger import JsonlLogger
from q3.models import Point
from q3.safety import PRACTICE_CONFIRMATION, require_practice_confirmation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal official simulator API smoke test.")
    parser.add_argument("--robot-id", default=os.getenv("ROBOT_ID"), help="Current logged-in team/robot id.")
    parser.add_argument("--base-url", default=os.getenv("SIM_BASE_URL", "http://127.0.0.1:2026"))
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--measure-x", type=float, default=0.0)
    parser.add_argument("--measure-y", type=float, default=0.0)
    parser.add_argument("--clear-x", type=float, default=0.0)
    parser.add_argument("--clear-y", type=float, default=0.0)
    parser.add_argument("--log", default="代码/logs/api_smoke.jsonl")
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
        request_ids=RequestIdFactory("smoke"),
        logger=logger,
    )

    enter = client.enter()
    print("enter:", enter)

    measure = client.measure(Point(args.measure_x, args.measure_y), args.channel)
    result = measure["measure_result"]
    if result == "direction":
        print(f"measure: direction, svd_deg={measure['svd_deg']}")
    elif result == "near":
        print("measure: near")
    else:
        print("measure: no_signal")

    clear = client.clear(Point(args.clear_x, args.clear_y), args.channel)
    print("clear:", clear["clear_result"])

    exit_response = client.exit()
    print("exit:", exit_response.get("exit_reason"))
    print(f"log: {Path(args.log).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
