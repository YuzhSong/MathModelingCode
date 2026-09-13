"""Run three reproducible V4 offline episodes and persist full action traces."""
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from offline_sim.case import generate_case
from offline_sim.harness import PolicyRunnerProxy, EpisodeRunner
from q3.offline_policy import policy_v4


def run(seed: int):
    case = generate_case(seed=seed, problem=3, field_kind="smooth", mode="formal")
    runner = EpisodeRunner(case)
    try:
        policy_v4(PolicyRunnerProxy(runner))
    except Exception as exc:
        runner.res.error = f"{type(exc).__name__}: {exc}"
    result = runner.finalize()
    return {
        "seed": seed,
        "result": asdict(result),
        "action_trace": [asdict(a) for a in result.action_log],
        "truth": [{"channel": j.channel, "x": j.x, "y": j.y,
                   "r_eff": j.r_eff, "kind": j.kind} for j in case.jammers],
    }


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "v4_traces"
    out_dir.mkdir(parents=True, exist_ok=True)
    seeds = [int(x) for x in (sys.argv[2:] or [1000, 1001, 1002])]
    for seed in seeds:
        payload = run(seed)
        path = out_dir / f"v4_detailed_trace_seed_{seed}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        r = payload["result"]
        print(json.dumps({"seed": seed, "success": r["success"],
                          "cleared": f"{r['cleared']}/{r['total']}",
                          "virtual_time_s": r["virtual_time_s"],
                          "move_distance_m": r["move_distance_m"],
                          "n_measure": r["n_measure"],
                          "n_clear": r["n_clear"], "trace_file": str(path)},
                         ensure_ascii=False))
