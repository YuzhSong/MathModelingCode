# Q3 V4 Dynamic Routing and Oracle Benchmarks

Scope: local offline_sim/practice only. Compared V3/V4 at n=8 and n=9 with identical seeds: random 0:100, min_reff/collinear 10000:10050. V5 and Fisher/particle/RL/MILP/POMDP were not implemented. Official formal test was not touched.

## Validation

- Episodes: 800; ClearRate: 800/800 = 100%.
- clear_fail total: 0.
- Max absolute time-component delta: 7.14e-06s.
- Conditional Route Oracle: approximate for all cases.
- Full-information Oracle Proxy: exact route for 380 case rows, approximate route for 420 case rows.

## Main Summary

| version | n | ClearRate | mean T | mean avg/src | pooled avg/src | P95 | max | move m | move time | measure time | switch time | clear time | measure | switch | clear fail |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v3 | 8 | 100.0% | 5330.12 | 424.05 | 418.38 | 7219.52 | 8006.31 | 22689.14 | 4537.83 | 613.85 | 114.75 | 63.70 | 122.77 | 114.75 | 0.00 |
| v3 | 9 | 100.0% | 5293.91 | 420.89 | 415.53 | 7303.74 | 8360.55 | 22217.04 | 4443.41 | 663.00 | 123.81 | 63.70 | 132.60 | 123.81 | 0.00 |
| v4 | 8 | 100.0% | 3579.99 | 285.01 | 281.00 | 4372.36 | 4886.33 | 13979.83 | 2795.97 | 605.20 | 115.12 | 63.70 | 121.04 | 115.12 | 0.00 |
| v4 | 9 | 100.0% | 3642.09 | 290.07 | 285.88 | 4556.78 | 4819.12 | 14028.94 | 2805.79 | 649.20 | 123.40 | 63.70 | 129.84 | 123.40 | 0.00 |

## Grouped Results


### random

| version | n | ClearRate | mean T | P95 | max | move m | move time | measure time | switch time | measure | switch | clear fail |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v3 | 8 | 100.0% | 5923.62 | 7290.11 | 7807.04 | 25609.14 | 5121.83 | 622.00 | 116.09 | 124.40 | 116.09 | 0.00 |
| v3 | 9 | 100.0% | 5868.27 | 7511.87 | 8360.55 | 25039.74 | 5007.95 | 671.40 | 125.22 | 134.28 | 125.22 | 0.00 |
| v4 | 8 | 100.0% | 3793.41 | 4380.83 | 4886.33 | 15000.00 | 3000.00 | 613.10 | 116.61 | 122.62 | 116.61 | 0.00 |
| v4 | 9 | 100.0% | 3864.88 | 4621.49 | 4728.99 | 15105.76 | 3021.15 | 655.30 | 124.73 | 131.06 | 124.73 | 0.00 |

### min_reff

| version | n | ClearRate | mean T | P95 | max | move m | move time | measure time | switch time | measure | switch | clear fail |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v3 | 8 | 100.0% | 5899.85 | 7142.01 | 8006.31 | 25266.55 | 5053.31 | 659.00 | 123.84 | 131.80 | 123.84 | 0.00 |
| v3 | 9 | 100.0% | 5885.80 | 7282.22 | 7893.77 | 24874.30 | 4974.86 | 713.50 | 133.74 | 142.70 | 133.74 | 0.00 |
| v4 | 8 | 100.0% | 3798.02 | 4380.28 | 4850.69 | 14814.70 | 2962.94 | 648.00 | 123.38 | 129.60 | 123.38 | 0.00 |
| v4 | 9 | 100.0% | 3942.17 | 4519.77 | 4819.12 | 15191.76 | 3038.35 | 705.80 | 134.32 | 141.16 | 134.32 | 0.00 |

### collinear

| version | n | ClearRate | mean T | P95 | max | move m | move time | measure time | switch time | measure | switch | clear fail |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v3 | 8 | 100.0% | 3573.40 | 4611.15 | 4729.13 | 14271.72 | 2854.34 | 552.40 | 102.96 | 110.48 | 102.96 | 0.00 |
| v3 | 9 | 100.0% | 3553.31 | 4487.91 | 5538.05 | 13914.37 | 2782.87 | 595.70 | 111.04 | 119.14 | 111.04 | 0.00 |
| v4 | 8 | 100.0% | 2935.12 | 3389.47 | 3802.53 | 11104.61 | 2220.92 | 546.60 | 103.90 | 109.32 | 103.90 | 0.00 |
| v4 | 9 | 100.0% | 2896.41 | 3279.21 | 3443.89 | 10712.46 | 2142.49 | 580.40 | 109.82 | 116.08 | 109.82 | 0.00 |

## Paired V4 - V3

delta = T(V4) - T(V3); negative means V4 is faster.

| n | suite | pairs | V4 win rate | mean delta | median delta | P95 delta | max delta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | random | 100 | 100.0% | -2130.21 | -2100.69 | -1082.87 | -612.15 |
| 8 | min_reff | 50 | 100.0% | -2101.83 | -2085.79 | -1151.77 | -932.72 |
| 8 | collinear | 50 | 92.0% | -638.28 | -650.37 | 108.76 | 193.85 |
| 8 | overall | 200 | 98.0% | -1750.13 | -1834.60 | -232.52 | 193.85 |
| 9 | random | 100 | 100.0% | -2003.39 | -1964.53 | -952.86 | -496.04 |
| 9 | min_reff | 50 | 100.0% | -1943.63 | -1876.13 | -760.64 | -621.07 |
| 9 | collinear | 50 | 92.0% | -656.90 | -552.22 | 30.75 | 248.27 |
| 9 | overall | 200 | 98.0% | -1651.83 | -1722.41 | -268.36 | 248.27 |

