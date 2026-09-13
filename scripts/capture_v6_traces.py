from __future__ import annotations
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_sim.case import generate_case
from offline_sim.harness import run_episode
from q3.v6_policy import policy_v6

out = Path(__file__).resolve().parents[1] / "results" / "v6_traces"
out.mkdir(parents=True, exist_ok=True)
for seed in range(5):
    case = generate_case(seed=seed, problem=3, mode="practice", field_kind="smooth")
    result = run_episode(case, lambda runner: policy_v6(runner, n=8), include_oracles=False)
    x = y = 0.0
    events = []
    for a in result.action_log:
        e = {"op": a.action, "from": [x, y], "to": [a.x, a.y],
             "channel": a.channel, "time_s": a.virtual_time_s,
             "result": a.result}
        events.append(e); x, y = a.x, a.y
    payload = {"algorithm": "V6", "seed": seed, "problem": 3,
               "total": case.total, "cleared": result.cleared,
               "success": result.success, "virtual_time_s": result.virtual_time_s,
               "per_source_s": result.virtual_time_s / case.total if case.total else 0,
               "sources": [{"channel": j.channel, "x": j.x, "y": j.y,
                            "cleared": j.cleared} for j in case.jammers],
               "events": events, "metrics": {"move_distance_m": result.move_distance_m,
               "n_measure": result.n_measure, "n_clear": result.n_clear,
               "n_clear_fail": result.n_clear_fail, "error": result.error}}
    (out / f"v6_seed{seed}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(seed, payload["total"], payload["cleared"], payload["virtual_time_s"], payload["per_source_s"], len(events))
