"""Offline-only W6 runner, shared tail diagnostics and paired comparisons."""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_sim.case import generate_case, generate_stress_case
from offline_sim.harness import run_episode
from q4.run_w0_baseline import percentile, parse_seed_range
from q4.run_w3_benchmark import strategy_case_row, source_local_rows
from q4.run_w4a_benchmark import write_union_csv
from q4.run_w5_benchmark import decompose_episode
from q4.tail_robustness import ObservedW5Policy
from q4.w1_policy import w1_search_points
from q4.w5_geometry import w5_detection_points
from q4.w5_policy import W5_SELECTED_SPEC

ROOT = Path(__file__).resolve().parents[1]


def frozen_hashes():
    paths = list((ROOT / "q3").glob("*.py")) + list((ROOT / "offline_sim").glob("*.py"))
    paths += [p for p in (ROOT / "q4").glob("*.py") if not ("w6" in p.name or p.name in {"stress_cases.py", "tail_robustness.py"})]
    paths += list((ROOT / "results/q4/w5").glob("*"))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}


def assert_isolated():
    forbidden = {"case", "engine", "sources", "jammers", "r_eff", "direction_deg"}
    for name in ("tail_robustness.py", "w6_policy.py"):
        path = ROOT / "q4" / name
        if not path.exists():
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Attribute) and node.attr in forbidden:
                raise AssertionError(f"Forbidden policy attribute: {name}:{node.lineno}")
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("offline_sim", "q4.stress_cases"))
            if isinstance(node, ast.Import):
                assert not any(n.name.startswith(("offline_sim", "q4.stress_cases")) for n in node.names)


def normal_case(suite, seed):
    if suite == "random":
        return generate_case(seed=seed, problem=4, margin_m=0.0, mode="practice", field_kind="smooth")
    return generate_stress_case(suite, seed=seed, problem=4, mode="practice", field_kind="adversarial", scan_points=[(p.x,p.y) for p in w1_search_points()])


def tail_sources(version, suite, seed, case, result):
    rows = source_local_rows(version, suite, seed, case, result)
    observations = [e for e in result.policy_diagnostics if e.get("event") == "tail_observation"]
    for row in rows:
        ch = row["channel"]
        found = row["first_found_time_s"]
        events = [e for e in observations if e["channel"] == ch and e["time_s"] > found + 1e-6]
        useful = [e for e in events if e["result"] in {"direction", "near"}]
        row["first_supplement_time_s"] = events[0]["time_s"] if events else None
        row["first_useful_after_found_time_s"] = useful[0]["time_s"] if useful else None
        row["found_to_next_useful_s"] = useful[0]["time_s"] - found if useful else None
        # Wait is distinct from explicit DEFERRED duration; includes dynamic scheduling.
        all_valid_times = [found] + [e["time_s"] for e in useful]
        row["max_useful_observation_gap_s"] = max([b-a for a,b in zip(all_valid_times, all_valid_times[1:])] or [0.0])
        row["movement_before_revisit_m"] = sum(math.hypot(b.x-a.x,b.y-a.y) for a,b in zip(result.action_log,result.action_log[1:]) if found < b.virtual_time_s <= (events[0]["start_time_s"] if events else found))
        deferred_at = None
        waits = []
        for e in events:
            if e["lifecycle_after"] == "deferred" and deferred_at is None:
                deferred_at = e["time_s"]
            if deferred_at is not None and e["lifecycle_after"] != "deferred":
                waits.append(e["time_s"] - deferred_at)
                deferred_at = None
        row["max_defer_until_observation_s"] = max(waits or [0.0])
        row["defer_cycles"] = max([e["deferred_count"] for e in events] or [0])
        streak = maximum = stable_small = 0
        for e in events:
            streak = streak+1 if e["result"] == "direction" else 0
            maximum = max(maximum, streak)
            # Diagnostic threshold from bearing uncertainty, not a policy trigger.
            stable_small += int(e["result"] == "direction" and e["bearing_variation_deg"] is not None and e["bearing_variation_deg"] <= 2*1.005 and e["move_m"] <= 20.0)
        row["max_consecutive_direction"] = maximum
        row["stable_small_measure_count"] = stable_small
        for name in ("geometry_acceleration", "rescue_attempt", "rescue_success", "rescue_failure"):
            row[name+"_count"] = sum(e.get("event") == "w6_"+name and e.get("channel") == ch for e in result.policy_diagnostics)
    return rows


def run_one(version, suite, seed, case, output):
    case_hash = hashlib.sha256(case.to_json().encode()).hexdigest()
    def policy(runner):
        if version == "w5":
            ObservedW5Policy(runner).run()
        else:
            from q4.w6_policy import W6Policy
            W6Policy(runner, variant=version).run()
    cpu_start = time.process_time()
    result = run_episode(case, policy, include_oracles=False)
    cpu = time.process_time()-cpu_start
    row = strategy_case_row(version,suite,seed,result,case)
    movement,_ = decompose_episode(suite,seed,result,w5_detection_points(W5_SELECTED_SPEC))
    row.update(movement)
    row.update(case_sha256=case_hash, policy_cpu_s=cpu, error=result.error or "", n=25)
    residual = result.virtual_time_s-(result.move_distance_m/5+5*result.n_measure+result.n_channel_switch+5*(result.n_clear-result.n_clear_fail)+3*result.n_clear_fail)
    row["time_residual_s"] = residual
    assert abs(residual) < 0.001, (suite,seed,residual)
    sources = tail_sources(version,suite,seed,case,result)
    for name in ("geometry_acceleration", "rescue_attempt", "rescue_success", "rescue_failure"):
        row[name+"_count"] = sum(e.get("event") == "w6_"+name for e in result.policy_diagnostics)
    trace = output / "traces" / f"{version}_{suite}_{seed}.json"
    trace.parent.mkdir(parents=True, exist_ok=True)
    trace.write_text(json.dumps({"case":json.loads(case.to_json()),"details":row,"sources":sources,"actions":[asdict(a) for a in result.action_log],"events":result.policy_diagnostics},ensure_ascii=False))
    return row,sources


