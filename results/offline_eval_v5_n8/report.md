# Q3 V5 FOUND-source task-generation study

## Scope and decision

This study used only the local `offline_sim` practice environment. It did not call any official HTTP endpoint or formal test.

The frozen V4/n=8 candidate remains the recommended policy. V5 does not satisfy the replacement gate: all variants preserve 100% clearance and zero clear failures, but none gives a material, tail-safe total-time improvement over V4.

## Frozen baseline and isolation

- V4/n=8 was copied to `frozen/v4_n8_20260911/` before V5 edits, with SHA-256 checksums.
- The diagnostic V4 rerun matched all 200 frozen same-seed cases exactly: maximum time and movement deltas were both 0, with no action-count mismatch.
- V5 modules import no `offline_sim` internals and are statically rejected if they access `.case`, `.engine`, `.sources`, or `.jammers`.
- Policies receive only the API-facing runner proxy. Ground truth is not used by V4 or V5 decisions.

## V5 rules

All variants inherit V4's fixed n=8 search coverage, UNKNOWN scanning, 16-source early stop, `MEC <= 20.0m` clearing rule, and rolling online router.

### V5-A: wait for a mandatory SEARCH point

For each FOUND channel with `MEC > 20m`, V5-A compares the existing V4 dedicated-measure point with every unfinished mandatory SEARCH point that guarantees reception for the current feasible polygon. The SEARCH-point option has zero incremental movement cost because it must be visited anyway. V5-A waits when that option has no larger estimated incremental completion time; otherwise it emits the unchanged V4 dedicated MEASURE task.

### V5-B: maximize one-shot clearance probability

V5-B does not wait for SEARCH. It evaluates a deterministic candidate set consisting of the V4 point plus the MEC center and rings at 500m and 950m with a 30-degree angular step. It first maximizes predicted `P(MEC_after <= 20m)` and uses expected incremental completion time only as the tie-breaker. This is a parameter-free one-shot-clearance ablation.

### V5-final: conservative combination

V5-final uses the V5-B dedicated candidate. It waits for a future SEARCH point only when that point has both no lower predicted clearance probability and no higher expected incremental completion time than the dedicated candidate.

### Prediction model

- Fixed sampling seed: `20260911`.
- Feasible-region samples per state: 12, sampled uniformly from the current convex polygon.
- Hypothetical bearing errors: `-1, 0, +1` degrees, followed by two-decimal quantization.
- Each hypothetical bearing updates only the policy-visible feasible polygon and MEC.
- Estimated cost uses physical units: movement divided by 5m/s, 5s per measure, and 5s per successful clear.
- A non-clearable outcome estimates the next retry with the frozen V4-style geometry candidate. No lambda, alpha, 25m threshold, or ground truth is used.

## Validation

- Episodes: 800 total, 200 per version.
- Cases per version: random 100, min_reff 50, collinear 50.
- Clearance: 800/800 episodes, 100%.
- Clear failures: 0.
- Policy errors: 0.
- Maximum absolute time-component identity error: `5.45e-6s`.

## Overall metrics

| Version | ClearRate | Mean time (s) | Median | P95 | Max | Move (m) | Move time | Measure | Switch | Mean avg/source | Pooled avg/source | Clear fail |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| V4 | 100% | 3579.99 | 3605.04 | 4372.36 | 4886.33 | 13979.83 | 2795.97 | 121.04 | 115.13 | 285.01 | 281.00 | 0 |
| V5-A | 100% | 3563.42 | 3588.30 | 4321.58 | 5188.45 | 13892.88 | 2778.58 | 121.20 | 115.17 | 284.11 | 279.70 | 0 |
| V5-B | 100% | 3584.05 | 3611.89 | 4392.78 | 4844.31 | 14065.08 | 2813.02 | 118.70 | 113.81 | 285.21 | 281.32 | 0 |
| V5-final | 100% | 3598.15 | 3645.96 | 4463.03 | 4816.94 | 14135.05 | 2827.01 | 118.70 | 113.92 | 286.31 | 282.43 | 0 |

