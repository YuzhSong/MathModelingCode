# Result Appendix Index

## Q3

| Item | Handoff file | Authoritative source |
|---|---|---|
| Three official tests | `q3/tables/q3_formal_results.csv` and `.md` | `official_results/q3/q3_formal_summary.csv` |
| Final 200-case RARC summary | `q3/tables/q3_rarc_offline_summary.csv` | `results/q3/offline_eval_v6_n8/summary.csv` |
| n=6..12 sensitivity | `q3/tables/q3_ring_count_source_summary.csv` | `results/q3/offline_eval_ring_count_200/source_count_summary.csv` |
| Readable n=6..12 table | `q3/tables/q3_n_sensitivity.md` | `results/q3/offline_eval_ring_count_200/summary.csv` |
| N=10..16 source-count result | section F of final ring-count report | `results/q3/offline_eval_ring_count_200/report.md` |
| Complete per-case result | not copied | `results/q3/offline_eval_v6_n8/details.csv` |
| Negative experiments | not copied | L2, backbone, no_signal and ring-only result directories in `results/` |

Q3 final offline aggregate: 100% clear, 0 clear fail, mean total 3496.6868 s, Mean(T/N) 278.6923 s/source, P95 4244.8282 s, max 4817.5002 s, mean movement 13554.1342 m.

## Q4

| Item | Handoff file | Authoritative source |
|---|---|---|
| Three official tests | `q4/tables/q4_formal_results.csv` and `.md` | `official_results/q4/q4_formal_summary.csv` |
| Final 200-case W6 summary | `q4/tables/q4_25ppfr_offline_summary.csv` | `results/q4/w6/feasible_region_full/summary.csv` |
| Readable final summary | `q4/tables/q4_offline_summary.md` | `results/q4/w6/feasible_region_full/summary.csv` |
| Complete per-case result | not copied | `results/q4/w6/feasible_region_full/details.csv` |
| Source-level result | not copied | `results/q4/w6/feasible_region_full/source_local.csv` |
| W5/W6 comparison | final report | `results/q4/w6/feasible_region_full/report.md` |
| Negative/ablation results | not copied | W6-A, W7, W8 and candidate-validation directories in `results/q4/` |

Q4 final offline aggregate: 200/200 full clear, 0 clear fail, 0 unresolved, mean total 7356.1624 s, Mean(T/N) 589.4794 s/source, P95 9047.5088 s, max 11018.9690 s, mean movement 25616.8118 m.

## Metric rules

For formal tests, `avg_time_per_cleared_s = total_virtual_time_s / cleared_count`; `program_real_time_s` is real `/enter`-to-`/exit` time. For multi-case offline results, Mean(T/N) means compute `T_i/N_i` per case and then average the cases. It is not `mean(T)/mean(N)`.

Large case-level tables should remain in the original support directories. The appendix contains summaries and paths, not hundreds of duplicated rows.
