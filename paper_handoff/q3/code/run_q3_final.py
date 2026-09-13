from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from q3.api_client import RequestIdFactory, SimulatorClient
from q3.logger import JsonlLogger
from q3.models import ChannelStatus
from q3.run_logger import RunLogger, print_run_summary
from q3.v6_policy import policy_v6_official


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean Q3 final runner: RARC, fixed n=8, official simulator API."
    )
    parser.add_argument("--robot-id", default=os.getenv("ROBOT_ID"))
    parser.add_argument("--base-url", default=os.getenv("SIM_BASE_URL", "http://127.0.0.1:2026"))
    parser.add_argument(
        "--case-id",
        default=None,
        help="Test case code shown by the simulator UI. The API normally does not return it.",
    )
    parser.add_argument(
        "--test-kind",
        choices=("practice", "formal"),
        default="practice",
        help="Only affects local log labels. Choose formal for the three official attempts.",
    )
    parser.add_argument("--log", default="logs/q3_final_api.jsonl")
    return parser.parse_args()


def prompt_missing_args(args: argparse.Namespace) -> None:
    try:
        if not args.robot_id:
            args.robot_id = input("请输入参赛队号(须与模拟器登录队号完全一致): ").strip()
        if not args.case_id:
            case_id = input("请输入测试案例编码(可先留空, 结束后从模拟器日志列表补记): ").strip()
            args.case_id = case_id or None
    except EOFError:
        print()


def main() -> int:
    args = parse_args()
    prompt_missing_args(args)

    if not args.robot_id:
        print("未提供参赛队号, 已退出。", file=sys.stderr)
        return 2

    api_logger = JsonlLogger(Path(args.log))
    run_logger = RunLogger(
        base_dir="logs/q3_final",
        mode=args.test_kind,
        strategy="RARC",
        problem=3,
        case_id=args.case_id,
    )
    client = SimulatorClient(
        robot_id=args.robot_id,
        base_url=args.base_url,
        request_ids=RequestIdFactory("q3-rarc"),
        logger=api_logger,
        run_logger=run_logger,
    )

    policy = policy_v6_official(client, n=8)
    cleared = sum(1 for track in policy.tracks.values() if track.status == ChannelStatus.CLEARED)
    print(f"Q3 final RARC run complete: {cleared} channels cleared.")
    print(f"API log: {Path(args.log).resolve()}")
    if run_logger.summary:
        print_run_summary(run_logger.summary)
        print("Table 1 fields:")
        print(f"  测试案例编码: {run_logger.summary.get('case_id') or 'N/A'}")
        print(f"  清除干扰源个数: {run_logger.summary.get('cleared_count')}")
        print(f"  平均定位清除时间: {run_logger.summary.get('avg_time_per_cleared_s')}")
        print(f"  程序运行时间: {run_logger.summary.get('program_real_time_s')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
