# Q3 Experiment Index

| Research question | Baseline → variant | Result directory / report | Main CSV | Conclusion | Paper use |
|---|---|---|---|---|---|
| Early baseline evolution | V0 → V3 | `results/q3/offline_eval_clean_v0_v3_n6_n9/` | `summary.csv`, `paired_key_comparison.csv` | staged development history | Archive / brief background |
| Rolling joint routing | V3 → V4 | `results/q3/offline_eval_v4_n8_n9/report.md` | `paired_v4_minus_v3.csv` | rolling joint scheduling is core | Main mechanism |
| Local-information supplement | V4 → V5-A/B/final | `results/q3/offline_eval_v5_n8/report.md` | `paired_v5_minus_v4.csv` | local score alone is not enough | Ablation |
| Route-aware final strategy | V4/V5 → V6 | `results/q3/offline_eval_v6_n8/report.md` | `details.csv`, `summary.csv` | final RARC candidate | Main result |
| Ring-count sensitivity | V6 n=6..12 | `results/q3/offline_eval_ring_count_200/report.md` | `paired_vs_n8.csv`, `source_count_summary.csv` | n=8 selected | Main sensitivity |
| Stage-2 mechanism | V6 vs stage2 variants | `results/q3/offline_eval_stage2_analysis/report.md` | `phase_summary.csv`, `v6_regression_decomposition.csv` | explains route/task coupling | Ablation / supplement |
| Deep lookahead | V6 → V6-L2 | `results/q3/offline_eval_v6_l2_200/report.md` | `details.csv` | unstable/worse | Negative result |
| Ring-only center ablation | V6 → ring-only | `results/offline_eval_ring_only_center_ablation_200/report.md` | `paired_comparison.csv`, `theory.csv` | coverage idea does not ensure lower total time | Optional ablation |
| Historical no_signal | V6 → no_signal variants | `results/offline_eval_v6_nosignal_200/report.md` | `paired_comparison.csv`, `negative_info_summary.csv` | limited gain, not replacement | Supplementary |
| SEARCH backbone + bundle | V6 → BackboneBundle | `results/offline_eval_v6_backbone_bundle_200/report.md` | `paired_comparison.csv`, `tail_cases.csv` | over-constrains rolling flexibility | Negative result |
| Official practice | adapter only; no raw result found | `main.py`, `scripts/run_official_practice.py` | none | no official metric claimed | Procedure only |

Historical pilot/smoke/refine directories under `results/q3/` are retained and are indexed by their parent experiment family; they are not overwritten or promoted to final evidence.