Mean service-time components were 605.20/115.13/63.70s for V4 measure/switch/clear. V5-B reduced measure and switch time by about 13.0s combined, but added 17.1s of movement time, leaving total time slightly worse.

## Results by suite

| Suite | Version | Mean time (s) | P95 | Max | Move (m) | First supplement clearable |
|---|---|---:|---:|---:|---:|---:|
| random | V4 | 3793.41 | 4380.83 | 4886.33 | 15000.00 | 31.48% |
| random | V5-A | 3783.15 | 4276.94 | 4799.64 | 14961.04 | 24.02% |
| random | V5-B | 3759.72 | 4434.18 | 4844.31 | 14891.66 | 39.48% |
| random | V5-final | 3780.77 | 4498.11 | 4697.00 | 14995.90 | 38.46% |
| min_reff | V4 | 3798.02 | 4380.28 | 4850.69 | 14814.70 | 52.90% |
| min_reff | V5-A | 3814.44 | 4404.56 | 5188.45 | 14887.21 | 43.49% |
| min_reff | V5-B | 3885.85 | 4470.49 | 4736.74 | 15322.27 | 59.65% |
| min_reff | V5-final | 3885.68 | 4493.84 | 4816.94 | 15318.08 | 60.91% |
| collinear | V4 | 2935.12 | 3389.47 | 3802.53 | 11104.61 | 39.15% |
| collinear | V5-A | 2872.92 | 3216.35 | 3251.33 | 10762.22 | 27.99% |
| collinear | V5-B | 2930.88 | 3434.75 | 3569.74 | 11154.72 | 42.92% |
| collinear | V5-final | 2945.40 | 3514.26 | 3673.48 | 11230.32 | 40.41% |

The distribution shift is not uniform. V5-B helps random cases on mean and `min_reff` on first-pass geometry, but its farther candidates increase `min_reff` movement enough to lose 87.84s on average.

## Same-seed paired comparison

`delta = T(V5) - T(V4)`; negative is better for V5.

| Target | Suite | Win rate | Mean delta (s) | Median | P95 delta | Max delta | Mean supplement delta | Cases worse by >300s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| V5-A | random | 51% | -10.26 | -3.61 | 420.11 | 511.38 | +0.22 | 12 |
| V5-A | min_reff | 46% | +16.42 | 30.35 | 353.03 | 523.52 | +1.10 | 4 |
| V5-A | collinear | 62% | -62.20 | -44.25 | 284.36 | 325.74 | +1.28 | 2 |
| V5-A | overall | 52.5% | -16.57 | -13.38 | 357.60 | 523.52 | +0.705 | 18 |
| V5-B | random | 51% | -33.69 | -3.53 | 399.05 | 1033.38 | -1.77 | 12 |
| V5-B | min_reff | 38% | +87.84 | 115.51 | 370.28 | 448.49 | -0.90 | 11 |
| V5-B | collinear | 56% | -4.24 | -15.25 | 366.09 | 648.94 | -0.58 | 7 |
| V5-B | overall | 49% | +4.06 | 4.17 | 378.10 | 1033.38 | -1.255 | 30 |
| V5-final | random | 49% | -12.64 | 2.67 | 350.78 | 511.86 | -1.68 | 8 |
| V5-final | min_reff | 30% | +87.66 | 98.80 | 447.09 | 747.94 | -1.08 | 6 |
| V5-final | collinear | 44% | +10.28 | 12.72 | 401.01 | 667.55 | -0.24 | 5 |
| V5-final | overall | 43% | +18.16 | 39.35 | 422.58 | 747.94 | -1.17 | 19 |

## First-supplement MEC distribution

Denominator: sources that received at least one FOUND-after supplement. `<=20/near` is the first-supplement-clearable rate.

| Version | <=20/near | 20-25m | 25-30m | 30-50m | >50m |
|---|---:|---:|---:|---:|---:|
| V4 | 38.75% (987) | 17.12% (436) | 11.27% (287) | 23.24% (592) | 9.62% (245) |
| V5-A | 29.88% (761) | 14.25% (363) | 11.54% (294) | 25.36% (646) | 18.96% (483) |
| V5-B | 45.39% (1156) | 18.45% (470) | 10.84% (276) | 17.20% (438) | 8.13% (207) |
| V5-final | 44.56% (1135) | 18.14% (462) | 10.33% (263) | 17.39% (443) | 9.58% (244) |

