from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from q3.api_client import RequestIdFactory, SimulatorClient
from q3.logger import JsonlLogger
from q3.planner import Q3BaselinePlanner, Q3Config
from q3.run_logger import RunLogger, print_run_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Q3 official runner.")
    parser.add_argument(
        "--strategy",
        choices=("v3", "v4", "v6"),
        default="v6",
        help="v6: route-aware supplement (default); v4: frozen official baseline; v3: baseline planner.",
    )
    parser.add_argument("--robot-id", default=os.getenv("ROBOT_ID"), help="Current logged-in team/robot id.")
    parser.add_argument("--base-url", default=os.getenv("SIM_BASE_URL", "http://127.0.0.1:2026"))
    parser.add_argument("--log", default="logs/q3_official.jsonl")
    parser.add_argument("--search-radius", type=float, default=1150.0, help="v3 baseline planner search ring radius.")
    parser.add_argument("--search-points-n", type=int, default=8, help="v4 outer ring point count.")
    parser.add_argument("--max-localization-measures", type=int, default=8, help="v3 baseline planner localization cap.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.robot_id:
        print("请通过 --robot-id 或环境变量 ROBOT_ID 指定当前登录参赛队号。", file=sys.stderr)
        return 2

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

    planner = Q3BaselinePlanner(
        client,
        logger=logger,
        config=Q3Config(search_radius=args.search_radius, max_localization_measures=args.max_localization_measures),
    )
    summary = planner.run()
    print("Q3 baseline summary:", summary)
    print(f"log: {Path(args.log).resolve()}")
    if run_logger.summary:
        print_run_summary(run_logger.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
