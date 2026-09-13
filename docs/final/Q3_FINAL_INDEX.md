# Q3 Final Offline Index

## Final identity

- Paper method: **RARC — Route-Aware Rolling Coordination**（路径感知滚动联合调度策略）
- Internal implementation: **frozen V6 / n=8**
- Final runner: [`run_q3_final.py`](../../run_q3_final.py)
- Frozen snapshot: [`frozen/v6_n8_20260912/`](../../frozen/v6_n8_20260912/)

## Main data

| Use | Source |
|---|---|
| Final report and 200-case comparison | [`results/q3/offline_eval_v6_n8/report.md`](../../results/q3/offline_eval_v6_n8/report.md) |
| Per-case details | [`results/q3/offline_eval_v6_n8/details.csv`](../../results/q3/offline_eval_v6_n8/details.csv) |
| Aggregate summary | [`results/q3/offline_eval_v6_n8/summary.csv`](../../results/q3/offline_eval_v6_n8/summary.csv) |
| Route decisions and source diagnostics | `results/q3/offline_eval_v6_n8/route_decisions.csv`, `source_diagnostics.csv` |
| Source-count N=10..16 table and figures | [`results/q3/offline_eval_ring_count_200/report.md`](../../results/q3/offline_eval_ring_count_200/report.md), its `figures/` and `source_count_summary.csv` |
| n=6..12 sensitivity | [`results/q3/offline_eval_ring_count_200/`](../../results/q3/offline_eval_ring_count_200/) |
| Representative trajectories | `results/q3/offline_eval_v6_n8/typical_cases.csv` and the corresponding final figures in the ring-count result |

For `summary.csv`, the main columns are `mean_total_time_s`, `p95_total_time_s`, `max_total_time_s`, `mean_avg_source_s`, `pooled_avg_source_s`, `mean_move_distance_m`, `clear_rate`, and `clear_fail_total`. Mean(T/N) means compute `T_i/N_i` per case first and then average the cases.

## Historical and negative evidence

Official formal summary: `official_results/q3/q3_formal_summary.csv` (3 rows; all case IDs and required table fields present; average-time formula validated).

- V4/V5 evolution: `results/q3/offline_eval_v4_n8_n9/`, `offline_eval_v5_n8/`.
- Stage-2/N1/N2/Minimax family: `results/q3/offline_eval_stage2_200/`, `offline_eval_stage2_mn_200/`, `offline_eval_stage2_analysis/`.
- L2 lookahead: `results/q3/offline_eval_v6_l2_200/`.
- Ring-only, no_signal, and SEARCH-backbone bundle: root-level `results/offline_eval_ring_only_center_ablation_200/`, `offline_eval_v6_nosignal_200/`, `offline_eval_v6_backbone_bundle_200/`.

These are retained as model-selection evidence, not final policies.
