# Q4 `random/2` route regression diagnosis

Source trace: `traces/w5pro_random_smooth_2.json` and the paired frozen W5 trace.

## Current paired result

| strategy | search points | cleared | total time (s) | move distance (m) | measurements |
|---|---:|---:|---:|---:|---:|
| W5 | 8 | 16/16 | 5303.34 | 19276.68 | 241 |
| W5Pro | 8 | 16/16 | 5780.96 | 24249.81 | 148 |

The former 18-point W5Pro regression is no longer present: discovery is capped
at 8 backbone points for this case. The remaining regression is execution
geometry, not backbone expansion: W5Pro saves 93 measurements but travels
4973.13 m more, leaving a 477.63 s time deficit.

## W5Pro selected-task movement attribution

| task family | count | selected-task distance (m) |
|---|---:|---:|
| SEARCH | 8 | 4203.45 |
| MEASURE | 22 | 12562.39 |
| CLEAR | 13 | 3386.68 |
| REACQUIRE | 30 | 3541.60 |

The largest jumps are REACQUIRE channel 13 (1891.91 m), MEASURE channel 4
(1153.80 m), and MEASURE channel 11 (1076.18 m). A nearest-point penalty was
tested and rejected because it increased the total to 5801.81 s; task ordering
must preserve localization dependencies rather than greedily minimize each
individual jump.

## Mechanism audit

- Hard Clear-Ready preemption fired 13 times in the current trace; directional
  sources receive higher urgency.
- NBV feasibility is filtered before minimax selection. Current trace:
  `selected=0`, `effective=0`; no rejected candidate contributes reward.
- Intersection and route-repair counters count only physically applied or
  genuinely required actions.
- Tail fallback has per-channel and per-state budgets and emits
  `switch_strategy` after exhaustion.

## Gate

The case is correct and fully cleared, but W5Pro remains above W5 by 477.63 s.
The 7-case paired suite and full Hard matrix must remain deferred until this
single regression passes the time gate.
