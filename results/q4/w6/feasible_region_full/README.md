# W6-25PFR final offline validation

This directory contains the completed 200-case offline validation for the
frozen Q4 policy `W6-25PFR` / `25-Point Symmetric Search with Persistent
Feasible-Region Clearing`.

The policy uses the W5 geometry implementation with exactly 25 points:
`a=970 m`, `p=140 m`, `rho=sqrt(3)*a+p=1820.089... m`. The historical
`n=27` value found in the original `details.csv` is a metadata labeling error
from a shared benchmark summary helper; it does not describe the executed
policy geometry. The original CSV is retained unchanged for provenance.

Final recorded gate: 200/200 full clear, 0 clear failure, 0 unresolved, and 0
guaranteed-clear failure. No benchmark is rerun by this documentation note.

Recorded per-source metrics are `Macro-average T/N=589.4794 s/source` and
`Pooled T/N=577.4068 s/source`; they are different aggregations and must not
be interchanged.
