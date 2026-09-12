"""Post-episode analysis only; reconstruct exact defer episodes from event order."""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from q4.run_w0_baseline import percentile
from q4.run_w4a_benchmark import write_union_csv
from q4.run_w6_benchmark import ROOT, paired, write_outputs


def exact_source_metrics(trace):
    events=trace["events"]
    clock=0.0
    starts={}; durations=defaultdict(list)
    counts=defaultdict(int)
    for e in events:
        clock=max(clock,float(e.get("time_s",clock)))
        ch=e.get("channel")
        if e["event"]=="w2_target_deferred":
            starts.setdefault(ch,clock)
            counts[ch]+=1
        if e["event"] in {"w2_target_reactivated","w2_reacquisition_success","w2_target_resolved"} and ch in starts:
            durations[ch].append(clock-starts.pop(ch))
    for ch,start in starts.items():
        durations[ch].append(clock-start)
    observations=[dict(e) for e in events if e["event"]=="tail_observation"]
    measurements=[a for a in trace["actions"] if a["action"]=="measure"]
    assert len(observations)==len(measurements)
    for e,a in zip(observations,measurements):
        assert e["channel"]==a["channel"]
        # `near` clears synchronously; use the actual measurement completion,
        # not the observer's post-clear timestamp, for observation delays.
        e["time_s"]=a["virtual_time_s"]
    rows=[]
    for row in trace["sources"]:
        row=dict(row)
        ch=row["channel"]
        obs=[e for e in observations if e["channel"]==ch and e["result"]!="unknown_no_signal"]
        useful=[e for e in obs if e["result"] in {"direction","near"}]
        found=row["first_found_time_s"]
        after=[e for e in obs if e["time_s"]>found+1e-6]
        next_useful=[e for e in useful if e["time_s"]>found+1e-6]
        row["first_supplement_time_s"]=after[0]["time_s"] if after else None
        row["first_useful_after_found_time_s"]=next_useful[0]["time_s"] if next_useful else None
        row["found_to_next_useful_s"]=next_useful[0]["time_s"]-found if next_useful else None
        row["explicit_defer_cycles"]=counts[ch]
        row["explicit_defer_total_s"]=sum(durations[ch])
        row["explicit_defer_max_s"]=max(durations[ch],default=0)
        row["total_measures_after_found"]=len([e for e in obs if e["time_s"]>found+1e-6])
        row["total_channel_measure_count"]=sum(a["channel"]==ch for a in measurements)
        row["initial_mec_m"]=useful[0]["mec_radius_m"] if useful else None
        row["final_observed_mec_m"]=useful[-1]["mec_radius_m"] if useful else None
        reacquired=[e for e in useful if e["role"] in {"reacquire","search_reacquire"}]
        row["first_successful_reacquisition_s"]=reacquired[0]["time_s"] if reacquired else None
        row["mec_ready_with_legacy_check_disabled_count"]=sum(e["result"]=="direction" and e["mec_radius_m"] is not None and e["mec_radius_m"]<=20 and (e["fallback_active"] or e["mec_checks"]>=32) for e in obs)
        row["large_lower_extent_small_step_count"]=sum(e["longitudinal_low_m"] is not None and e["longitudinal_low_m"]>e["step_after_m"] and e["step_after_m"]<=20 for e in obs)
        row["second_observation_no_signal"]=int(len(obs)>1 and obs[1]["result"]=="no_signal")
        row["visibility_alternations"]=sum((a["result"]=="no_signal")!=(b["result"]=="no_signal") for a,b in zip(obs,obs[1:]))
        rows.append(row)
    return rows


