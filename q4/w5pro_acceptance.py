"""Conservative acceptance gate for W5Pro benchmark artifacts."""
from __future__ import annotations

import csv
import json
from pathlib import Path


REQUIRED = {"total_time_s", "move_time_s", "measure_time_s",
            "clear_time_s", "channel_switch_time_s", "termination_reason"}


def check(directory: str | Path) -> dict:
    directory = Path(directory)
    details_path = directory / "details.csv"
    if not details_path.exists():
        return {"accepted": False, "reason": "missing details.csv"}
    with details_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    missing = sorted(REQUIRED - set(rows[0]) if rows else REQUIRED)
    truncated = [r for r in rows if r.get("termination_reason") == "max_macro_steps"]
    incomplete = [r for r in rows if str(r.get("success", "0")).lower() not in {"1", "true"}]
    accepted = bool(rows) and not missing and not truncated and not incomplete
    missing_exit_trace = []
    trace_dir = directory / "traces"
    if trace_dir.exists():
        for row in rows:
            base = f"{row.get('version')}_{row.get('suite')}"
            field = row.get("error_field", "smooth")
            trace = trace_dir / f"{base}_{field}_{row.get('seed')}.json"
            # Backward compatibility for artifacts produced before the
            # error-field dimension was added to trace names.
            if not trace.exists():
                trace = trace_dir / f"{base}_{row.get('seed')}.json"
            if not trace.exists():
                missing_exit_trace.append(trace.name)
                continue
            events = json.loads(trace.read_text(encoding="utf-8")).get("events", [])
            if not any(event.get("event") == "w5pro_exit_state" for event in events):
                missing_exit_trace.append(trace.name)
    if missing_exit_trace:
        accepted = False
    result = {"accepted": accepted, "episodes": len(rows),
              "missing_fields": missing,
              "truncated_episodes": len(truncated),
              "incomplete_episodes": len(incomplete)}
    result["missing_exit_trace"] = missing_exit_trace
    utilization = directory / "mechanism_utilization.json"
    if utilization.exists():
        result["mechanism_utilization"] = json.loads(utilization.read_text(encoding="utf-8"))
    if not (directory / "core_metrics.json").exists():
        accepted = False
        result["missing_core_metrics"] = True
    result["accepted"] = accepted
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = check(args.directory)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["accepted"] else 1)
