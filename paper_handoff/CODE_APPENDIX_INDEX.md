# Complete Final Code Appendix Index

The appendix code is the complete static project-internal import closure of each clean final runner. It excludes historical policies, ablations, benchmark/plotting/debug scripts and `offline_sim`.

## Appendix A — Q3 RARC

Full merged source: [q3/Q3_CODE_APPENDIX.md](q3/Q3_CODE_APPENDIX.md). Exact copied source files:

1. `run_q3_final.py` — final RARC runner.
2. `q3/api_client.py` — simulator API client and request IDs.
3. `q3/logger.py` — JSONL API logging.
4. `q3/run_logger.py` — run metrics and real-time boundary logging.
5. `q3/models.py` — points, channels, tracks and visible state.
6. `q3/offline_policy.py` — task model, runner adapter and policy base.
7. `q3/v6_policy.py` — RARC/frozen V6 policy.
8. `q3/v5_policy.py` — inherited V5/V4 policy machinery used by V6.
9. `q3/v5_prediction.py` — visible-geometry prediction used by V6.
10. `q3/geometry.py` — geometry helpers.
11. `q3/planner.py` — task planning helpers imported by the final chain.
12. `q3/routing.py` — open-route optimizer.
13. `q3/__init__.py` — package marker.

## Appendix B — Q4 25P-PFRC

Full merged source: [q4/Q4_CODE_APPENDIX.md](q4/Q4_CODE_APPENDIX.md). Q4 uses the Q3 shared foundation files listed above, plus:

1. `run_q4_final.py` — final W6-25PFR runner.
2. `q4/final_policy.py` — thin final policy wrapper.
3. `q4/w6_policy.py` — W6-25PFR final policy.
4. `q4/w6_feasible_region.py` — persistent bearing feasible-region certificate.
5. `q4/w5_policy.py` — W5 geometry policy ancestry.
6. `q4/w5_geometry.py` — final 25-point geometry.
7. `q4/w4a_policy.py` — unified rolling task pool.
8. `q4/w3_policy.py` — adaptive reacquisition.
9. `q4/w2_policy.py` — target lifecycle.
10. `q4/w1_policy.py` — Q4 search-point support.
11. `q4/routing.py` — Q4 routing utilities.
12. `q4/geometry.py` — Q4 geometry helpers.
13. `q3/__init__.py` and `q4/__init__.py` — package markers loaded by the import chain.

The appendix includes the complete source of every listed file, not an ellipsis or pseudocode. It does not include W0–W5 as standalone historical policies, W6-A/W7/W8, L2, no_signal, ring-only, backbone bundle, or offline simulator internals.