def audit(directory):
    details=[]; sources=[]; sequence=[]; phase=[]; rescue_failures=[]
    for file in sorted((directory/"traces").glob("*.json")):
        trace=json.loads(file.read_text())
        row=trace["details"]
        truth={j["channel"]:j for j in trace["case"]["jammers"]}
        for e in trace["events"]:
            if e["event"]!="w3_probe_outcome" or e.get("kind")!="rescue" or e.get("result")!="no_signal":
                continue
            j=truth[e["channel"]]
            dx=e["x"]-j["x"]; dy=e["y"]-j["y"]
            radius=math.hypot(dx,dy)
            inside=True
            if j["kind"]=="dir":
                angle=math.radians(j["direction_deg"])
                inside=dx*math.cos(angle)+dy*math.sin(angle)>=-1e-8
            reason="outside_radius" if radius>j["r_eff"] else "backside" if not inside else "other"
            rescue_failures.append({"version":row["version"],"suite":row["suite"],"seed":row["seed"],"channel":e["channel"],"time_s":e["time_s"],"reason":reason,"distance_m":radius,"receive_radius_m":j["r_eff"]})
        details.append(row)
        sources.extend(exact_source_metrics(trace))
        streaks=defaultdict(int)
        for e in trace["events"]:
            if e["event"]=="tail_observation":
                ch=e["channel"]
                streaks[ch]=streaks[ch]+1 if e["result"]=="direction" else 0
                sequence.append({"version":row["version"],"suite":row["suite"],"seed":row["seed"],**e,"consecutive_direction_count":streaks[ch]})
        phases=defaultdict(lambda:[0.0,0,0,0.0])
        prev=(0.0,0.0); channel=1
        # Match recorded roles, not endpoint proximity (SEARCH may also reacquire).
        role_events=[e for e in trace["events"] if e["event"]=="tail_observation"]
        measure_index=0
        for a in trace["actions"]:
            movement=math.hypot(a["x"]-prev[0],a["y"]-prev[1])
            if a["action"]=="clear":
                category="CLEAR"
            else:
                role=role_events[measure_index]["role"]
                measure_index+=1
                category="SEARCH" if role.startswith("search") else "FOUND"
            p=phases[category]; p[0]+=movement/5
            if a["action"]=="measure":
                p[1]+=1; p[2]+=int(channel!=a["channel"]); channel=a["channel"]
            else: p[3]+=5 if a["result"]=="success" else 3
            prev=(a["x"],a["y"])
        total=0
        for category,(move,measures,switches,clear) in phases.items():
            t=move+5*measures+switches+clear; total+=t
            phase.append({"version":row["version"],"suite":row["suite"],"seed":row["seed"],"phase":category,"move_time":move,"measure_time":5*measures,"switch_time":switches,"clear_time":clear,"total":t})
        assert abs(total-row["total_time_s"])<0.001
    write_outputs(directory,details,sources)
    write_union_csv(directory/"source_tail_exact.csv",sources)
    write_union_csv(directory/"measurement_sequences.csv",sequence)
    write_union_csv(directory/"phase_details.csv",phase)
    write_union_csv(directory/"rescue_failure_taxonomy.csv",rescue_failures)
    summaries=[]
    for version in sorted({r["version"] for r in details}):
        ss=[s for s in sources if s["strategy"]==version]
        out={"version":version,"sources":len(ss)}
        for key in ("explicit_defer_max_s","explicit_defer_total_s","found_to_next_useful_s","found_to_clear_s","total_measures_after_found","total_channel_measure_count","reacquisition_attempts","max_useful_observation_gap_s"):
            vals=[float(s[key]) for s in ss if s.get(key) not in (None,"")]
            out["mean_"+key]=statistics.fmean(vals) if vals else None
            out["p95_"+key]=percentile(vals,.95)
            out["max_"+key]=max(vals,default=0)
        for key in ("mec_ready_with_legacy_check_disabled_count","large_lower_extent_small_step_count","stable_small_measure_count","rescue_attempt_count","rescue_success_count","rescue_failure_count"):
            out[key]=sum(s[key] for s in ss)
        summaries.append(out)
    write_union_csv(directory/"tail_summary_exact.csv",summaries)
    ps=[]
    for v in sorted({r["version"] for r in details}):
        n=sum(r["version"]==v for r in details)
        for category in ("SEARCH","FOUND","CLEAR"):
            rs=[p for p in phase if p["version"]==v and p["phase"]==category]
            ps.append({"version":v,"phase":category,**{k:sum(p[k] for p in rs)/n for k in ("move_time","measure_time","switch_time","clear_time","total")}})
    write_union_csv(directory/"phase_summary.csv",ps)
    by_count=[]
    for version in sorted({r["version"] for r in details}):
        for n in range(10,17):
            rs=[r for r in details if r["version"]==version and int(r["source_count"])==n]
            values=[r["total_time_s"]/n for r in rs]
            by_count.append({"version":version,"source_count":n,"cases":len(rs),"mean_time":statistics.fmean(r["total_time_s"] for r in rs) if rs else None,"mean_t_per_source":statistics.fmean(values) if values else None,"p95_t_per_source":percentile(values,.95) if values else None})
    write_union_csv(directory/"by_source_count.csv",by_count)
    baseline={(r["suite"],int(r["seed"])):r for r in csv.DictReader((ROOT/"results/q4/w5/details.csv").open())}
    checks=[]
    for r in details:
        key=(r["suite"],int(r["seed"]))
        if r["version"]=="w5" and key in baseline:
            b=baseline[key]
            checks.append({"suite":key[0],"seed":key[1],"time_delta":r["total_time_s"]-float(b["total_time_s"]),"move_delta":r["move_distance_m"]-float(b["move_distance_m"]),"measure_delta":r["measure_count"]-int(b["measure_count"])})
    write_union_csv(directory/"frozen_replay_check.csv",checks)
    assert all(r["time_delta"]==r["move_delta"]==r["measure_delta"]==0 for r in checks)
    return details,sources


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("directory",type=Path)
    args=parser.parse_args()
    details,sources=audit(args.directory)
    print(f"Audited {len(details)} episodes and {len(sources)} sources; phase identity and frozen replay passed.")
