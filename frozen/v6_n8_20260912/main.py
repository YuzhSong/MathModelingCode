from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from q3.safety import PRACTICE_CONFIRMATION, require_practice_confirmation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Q3 unified entry point (practice/offline only).")
    parser.add_argument("--mode", choices=("official", "offline"), default="official")
    parser.add_argument(
        "--strategy",
        default="v4",
        help="Strategy generation. Offline: v0-v4. Official: v4 (default), v6 (explicit practice candidate), or v3.",
    )
    parser.add_argument("--robot-id", default=os.getenv("ROBOT_ID"))
    parser.add_argument("--base-url", default=os.getenv("SIM_BASE_URL", "http://127.0.0.1:2026"))
    parser.add_argument("--search-points-n", type=int, default=8, help="Official V4/V6 outer search point count (default: 8).")
    parser.add_argument("--confirm-practice", help=f"Required for official practice mode: {PRACTICE_CONFIRMATION}")
    parser.add_argument("--log", default="logs/q3_official.jsonl")
    return parser.parse_args()


def prompt_missing_args(args: argparse.Namespace) -> None:
    """Interactively collect required official-mode inputs when not supplied via CLI/env."""
    try:
        if not args.robot_id:
            args.robot_id = input("请输入参赛队号(须与模拟器登录队号完全一致): ").strip()
        if not args.confirm_practice:
            print()
            print("安全提示: 本程序只允许连接官方'问题3演练测试/模拟测试'。")
            print("请先在模拟器中开启'问题3演练测试'并等待5秒倒计时结束。")
            print("确认当前不是正式测试后, 输入 Q3_PRACTICE_ONLY 继续, 直接回车则安全退出。")
            args.confirm_practice = input("确认: ").strip() or None
    except EOFError:
        print()
        print("无交互输入, 已安全退出。", file=sys.stderr)


def main() -> int:
    args = parse_args()
    if args.mode == "offline":
        from scripts.run_offline_eval import main as offline_main

        sys.argv = [sys.argv[0], "--versions", args.strategy]
        return offline_main()

    prompt_missing_args(args)

    if not args.robot_id:
        print("未提供参赛队号, 已退出。", file=sys.stderr)
        return 2
    try:
        require_practice_confirmation(args.confirm_practice)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    if args.strategy not in ("v3", "v4", "v6"):
        print("官方模式仅支持 --strategy v3、v4 或 v6。", file=sys.stderr)
        return 2

    from q3.api_client import RequestIdFactory, SimulatorClient
    from q3.logger import JsonlLogger

    logger = JsonlLogger(Path(args.log))
    client = SimulatorClient(
        robot_id=args.robot_id,
        base_url=args.base_url,
        request_ids=RequestIdFactory("q3"),
        logger=logger,
    )
    if args.strategy == "v4":
        from q3.models import ChannelStatus
        from q3.offline_policy import policy_v4_official

        policy = policy_v4_official(client, n=args.search_points_n)
        cleared = sum(1 for t in policy.tracks.values() if t.status == ChannelStatus.CLEARED)
        print(f"Q3 V4 practice run complete: {cleared} channels cleared.")
        print(f"log: {Path(args.log).resolve()}")
        return 0

    if args.strategy == "v6":
        from q3.models import ChannelStatus
        from q3.v6_policy import policy_v6_official

        policy = policy_v6_official(client, n=args.search_points_n)
        cleared = sum(1 for t in policy.tracks.values() if t.status == ChannelStatus.CLEARED)
        print(f"Q3 V6 practice run complete: {cleared} channels cleared.")
        print(f"log: {Path(args.log).resolve()}")
        return 0

    from q3.planner import Q3BaselinePlanner, Q3Config

    summary = Q3BaselinePlanner(client, logger=logger, config=Q3Config()).run()
    print("Q3 practice summary:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
