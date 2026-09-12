"""Persist complete deterministic stress fixtures before offline paired replay."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from q4.run_w6_benchmark import ROOT, assert_isolated, frozen_hashes, run_one, write_outputs
from q4.run_w4a_benchmark import write_union_csv
from q4.stress_cases import tail_stress_cases


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--versions",default="w5,w6a,w6b,w6c")
    parser.add_argument("--output",type=Path,default=ROOT/"results/q4/w6_stress")
    args=parser.parse_args()
    assert_isolated()
    frozen=frozen_hashes()
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/"fixtures").mkdir(exist_ok=True)
    details=[]; sources=[]; targets=[]
    for version in args.versions.split(","):
        for family,seed,case,channel in tail_stress_cases():
            fixture=args.output/"fixtures"/f"{family}_{seed}.json"
            if fixture.exists(): assert json.loads(fixture.read_text())==json.loads(case.to_json())
            else: fixture.write_text(case.to_json())
            trace=args.output/"traces"/f"{version}_{family}_{seed}.json"
            if trace.exists():
                saved=json.loads(trace.read_text()); row,ss=saved["details"],saved["sources"]
            else:
                row,ss=run_one(version,family,seed,case,args.output)
            details.append(row); sources.extend(ss)
            target=next((s for s in ss if s["channel"]==channel),{})
            targets.append({**target,"episode_time_s":row["total_time_s"],"episode_move_m":row["move_distance_m"]})
            print(f'{version}/{family}/{seed}: T={row["total_time_s"]:.2f} clear={row["success"]}',flush=True)
        write_outputs(args.output,details,sources)
        write_union_csv(args.output/"target_comparison.csv",targets)
    assert frozen_hashes()==frozen


if __name__=="__main__": main()
