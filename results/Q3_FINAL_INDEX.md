# Q3 Final Results Index

## Final candidate

- V6/RARC: `q3/offline_eval_v6_n8/` — [report](q3/offline_eval_v6_n8/report.md), `summary.csv`, `details.csv`, `source_diagnostics.csv`.
- Final implementation: `q3/v6_policy.py`; immutable snapshot: `../frozen/v6_n8_20260912/`.

## Core selection and evolution

- n=6..12: `q3/offline_eval_ring_count_200/` — `report.md`, `paired_vs_n8.csv`, `source_count_summary.csv`, `phase_summary.csv`.
- V0–V3 early baselines: `q3/offline_eval_clean_v0_v3_n6_n9/`.
- V4/V5 evolution: `q3/offline_eval_v4_n8_n9/`, `q3/offline_eval_v5_n8/`.
- Stage-2 mechanism: `q3/offline_eval_stage2_analysis/` and its source `offline_eval_stage2_200/` family.

## Negative and exploratory evidence

- V6-L2: `q3/offline_eval_v6_l2_200/`.
- Ring-only center ablation: `../offline_eval_ring_only_center_ablation_200/`.
- Historical no_signal: `../offline_eval_v6_nosignal_200/`.
- SEARCH-backbone + bundle: `../offline_eval_v6_backbone_bundle_200/`.

All historical result paths remain unchanged. The archive docs under `docs/q3_final/` explain which files are paper-relevant.
