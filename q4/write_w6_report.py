"""Rebuild the requested Markdown report from audited offline outputs."""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
from pathlib import Path

from q4.analyze_w6 import audit
from q4.run_w4a_benchmark import write_union_csv
from q4.run_w6_benchmark import ROOT, frozen_hashes


def read(path):
    with path.open() as handle:
        return list(csv.DictReader(handle))


def fmt(value):
    if value in (None,""): return "NA"
    if isinstance(value,str):
        try: value=float(value)
        except ValueError: return value
    if value==int(value): return str(int(value))
    return f"{value:.2f}"


def table(rows, fields):
    lines=["| "+" | ".join(label for _,label in fields)+" |", "|"+"---|"*len(fields)]
    lines.extend("| "+" | ".join(f"{float(r[key])*100:.1f}%" if key=="win_rate" else fmt(r.get(key)) for key,_ in fields)+" |" for r in rows)
    return "\n".join(lines)


def main():
    final=ROOT/"results/q4/w6"
    pilot=ROOT/"results/q4/w6_pilot"
    stress=ROOT/"results/q4/w6_stress"
    for directory in (final,pilot,stress): audit(directory)
    summaries=read(final/"summary.csv")
    normal=[r for r in summaries if r["suite"]=="overall"]
    assert {(r["version"],int(r["cases"])) for r in normal}=={("w5",200),("w6a",200)}
    baseline=next(r for r in normal if r["version"]=="w5")
    candidate=next(r for r in normal if r["version"]=="w6a")
    pilot_summary=[r for r in read(pilot/"summary.csv") if r["suite"]=="overall"]
    stress_summary=[r for r in read(stress/"summary.csv") if r["suite"]=="overall"]
    tails=read(final/"tail_summary_exact.csv")
    pairs=read(final/"paired_comparison.csv")
    pc=read(final/"paired_cases.csv")
    source=read(final/"source_tail_exact.csv")
    base_source={(r["suite"],int(r["seed"]),int(r["channel"])):r for r in source if r["strategy"]=="w5"}
    variant_source={(r["suite"],int(r["seed"]),int(r["channel"])):r for r in source if r["strategy"]=="w6a"}
    repaired=[]
    for key,b in base_source.items():
        if int(b["reacquisition_attempts"])<=50: continue
        v=variant_source[key]
        repaired.append({"suite":key[0],"seed":key[1],"channel":key[2],"w5_attempts":b["reacquisition_attempts"],"w6_attempts":v["reacquisition_attempts"],"w5_found_clear":b["found_to_clear_s"],"w6_found_clear":v["found_to_clear_s"],"delta_found_clear":float(v["found_to_clear_s"])-float(b["found_to_clear_s"])})
    write_union_csv(final/"original_tail_sources.csv",repaired)
    worst=sorted(pc,key=lambda r:float(r["delta"]),reverse=True)[:5]
    detail_map={(r["version"],r["suite"],int(r["seed"])):r for r in read(final/"details.csv")}
    regressions=[]
    for r in pc:
        if float(r["delta"])<=100: continue
        key=(r["suite"],int(r["seed"]))
        b=detail_map[("w5",*key)]; v=detail_map[("w6a",*key)]
        delta_move=float(v["move_time_s"])-float(b["move_time_s"])
        delta_measure=float(v["measure_time_s"])-float(b["measure_time_s"])
        delta_switch=float(v["switch_time_s"])-float(b["switch_time_s"])
        delta_clear=float(v["clear_time_s"])-float(b["clear_time_s"])
        assert abs(sum((delta_move,delta_measure,delta_switch,delta_clear))-float(r["delta"]))<.001
        regressions.append({**r,"delta_move_time_s":delta_move,"delta_measure_time_s":delta_measure,"delta_switch_time_s":delta_switch,"delta_clear_time_s":delta_clear})
    write_union_csv(final/"regression_decomposition.csv",sorted(regressions,key=lambda r:float(r["delta"]),reverse=True))
    typical={("random",s) for s in (81,9,64,58)}|{(r["suite"],int(r["seed"])) for r in worst}
    timeline=[]
    for suite,seed in sorted(typical):
        for version in ("w5","w6a"):
            trace=json.loads((final/"traces"/f"{version}_{suite}_{seed}.json").read_text())
            observations=iter(e for e in trace["events"] if e["event"]=="tail_observation")
            previous=(0.0,0.0)
            for action in trace["actions"]:
                e=next(observations) if action["action"]=="measure" else {}
                movement=((action["x"]-previous[0])**2+(action["y"]-previous[1])**2)**.5
                timeline.append({"version":version,"suite":suite,"seed":seed,**action,"move_m":movement,**{k:e.get(k) for k in ("role","mec_radius_m","longitudinal_low_m","longitudinal_high_m","step_after_m","lifecycle_after","bearing_variation_deg")}})
                previous=(action["x"],action["y"])
    write_union_csv(final/"typical_timelines.csv",timeline)
    detail=read(final/"details.csv")
    parts=[]
    for version in ("w5","w6a"):
        rows=[r for r in detail if r["version"]==version]
        parts.append({"version":version,**{k:statistics.fmean(float(r[k]) for r in rows) for k in ("move_time_s","measure_time_s","switch_time_s","clear_time_s")}})
    write_union_csv(final/"time_decomposition.csv",parts)
    manifest=json.loads((final/"frozen_manifest.json").read_text())
    assert frozen_hashes()==manifest
    policy_files=[ROOT/"q4"/n for n in ("w6_policy.py","tail_robustness.py","run_w6_benchmark.py","stress_cases.py","run_w6_stress_benchmark.py","analyze_w6.py","write_w6_report.py","test_w6.py")]
    metadata={"selected":"w6a","official_calls":0,"random_seeds":"0:100","stress_seeds":"10000:10050","pilot_random":"0:20","pilot_stress":"10000:10010","random_margin_m":0,"historical_stress_layout":"unchanged: min_reff R-30; collinear +/-1700 with jitter","policy_sha256":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in policy_files},"max_time_identity_residual_s":max(abs(float(r["time_residual_s"])) for r in detail),"frozen_replay_exact_cases":len(read(final/"frozen_replay_check.csv"))}
    (final/"metadata.json").write_text(json.dumps(metadata,indent=2))

    main_fields=[("version","策略"),("full_clear","全清局数"),("mean","Mean s"),("p95","P95 s"),("max","Max s"),("mean_move_distance_m","Move m"),("mean_measure_count","Measures"),("mean_reacquisition_attempts","Reacq"),("clear_fail","clear fail"),("unresolved","unresolved")]
    a_delta={k:float(candidate[k])-float(baseline[k]) for k in ("mean","p95","max","mean_move_distance_m","mean_reacquisition_attempts")}
    phase=read(final/"phase_summary.csv")
    tail_fields=[("version","策略"),("max_found_to_clear_s","Max F→C s"),("p95_found_to_clear_s","P95 F→C s"),("max_total_measures_after_found","Max 补测/源"),("p95_total_measures_after_found","P95 补测/源"),("max_explicit_defer_max_s","Max 显式 defer s"),("p95_explicit_defer_max_s","P95 显式 defer s")]
    tail_thresholds=[{k:r[k] for k in ("version","sources_reacq_gt_50","sources_reacq_gt_100","sources_reacq_gt_200")} for r in normal]
    stress_target=read(stress/"target_comparison.csv")
    stress_b=next(r for r in stress_summary if r["version"]=="w6b")
    selected_original= [r for r in stress_target if r["suite"]=="stable_bearing_replay" and r["strategy"] in {"w5","w6a"}]
    hard=all(int(candidate[k])==expected for k,expected in (("full_clear",200),("clear_fail",0),("unresolved",0)))
    tail_ok=float(candidate["max"])<=float(baseline["max"]) and int(candidate["sources_reacq_gt_100"])<int(baseline["sources_reacq_gt_100"])
    ordinary_ok=all(float(candidate[k])<=float(baseline[k]) for k in ("mean","p95","mean_move_distance_m"))
    conclusion="W6-A 的局部长尾修复有效，可作为另行授权后的对照演练候选；但仍有严重 same-seed 回退，本轮不直接替换 frozen W5。B/C 不纳入候选。" if hard and tail_ok and ordinary_ok else "本轮不建议替换 frozen W5；W6-A 仅保留为长尾机制实验，不能因局部改善忽略完整验收条件。"
    lines=[
        "# Q4 W6：Tail Robustness Optimization",
        "",
        conclusion,
        "",
        "## 1. 实验边界与数据",
        "只运行本地 offline_sim，没有调用官方演练或正式接口。W5 的原始源码与已有结果哈希逐项未变。25 点 a=970、p=140，W4-A task pool/router，生命周期、DEFERRED/REACQUIRE 与显式退出条件均沿用；不继承 W4-B，不进入 W7。",
        "主比较：random 0–99、min_reff/collinear 各 10000–10049，共200局/版本；source_count 只用于 episode 完成后的统计。策略仅接收受限 API proxy。逐 case JSON 的 SHA256 要求同 seed 完全一致。",
        "重要历史口径：random 显式 margin_m=0；原 stress helper 没有 margin 参数，min_reff 内置1770m圆盘，collinear 内置约±1700m直线。本轮为保持 frozen same-case 不改生成器，不能把全部200局写成边界零裕量随机分布。新增 outward stress 精确包含 r=1800、R_eff=1000。",
        "pilot 为20 random+10 min_reff+10 collinear。完整200局包含pilot，且4个 stable-bearing stress 是已有离线难例重放，因此不是独立外部测试，也不能把两组样本量相加声称更强统计保证。",
        "",
        "## 2. W5 长尾根因",
        "失败减半后的 local.step_m 会持续限制后续 adaptive_step，即使在另一个 SEARCH 点重新观察、实际距离重新变大；成功不恢复步长。fallback_active 持续锁定5m族，MEC检查最多32次且fallback中禁用。REACQUIRE状态又不走普通ACTIVE的MEC判断。",
        "random81/channel12在t=6285.801623s的新区域沿bearing投影为1251.375–1290.243m，步长却仍5.21327m。随后0.03°级方向变化对应大量有效小步，直接说明历史步长上限与新几何不匹配。",
        "本地仅有Q4 practice001/002日志，未找到官方Run7/channel19的原始轨迹。Run7数值来自用户描述；本报告只复现offline analogues，不声称精确修复该官方case。",
        "",
        "## 3. W6-A 的几何定义",
        "令G为当前可行多边形、A为最后有效观测点、u为测得bearing单位向量，计算 l=min_{g∈G}(g−A)·u。仅当l大于W5原步长时，提出 s=min(l,600m)，P=A+s·u；600m为冻结W3已有上限，不是新调参。",
        "l来自多边形支撑投影，候选不会跨过可行域最近的纵向支撑平面，但**不能保证不越过未知定向半平面**。每份有效观测状态最多尝试一次加速点，已知no_signal坐标不重复；失败后保留全部有效几何并走原W5缩步/侧向/DEFERRED流程，不丢目标。",
        "第二部分恢复在fallback或32次上限后被跳过的局部MEC检查，只在MEC≤20.0时产生原CLEAR任务；near仍原地立即clear。这是局部tail处理，不改变阈值、几何误差或router。代码不以bearing差小于某常数来触发加速；方向稳定只作为诊断指标。",
        "A内部没有进一步拆分“投影步长”和“恢复被跳过的MEC检查”，因此本轮不能分别估计两者的因果贡献，不能将A的所有收益都归为单纯走大步。",
        "",
        "## 4. W6-B 的有界局部救援",
        "每个源只在首个专门LOCALIZE/REACQUIRE失败后开启一次机会；不是每次no_signal都抢占。用可行域垂直bearing方向的宽度w构造当前点左右两个候选 P±w·n。按到当前router所选下一任务B的 detour 排序。",
        "预算取当前到B的距离D；每次试探扣除 d(P,S)+d(S,B)−d(P,B)+5×(5+1) 米等价成本，分别对应移动、5秒测量、最坏1秒切频道。两侧各只试一次且共享递减预算；无固定200m、500m或自由alpha/lambda。成功返回ACTIVE；确实执行救援且失败后显式DEFERRED，下一次SEARCH完成后沿用原机制激活；无SEARCH剩余时原task builder仍处理DEFERRED目标，不会遗留。",
        "这仍是启发式预算和候选规则，不是可见性保证；同量纲不意味着最优。其有限候选数来自两个侧向方向，不以pilot反复调次数。它只覆盖首次专门补测失败，不覆盖所有在SEARCH期间发生的失联。",
        "",
        "## 5. A/B/C 分离消融",
        "### 固定40局pilot",
        table(pilot_summary,main_fields),
        "### 24局tail stress",
        table(stress_summary,main_fields),
        "实现复核曾发现B初版预算耗尽后仅交回router，未显式DEFERRED；这与要求不符。修正该状态收尾后，B/C的40局pilot与24局stress均重新运行，初版结果独立保存在pre_defer_fix，不与本表混用。A分支未改变，完整200局也不据此调参。",
        f"B在stress平均每局尝试{float(stress_b['mean_rescue_attempt_count']):.2f}次救援，成功{float(stress_b['mean_rescue_success_count']):.2f}次；不能据此声称已解决长期等待。修正后的C可能在定向stress上优于A，但普通pilot的P95/Max更差，因此仍保留A用于完整200局，不把stress收益当作稳健升级证据。B/C不继续完整跑分；逐个救援失败的距离/背面构成见各目录rescue_failure_taxonomy.csv（仅事后使用真值）。",
        "",
        "## 6. 完整200局",
        table(normal,main_fields),
        table(normal,[("version","策略"),("mean_t_per_source","Mean T/N s"),("p95_t_per_source","P95 T/N s"),("mean_policy_cpu_s","平均CPU s/局")]),
        f"W6-A减W5：Mean {a_delta['mean']:+.2f}s，P95 {a_delta['p95']:+.2f}s，Max {a_delta['max']:+.2f}s，移动 {a_delta['mean_move_distance_m']:+.2f}m。",
        "CPU为带相同观察器的完整policy+本地runner process_time，不是Windows网络实测；观察器会额外重建几何，所以不能直接解释为生产版本实时开销。",
        "",
        "## 7. Same-seed paired comparison",
        table(pairs,[("suite","组"),("pairs","配对数"),("win_rate","Win rate"),("mean_delta","Mean Δs"),("median_delta","Median Δs"),("p95_delta","P95 Δs"),("worst_regression","Worst Δs"),("regression_gt_100",">100s"),("regression_gt_300",">300s")]),
        "胜率分母包括平局；Δ=T_W6A−T_W5。不是仅报告获胜案例。",
        "### 最坏五局",
        table(worst,[("suite","组"),("seed","seed"),("w5_time","W5 s"),("time","W6-A s"),("delta","Δs"),("delta_move","Δmove m"),("delta_measure","Δmeasure")]),
        "所有>100s回退逐局分解见regression_decomposition.csv，移动/测量/切频道/clear四项之和与总回退一致。例如random41：+863.53s移动、+410s测量、+73s切频道，合计+1346.53s。",
        "定位候选位置改变后，即便router代码冻结，全局任务共存关系和访问顺序仍可能改变。局部步数减少不保证每局总路程下降。各case完整轨迹保存在traces，典型逐动作对照在typical_timelines.csv；不能把所有时间变化都解释成步长本身。",
        "",
        "## 8. Tail-specific 指标",
        table(normal,[("version","策略"),("sources_reacq_gt_50",">50/源"),("sources_reacq_gt_100",">100/源"),("sources_reacq_gt_200",">200/源"),("mean_geometry_acceleration_count","加速次数/局")]),
        table(tails,tail_fields),
        table(tails,[("version","策略"),("max_total_channel_measure_count","Max 每真实频道总measure"),("p95_total_channel_measure_count","P95 每真实频道总measure")]),
        table(tails,[("version","策略"),("max_found_to_next_useful_s","Max FOUND→下一有效观测 s"),("p95_found_to_next_useful_s","P95 同指标 s"),("stable_small_measure_count","稳定小步measure总数")]),
        "显式defer按事件顺序重建：w2_target_deferred至reactivated/有效reacquire/clear；没有时间戳的转换继承当时最近虚拟时钟。FOUND→下一有效观测还包含调度等待，不与defer混用。没有后续观测就clear的目标，其下一观测等待记NA而不是0；每真实频道总measure包括FOUND之前的扫描。稳定小步诊断采用方向差≤2×1.005°、实际移动≤20m，仅用于统计，不是policy阈值。",
        "### 原W5五个>50次目标的修复",
        table(repaired,[("suite","组"),("seed","seed"),("channel","ch"),("w5_attempts","W5 reacq"),("w6_attempts","W6-A reacq"),("w5_found_clear","W5 F→C"),("w6_found_clear","W6 F→C"),("delta_found_clear","ΔF→C")]),
        "random58/channel15是必须保留的反例：补测次数减少不等同于该源更早clear，需直接看上表F→C变化。",
        "",
        "## 9. 时间分解",
        table(parts,[("version","策略"),("move_time_s","移动s"),("measure_time_s","测量s"),("switch_time_s","切频道s"),("clear_time_s","清除s")]),
        table(phase,[("version","策略"),("phase","阶段"),("move_time","移动s"),("measure_time","测量s"),("switch_time","切频道s"),("clear_time","清除s"),("total","合计s")]),
        "阶段账本显示：CLEAR阶段平均减少190.86s，FOUND阶段反而增加75.87s，SEARCH约减少2.67s，合计减少117.66s。尤其FOUND移动增加约111.44s，不能宣称全部定位移动都下降；这是执行阶段归因，不是A内部子补丁的因果拆分。整体移动仍约占W6-A总时间70%。",
        f"每局验证 T=move/5+5×measure+switch+5×clear_success+3×clear_fail，最大残差{metadata['max_time_identity_residual_s']:.8f}s，为接口时间舍入积累。SEARCH按执行role划分，包含SEARCH点上的复测；CLEAR单列，不把位置相同的reacquire混淆成未知频道扫描。",
        "",
        "## 10. Stress构造与局限",
        "四个固定旋转，各生成失联、outward边界、±90°边界、small_reff、多目标布局，共20个合成case；另加4个确定性稳定bearing难例，共24个。source位置/频道/type/reff/方向/误差场配置完整保存于w6_stress/fixtures。ground truth仅存在生成器和事后分析，不进入policy。",
        "lost_visibility布局并非每个旋转都令首个补测失联：这是要核验的实际行为，不因类别名就假定已触发。source_tail_exact.csv给出second_observation_no_signal和visibility_alternations，可审计触发情况。small_reff全部源半径1000；outward目标精确位于1800边界；多目标保持16个源且含omni/dir。",
        table(selected_original,[("strategy","策略"),("seed","离线analog seed"),("channel","ch"),("episode_time_s","episode s"),("found_to_clear_s","target F→C s"),("reacquisition_attempts","target reacq"),("episode_move_m","episode move m")]),
        "这些是离线tail analogues，不是官方Run7的因果重放。没有官方原始布局和误差场，无法给出Run7本身会快多少的可信数值。",
        "",
        "## 11. 验收判断",
        f"正确性硬条件通过：{hard}；Mean/P95/Move均不恶化：{ordinary_ok}；Max不增且>100次源减少：{tail_ok}。这些是当前有限case集上的观测，不构成任意隐藏分布全清证明。",
        conclusion,
        "B的救援低成功率说明附近不等于可见：在当前stress中，B的31次失败、C的26次失败全部发生在接收距离以内但处于背面。本轮不扩大救援半径、不强制追到clear、不恢复route commitment。剩余等待/调度长尾仍需如实保留，不能宣称W6完全解决所有tail。没有自动修改官方入口或frozen best指向。",
        "",
        "## 12. 文件与复现",
        "新增代码：q4/w6_policy.py、tail_robustness.py、stress_cases.py、run_w6_benchmark.py、run_w6_stress_benchmark.py、analyze_w6.py、write_w6_report.py、test_w6.py。旧W0–W5、router、Q3、模拟器物理与官方入口未修改。13项单元测试通过，包括disabled逐动作退化为W5、几何/router冻结、失败加速不重复、救援失败显式defer且无SEARCH时仍可恢复；另对random81重新执行确认B修正前后A动作序列完全相同。",
        "结果：w6_diagnosis诊断与四个tail；w6_pilot四版本40局；w6_stress四版本24局及fixtures；w6最终200局主比较。summary/paired/source_tail_exact/measurement_sequences/phase_details/by_source_count/typical_timelines均可追溯到每局trace。",
        "```bash\ncd Code\npython3 -m unittest q4.test_w6\npython3 q4/run_w6_benchmark.py --output results/q4/w6_pilot\npython3 q4/run_w6_stress_benchmark.py\npython3 q4/run_w6_benchmark.py --versions w5,w6a --random-seeds 0:100 --stress-seeds 10000:10050 --output results/q4/w6\npython3 -m q4.write_w6_report\n```",
        "同一结果目录存在trace时会复用已完成episode；真正重新执行请用一个新的输出目录。不得将旧trace与变更后的策略代码混用。frozen_manifest.json验证旧文件，metadata.json记录本轮新代码hash与准确seed口径。",
    ]
    (final/"report.md").write_text("\n\n".join(line for line in lines if line),encoding="utf-8")
    (pilot/"selection.md").write_text("# Final Pilot Revalidation\n\nAfter the explicit-DEFERRED correctness fix, B/C were rerun on the same fixtures. Earlier results remain in pre_defer_fix. No change was made to the A branch.\n\n"+table(pilot_summary,main_fields)+"\n\nStress:\n\n"+table(stress_summary,main_fields)+"\n\nRetain A as the standalone full-set local-tail experiment; the final promotion decision is in ../w6/report.md.\n")
    print(conclusion)


if __name__=="__main__": main()
