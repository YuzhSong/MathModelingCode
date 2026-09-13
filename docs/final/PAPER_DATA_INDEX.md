# Paper Data Index

论文手先使用本文件，再打开对应的 Q3/Q4 final index。所有链接均指向原始结果路径，避免复制和路径漂移。

正式测试表与离线证据分开：Q3 正式表应使用 `official_results/q3/q3_formal_summary.csv`，Q4 正式表应使用 `official_results/q4/q4_formal_summary.csv`。当前这两个文件尚未出现在 Mac checkout；在合并前不要填写正式测试数值。

## Q3 recommended

| Paper use | Data source | CSV columns / section | Suggested placement |
|---|---|---|---|
| Final RARC metrics | `results/q3/offline_eval_v6_n8/summary.csv` | overall row: `mean_total_time_s`, `mean_avg_source_s`, `p95_total_time_s`, `max_total_time_s`, `clear_rate`, `clear_fail_total` | main results |
| V4/V5/RARC comparison | `results/q3/offline_eval_v6_n8/report.md` | sections 3, 5, 6 | method evolution / main table |
| n=6..12 selection | `results/q3/offline_eval_ring_count_200/report.md` and `summary.csv` | `n`, `mean_avg_source_time_s`, P95 and clear columns | parameter sensitivity |
| N=10..16 curve | same ring-count report, section F and `source_count_summary.csv` | `source_count`, `mean_avg_source_time_s`, P95 | main results figure/table |
| Route mechanism | `details.csv`, `route_decisions.csv`, `source_diagnostics.csv` | supplement, route marginal and movement fields | mechanism analysis |
| Final trajectory | ring-count `figures/` and final typical-case artifacts | figure files and timeline CSV | representative figure |
| L2 / backbone negative ablation | `results/q3/offline_eval_v6_l2_200/`, `results/offline_eval_v6_backbone_bundle_200/` | respective `report.md`, paired and phase CSV | ablation/supplement |
| no_signal and ring-only | `results/offline_eval_v6_nosignal_200/`, `results/offline_eval_ring_only_center_ablation_200/` | report and summary | optional / page-limited |

## Q4 recommended

| Paper use | Data source | CSV columns / section | Suggested placement |
|---|---|---|---|
| Final 25P-PFRC metrics | `results/q4/w6/feasible_region_full/summary.csv` | overall row: `mean_total_time_s`, `p95_total_time_s`, `max_total_time_s`, `mean_avg_time_per_source_s`, `mean_move_distance_m`, `clear_rate`, `clear_fail_total` | main results |
| Q4 geometry/core evolution | `results/q4/w0_baseline/` through `results/q4/w5/` | reports and summary tables | method development |
| Persistent feasible-region mechanism | `results/q4/w6/feasible_region_full/report.md` | certificate and full-clear sections | main method |
| Source-level behavior | `results/q4/w6/feasible_region_full/source_local.csv` | reacquisition and clear fields | mechanism analysis |
| W6-A, W7, W8 negative evidence | their `report.md`, paired CSVs | gate, regression and failure sections | ablation/supplement |
| Q4 trajectory | `results/q4/` trajectory/trace artifacts where present | preserve action order and lifecycle endpoints | representative figure |

Do not fabricate official results. Official Windows files, if later available, should be added as a separate clearly labeled source rather than mixed into these offline CSVs.
