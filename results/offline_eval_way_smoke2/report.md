# Q3 Way1 / Way3 Unified Offline Benchmark

Environment: local `offline_sim` practice-only. No official formal test was run.

## Overall Summary

| version | success | mean | median | P95 | max | move m | measure | clear fail | move regret | info regret |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v4 | 100.0% | 4092.60 | 4092.60 | 4092.60 | 4092.60 | 17343.01 | 92.00 | 0 | 1525.61 | 425.00 |
| v6 | 100.0% | 3522.26 | 3522.26 | 3522.26 | 3522.26 | 14206.30 | 101.00 | 0 | 898.27 | 482.00 |
| way1 | 100.0% | 6526.35 | 6526.35 | 6526.35 | 6526.35 | 29826.75 | 86.00 | 0 | 4022.36 | 362.00 |
| way3 | 100.0% | 5344.86 | 5344.86 | 5344.86 | 5344.86 | 22394.31 | 133.00 | 0 | 2535.87 | 667.00 |

## Paired Comparison

| target | base | suite | win rate | mean delta | median | P95 | worst | best |
|---|---|---|---:|---:|---:|---:|---:|---:|
| way1 | v4 | overall | 0.0% | 2433.75 | 2433.75 | 2433.75 | 2433.75 | 2433.75 |
| way1 | v6 | overall | 0.0% | 3004.09 | 3004.09 | 3004.09 | 3004.09 | 3004.09 |
| way3 | v4 | overall | 0.0% | 1252.26 | 1252.26 | 1252.26 | 1252.26 | 1252.26 |
| way3 | v6 | overall | 0.0% | 1822.60 | 1822.60 | 1822.60 | 1822.60 | 1822.60 |

## Adaptation Notes

- Way1 is run through its original `Controller` and Q3 feasible-set stack, with a runner-to-response adapter. Its run-script defaults are used: safe coverage radius 980m, 6 outer points, clear certificate 19m, coarse/fine 40m/15m.
- Way3 is run through its original `Hunter(problem=3)` and `RunnerWorld` adapter. It keeps its 7-point coverage search, stage-style scan then homing/clear design, clear margin 14m, prune radius 30m.
- The simulator, seeds, source generation, fixed location bearing error, movement, measure, switch, clear, and termination rules are our unified local `offline_sim`.
- Lower-bound regret uses the evaluate branch's strict disc-distance Held-Karp movement lower bound. The SLSQP TSPN upper bound was not used because scipy is unavailable in this environment.

See CSV files in this directory for group tables, phase decomposition, source-level FOUND-to-CLEAR statistics, and timelines.
