# Q4 Experiment Index

| Research question | Main variant | Result directory | Main report | Core conclusion | Paper role |
|---|---|---|---|---|---|
| Can Q3 transfer directly to Q4? | W0 | `results/q4/w0_baseline/` | `report.md` | Direct transfer fails under directional visibility | Motivation |
| What geometry covers directional sources? | W1/W5 geometry | `results/q4/w1_geometry/`, `results/q4/w5_geometry/` | `geometry_report.md` | Use fixed 25-point geometry for final method | Main method |
| How to handle FOUND targets after no_signal? | W2 | `results/q4/w2/` | `report.md` | Persistent lifecycle restores correctness | Main method |
| How to reduce local reacquisition cost? | W3 | `results/q4/w3/` | `report.md` | Adaptive reacquisition reduces local overhead | Main method |
| How to order search, reacquire, localize, clear? | W4-A | `results/q4/w4a/` | `report.md` | Unified rolling task pool with open-route replanning is retained | Main method |
| Does continuity/backbone commitment help? | W4-B | `results/q4/w4b/` | `report.md` | Over-constrained continuity worsens route efficiency | Negative result |
| Can local tail acceleration replace W5? | W6 | `results/q4/w6/`, `results/q4/w6a_decomposition/` | `report.md` | Tail improves in some cases but route-level regressions remain | Ablation/negative |
| Can static macro regret guide scheduling? | W7 | `results/q4/w7_macro_regret/` | `report.md` | Shadow calibration fails; no final policy benchmark | Negative result |
| Can stale-state repair replace W5? | W8 | `results/q4/w8_stale_repair/`, `results/q4/final_candidate_validation/` | `report.md` | W8 has useful tail evidence but held-out regressions prevent replacement | Robustness comparison |
| What is the final frozen choice? | W6-25PFR vs W5/W8 | `results/q4/w6/feasible_region_full/`, `results/q4/final_candidate_validation/` | `report.md`, `summary.csv` | W6-25PFR/25P-PFRC is final; W5/W8 remain comparison evidence | Main result |
