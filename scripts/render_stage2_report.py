from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "results/offline_eval_stage2_analysis"


def read(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_from(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def n(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    return 0.0 if value in {None, ""} else float(value)


def table(
    rows: list[dict[str, Any]],
    columns: list[tuple[str, str, str]],
) -> list[str]:
    lines = [
        "| " + " | ".join(label for _, label, _ in columns) + " |",
        "|" + "|".join("---" if fmt == "s" else "---:" for _, _, fmt in columns) + "|",
    ]
    for row in rows:
        cells: list[str] = []
        for key, _, fmt in columns:
            value = row.get(key, "")
            if fmt == "s":
                cells.append(str(value))
            elif value in {None, ""}:
                cells.append("")
            elif fmt == "pct":
                cells.append(f"{100.0 * float(value):.1f}%")
            elif fmt == "i":
                cells.append(str(int(float(value))))
            else:
                cells.append(format(float(value), fmt))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def main() -> int:
    summaries = read("summary.csv")
    pairs = read("paired_vs_v6_and_n1.csv")
    phases = read("phase_summary.csv")
    sources = read("source_summary.csv")
    decisions = read("candidate_decision_summary.csv")
    decomposition = read("v6_regression_decomposition.csv")
    classes = read("v6_regression_classification.csv")
    audit = read("v6_dedicated_search_audit_by_population.csv")
    typical = read("typical_case_decomposition.csv")
    expensive = read("v6_expensive_sources.csv")[:10]
    supplement_heavy = read("v6_supplement_heavy_sources.csv")[:10]
    pilot_rows = read_from(ROOT / "results/offline_eval_stage2_m_pilot/summary.csv")
    refine_rows = read_from(ROOT / "results/offline_eval_stage2_m_refine/summary.csv")
    regressions = sorted(
        [row for row in read("v6_regression_cases.csv") if n(row, "delta_total_s") > 300.0],
        key=lambda row: n(row, "delta_total_s"),
        reverse=True,
    )

    overall = [row for row in summaries if row["suite"] == "overall"]
    grouped = [row for row in summaries if row["suite"] != "overall"]
    paired_overall = [
        row for row in pairs if row["suite"] == "overall" and row["base"] == "v6"
    ]
    paired_grouped = [
        row for row in pairs if row["suite"] != "overall" and row["base"] == "v6"
    ]
    mn_vs_n1 = [
        row for row in pairs if row["suite"] == "overall" and row["base"] == "n1"
    ]
    phase_overall = [row for row in phases if row["suite"] == "overall"]
    source_overall = [row for row in sources if row["suite"] == "overall"]
    decision_map = {row["version"]: row for row in decisions}
    pilot = [row for row in pilot_rows + refine_rows if row["suite"] == "overall"]

    lines = [
        "# Q3 第二阶段：V6 诊断与 Way1/Way3 局部机制消融",
        "",
        "## Executive Summary",
        "",
        "- 本轮只运行本地 offline_sim/practice。没有调用官方 HTTP、正式测试或正式测试入口。",
        "- 1,400 个正式消融 episode（7 个版本 × 200 seeds）全部 100% clear、0 clear fail；另有 400 个 V6/V6Audit 行为校验 episode。V6 重放与既有 200 局逐 seed 完全一致。",
        "- 纯 Minimax M1 明确失败：平均慢 315.77s。M2 只快 18.46s，但最坏 paired regression 达 737.53s，不满足升级条件。",
        "- 条件 85m 近场候选 N1 是唯一实质单模块收益：平均快 79.07s、P95 改善 64.18s、平均少走 388.73m、paired win 74%。但仍有 3 个 >300s 回退，且聚合 max 比 V6 高 160.16s。",
        "- 精确大交角候选 N2 基本冗余；N3 与 N1 几乎相同。MN 相对 N1 平均只快 0.07s，却有更差 P95 和 8 个 >300s 回退，Minimax 与近场在当前实现下不互补。",
        "- V6 的平均收益来自 FOUND/CLEAR 路段缩短，但主要回退来自 SEARCH/任务顺序扰动。当前建议保留 frozen V6；N1 仅作为 V6.x 离线候选，不创建 V7。",
        "",
        "## 1. Safety And Reproducibility",
        "",
        "- Policy 只接收 runner/API 可见信息。stage2 policy 静态检查禁止导入 offline_sim 或访问 case/engine/sources/jammers。",
        "- Ground truth 仅在 episode 完成后用于典型路线图的 source 标注。",
        "- V6Audit 只增加日志；200 局相对 V6 的时间和移动最大绝对差均为 0。",
        "- 每局均验证 total = move + measure + switch + clear；最大数值误差低于 8e-6s。",
        "- M2 beta=0.10 s/m 由固定 40-case pilot 在 0.01/0.025/0.05/0.075/0.10/0.15/0.25 中选出，随后才运行正式 200 局。",
        "",
        "## 2. V6 Failure Diagnosis",
        "",
        "V6 相对 V4 在 130/200 局获胜、70/200 局失败；12 局回退超过 300s。以下分解使用互斥的 phase/action 时间，能与总 delta 对账；dedicated detour proxy 与 phase move 重叠，仅作诊断。",
        "",
    ]
    lines.extend(
        table(
            decomposition,
            [
                ("population", "Population", "s"),
                ("cases", "Cases", "i"),
                ("mean_delta_total_s", "Total Δs", ".2f"),
                ("mean_search_move_delta_s", "SEARCH move", ".2f"),
                ("mean_search_info_delta_s", "SEARCH info", ".2f"),
                ("mean_found_move_delta_s", "FOUND move", ".2f"),
                ("mean_found_info_delta_s", "FOUND info", ".2f"),
                ("mean_clear_move_delta_s", "CLEAR move", ".2f"),
                ("mean_dedicated_detour_proxy_delta_s", "Dedicated proxy", ".2f"),
                ("mean_task_ordering_remainder_s", "Order remainder", ".2f"),
                ("mean_delta_supplements", "Supp Δ", ".2f"),
            ],
        )
    )
    lines.extend(
        [
            "",
            "全体均值中，V6 的 SEARCH 移动比 V4 多 166.52s，但 FOUND 移动少 175.09s、CLEAR 移动少 76.57s，净改善 83.30s。也就是说，V6 不是把所有阶段都变短，而是用更长的搜索共存路线换取后续定位/清除协同。",
            "",
            "在 70 个失败局中，SEARCH 移动平均多 240.25s，是主要正损失；FOUND 移动仍平均少 80.26s。12 个 >300s 回退局中，SEARCH 移动多 272.84s，CLEAR 移动再多 164.54s，二者解释了主要长尾。",
            "其中 CLEAR move 是 READY_TO_CLEAR 后到实际 clear 点的最后移动；Dedicated proxy 是固定 SEARCH 点之外 supplement move 的诊断量，会与 FOUND/SEARCH move 重叠；Order remainder 是总 delta 扣除互斥 phase/action 项后的剩余。大幅回退局的 Order remainder 为 +251.72s，表明多任务发现时序和排序效应不可忽略。",
            "",
            "回退分类是基于动作日志的启发式归因。Primary class 互斥；overlap flags 可重叠，不能解释为严格因果。",
            "",
        ]
    )
    lines.extend(
        table(
            classes,
            [
                ("classification", "Class", "s"),
                ("case_count", "Cases", "i"),
                ("share_of_v6_losses", "Loss share", "pct"),
                ("mean_loss_s", "Mean loss s", ".2f"),
                ("max_loss_s", "Max loss s", ".2f"),
            ],
        )
    )
    lines.extend(["", "12 个大幅回退 case：", ""])
    lines.extend(
        table(
            regressions,
            [
                ("suite", "Suite", "s"),
                ("seed", "Seed", "i"),
                ("delta_total_s", "Δ total s", ".2f"),
                ("search_move_delta_s", "SEARCH move", ".2f"),
                ("found_move_delta_s", "FOUND move", ".2f"),
                ("clear_move_delta_s", "CLEAR move", ".2f"),
                ("delta_supplements", "Supp Δ", ".0f"),
                ("primary_class", "Primary", "s"),
            ],
        )
    )
    lines.extend(
        [
            "",
            "### Dedicated Supplement And Future SEARCH",
            "",
            "V6 共执行 3,482 次 FOUND 后补测，其中 2,686 次是 dedicated supplement。1,627 次 dedicated 动作发生时仍存在至少一个合法、未完成的 SEARCH 点；337 次其补测点距离未来 SEARCH 点不超过 250m，807 次不超过 500m。距离切分仅用于敏感性统计，不是策略阈值。",
            "",
        ]
    )
    lines.extend(
        table(
            audit,
            [
                ("population", "Population", "s"),
                ("cases", "Cases", "i"),
                ("dedicated_supplements", "Dedicated", "i"),
                ("dedicated_with_legal_future_search", "With legal SEARCH", "i"),
                ("legal_future_search_share_of_dedicated", "Share", "pct"),
                ("within_250m_count", "<=250m", "i"),
                ("within_500m_count", "<=500m", "i"),
                ("mean_selected_route_marginal_s", "Marginal s", ".2f"),
            ],
        )
    )
    lines.extend(
        [
            "",
            "这些 dedicated 选择并非没有比较 future SEARCH：在可用时，V6 预测 future SEARCH objective 平均比已选 dedicated 高 58.02s。问题更像是 one-step future-cost 近似与后续全局任务演化不一致，而不是候选缺失。",
            "",
            "### Most Expensive FOUND Sources",
            "",
        ]
    )
    lines.extend(
        table(
            expensive,
            [
                ("suite", "Suite", "s"),
                ("seed", "Seed", "i"),
                ("channel", "Ch", "i"),
                ("found_to_clear_elapsed_s", "FOUND-clear s", ".2f"),
                ("found_after_move_m", "Move m", ".2f"),
                ("supplement_measure_count", "Supp", "i"),
                ("first_supplement_mec_after_m", "First MEC m", ".2f"),
                ("final_clear_mec_m", "Final MEC m", ".2f"),
            ],
        )
    )
    lines.extend(["", "补测次数最高的 source：", ""])
    lines.extend(
        table(
            supplement_heavy,
            [
                ("suite", "Suite", "s"),
                ("seed", "Seed", "i"),
                ("channel", "Ch", "i"),
                ("supplement_measure_count", "Supp", "i"),
                ("found_to_clear_elapsed_s", "FOUND-clear s", ".2f"),
                ("found_after_move_m", "Move m", ".2f"),
                ("threshold_chasing_20_30", "20-30m chase", "i"),
            ],
        )
    )
    lines.extend(
        [
            "",
            "## 3. Mechanism Overlap",
            "",
            "| Mechanism | Mark | Code-level conclusion |",
            "|---|---|---|",
            "| Way1 set-membership / feasible region | A | V6 已使用 bearing wedge 的 feasible polygon 与保守定位区域。 |",
            "| Way1 MEC | A | V6 使用 MEC radius <=20m；Way1 内部为更保守的 19m。 |",
            "| Way1 Minimax active localization | C | V6 原本是采样期望 future cost，不含 worst-after residual；M1/M2 是真实新增。 |",
            "| Way1 candidate generation | B | 都有 center/ring/perpendicular 几何，但半径、点数和评分不同。 |",
            "| Way1 task scheduling | B/D | V6 已联合 SEARCH/MEASURE/CLEAR；Way1 COVER/LOCALIZE 优先级会带来回头路，不移植。 |",
            "| Way1 route planning | B/D | 都含 nearest/2-opt 元素；Way1 的逐频道 LOCALIZE 路线已被统一 benchmark 判定为高移动。 |",
            "| Way3 coverage scan | A | V6 已有中心+8 外圈确定性覆盖、FOUND 退出 UNKNOWN、16 源提前停止。 |",
            "| Way3 near-field | C | Way3 85m orbit 原本不存在于 V6 固定 500/950m ring；N1 条件加入。 |",
            "| Way3 large intersection angle | B | V6 环候选已近似覆盖；N2 精确垂直点仅 17 次被选。 |",
            "| Way3 homing | D | 强制顺序 homing 是 Way3 移动膨胀主因，不引入。 |",
            "| Way3 replanning | B/D | V6 已在每次动作后全局重排；Way3 的阶段式 replanning 不是新增能力。 |",
            "",
            "A=等价包含，B=部分包含，C=真正新增，D=不值得引入。",
            "",
            "## 4. Ablation Definitions",
            "",
            "所有版本继承 frozen V6 的 n=8 搜索、状态机、20m MEC 判据与 online router，只覆盖 supplement candidate ranking/generation。固定预测设置为 feasible polygon 内 12 个确定性样本、bearing error {-1,0,+1} degree、V6 ring 半径 {500,950}m、合法接收上限 995m、与旧测点最小间距 10m。",
            "",
            "- M1: 候选集合完全不变，选择使 R_worst-after(S) 最小的点；R_worst-after 是样本及离散 bearing outcome 更新后 MEC 半径的最大值。它有意隔离纯 Minimax 信息准则，完全不看 route cost。",
            "- M2: 候选集合完全不变，最小化 J_M2(S)=route_marginal(S)+5s+E[remaining time|S]+beta*R_worst-after(S)。beta 单位为 s/m，因此各项统一为秒。",
            "- N1: 仅对 MEC>20m 且已有至少 2 次 direction 的困难源，在当前 MEC 中心周围增加 8 个均匀 85m near-field 点；仍由原 V6 objective 与全部原候选共同竞争，不强制选择。",
            "- N2: 同一困难源门控下，在 MEC 中心沿最新观测点到 MEC 中心连线的法向两侧，按 500m/950m 生成 exact large-angle 候选；仍由 V6 objective 竞争。",
            "- N3: N1 与 N2 候选并集。MN: N1 加 M2(beta=0.10)，仅在单模块完成后作为互补性验证。",
            "",
            "M2 beta 使用固定 40-case pilot，不使用正式 200 局挑参：",
            "",
        ]
    )
    lines.extend(
        table(
            pilot,
            [
                ("version", "Pilot", "s"),
                ("mean_total_time_s", "Mean s", ".2f"),
                ("p95_total_time_s", "P95", ".2f"),
                ("max_total_time_s", "Max", ".2f"),
                ("mean_move_distance_m", "Move m", ".2f"),
            ],
        )
    )
    lines.extend(
        [
            "",
            "beta=0.10 在该 pilot 上 mean 最低；0.075/0.15 是同一批 case 的局部细化。正式 200 局中 beta 不再调整。",
            "",
            "## 5. Controlled Ablation Results",
            "",
        ]
    )
    lines.extend(
        table(
            overall,
            [
                ("version", "Version", "s"),
                ("clear_rate", "Clear", "pct"),
                ("mean_total_time_s", "Mean s", ".2f"),
                ("median_total_time_s", "Median", ".2f"),
                ("p95_total_time_s", "P95", ".2f"),
                ("max_total_time_s", "Max", ".2f"),
                ("mean_move_distance_m", "Move m", ".2f"),
                ("mean_measure_count", "Measure", ".2f"),
                ("clear_fail_total", "Fail", "i"),
            ],
        )
    )
    lines.extend(["", "分组结果：", ""])
    lines.extend(
        table(
            grouped,
            [
                ("version", "Version", "s"),
                ("suite", "Group", "s"),
                ("mean_total_time_s", "Mean s", ".2f"),
                ("p95_total_time_s", "P95", ".2f"),
                ("max_total_time_s", "Max", ".2f"),
                ("mean_move_distance_m", "Move m", ".2f"),
            ],
        )
    )
    lines.extend(["", "同 seed paired comparison，相对 V6 的 delta 为 target - V6：", ""])
    lines.extend(
        table(
            paired_overall,
            [
                ("target", "Target", "s"),
                ("target_win_rate", "Win", "pct"),
                ("mean_delta_time_s", "Mean Δs", ".2f"),
                ("median_delta_time_s", "Median", ".2f"),
                ("p95_delta_time_s", "P95 Δ", ".2f"),
                ("worst_regression_s", "Worst", ".2f"),
                ("best_improvement_s", "Best", ".2f"),
                ("worse_over_300s_count", ">300s", "i"),
            ],
        )
    )
    lines.extend(["", "分 random/min_reff/collinear 的 paired 结果：", ""])
    lines.extend(
        table(
            paired_grouped,
            [
                ("target", "Target", "s"),
                ("suite", "Group", "s"),
                ("target_win_rate", "Win", "pct"),
                ("mean_delta_time_s", "Mean delta s", ".2f"),
                ("p95_delta_time_s", "P95 delta", ".2f"),
                ("worst_regression_s", "Worst", ".2f"),
                ("worse_over_300s_count", ">300s", "i"),
            ],
        )
    )
    lines.extend(
        [
            "",
            "### M1 / M2",
            "",
            f"M1 在 {int(n(decision_map['m1'], 'changed_from_v6_count'))} 次实际补测中改变 V6 选择，占 {100*n(decision_map['m1'], 'changed_from_v6_rate'):.1f}%。它平均少 2.31 次 measure/case、少 1.61 次 switch/case，仅省 13.16s 信息时间，却多走 1,644.66m（328.93s），净慢 315.77s。Way1 的信息优势不能通过纯 Minimax 原样迁移。",
            "",
            f"M2 只在 {int(n(decision_map['m2_b0p1'], 'changed_from_v6_count'))} 次补测改变选择，占 {100*n(decision_map['m2_b0p1'], 'changed_from_v6_rate'):.1f}%。总体平均快 18.46s，但 min_reff 平均反而慢 14.77s，且最坏 paired regression 737.53s。因此 M2 不通过稳定性门槛。",
            "",
            "### N1 / N2 / N3",
            "",
            f"N1 的 85m near-field 候选实际被选择 {int(n(decision_map['n1'], 'selected_near_field_count'))} 次。它不明显减少首次补测后过线率（34.90% -> 34.94%），但把 >=3 次补测源占比从 7.42% 降到 5.53%，FOUND 后移动从 662.44m/source 降到 631.79m/source。总收益 98% 来自移动。",
            "",
            f"N2 的 exact perpendicular 候选只被选择 {int(n(decision_map['n2'], 'selected_large_angle_count'))} 次，平均慢 0.72s，可视为被 V6 原候选集合覆盖。N3 中 large-angle 只被选择 {int(n(decision_map['n3'], 'selected_large_angle_count'))} 次，且比 N1 平均慢 1.42s。",
            "",
            "### MN Complementarity",
            "",
        ]
    )
    lines.extend(
        table(
            mn_vs_n1,
            [
                ("target", "Target", "s"),
                ("target_win_rate", "Win vs N1", "pct"),
                ("mean_delta_time_s", "Mean Δs", ".2f"),
                ("p95_delta_time_s", "P95 Δ", ".2f"),
                ("worst_regression_s", "Worst", ".2f"),
                ("worse_over_300s_count", ">300s", "i"),
            ],
        )
    )
    lines.extend(
        [
            "",
            "MN 相对 N1 平均仅快 0.07s，属于数值上的平局；其 P95 从 4180.65s 恶化到 4241.60s，paired worst 为 +680.85s，8 局回退超过 300s。Minimax 不为 N1 提供可接受的互补收益。",
            "",
            "## 6. Time And Source Decomposition",
            "",
            "Episode-level 完整指标与策略计算开销：",
            "",
        ]
    )
    lines.extend(
        table(
            overall,
            [
                ("version", "Version", "s"),
                ("mean_avg_source_s", "Mean avg/source s", ".2f"),
                ("pooled_avg_source_s", "Pooled avg/source s", ".2f"),
                ("std_total_time_s", "Std s", ".2f"),
                ("mean_move_time_s", "Move time s", ".2f"),
                ("mean_measure_time_s", "Measure time s", ".2f"),
                ("mean_switch_time_s", "Switch time s", ".2f"),
                ("mean_clear_time_s", "Clear time s", ".2f"),
                ("mean_policy_runtime_s", "Policy CPU s", ".3f"),
                ("p95_policy_runtime_s", "CPU P95 s", ".3f"),
            ],
        )
    )
    lines.extend(["", "Phase-level：", ""])
    lines.extend(
        table(
            phase_overall,
            [
                ("version", "Version", "s"),
                ("phase", "Phase", "s"),
                ("mean_move_time_s", "Move s", ".2f"),
                ("mean_measure_time_s", "Measure s", ".2f"),
                ("mean_switch_time_s", "Switch s", ".2f"),
                ("mean_clear_time_s", "Clear s", ".2f"),
                ("mean_total_time_s", "Total s", ".2f"),
            ],
        )
    )
    lines.extend(["", "FOUND -> CLEAR source-level：", ""])
    lines.extend(
        table(
            source_overall,
            [
                ("version", "Version", "s"),
                ("mean_found_to_clear_s", "Elapsed s/source", ".2f"),
                ("mean_found_after_move_m", "Move m/source", ".2f"),
                ("mean_off_search_supplement_move_m", "Dedicated move m/source", ".2f"),
                ("mean_supplements_per_source", "Supp/source", ".3f"),
                ("first_supplement_clearable_rate", "First clearable", "pct"),
                ("supp_ge2_rate", ">=2", "pct"),
                ("supp_ge3_rate", ">=3", "pct"),
                ("supp_ge4_rate", ">=4", "pct"),
                ("threshold_chasing_20_30_count", "20-30m chase", "i"),
            ],
        )
    )
    lines.extend(["", "首次 supplement 后 MEC 分布（分母为发生过 supplement 的 source）：", ""])
    lines.extend(
        table(
            overall,
            [
                ("version", "Version", "s"),
                ("first_supplement_le20_or_near_rate", "<=20m/near", "pct"),
                ("first_supplement_20_25_rate", "20-25m", "pct"),
                ("first_supplement_25_30_rate", "25-30m", "pct"),
                ("first_supplement_30_50_rate", "30-50m", "pct"),
                ("first_supplement_gt50_rate", ">50m", "pct"),
                ("first_supplement_unknown_rate", "Unknown", "pct"),
            ],
        )
    )
    lines.extend(
        [
            "",
            "N1 的平均收益并非来自首次补测更容易直接过线，而是减少了多次补测和最终 clear 路段的空间错位。其 CLEAR phase 平均从 749.50s 降到 672.75s，是 79.07s 总收益中的 76.75s。",
            "",
            "## 7. Typical Cases",
            "",
        ]
    )
    lines.extend(
        table(
            typical,
            [
                ("label", "Case", "s"),
                ("suite", "Group", "s"),
                ("seed", "Seed", "i"),
                ("base", "Base", "s"),
                ("target", "Target", "s"),
                ("delta_time_s", "Total Δs", ".2f"),
                ("delta_search_total_s", "SEARCH Δ", ".2f"),
                ("delta_found_total_s", "FOUND Δ", ".2f"),
                ("delta_clear_total_s", "CLEAR Δ", ".2f"),
                ("delta_supplements", "Supp Δ", ".0f"),
            ],
        )
    )
    lines.extend(
        [
            "",
            "- [V6 大胜 V4: random seed 72](figures/v6_big_win_v4_random_72.svg)：V6 少走约 3,967m、少 4 次补测；FOUND 阶段节省 743.00s。",
            "- [V6 大输 V4: random seed 70](figures/v6_big_loss_v4_random_70.svg)：SEARCH 多 617.26s，尽管 FOUND 少 354.94s，最终仍慢 553.01s；这是典型等待/排序回退。",
            "- [M2 最佳改善: random seed 81](figures/m2_best_improvement_random_81.svg)：少走约 3,346m、少 2 次补测，三个阶段都改善；但该收益不是普遍现象。",
            "- [N1 最佳改善: random seed 90](figures/n1_best_improvement_random_90.svg)：少走约 3,581m、少 5 次补测，FOUND 阶段节省 664.81s。",
            "- [N1 最坏回退: random seed 95](figures/n1_worst_regression_random_95.svg)：FOUND 后累计移动其实少 658m，但 SEARCH 路线多 534.44s，说明新增近场任务改变了全局共存顺序，造成另一种 route coupling。",
            "",
            "完整事件见 typical_timelines.csv；每个动作保留时间、位置、频道、SEARCH/FIRST_FOUND/SUPPLEMENT/CLEAR 和移动距离。",
            "",
            "## 8. Final Recommendation",
            "",
            "1. 保留 frozen V6 作为当前正式候选，不覆盖、不改名。",
            "2. 将 N1 保留为 V6.x experimental：它在均值、P95、移动和 74% paired seeds 上显著优于 V6，但 3 个 >300s 回退和更高聚合 max 尚未满足替换门槛。",
            "3. 淘汰 M1、M2、N2、N3、MN；不形成 V7。",
            "4. 当前剩余主要问题不是缺少 Minimax 或大交角候选，而是候选任务加入后对 SEARCH/CLEAR 全局顺序的耦合与 one-step future-cost 误差。这个结论来自分解与路线图，不是新的策略设计。",
            "",
            "## 9. Reusable Pipeline",
            "",
            "- run_stage2_eval.py：统一 case/seeds、episode/phase/source/paired 输出及 V6 重放校验。",
            "- analyze_stage2.py：回退分类、future SEARCH audit、source 极值、典型 seed 选择。",
            "- plot_stage2_typical.py：只对典型 seed 事后读取 ground truth 生成路线图和 timeline。",
            "- 原始与派生 CSV 均位于本目录；所有后续 V6.x 候选可复用相同口径。",
        ]
    )
    (DATA / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(DATA / "report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
