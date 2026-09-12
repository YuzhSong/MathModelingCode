# Q3 Way1 / Way3 Unified Offline Benchmark

Environment: local `offline_sim` practice-only. No official formal test or official HTTP simulator was run.

Cases: 100 random seeds `0:100`, 50 `min_reff` seeds `10000:10050`, 50 `collinear` seeds `10000:10050`. All four policies use the same generated cases and runner timing rules.

## 1. Strategy Structure Confirmed From Code

### Way1

Source: `external/SXJM-way1/Way1/radio_locator/src`.

- Coverage/search: `coverage/q3_hex_cover.py` uses center + a regular outer ring, default `outer_points=6`, but with `safe_receive_radius=980m`; if the single ring fails coverage it falls back to a triangular grid. In this run the 7-point plan was used.
- Feasible region: `set_estimation/q3_feasible_set.py` uses conservative quadtree set membership, bearing wedges, near disks, arena constraint, and radius-consistency constraints after eliminating unknown `R_eff`.
- MEC criterion: `RobotConstants.clear_mec_radius=19.0`, not 20.0. This is a conservative certificate inside the physical 20m clear radius.
- Active localization: `localization/second_viewpoint.py` and `optimization/robust_lookahead.py` implement minimax candidate scoring over representative feasible points.
- Scheduler: `runtime/controller.py` uses an online loop: READY_TO_CLEAR first, then LOCALIZE, then per-channel COVER sweep. It records coverage per `(channel, cover point)` and only marks ABSENT after that channel is measured negative at every cover point.
- Next FOUND measure generation: for DETECTED/LOCALIZING channels, `task_scheduler.localize_candidates()` calls minimax/robust lookahead and avoids repeated apex points.
- Route planning: coverage route is ordered by `Scheduler.order_cover_route()` using `two_opt.solve_route`; ongoing task selection is local online scoring, not a global V4-style task-route solver.

### Way3

Source: `external/SXJM-way3/Way3/jammerhunt`.

- Coverage scan: `coverage.omni_scan_points()` searches center + K outer ring (`K=6,7,8`) and accepts the first with worst sampled nearest distance <= `1000-50=950m`. In practice Q3 uses 7 points.
- Stage structure: `agent.Hunter.run()` first executes coverage scanning, then calls `_clear_all_present()`.
- FOUND handling during scan: `_active_channels_for_scan()` prunes cleared/absent channels and skips detected channels once `region_r <= prune_radius_m=30`.
- Homing / near-field localization: `_home_and_clear()` uses single-bearing baseline establishment, forward/perpendicular moves, then orbit triangulation around the current estimate with `orbit_radius=85m`, `orbit_delta=42deg`.
- Clear criterion: blind clear only when reliable and `region_r <= clear_margin_m=14`, then clear at the estimated center. `near` immediately clears at current position.
- Route planning: scan points and later known estimated clear targets are ordered by nearest-neighbor + 2-opt (`geometry.ordered_tour`). Homing itself is per-channel and mostly sequential.
- Search/localize staging: yes, the implementation is explicitly stage-style: coverage scan first, then ordered homing/clear of detected channels.

## 2. Adaptation

Added a bridge in `q3/external_policies.py`:

- `policy_way1(runner)`: wraps our `offline_sim` runner as Way1's simulator response objects and runs Way1's original `Controller`.
- `policy_way3(runner)`: uses Way3's original `Hunter(problem=3)` through its `RunnerWorld`.

Important fairness notes:

- The physical simulator is unified: our `offline_sim` case generator, position-fixed bearing error, movement speed, measure/switch/clear timing, clear success rule, source distribution, and termination rules.
- Way1/Way3 core strategy constants were not tuned to our V6. Way1 keeps its conservative `980m` coverage radius and `19m` clear certificate; Way3 keeps `14m` clear margin and its homing constants.
- No ground truth is passed to any policy. Ground truth is used only after each episode for lower-bound/regret analysis.
- The evaluate branch's exact disc-distance Held-Karp movement lower bound was adapted. The SLSQP TSPN upper-bound refinement was not used because `scipy` is not available in this environment.

## 3. Main Benchmark