def mean(xs):
    return statistics.fmean(xs) if xs else None


def summarize(details,sources):
    rows=[]
    for version in sorted({r["version"] for r in details}):
        for suite in sorted({r["suite"] for r in details})+["overall"]:
            rs=[r for r in details if r["version"]==version and (suite=="overall" or r["suite"]==suite)]
            ss=[s for s in sources if s["strategy"]==version and (suite=="overall" or s["suite"]==suite)]
            if not rs: continue
            times=[float(r["total_time_s"]) for r in rs]
            out={"version":version,"suite":suite,"cases":len(rs),"full_clear":sum(int(r["success"]) for r in rs),"clear_fail":sum(int(r["clear_fail"]) for r in rs),"unresolved":sum(int(r["targets_remaining_at_exit"]) for r in rs),"mean":mean(times),"median":statistics.median(times),"p95":percentile(times,.95),"max":max(times)}
            for field in ("move_distance_m","measure_count","switch_count","reacquisition_attempts","policy_cpu_s","rescue_attempt_count","rescue_success_count","rescue_failure_count","geometry_acceleration_count","search_move_distance_m"):
                out["mean_"+field]=mean([float(r[field]) for r in rs])
            ratios=[float(r["total_time_s"])/int(r["source_count"]) for r in rs]
            out.update(mean_t_per_source=mean(ratios),p95_t_per_source=percentile(ratios,.95))
            for field in ("found_to_clear_s","supplement_measure_count","max_defer_until_observation_s","max_useful_observation_gap_s","found_to_next_useful_s"):
                values=[float(s[field]) for s in ss if s.get(field) not in (None,"")]
                out["p95_"+field]=percentile(values,.95)
                out["max_"+field]=max(values,default=0)
            for limit in (50,100,200):
                out[f"sources_reacq_gt_{limit}"]=sum(int(s["reacquisition_attempts"])>limit for s in ss)
            rows.append(out)
    return rows


def paired(details):
    base={(r["suite"],int(r["seed"])):r for r in details if r["version"]=="w5"}
    cases=[]
    for r in details:
        if r["version"]=="w5": continue
        b=base.get((r["suite"],int(r["seed"])))
        if b is None: continue
        assert b["case_sha256"]==r["case_sha256"]
        cases.append({"version":r["version"],"suite":r["suite"],"seed":r["seed"],"w5_time":b["total_time_s"],"time":r["total_time_s"],"delta":float(r["total_time_s"])-float(b["total_time_s"]),"delta_move":float(r["move_distance_m"])-float(b["move_distance_m"]),"delta_measure":int(r["measure_count"])-int(b["measure_count"])})
    rows=[]
    for v in sorted({r["version"] for r in cases}):
        for suite in sorted({r["suite"] for r in cases})+["overall"]:
            selected=[r for r in cases if r["version"]==v and (suite=="overall" or r["suite"]==suite)]
            if not selected: continue
            ds=[r["delta"] for r in selected]
            rows.append({"version":v,"suite":suite,"pairs":len(ds),"win_rate":sum(d<0 for d in ds)/len(ds),"mean_delta":mean(ds),"median_delta":statistics.median(ds),"p95_delta":percentile(ds,.95),"worst_regression":max(ds),"best_improvement":min(ds),"regression_gt_100":sum(d>100 for d in ds),"regression_gt_300":sum(d>300 for d in ds)})
    return rows,cases


def write_outputs(output,details,sources):
    write_union_csv(output/"details.csv",details)
    write_union_csv(output/"source_tail.csv",sources)
    write_union_csv(output/"summary.csv",summarize(details,sources))
    ps,pc=paired(details)
    write_union_csv(output/"paired_comparison.csv",ps)
    write_union_csv(output/"paired_cases.csv",pc)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--versions",default="w5,w6a,w6b,w6c")
    parser.add_argument("--random-seeds",default="0:20")
    parser.add_argument("--stress-seeds",default="10000:10010")
    parser.add_argument("--output",type=Path,default=ROOT/"results/q4/w6_pilot")
    args=parser.parse_args()
    assert_isolated()
    frozen=frozen_hashes()
    args.output.mkdir(parents=True,exist_ok=True)
    manifest=args.output/"frozen_manifest.json"
    if manifest.exists(): assert json.loads(manifest.read_text())==frozen
    else: manifest.write_text(json.dumps(frozen,indent=2))
    details=[]; sources=[]
    for version in args.versions.split(","):
        for suite,seeds in (("random",parse_seed_range(args.random_seeds)),("min_reff",parse_seed_range(args.stress_seeds)),("collinear",parse_seed_range(args.stress_seeds))):
            for seed in seeds:
                trace=args.output/"traces"/f"{version}_{suite}_{seed}.json"
                if trace.exists():
                    saved=json.loads(trace.read_text()); row,ss=saved["details"],saved["sources"]
                else:
                    row,ss=run_one(version,suite,seed,normal_case(suite,seed),args.output)
                details.append(row); sources.extend(ss)
                print(f'{version}/{suite}/{seed}: T={row["total_time_s"]:.2f} clear={row["success"]}',flush=True)
        write_outputs(args.output,details,sources)
    assert frozen_hashes()==frozen,"Frozen dependency changed"


if __name__=="__main__": main()
