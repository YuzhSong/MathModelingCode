"""Audit long refinement jumps and their local task neighborhoods."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--threshold-m", type=float, default=500.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    trace = json.loads(args.trace.read_text(encoding="utf-8"))
    actions = trace.get("action_log", [])
    jumps = []
    for index, action in enumerate(actions):
        if action.get("action") != "measure":
            continue
        before = actions[index - 1] if index else {"x": 0.0, "y": 0.0}
        distance = math.hypot(float(action["x"]) - float(before["x"]),
                              float(action["y"]) - float(before["y"]))
        if distance < args.threshold_m:
            continue
        jumps.append({
            "action_index": index,
            "channel": action.get("channel"),
            "distance_m": distance,
            "from": [before.get("x", 0.0), before.get("y", 0.0)],
            "to": [action.get("x"), action.get("y")],
            "previous_action": before.get("action"),
            "previous_channel": before.get("channel"),
        })
    marginal = [event for event in trace.get("events", [])
                if event.get("event") == "w5pro_route_marginal_candidates"]
    result = {
        "trace": str(args.trace),
        "threshold_m": args.threshold_m,
        "measure_actions": sum(1 for item in actions if item.get("action") == "measure"),
        "long_jump_count": len(jumps),
        "long_jumps": jumps,
        "route_marginal_event_count": len(marginal),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("long_jump_count", "route_marginal_event_count")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
