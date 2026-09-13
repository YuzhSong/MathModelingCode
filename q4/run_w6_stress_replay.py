#!/usr/bin/env python3
"""Replay existing W5 traces for Run 25/26/28 against W6 certificates.

No policy or simulator is executed.  This is an analysis of stored API-visible
events and action logs in their original order.
"""
from __future__ import annotations
import csv, json, math
from pathlib import Path
from q3.models import Point
from q4.w6_feasible_region import BearingObservation, persistent_bearing_region

ROOT = Path(__file__).resolve().parents[1]
TRACE_DIR = ROOT / "results/q4/w6a_decomposition/traces"
OUT = ROOT / "results/q4/w6_stress"
CASES = {25: "w5_random_25.json", 26: "w5_random_26.json", 28: "w5_random_28.json"}

def write_csv(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields=[]
    for row in data:
        for key in row:
            if key not in fields: fields.append(key)
    with open(path,'w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(data)

def replay(path, run_id):
    d=json.loads(path.read_text())
    by_channel={}
    rows=[]
    for event in sorted(d['events'], key=lambda e: float(e.get('time_s',0))):
        if event.get('event') not in {'w2_target_discovered','w2_direction_update'} or event.get('result') not in (None,'direction'):
            continue
        if event.get('svd_deg') is None or event.get('x') is None:
            continue
        ch=int(event['channel'])
        by_channel.setdefault(ch,[]).append(BearingObservation(Point(float(event['x']),float(event['y'])),float(event['svd_deg'])))
        region=persistent_bearing_region(by_channel[ch])
        rows.append({'run':run_id,'suite':d['details']['suite'],'seed':d['details']['seed'],'channel':ch,
                     'time_s':float(event['time_s']),'observation_count':len(by_channel[ch]),
                     'feasible_vertices':len(region.vertices),'mec_radius_m':region.mec.radius,
                     'mec_center_x':region.mec.center.x,'mec_center_y':region.mec.center.y,
                     'valid':int(region.valid),'clear_ready':int(region.valid and region.mec.radius <= 20.0)})
    source={int(s['channel']):s for s in d['sources']}
    actions=d['actions']; action_rows=[]
    for ch, s in source.items():
        ready=next((r for r in rows if r['channel']==ch and r['clear_ready']),None)
        clear_t=float(s['clear_time_s']) if s.get('clear_time_s') not in (None,'') else None
        after_measures=0; after_move=0.0
        if ready and clear_t is not None:
            prev=Point(0.0,0.0)
            for a in actions:
                cur=Point(float(a['x']),float(a['y']))
                if float(a.get('virtual_time_s',0)) > float(ready['time_s']) and float(a.get('virtual_time_s',0)) <= clear_t and int(a.get('channel',-1))==ch:
                    if a.get('action')=='measure': after_measures += 1
                if float(a.get('virtual_time_s',0)) > float(ready['time_s']) and float(a.get('virtual_time_s',0)) <= clear_t:
                    after_move += math.hypot(cur.x-prev.x,cur.y-prev.y)
                prev=cur
        action_rows.append({'run':run_id,'channel':ch,'first_ready_time_s':None if not ready else ready['time_s'],
                            'first_ready_observations':None if not ready else ready['observation_count'],
                            'actual_clear_time_s':clear_t,
                            'potential_saved_time_upper_bound_s':None if not ready or clear_t is None else max(0.0,clear_t-float(ready['time_s'])),
                            'measure_actions_after_ready_before_clear':after_measures,
                            'movement_m_after_ready_before_clear':after_move})
    return rows, action_rows, d

def main():
    timeline=[]; summary=[]; focus=[]
    for run_id, name in CASES.items():
        rows, action_rows, d=replay(TRACE_DIR/name,run_id); timeline += rows
        focus += action_rows
        for ch in sorted({int(x['channel']) for x in action_rows}):
            q=next(x for x in action_rows if int(x['channel'])==ch)
            summary.append({'run':run_id,'channel':ch,'first_ready_time_s':q['first_ready_time_s'],'actual_clear_time_s':q['actual_clear_time_s'],
                            'potential_saved_time_upper_bound_s':q['potential_saved_time_upper_bound_s'],'measure_actions_after_ready_before_clear':q['measure_actions_after_ready_before_clear'],
                            'movement_m_after_ready_before_clear':q['movement_m_after_ready_before_clear']})
    write_csv(OUT/'feasible_region_timeline.csv',timeline)
    write_csv(OUT/'replay_summary.csv',summary)
    focus_channels={7,12,10,18}
    write_csv(OUT/'focus_channels.csv',[x for x in focus if int(x['channel']) in focus_channels])
    ready=[x for x in summary if x['first_ready_time_s'] not in (None,'')]
    report=['# W6 Persistent Bearing Feasible-Region Replay','',
            '本报告只读取既有 W5 离线 trace，不执行 policy、不修改 simulator，也不调用官方接口。',
            '',f'- 输入：`{TRACE_DIR}` 中 `w5_random_25/26/28.json`；',
            f'- Run 数：3；记录了 {len(timeline)} 次历史 direction 后的可行域更新；',
            f'- 首次 `MEC<=20m` 的 channel 数：{len(ready)}；详细数据见 `replay_summary.csv`。','',
            '## 解释边界','',
            '可行域使用圆盘外接多边形与精确 bearing wedge half-plane clipping，MEC 只对外逼近多边形顶点求解。`no_signal` 未进入观测集合；空集或数值异常不会产生 clear-ready。',
            '', '本阶段是证书几何的 trace replay；新的 certificate 已接入 `q4/w6_policy.py`，但 replay 本身不重新执行 policy。Run 标签是存储的 `w5_random_25/26/28.json` 代理，当前资产中未找到能独立证明官方 Run 26 ch12 或 Run 28 ch10 的原始文件，因此不能把缺失 focus channel 当作零现象。','']
    (OUT/'report.md').write_text('\n'.join(report))
    print(json.dumps({'runs':3,'timeline_rows':len(timeline),'ready_channels':len(ready)},indent=2))
if __name__=='__main__': main()
