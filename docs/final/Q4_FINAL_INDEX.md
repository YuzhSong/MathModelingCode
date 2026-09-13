# Q4 Final Offline Index

## Final identity confirmed from current code

- Internal final policy: **W6-25PFR** (`q4/w6_policy.py`)
- Paper method: **25P-PFRC — 25-Point Symmetric Search with Persistent Feasible-Region Clearing**
- Thin policy wrapper: `q4/final_policy.py`
- Clean runner: [`run_q4_final.py`](../../run_q4_final.py)
- Final geometry: `q4/w5_geometry.py`; 25 points, side 970 m, cap extension 140 m

## Main data

| Use | Source |
|---|---|
| Final report | [`results/q4/w6/feasible_region_full/report.md`](../../results/q4/w6/feasible_region_full/report.md) |
| Final 200-case details | [`results/q4/w6/feasible_region_full/details.csv`](../../results/q4/w6/feasible_region_full/details.csv) |
| Aggregate summary | [`results/q4/w6/feasible_region_full/summary.csv`](../../results/q4/w6/feasible_region_full/summary.csv) |
| Source-level data | `results/q4/w6/feasible_region_full/source_local.csv` |
| Final policy and mechanisms | `q4/w6_policy.py`, `q4/w2_policy.py`, `q4/w3_policy.py`, `q4/w4a_policy.py`, `q4/routing.py` |

The final W6 overall row reports 200/200 full clear, zero clear failures, zero unresolved targets, mean total 7356.1624 s, P95 9047.5088 s, maximum 11018.9690 s, mean movement 25616.8118 m, and mean per-case T/N 589.4794 s/source. These values are copied from `summary.csv`/`report.md` and are offline only.

## Evolution and negative evidence

Official formal summary (pending Windows merge): `official_results/q4/q4_formal_summary.csv`. It is intentionally not present in the current Mac checkout.

- W0--W4-A: `results/q4/w0_baseline/` through `results/q4/w4a/`.
- W5 geometry selection: `results/q4/w5/`, `results/q4/w5_geometry/`.
- W6-A decomposition: `results/q4/w6a_decomposition/`; useful ablation but not the final W6-25PFR policy.
- W7 macro-regret: `results/q4/w7_macro_regret/`; Gate 2 failed, so no true W7 benchmark was claimed.
- W8 stale repair and W5/W8 candidate comparison: `results/q4/w8_stale_repair/`, `results/q4/final_candidate_validation/`.

All are preserved and should be cited as ablation/negative evidence where useful.