| version | success | mean s | median s | P95 s | max s | std s | move m | measure | switch | clear fail |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| V4 | 100% | 3579.99 | 3605.04 | 4372.36 | 4886.33 | 517.53 | 13979.83 | 121.04 | 115.12 | 0 |
| V6 | 100% | 3496.69 | 3534.23 | 4244.83 | 4817.50 | 505.40 | 13554.13 | 121.31 | 115.58 | 0 |
| Way1 | 100% | 5835.43 | 5770.98 | 6798.73 | 7175.39 | 573.34 | 25851.36 | 105.05 | 76.23 | 0 |
| Way3 | 100% | 5134.83 | 4988.93 | 6981.40 | 8516.61 | 1050.29 | 21253.62 | 138.11 | 129.85 | 0 |

All 800 episodes succeeded. Time-component identity max absolute error: `7.9e-6s`.

## 4. Paired Comparison

Delta is `target - base` on the same seed. Negative would mean the target is faster.

| target | base | suite | win rate | mean delta s | median s | P95 s | worst regression s | best improvement s |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Way1 | V6 | random | 0% | 2270.53 | 2269.60 | 3229.08 | 3528.49 | 961.49 |
| Way1 | V6 | min_reff | 0% | 1927.59 | 1849.35 | 2789.12 | 3289.87 | 951.21 |
| Way1 | V6 | collinear | 0% | 2886.32 | 2763.52 | 3858.76 | 4344.63 | 1980.29 |
| Way1 | V6 | overall | 0% | 2338.74 | 2330.33 | 3513.29 | 4344.63 | 951.21 |
| Way3 | V6 | random | 0% | 1444.79 | 1390.15 | 2338.98 | 3383.08 | 492.51 |
| Way3 | V6 | min_reff | 0% | 2451.35 | 2433.77 | 3740.15 | 4024.72 | 1094.41 |
| Way3 | V6 | collinear | 0% | 1211.65 | 1106.48 | 2718.25 | 3496.57 | 86.55 |
| Way3 | V6 | overall | 0% | 1638.14 | 1464.46 | 3186.13 | 4024.72 | 86.55 |

No Way1/Way3 case beat V4 or V6 in this unified environment. The "typical fast" cases in `typical_cases.csv` are therefore least-slow cases, not wins.

## 5. Time Decomposition

Overall mean phase decomposition:

| version | phase | move s | measure s | switch s | clear s | total phase s | move m | measure count |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| V6 | SEARCH | 931.02 | 496.15 | 95.92 | 0.00 | 1523.09 | 4655.08 | 99.23 |
| V6 | FOUND | 1094.01 | 110.43 | 19.66 | 0.00 | 1224.10 | 5470.07 | 22.09 |
| V6 | CLEAR | 685.80 | 0.00 | 0.00 | 63.70 | 749.50 | 3428.98 | 0.00 |
| Way1 | SEARCH | 2379.82 | 409.28 | 76.23 | 0.00 | 2865.33 | 11899.10 | 81.86 |
| Way1 | FOUND | 2432.67 | 115.95 | 0.00 | 0.00 | 2548.62 | 12163.36 | 23.19 |
| Way1 | CLEAR | 357.78 | 0.00 | 0.00 | 63.70 | 421.48 | 1788.90 | 0.00 |
| Way3 | SEARCH | 955.08 | 412.18 | 81.44 | 0.00 | 1448.69 | 4775.40 | 82.44 |
| Way3 | FOUND | 3019.20 | 278.38 | 48.42 | 0.00 | 3346.00 | 15096.01 | 55.68 |
| Way3 | CLEAR | 276.44 | 0.00 | 0.00 | 63.70 | 340.14 | 1382.21 | 0.00 |

Way1 relative to V6:

```text
+ 2459.44 s movement
-   81.35 s measurement
-   39.35 s switching
+    0.00 s clear
= 2338.74 s total
```

Way3 relative to V6:

```text
+ 1539.90 s movement
+   83.98 s measurement
+   14.27 s switching
+    0.00 s clear
= 1638.14 s total
```

## 6. Where The 5000+s Goes

Way1 mean is `5835.43s`, about `+2338.74s` over V6. The extra time is almost entirely movement:

- `+1448.80s` SEARCH movement: Way1's per-channel coverage sweep and online local scoring produce much longer travel during discovery.
- `+1338.66s` FOUND movement: Minimax points are geometrically conservative but globally route-expensive.
- `-328.02s` CLEAR movement: Way1 clears from tighter certificates and pays less final clear travel.
- `-120.70s` information time: fewer measures and channel switches than V6, but that saving is tiny compared with added movement.

