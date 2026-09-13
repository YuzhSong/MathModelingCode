# Final Candidate: frozen V6/n=8 == RARC

## Identity

- Paper name: Route-Aware Rolling Coordination (RARC)，中文“路径感知滚动联合调度策略”。
- Internal implementation: `q3/v6_policy.py:policy_v6`，不要把代码中的 V6 批量改名。
- Snapshot: `frozen/v6_n8_20260912/`。
- Frozen source hash record: `frozen/v6_n8_20260912/SHA256SUMS`。
- Current six core hashes match the snapshot: `q3/v6_policy.py`, `q3/v5_prediction.py`, `q3/geometry.py`, `q3/planner.py`, `q3/offline_policy.py`, `q3/routing.py`。

## Method

1. Deterministic coverage search with `n=8` outer search points.
2. Bounded-bearing feasible region from API-visible directional measurements.
3. Minimum enclosing circle (MEC) localization; clear only when `MEC radius <= 20 m`.
4. Rolling SEARCH / MEASURE / CLEAR joint task construction and frozen open-route heuristic.
5. Route-aware supplement generation using the frozen V4 route marginal plus visible-geometry prediction.
6. Stop mandatory SEARCH after 16 discovered sources; unknown channels then become absent under the existing policy state machine.

The n=8 choice comes from the recorded V6 ring-count benchmark, not from a new tuning run in this archive task.

## Final offline metrics

Source: `results/q3/offline_eval_v6_n8/summary.csv` and `report.md`.

- 200 cases, local `offline_sim/practice` only.
- ClearRate 100%; clear fail 0.
- Mean total 3496.69 s.
- Mean(T/N) 278.69 s/source; calculate per case first, then average.
- P95 total 4244.83 s; max total 4817.50 s.
- Mean movement 13554.13 m.

No saved official V6 raw practice result was found in the repository. The official adapter and instructions remain available under `main.py`, `scripts/run_official_practice.py`, and the frozen snapshot, but no official metric is claimed here.

## Why final

V6 improved the rolling V4/V5 route-aware task organization while preserving deterministic clearing. Later lookahead, ring-only, no_signal, and SEARCH-backbone bundle explorations were retained as model-selection evidence but did not produce a replacement candidate.
