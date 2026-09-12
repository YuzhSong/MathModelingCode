"""Backfill the official source count of a finished Q3 run.

The official API never reveals how many sources a case contains, so
summary.json starts with source_count=null. After a practice/formal session
the platform UI shows the count; record it here and the derived fields
(clear_rate, avg_time_per_source_s) are recomputed in both summary.json and
logs/q3/runs_summary.csv.

Usage:
    python scripts/update_run_metadata.py RUN_ID --source-count 14
    python main.py --update-source-count RUN_ID 14
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from q3.run_logger import RUNS_SUMMARY_FIELDS  # noqa: E402

BASE_DIR = Path("logs/q3")


def recompute(summary: dict) -> dict:
    source = summary.get("source_count")
    cleared = summary.get("cleared_count")
    total = summary.get("total_virtual_time_s")
    summary["clear_rate"] = (cleared / source) if (source and cleared is not None) else None
    summary["avg_time_per_source_s"] = (total / source) if (source and total is not None) else None
    if cleared and total is not None:
        summary["avg_time_per_cleared_s"] = total / cleared
    return summary


def update_source_count(run_id: str, source_count: int, base_dir: Path = BASE_DIR) -> int:
    run_dir = base_dir / run_id
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        print(f"找不到 {summary_path}", file=sys.stderr)
        return 2
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["source_count"] = int(source_count)
    summary = recompute(summary)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    target = base_dir / "runs_summary.csv"
    if target.exists():
        with target.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        for row in rows:
            if row.get("run_id") == run_id:
                row["source_count"] = summary["source_count"]
                row["clear_rate"] = summary["clear_rate"]
                row["avg_time_per_source_s"] = summary["avg_time_per_source_s"]
        with target.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=RUNS_SUMMARY_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key) for key in RUNS_SUMMARY_FIELDS})

    print(f"已补录 {run_id}: source_count={summary['source_count']}, "
          f"clear_rate={summary['clear_rate']}, avg_time_per_source_s={summary['avg_time_per_source_s']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill run metadata (source count) after an official session.")
    parser.add_argument("run_id")
    parser.add_argument("--source-count", type=int, required=True)
    parser.add_argument("--base-dir", default=str(BASE_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return update_source_count(args.run_id, args.source_count, Path(args.base_dir))


if __name__ == "__main__":
    raise SystemExit(main())
