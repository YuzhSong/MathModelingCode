# Q4 Evidence Index

| Claim | Value / conclusion | Source file | Column / section | Notes |
|---|---|---|---|---|
| 最终正式算法 | 25G-ASR；内部实现 W5 | `Code/q4/w5_policy.py` | `W5_SELECTED_SPEC`、`W5SymmetricDetectionPolicy` | 论文正文不写 W5 |
| 目标区域 | `R=1800 m` | `Code/q4/w5_geometry.py` | `ARENA_RADIUS_M` | frozen geometry |
| 最小接收半径 | `r_min=1000 m` | `Code/q4/w5_geometry.py` | `MIN_RECEIVE_RADIUS_M` | worst-case construction |
| 25 点参数 | `a=970 m`, `p=140 m` | `Code/q4/w5_policy.py` | `W5_SELECTED_SPEC` | 由真实代码核对 |
| 外部补偿半径 | `ρ=1820.0893 m` | `Code/q4/w5_geometry.py` | `supplement_radius_m` | `sqrt(3)*970+140` |
| 条件性 25 点论证 | `19+6=25` | `Code/q4/w5_geometry.py` | `fixed_skeleton_minimum_argument()` | 不是全局最少证明 |
| W5 historical full clear | `200/200` | `Code/results/q4/final_candidate_validation/historical_200/summary.csv` | `policy=w5,full_clear` | final recomputation |
| W8 historical full clear | `200/200` | 同上 | `policy=w8,full_clear` | final recomputation |
| W5 held-out full clear | `600/600` | `Code/results/q4/final_candidate_validation/heldout_600/summary.csv` | `policy=w5,full_clear` | 600 new cases |
| W8 held-out full clear | `600/600` | 同上 | `policy=w8,full_clear` | 600 new cases |
| W5 held-out Mean | `7365.1119 s` | `Code/results/q4/final_candidate_validation/heldout_600/summary.csv` | `policy=w5,mean_total_s` | raw-derived |
| W8 held-out Mean | `7368.6095 s` | 同上 | `policy=w8,mean_total_s` | raw-derived |
| W5 held-out PooledTN | `571.1603 s/source` | 同上 | `policy=w5,pooled_time_per_source_s` | `ΣT/ΣN` |
| W8 held-out PooledTN | `571.4315 s/source` | 同上 | `policy=w8,pooled_time_per_source_s` | `ΣT/ΣN` |
| W5/W8 held-out paired | `84 wins / 417 ties / 99 losses` | `Code/results/q4/final_candidate_validation/heldout_600/paired_summary.json` | paired summary | Δ=W8−W5 |
| Mean paired delta | `+3.4976 s` | 同上 | `mean_delta_s` | positive favors W5 |
| Severe regression | `48 >100 s; 19 >300 s; 6 >600 s; 3 >1000 s` | 同上 | regression fields | no post-hoc filtering |
| Worst regression | `+2309.8168 s` | 同上 | `worst_regression_s` | W8−W5 |
| W8 tail trade-off | held-out P95/CVaR95 slightly lower, P99/movement risk higher | `heldout_600/summary.csv` | `p95_total_s`, `p99_total_s`, `cvar95_total_s`, movement columns | describe trade-off, not “W8 failed” |
| Historical W8 tail | >50/100/200 source reacq = `1/0/0` | `Code/results/q4/w8_stale_repair/tail_metrics.csv` | corresponding columns | historical/stress context |
| Historical W5 tail | >50/100/200 source reacq = `5/4/3` | 同上 | corresponding columns | historical/stress context |
| W8 trigger audit | 309 triggers / 3973 A2 opportunities = 7.78% | `Code/results/q4/w8_stale_repair/trigger_audit/summary.json` | trigger counts | all triggers strict A2 subset per report |
| W6-A2 diagnosis | local extreme tail reduced but global route/timing regression | `Code/results/q4/w6/report.md` | sections 5–8 | alternative strategy, not final |
| W7 diagnosis | shadow Gate 2 failed; no formal policy benchmark | `Code/results/q4/w7_macro_regret/report.md` | `Final gate result` | static proxy not reliable |
| Oracle distinctions | lower bound/oracle/reference/conditional diagnostics kept separate | `Code/results/q4/oracle_regret/report.md` | `Oracle definitions and limits` | not policy performance |
| Final freeze integrity | seven hashes equal before/after | `Code/results/q4/final_candidate_validation/frozen_manifest_before.json`, `frozen_manifest_after.json` | `hashes` | metadata differs only because before stores seed matrix |

## 使用规则

论文手写数字时优先从本表给出的 raw CSV/JSON 字段读取；早期 report 中的 `Mean T/N` 若未明确为 PooledTN，应标为 MacroTN 或重新从 episode raw CSV 计算。所有结论须保留 suite、case 数、offline/official 标签。

