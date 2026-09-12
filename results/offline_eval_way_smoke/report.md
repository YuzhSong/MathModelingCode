# Q3 Way1 / Way3 Unified Offline Benchmark

Environment: local `offline_sim` practice-only. No official formal test was run.

## Overall Summary

| version | success | mean | median | P95 | max | move m | measure | clear fail | move regret | info regret |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v4 | 100.0% | 3883.56 | 3944.69 | 4683.36 | 4787.61 | 15617.79 | 116.25 | 0 | 1566.69 | 572.25 |
| v6 | 100.0% | 3706.12 | 3786.88 | 4368.82 | 4424.82 | 14636.85 | 119.25 | 0 | 1370.50 | 591.00 |
| way1 | 100.0% | 6235.74 | 6332.79 | 6503.00 | 6526.35 | 27919.95 | 102.50 | 0 | 4027.12 | 464.00 |
| way3 | 100.0% | 5619.80 | 5449.80 | 6814.12 | 7036.36 | 23702.75 | 136.50 | 0 | 3183.68 | 691.50 |

## Paired Comparison

| target | base | suite | win rate | mean delta | median | P95 | worst | best |
|---|---|---|---:|---:|---:|---:|---:|---:|
| way1 | v4 | overall | 0.0% | 2352.18 | 2503.82 | 3308.11 | 3437.67 | 963.42 |
| way1 | v6 | overall | 0.0% | 2529.62 | 2661.63 | 3399.27 | 3469.01 | 1326.21 |
| way3 | v4 | overall | 0.0% | 1736.24 | 1469.13 | 3006.55 | 3239.59 | 767.12 |
| way3 | v6 | overall | 0.0% | 1913.68 | 1769.97 | 2810.53 | 2984.87 | 1129.91 |

## Adaptation Notes

- Way1 is run through its original `Controller` and Q3 feasible-set stack, with a runner-to-response adapter. Its run-script defaults are used: safe coverage radius 980m, 6 outer points, clear certificate 19m, coarse/fine 40m/15m.
- Way3 is run through its original `Hunter(problem=3)` and `RunnerWorld` adapter. It keeps its 7-point coverage search, stage-style scan then homing/clear design, clear margin 14m, prune radius 30m.
- The simulator, seeds, source generation, fixed location bearing error, movement, measure, switch, clear, and termination rules are our unified local `offline_sim`.
- Lower-bound regret uses the evaluate branch's strict disc-distance Held-Karp movement lower bound. The SLSQP TSPN upper bound was not used because scipy is unavailable in this environment.

See CSV files in this directory for group tables, phase decomposition, source-level FOUND-to-CLEAR statistics, and timelines.
