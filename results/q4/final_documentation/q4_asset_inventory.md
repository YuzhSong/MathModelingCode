# Q4 实验资产清单

本清单基于对 `Code/q4/`、`Code/results/q4/`、`Code/offline_sim/` 及 Q4 依赖模块的完整扫描。扫描得到：`q4/` 53 个文件，`results/q4/` 4683 个文件。本文档只做资产索引，不修改任何既有策略、路由、几何、模拟器、生成器或 CSV。

## 1. 当前正式冻结资产

| 资产 | 作用 | 状态 | 论文用途 |
|---|---|---|---|
| `q4/w5_policy.py` | 最终正式策略入口；继承统一动态任务池，固定 `a=970`、`p=140` 的 25 点几何 | frozen / final | 正文最终方法，论文名称为 25G-ASR |
| `q4/w5_geometry.py` | 19 点规则骨架、6 个边界补偿点、几何可行性检查 | frozen / final | 正文几何建模 |
| `q4/routing.py` | nearest、open-route、route-consequence 任务选择；最终 W5 使用 `open_route` | frozen / final | 正文动态路径重规划 |
| `q4/w8_stale_repair.py`、`q4/w8_policy.py` | stale-state repair 候选及其冻结入口 | frozen candidate | 仅作鲁棒性对照，不进入正式方法 |
| `offline_sim/case.py` | Q4 离线 case 结构与生成结果承载 | frozen support | 实验可复现性 |
| `offline_sim/engine.py` | 离线运动、测量、切换、清除时间与轨迹记录 | frozen support | 指标和时间分解来源 |
| `final_candidate_validation/` | 历史 200、held-out 600、stress 24、combined 800 的最终核验 | final evidence | 论文 Table 2/3 候选选择 |

`frozen_manifest_before.json` 与 `frozen_manifest_after.json` 的 7 个 hash 一致；最终验证前后未发生 policy/router/geometry/simulator mutation。

## 2. 代码资产与建模链条

| 文件/文件组 | 在 Q4 建模链条中的职责 | 主要实验/输出 |
|---|---|---|
| `q4/w0_policy.py` | 将 Q3 V6/n=8 直接带入 Q4，作为问题难度基线 | `results/q4/w0_baseline/` |
| `q4/geometry.py`、`q4/w1_policy.py` | triangular detection backbone 与第一版 Q4 搜索几何 | `w1_geometry/`、`w1/` |
| `q4/w2_policy.py` | `TargetLifecycle`、FOUND 后持久化、reacquire/defer/clear 状态 | `w2/`、`lifecycle_summary.csv` |
| `q4/w3_policy.py` | 基于 bearing/可行域的 adaptive coarse-to-fine local reacquisition | `w3/`、`time_decomposition.csv` |
| `q4/w4a_policy.py` | rolling unified task pool；每次 action 后重建任务并执行 open route 首任务 | `w4a/`、`w4a_diagnosis/` |
| `q4/w4b_policy.py`、`q4/routing_continuity.py` | 固定 backbone continuity 与 insertion 约束的对照实验 | `w4b/`；负结果 |
| `q4/w5_geometry.py`、`q4/w5_policy.py` | 25 点最终几何替换到 W4-A 行为 | `w5/`、`w5_geometry/` |
| `q4/w6_policy.py`、`q4/w6a_decomp_policy.py` | MEC-only、aggressive acceleration、组合消融及 rescue 诊断 | `w6/`、`w6a_decomposition/`；alternative/negative |
| `q4/w7_macro_regret.py` | macro completion regret scheduling 的 shadow 预测器 | `w7_macro_regret/`；shadow gate 后停止 |
| `q4/w8_stale_repair.py`、`q4/w8_policy.py` | 对 stale shrink 事件做局部 repair | `w8_stale_repair/`、最终 held-out 对照 |
| `q4/oracle_regret.py` | clear-disk Held–Karp、center-route、CompletionRegret、SEARCH gap 诊断 | `oracle_regret/`；诊断，不是 policy |
| `q4/stress_cases.py` | 24 个既有 stress fixture 的构造/读取 | `w6a_decomposition/stress/`、`w8_stale_repair/benchmark/stress/` |
| `q4/run_*_benchmark.py`、`run_*_diagnosis.py` | 各版本 benchmark、pilot、诊断和报告驱动脚本 | 对应版本结果目录 |
| `q4/run_final_candidate_validation.py` | 固定 held-out seed matrix，运行 W5/W8 及 smoke | `final_candidate_validation/` |
| `q4/analyze_final_candidate_validation.py` | 从 raw episode/source/trace 计算 pooled T/N、tail、paired、bootstrap 和报告 | `final_candidate_validation/` |
| `q4/export_trajectory.py` | 将 action log 导出为轨迹 CSV | `trajectory_plot/` |

