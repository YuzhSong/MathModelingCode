# Q4 Method Map

Internal version labels are development names. The paper should tell the modeling story by mechanism, not by W-number.

| Internal version | Paper role | Core idea | Final? |
|---|---|---|---|
| W0 | Direct-transfer baseline | Apply Q3-style strategy to Q4 directional sources | No |
| W1 | Geometric coverage transition | Triangular detection backbone | No |
| W2 | Persistent target lifecycle | Keep directional targets after visibility loss | Core mechanism |
| W3 | Adaptive reacquisition | Coarse-to-fine directional source recovery | Core mechanism |
| W4-A | Dynamic rolling routing | Unified task pool with open-route replanning | Core mechanism |
| W4-B | Continuity ablation | Backbone continuity and insertion constraint | No |
| W5 | 25-point symmetric geometry baseline | 25-point geometry plus W4-A/W3/W2 mechanisms | Historical support |
| W6-25PFR | 25P-PFRC | W5 mechanisms plus persistent feasible-region clearing certificate | YES / FINAL |
| W7 | Shadow scheduling diagnostic | Static macro-regret proxy | No |
| W8 | Stale-state repair candidate | Local repair for stale shrink events | No; robustness comparison only |

Paper narrative should be:

1. Directional sources break Q3's direct-transfer assumption.
2. Q4 needs deterministic geometric visibility coverage.
3. Directional visibility can disappear, so targets need persistent lifecycle states.
4. Local reacquisition must be adaptive rather than fixed-step.
5. Global ordering is handled by rolling route-aware task pooling.
6. Final 25-point geometry plus these mechanisms form 25G-ASR.
