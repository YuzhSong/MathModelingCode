# Q4 Paper Data Index

## Main-paper recommended

| Item | Source file | Columns / section | Recommended use |
|---|---|---|---|
| Final method definition | `results/q4/final_documentation/q4_final_25gasr_method.md` | all sections | Method description |
| Version-to-method mapping | `results/q4/final_documentation/q4_internal_version_crosswalk.md` | table | Keep W-numbers out of main narrative |
| Final evidence index | `results/q4/final_documentation/q4_evidence_index.md` | claim table | Source of exact claims |
| Final W6-25PFR metrics | `results/q4/w6/feasible_region_full/summary.csv` | `suite=overall` row | Main Q4 frozen-policy result |
| Historical 200 metrics | `results/q4/final_candidate_validation/historical_200/summary.csv` | `policy=w5` row | Compatibility with prior 200-case benchmark |
| Stress 24 metrics | `results/q4/final_candidate_validation/stress_24/summary.csv` | `policy=w5` row | Tail/stress evidence |
| W5 vs W8 paired selection | `results/q4/final_candidate_validation/heldout_600/paired_summary.json` | paired deltas and regressions | Justify not replacing W5 |
| Core result table | `results/q4/final_documentation/q4_core_results_for_paper.csv` | all fields | Draft paper tables |
| Metric definitions | `results/q4/final_documentation/q4_metric_definitions.md` | all sections | Avoid Macro vs Pooled T/N confusion |
| Figure/table plan | `results/q4/final_documentation/q4_figure_table_plan.md` | all sections | Paper figure planning |

## Main numbers to cite

- W6-25PFR 200-case: full clear `200/200`, mean total `7356.1624 s`, P95 `9047.5088 s`, pooled T/N `577.4068 s/source`.
- W5 historical 200: full clear `200/200`, mean total `7491.8110 s`, P95 `9250.0868 s`, pooled T/N `588.0542 s/source`.
- W5 stress 24: full clear `24/24`, mean total `6868.7234 s`, P95 `11108.2835 s`, pooled T/N `592.9833 s/source`.
- W8 held-out 600 is not final: mean delta W8-W5 `+3.4976 s`, worst regression `+2309.8168 s`, `48` regressions over 100 s and `19` over 300 s.

## Ablation recommended

- Direct transfer failure: W0.
- Persistent lifecycle: W2.
- Adaptive reacquisition: W3.
- Dynamic routing: W4-A.
- Continuity negative result: W4-B.
- Tail repair negative/robustness evidence: W6/W8.

Do not require the paper to narrate every W-number. Use W labels only in appendix or parentheses.
