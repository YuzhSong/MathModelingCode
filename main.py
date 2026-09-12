from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Q3/Q4 unified entry point (practice/offline only).")
    parser.add_argument("--problem", choices=("3", "4"), default="3")
    parser.add_argument("--mode", choices=("official", "offline"), default="official")
    parser.add_argument(
        "--strategy",
        default="v4",
        help="Q3: v3/v4/v6. Q4: w5.",
    )
    parser.add_argument("--robot-id", default=os.getenv("ROBOT_ID"))
    parser.add_argument("--base-url", default=os.getenv("SIM_BASE_URL", "http://127.0.0.1:2026"))
    parser.add_argument("--search-points-n", type=int, default=8, help="Official V4/V6 outer search point count (default: 8).")
    parser.add_argument("--log", default="logs/q3_official.jsonl")
    parser.add_argument(
        "--update-source-count",
        nargs=2,
        metavar=("RUN_ID", "COUNT"),
        help="Backfill the official source count of a finished run and recompute derived stats.",
    )
    return parser.parse_args()


def prompt_missing_args(args: argparse.Namespace) -> None:
    """Interactively collect required official-mode inputs when not supplied via CLI/env."""
    try:
        if not args.robot_id:
            args.robot_id = input("请输入参赛队号(须与模拟器登录队号完全一致): ").strip()
    except EOFError:
        print()
        print("无交互输入, 已安全退出。", file=sys.stderr)


def main() -> int:
    args = parse_args()
    if args.update_source_count:
        from scripts.update_run_metadata import update_source_count

        run_id, count = args.update_source_count
        return update_source_count(run_id, int(count))
    if args.mode == "offline":
        from scripts.run_offline_eval import main as offline_main

        if args.problem != "3":
            print("Q4 offline benchmark 请使用 q4/run_w5_benchmark.py；main.py 只提供官方 Q4 W5 入口。", file=sys.stderr)
            return 2
        sys.argv = [sys.argv[0], "--versions", args.strategy]
        return offline_main()

    prompt_missing_args(args)

    if not args.robot_id:
        print("未提供参赛队号, 已退出。", file=sys.stderr)
        return 2

    if args.problem == "4":
        if args.strategy != "w5":
            print("Q4 官方模式当前只支持 --strategy w5。", file=sys.stderr)
            return 2
        from q3.api_client import RequestIdFactory, SimulatorClient
        from q3.logger import JsonlLogger
        from q3.run_logger import RunLogger, print_run_summary
        from q3.offline_policy import OfficialClientRunnerAdapter
        from q4.w5_policy import W5SymmetricDetectionPolicy

        logger = JsonlLogger(Path(args.log.replace("q3_", "q4_")))
        run_logger = RunLogger(base_dir="logs/q4", mode="practice", strategy="w5", problem=4)
        client = SimulatorClient(
            robot_id=args.robot_id,
            base_url=args.base_url,
            request_ids=RequestIdFactory("q4-w5"),
            logger=logger,
            run_logger=run_logger,
        )
        policy = W5SymmetricDetectionPolicy(OfficialClientRunnerAdapter(client))
        policy.run()
        print(f"Q4 W5 practice run complete; log: {logger.path.resolve()}")
        if run_logger.summary:
            print_run_summary(run_logger.summary)
        return 0

    if args.strategy not in ("v3", "v4", "v6"):
        print("官方模式仅支持 --strategy v3、v4 或 v6。", file=sys.stderr)
        return 2

    from q3.api_client import RequestIdFactory, SimulatorClient
    from q3.logger import JsonlLogger
    from q3.run_logger import RunLogger, print_run_summary

    logger = JsonlLogger(Path(args.log))
    run_logger = RunLogger(mode="practice", strategy=args.strategy)
    client = SimulatorClient(
        robot_id=args.robot_id,
        base_url=args.base_url,
        request_ids=RequestIdFactory("q3"),
        logger=logger,
        run_logger=run_logger,
    )
    if args.strategy == "v4":
        from q3.models import ChannelStatus
        from q3.offline_policy import policy_v4_official

        policy = policy_v4_official(client, n=args.search_points_n)
        cleared = sum(1 for t in policy.tracks.values() if t.status == ChannelStatus.CLEARED)
        print(f"Q3 V4 practice run complete: {cleared} channels cleared.")
        print(f"log: {Path(args.log).resolve()}")
        if run_logger.summary:
            print_run_summary(run_logger.summary)
        return 0

    if args.strategy == "v6":
        from q3.models import ChannelStatus
        from q3.v6_policy import policy_v6_official

        policy = policy_v6_official(client, n=args.search_points_n)
        cleared = sum(1 for t in policy.tracks.values() if t.status == ChannelStatus.CLEARED)
        print(f"Q3 V6 practice run complete: {cleared} channels cleared.")
        print(f"log: {Path(args.log).resolve()}")
        if run_logger.summary:
            print_run_summary(run_logger.summary)
        return 0

    from q3.planner import Q3BaselinePlanner, Q3Config

    summary = Q3BaselinePlanner(client, logger=logger, config=Q3Config()).run()
    print("Q3 practice summary:", summary)
    if run_logger.summary:
        print_run_summary(run_logger.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
