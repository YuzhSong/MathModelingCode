# Offline Final Summary

数据全部来自现有 CSV/report；本轮未重新运行实验。

## Q3 — RARC / frozen V6, n=8

Source: `results/q3/offline_eval_v6_n8/summary.csv`, overall row; 200 cases = 100 random + 50 min_reff + 50 collinear, 2548 total sources.

| Metric | Value |
|---|---:|
| ClearRate | 100% |
| Clear fail | 0 |
| Mean total | 3496.6868 s |
| Mean(T/N) | 278.6923 s/source |
| P95 total | 4244.8282 s |
| Max total | 4817.5002 s |
| Mean move | 13554.1342 m |
| n | 8 |

Final V6 source-count values from the existing ring-count report:

| N | Cases | Mean(T/N) s/source |
|---:|---:|---:|
| 10 | 23 | 327.18 |
| 11 | 38 | 309.00 |
| 12 | 34 | 287.51 |
| 13 | 33 | 273.89 |
| 14 | 34 | 255.55 |
| 15 | 21 | 239.17 |
| 16 | 17 | 232.14 |

## Q4 — W6-25PFR / 25P-PFRC

Source: `results/q4/w6/feasible_region_full/summary.csv`, overall row; 200 cases = 100 random + 50 min_reff + 50 collinear.

| Metric | Value |
|---|---:|
| Full clear | 200/200 |
| Clear fail | 0 |
| Unresolved | 0 |
| Mean total | 7356.1624 s |
| Mean(T/N) | 589.4794 s/source |
| P95 total | 9047.5088 s |
| Max total | 11018.9690 s |
| Mean move | 25616.8118 m |
| Search points parameter | 25 |

Mean(T/N) is always the mean of per-case `T_i/N_i`; it is not `mean(T)/mean(N)`.

## Official-result boundary

These are offline simulator results only. The completed official formal results are stored separately in `official_results/q3/q3_formal_summary.csv` and `official_results/q4/q4_formal_summary.csv`; do not infer formal values from `runs_summary.csv` or offline summaries.