V5-B genuinely improves the immediate threshold-crossing probability by 6.64 percentage points and reduces the `>50m` tail. V5-A does the opposite: zero-movement opportunities are often geometrically weaker, so waiting trades route attribution for more residual uncertainty.

## Supplement and movement diagnostics

| Version | Supplements/source | Off-search supplements | Off-search supplement move/source (m) | FOUND-after move/source (m) | 20-30m chasing | Realized wait-save proxy |
|---|---:|---:|---:|---:|---:|---:|
| V4 | 1.680 | 3638 | 489.44 | 788.65 | 675 | 0 |
| V5-A | 1.735 | 1825 | 247.13 | 601.77 | 449 | 834 |
| V5-B | 1.582 | 2991 | 522.90 | 780.35 | 623 | 0 |
| V5-final | 1.588 | 2544 | 454.69 | 733.34 | 496 | 402 |

`FOUND-after move` uses endpoint attribution: off-search supplement arrival segments plus the final-clear arrival segment. This is diagnostic, not a causal decomposition of the shared route.

V5-A cuts attributed off-search supplement movement sharply, but total route movement falls by only 86.95m per episode. Waiting changes which tasks coexist and therefore changes the rolling route order; much of the apparently saved source-attributed movement reappears elsewhere in the shared route. V5-B performs fewer supplements but chooses farther one-shot candidates, increasing off-search supplement movement per source by 6.8%.

## Policy runtime

| Version | Mean wall time/episode (s) | P95 (s) |
|---|---:|---:|
| V4 | 0.205 | 0.273 |
| V5-A | 0.334 | 0.426 |
| V5-B | 0.769 | 1.046 |
| V5-final | 0.861 | 1.172 |

Prediction remains computationally practical offline, but V5-final is about 4.2x the V4 policy CPU cost. Official-machine timing was not tested in this study.

## Typical cases

### Success: V5-final, random seed 2

Time fell from 4423.94s to 3775.17s (`-648.76s`). Movement fell by 2783.82m, supplements by 6, off-search supplements from 29 to 14, and FOUND-after attributed movement by 6008.44m. Here both the one-shot choice and conservative SEARCH waiting align with the global route.

### Success: V5-A, collinear seed 10034

Time fell by 554.15s and movement by 2630.74m. Even with two additional supplements, reusing mandatory SEARCH locations removed enough dedicated travel to win strongly.

### Failure: V5-B, random seed 83

Time rose from 3400.28s to 4433.65s (`+1033.38s`). V5-B used two fewer supplements but moved 4741.89m farther; FOUND-after attributed movement rose 3956.20m. Several channels' first post-measure MEC moved into `>50m`, showing sampling/model mismatch, while far one-shot candidates distorted the shared online route.

### Failure: V5-final, min_reff seed 10048

Time rose by 747.94s and movement by 3529.72m with no supplement-count reduction. The wait rule reduced some off-search tasks, but the surviving dedicated candidates and changed task coexistence produced a substantially worse route.

## Final assessment

V5 partially diagnoses and reshapes low-value supplements, but it does not solve the system-level problem:

- V5-A reduces dedicated supplement attribution and 20-30m chasing, but lowers first-supplement clearance and creates a worse maximum.
- V5-B improves first-supplement clearance and reduces supplement count, but farther candidates erase the service-time gain and create a severe paired outlier.
- V5-final improves several local diagnostics yet is slower on mean, median, and P95, with only a 43% paired win rate.

Therefore V5 is not promoted. Keep V4/n=8 as the frozen official-practice candidate. The V5 variants are useful offline ablations, but they are not worth taking to Windows official rehearsal as replacement policies in their current form. Any future V5 revision should evaluate candidate generation jointly with its marginal effect on the current global route, while preserving the V4 routing implementation as the baseline comparator.
