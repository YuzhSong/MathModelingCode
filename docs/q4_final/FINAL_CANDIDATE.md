# Q4 Final Candidate

> Authoritative current archive: [`docs/final/Q4_FINAL_INDEX.md`](../final/Q4_FINAL_INDEX.md). The current code and latest W6 report supersede any older W5/held-out comparison references below; historical reports themselves remain unchanged.

## Identity

- Internal implementation: W6-25PFR
- Paper name: 25-Point Symmetric Search with Persistent Feasible-Region Clearing (25P-PFRC)
- Chinese name: 25点对称搜索与持续可行域清除策略
- Official clean runner: `run_q4_final.py`
- Development official adapter: `main.py --problem 4 --mode official --strategy w5`

## Core code paths

- Final policy: `q4/w6_policy.py` (single source of truth; `q4/final_policy.py` is a thin wrapper)
- Final geometry: `q4/w5_geometry.py`
- Persistent target lifecycle: `q4/w2_policy.py`
- Adaptive reacquisition: `q4/w3_policy.py`
- Unified rolling task pool: `q4/w4a_policy.py`
- Q4 routing: `q4/routing.py`
- Official API client and run logger: `q3/api_client.py`, `q3/run_logger.py`

Q4 still reuses shared Q3 foundations such as `q3.models`, `q3.geometry`, `q3.routing`, and `q3.offline_policy`. This should be disclosed as shared infrastructure, not hidden.

## Method components

1. A 25-point deterministic detection geometry with `a=970 m`, `p=140 m`, and supplement radius `sqrt(3)*970+140`.
2. Persistent target lifecycle for directional sources: UNKNOWN, ACTIVE, REACQUIRE, DEFERRED, RESOLVED.
3. Adaptive coarse-to-fine reacquisition after directional visibility loss.
4. Dynamic unified task pool for SEARCH, REACQUIRE, LOCALIZE, and CLEAR tasks.
5. Open-route rolling replanning after every real action.
6. Direction-only persistent feasible-region certificate; only an outer-region MEC at most 20 m creates a guaranteed-clear task.

## Final validation summary

The final W6-25PFR validation is recorded under `results/q4/w6/feasible_region_full/`. The earlier W5/W8 validation remains historical comparison evidence under `results/q4/final_candidate_validation/`.

| Dataset | Cases | Full clear | Mean total s | P95 s | Pooled T/N s/source | Source |
|---|---:|---:|---:|---:|---:|---|
| historical 200 | 200 | 200/200 | 7491.8110 | 9250.0868 | 588.0542 | `historical_200/summary.csv` |
| held-out 600 | 600 | 600/600 | 7365.1119 | 8763.0741 | 571.1603 | `heldout_600/summary.csv` |
| stress 24 | 24 | 24/24 | 6868.7234 | 11108.2835 | 592.9833 | `stress_24/summary.csv` |

The W8 robustness candidate also achieves full clear but is not selected: on held-out 600, W8 has mean `+3.4976 s` vs W5, pooled T/N `+0.2712 s/source`, 48 regressions over 100 s, 19 regressions over 300 s, and a worst regression of `+2309.8168 s`.

## Why W6-25PFR is final

W6-25PFR preserves full clearing in the completed 200-case validation and improves the aggregate time/movement metrics relative to W5 while reducing the most extreme reacquisition count. The complete paired evidence remains the authoritative record; W6-A/W7/W8 are not alternative final implementations.