Q4 仍复用 `q3.models`、`q3.geometry`、`q3.routing`、`q3.offline_policy` 等共享基础；这些共享依赖在论文/代码说明中应如实披露，不应误写为完全独立实现。

## 3. 实验目录索引

| 目录 | 实验目的与 variant | case 数 | 核心输出 | report |
|---|---|---:|---|---|
| `w0_baseline/` | Q3 V6/n=8 在 Q4 的失败基线 | 200（random 100/min_reff 50/collinear 50） | `details.csv`、`missed_sources.csv`、`summary.csv` | `w0_baseline/report.md` |
| `w1/` + `w1_geometry/` | triangular detection backbone；验证几何替换本身 | 200；几何扫描另有参数表 | `details.csv`、`geometry_scan.csv`、`selected_geometry.json` | `w1/report.md`、`w1_geometry/geometry_report.md` |
| `w2/` | persistent directional target lifecycle | 200 | `details.csv`、`lifecycle_summary.csv`、`paired_comparison.csv` | `w2/report.md` |
| `w3/` | fixed/adaptive/intersection local reacquisition 对照；正式选 adaptive | 200 formal + pilot | `details.csv`、`source_local.csv`、`time_decomposition.csv` | `w3/report.md` |
| `w4a/` | unified task pool 与 open-route/nearest/route-consequence 对照 | 200 formal + 40 pilot | `details.csv`、`movement_decomposition.csv`、`clear_delay_regret.csv` | `w4a/report.md` |
| `w4b/` | continuity/insertion alternative；确认过强 backbone commitment 的代价 | 200 confirmation + pilot | `details.csv`、`continuity_comparison.csv`、`w4a_original_regressions.csv` | `w4b/report.md` |
| `w5/` + `w5_geometry/` | 25 点 `a=970,p=140` 与 W4-A 行为的正式组合 | 200 | `details.csv`、`time_decomposition.csv`、`source_local.csv`、geometry SVG/PNG/TIFF | `w5/report.md`、`w5_geometry/geometry_report.md` |
| `w6/` | tail robustness：A/B/C 分离、W6-A 与 rescue 诊断 | 200 formal + 24 stress + pilots | `phase_summary.csv`、`tail_summary_exact.csv`、`regression_decomposition.csv` | `w6/report.md` |
| `w6a_decomposition/` | W5、MEC-only、acceleration-only、组合 W6-A3 的 controlled ablation | 200 formal + 24 stress | 各 variant `details.csv`、`source_tail.csv`、paired files、traces | 以 `w6/report.md` 和目录 CSV 为准 |
| `w7_macro_regret/` | shadow calibration：静态 regret 是否能预测动态 other-work regret | shadow only | `shadow_decisions.csv`、`endpoint_accuracy.csv`、`summary.json` | `w7_macro_regret/report.md` |
| `oracle_regret/` | oracle lower bound、completion regret 与 route gap 的条件诊断 | formal/stress | `case_oracle_metrics.csv`、`source_regret_metrics.csv`、`search_route_gap.csv` | `oracle_regret/report.md` |
| `w8_stale_repair/` | W8 formal/stress stale repair 与 trigger audit | 200 + 24 stress + trace subset | `summary.csv`、`tail_metrics.csv`、`repair_events.csv`、regression/best-wins | `w8_stale_repair/report.md` |
| `final_candidate_validation/` | W5/W8 最终冻结验证 | smoke 9 + held-out 600 + historical 200 + stress 24 | paired、source-tail、generator/source-count、trigger、bootstrap、combined | `final_candidate_validation/report.md` |

## 4. 资产角色分类

- 正文方法依据：`w5_geometry.py`、`w5_policy.py`、`w2_policy.py` 的最终生命周期语义、`w3_policy.py` 的 adaptive 局部机制、`w4a_policy.py`/`routing.py` 的统一任务池与 open route。
- 消融实验：`w1/`、`w3` 的 fixed/intersection pilot、`w4a` 的路由 pilot、`w6a_decomposition/`。
- 负结果：`w0` 的 Q4 失败基线、`w4b` continuity、`w6-A2/A3` global regression、`w7` shadow gate failure、W8 held-out severe regressions。
- 最终验证：`final_candidate_validation/` 的 smoke、held-out 600、历史 200、stress 24 和 combined 800。
- 工程部署：`main.py --problem 4 --mode official --strategy w5 ...`、`q4/` 入口与 `logs/q4_*.jsonl`；官方服务器结果不能用离线 benchmark 冒充。

## 5. 重要口径提醒

历史文件中的 `Mean T/N` 多为 MacroTN；最终资料包新增的 `Pooled T/N` 才是论文主 per-source 指标。W5/W8 held-out 的正式数值以 `final_candidate_validation/heldout_600/summary.csv` 为准，不能直接复制早期 report 的 T/N 字段。

