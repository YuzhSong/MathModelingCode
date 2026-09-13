# Paper Figure and Table Source Index

## Q3

| Suggested item | Recommended title/use | Data source | Existing figure/table |
|---|---|---|---|
| Table Q3-1 | Three official RARC tests | `official_results/q3/q3_formal_summary.csv` | `q3/tables/q3_formal_results.md` |
| Table Q3-2 | V4, V5-B and RARC comparison | `results/q3/offline_eval_v6_n8/report.md`, sections 3–6 | report tables |
| Figure Q3-1 | Mean(T/N) versus ring count n | `results/q3/offline_eval_ring_count_200/summary.csv` | `results/q3/offline_eval_ring_count_200/figures/mean_avg_source_vs_n.svg` |
| Figure Q3-2 | RARC Mean(T/N) by source count | `source_count_summary.csv` and report section F | `results/q3/offline_eval_ring_count_200/figures/final_candidate_avg_source_by_count.svg` |
| Table Q3-3 | n=6..12 sensitivity | ring-count `summary.csv` and report | section D/E of report |
| Table Q3-4 | L2/backbone negative evidence | corresponding reports and paired CSVs | appendix/ablations |

## Q4

| Suggested item | Recommended title/use | Data source | Existing figure/table |
|---|---|---|---|
| Table Q4-1 | Three official 25P-PFRC tests | `official_results/q4/q4_formal_summary.csv` | `q4/tables/q4_formal_results.md` |
| Table Q4-2 | W5 versus W6 final offline comparison | `results/q4/w6/feasible_region_full/report.md` | report overall-comparison table |
| Figure Q4-1 | 25-point symmetric detection geometry | `results/q4/w5_geometry/w5_geometry.svg` | existing SVG; copy not duplicated |
| Table Q4-3 | W6 certificate/full-clear gate | W6 final report and `summary.csv` | report full-clear table |
| Table Q4-4 | W6-A/W7/W8 negative or ablation evidence | respective reports and paired CSVs | appendix/ablations |

No final Q4 trajectory figure was found in the current repository; do not invent one. If needed, use the existing trace/action data as a separately generated paper figure and record the generating script before inclusion.

Suggested placement: core method and final comparisons in the main text; sensitivity, source-level details, L2/backbone/W6-A/W7/W8 and large tables in the appendix or supplementary material.
