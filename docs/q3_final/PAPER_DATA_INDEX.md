# Q3 Paper Data Index

## Main-paper recommended

| Item | Exact source | Column / section | Recommended use |
|---|---|---|---|
| Final RARC metrics | `results/q3/offline_eval_v6_n8/summary.csv` | `version=v6`, `suite=overall`; `mean_total_time_s`, `mean_avg_source_s`, `p95_total_time_s`, `max_total_time_s` | Main result table |
| Baseline vs rolling vs route-aware | `results/q3/offline_eval_v4_n8_n9/paired_comparison.csv`, `results/q3/offline_eval_v6_n8/report.md` | V4/V6 paired fields and report comparison | Evolution table |
| n=6..12 sensitivity | `results/q3/offline_eval_ring_count_200/paired_vs_n8.csv` | n-specific total/T/N and paired deltas | Parameter-selection table |
| N=10..16 | `results/q3/offline_eval_v6_n8/details.csv` | `total`, `total_time_s`, `avg_source_s`; group by `total` and average case-level `avg_source_s` | Source-count plot/table |
| Representative route/trajectory | `results/q3/offline_eval_stage2_analysis/typical_timelines.csv` and `results/q3/offline_eval_v6_backbone_bundle_200/figures/` | timeline/action coordinates | Mechanism illustration; BB figures are negative evidence |
| Official vs offline | No saved official raw file found | N/A | State data unavailable; do not fabricate comparison |

## Ablation recommended

- Local-information vs global route: `results/q3/offline_eval_v5_n8/report.md` and `paired_v5_minus_v4.csv` — main ablation if space allows.
- Lookahead negative result: `results/q3/offline_eval_v6_l2_200/report.md` — concise supplementary evidence.
- Backbone negative result: `results/offline_eval_v6_backbone_bundle_200/report.md` and `paired_comparison.csv` — demonstrates why preserving SEARCH order can hurt.
- Historical no_signal: `results/offline_eval_v6_nosignal_200/report.md` — Optional / supplementary.
- Ring-only: `results/offline_eval_ring_only_center_ablation_200/report.md` — Optional / omit if page-limited.

For every Mean(T/N) claim, use per-case `total_time_s / total` first, then average those case values; do not use pooled total divided by pooled N unless explicitly labeled.