Way3 mean is `5134.83s`, about `+1638.14s` over V6:

- `+1925.19s` FOUND movement: sequential homing/orbit triangulation is the dominant cost.
- `+167.95s` FOUND measurement/switch overhead: homing averages `4.37` supplement measures/source versus V6's `1.73`.
- `+24.06s` clear/search movement combined roughly cancels some SEARCH/CLEAR differences.
- `+98.25s` total information overhead.

So Way3's 5000+s is expensive because of FOUND-to-CLEAR homing, not because its global coverage scan is long. Way1 is expensive because both coverage/search movement and minimax localization movement are high.

## 7. FOUND To CLEAR Statistics

| version | supplements/source | 0 supp | 1 supp | 2 supp | 3 supp | >=4 supp | found-after move/source m | found-to-clear elapsed s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V4 | 1.68 | 0.04% | 38.74% | 55.02% | 5.61% | 0.59% | 797.28 | 1275.93 |
| V6 | 1.73 | 0.04% | 34.89% | 57.65% | 6.59% | 0.82% | 698.51 | 1269.67 |
| Way1 | 1.82 | 0.04% | 30.02% | 57.97% | 11.81% | 0.16% | 1095.15 | 233.13 |
| Way3 | 4.37 | 0.04% | 1.26% | 16.48% | 26.88% | 55.34% | 1293.42 | 2976.38 |

Way3's homing deliberately spends many near-field observations. It is robust, but expensive. Way1 has moderate supplement count, but the selected minimax points are far enough that movement dominates.

## 8. Lower-Bound / Regret

The movement lower bound is the evaluate branch's exact Held-Karp path over 20m clear disks:

`w0_i=max(0, |p_i|-20)`, `w_ij=max(0, |p_i-p_j|-40)`.

Mean overall:

| version | actual / abs LB | move regret s | info regret s |
|---|---:|---:|---:|
| V4 | 2.58 | 1383.18 | 601.33 |
| V6 | 2.52 | 1298.04 | 603.16 |
| Way1 | 4.38 | 3757.48 | 482.46 |
| Way3 | 3.68 | 2837.94 | 701.40 |

This agrees with the direct decomposition: Way1/Way3 lose primarily through movement. Way1's information regret is actually lower than V6, but the movement regret is much higher.

## 9. Typical Cases

See `typical_timelines.csv` for action-level timelines. Selected cases:

- Way1 least-slow case: `min_reff seed 10049`.
- Way1 worst regression: `collinear seed 10048`.
- Way3 least-slow case: `collinear seed 10026`.
- Way3 worst regression: `min_reff seed 10033`.
- V6 strongest lead over both external strategies: `min_reff seed 10048`.

The full event rows include `time_s`, `position`, `channel`, `phase`, `action`, `result`, and movement for each action.

## 10. Files

New/modified files for this stage:

- `q3/external_policies.py`: Way1/Way3 policy adapters.
- `scripts/run_way_benchmark.py`: unified benchmark and analysis script.
- `offline_sim/harness.py`: added post-episode action log fields `virtual_time_s` and `svd_deg`; simulator physics unchanged.
- `results/offline_eval_way1_way3_200/*.csv`: benchmark outputs and decomposition tables.

Main output files:

- `summary.csv`: group and overall metrics.
- `paired_comparison.csv`: same-seed paired deltas.
- `phase_summary.csv`: phase/time decomposition.
- `delta_vs_v6_decomposition.csv`: Way1/Way3 versus V6 time source decomposition.
- `source_found_clear.csv` and `supplement_summary.csv`: per-source and aggregate FOUND-to-CLEAR diagnostics.
- `typical_timelines.csv`: event timeline rows for selected cases.

## 11. Observations

- V6 remains the best current candidate in this unified offline environment.
- Way1 and Way3 are both correct and stable here, but neither is competitive with V4/V6 under the same simulator.
- Way1 confirms that fewer measurements/switches do not help if movement grows by 12.3km on average.
- Way3 confirms that robust homing can guarantee clearing but pays heavily in repeated FOUND-stage movement and measurements.
- The current bottleneck remains movement, especially FOUND-stage movement for Way3 and search/localization movement for Way1.