## Paired n=9 - n=8

delta = T(n=9) - T(n=8); negative means n=9 is faster.

| version | suite | pairs | n9 win rate | mean delta | median delta | P95 delta | max delta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v3 | random | 100 | 53.0% | -55.35 | -24.29 | 1092.78 | 1900.83 |
| v3 | min_reff | 50 | 58.0% | -14.05 | -118.23 | 867.74 | 1275.52 |
| v3 | collinear | 50 | 50.0% | -20.09 | -15.70 | 1070.85 | 1859.67 |
| v3 | overall | 200 | 53.5% | -36.21 | -37.06 | 1078.02 | 1900.83 |
| v4 | random | 100 | 38.0% | 71.47 | 65.59 | 481.21 | 670.30 |
| v4 | min_reff | 50 | 30.0% | 144.15 | 122.97 | 503.59 | 929.47 |
| v4 | collinear | 50 | 52.0% | -38.71 | -4.46 | 246.57 | 318.10 |
| v4 | overall | 200 | 39.5% | 62.10 | 62.08 | 467.84 | 929.47 |

## Oracle Gap Summary

Conditional Route Oracle is approximate and uses each policy own generated action/task endpoints. Full-information Oracle Proxy may read ground truth and visits source centers; it is not a TSP-with-neighborhood lower bound. Do not interpret these as strict inequalities.

| version | n | suite | T policy | T conditional | routing gap | T full proxy | full proxy gap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v3 | 8 | overall | 5330.12 | 3310.50 | 59.1% | 1582.23 | 243.3% |
| v3 | 8 | random | 5923.62 | 3554.53 | 66.3% | 1803.61 | 228.7% |
| v3 | 8 | min_reff | 5899.85 | 3545.94 | 66.2% | 1800.30 | 227.7% |
| v3 | 8 | collinear | 3573.40 | 2586.97 | 37.5% | 921.40 | 288.2% |
| v3 | 9 | overall | 5293.91 | 3409.51 | 53.3% | 1582.23 | 240.8% |
| v3 | 9 | random | 5868.27 | 3669.65 | 59.3% | 1803.61 | 225.9% |
| v3 | 9 | min_reff | 5885.80 | 3676.19 | 59.5% | 1800.30 | 226.1% |
| v3 | 9 | collinear | 3553.31 | 2622.55 | 35.0% | 921.40 | 285.3% |
| v4 | 8 | overall | 3579.99 | 3281.50 | 9.3% | 1582.23 | 138.7% |
| v4 | 8 | random | 3793.41 | 3506.60 | 8.2% | 1803.61 | 111.2% |
| v4 | 8 | min_reff | 3798.02 | 3482.21 | 9.1% | 1800.30 | 112.1% |
| v4 | 8 | collinear | 2935.12 | 2630.62 | 11.5% | 921.40 | 220.4% |
| v4 | 9 | overall | 3642.09 | 3370.11 | 8.1% | 1582.23 | 141.8% |
| v4 | 9 | random | 3864.88 | 3593.56 | 7.5% | 1803.61 | 115.3% |
| v4 | 9 | min_reff | 3942.17 | 3641.99 | 8.2% | 1800.30 | 119.9% |
| v4 | 9 | collinear | 2896.41 | 2651.34 | 9.2% | 921.40 | 216.6% |

## Conclusions

- V4 keeps 100% clear rate and is stably faster than V3 in every suite. Overall mean improves by -1750.13s at n=8 and -1651.83s at n=9.
- The improvement is overwhelmingly movement: V3/n=9 move time 4443.41s -> V4/n=9 2805.79s; measure/switch changed much less.
- Under V4, n=8 has better overall mean (3579.99s vs 3642.09s) and better P95 (4372.36s vs 4556.78s), while n=9 has a slightly better max (4819.12s vs 4886.33s). In paired overall n9-n8 for V4, n=9 wins 39.5% and mean delta is +62.10s, so n=8 is currently better on average and P95; max is the only aggregate tail metric favoring n=9.
- V4 conditional routing gap is small relative to V3: overall V4/n=8 9.3%, V4/n=9 8.1%. This says remaining pure route-ordering room is modest under the current approximate oracle.
- Full-information proxy gap remains large: V4/n=8 138.7%, V4/n=9 141.8%. Most remaining loss is therefore information/task generation/search-measure overhead, not just visit ordering.
- Current bottleneck after V4 is still movement as the largest component, but its share is much lower than V3; the next meaningful gains likely require reducing generated tasks/search-measure burden, which belongs to the deferred V5 question.
- Based on offline evidence alone, V4 is strong enough to consider a Windows official practice rehearsal next, but not formal test. Keep formal testing locked until explicit user command.

## Generated Files

- v4_summary_compact.csv
- paired_v4_minus_v3.csv
- paired_n9_minus_n8.csv
- oracle_method_counts.csv
- details.csv / summary.csv / paired_comparison.csv from the evaluator
