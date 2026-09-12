# Q3 Strategy Versions

All times below are Beijing time (UTC+8). Dates describe the current repository governance point; Git history remains the authoritative edit history.

| Version | Status | Parent Version | Created At | Last Updated | Main Changes | Entry Point | Offline Result | Recommended | Notes |
|---|---|---|---|---|---|---|---|---|---|
| V0 | Frozen baseline | - | 2026-09-11 00:00 | 2026-09-11 00:00 | Deterministic coverage, localization, per-channel resolution | `q3.offline_policy.policy_v0` | 100% clear in recorded suites | No | Offline only |
| V1 | Frozen experiment | V0 | 2026-09-11 00:00 | 2026-09-11 00:00 | Reuses later search points for found-channel measurements | `q3.offline_policy.policy_v1` | Recorded in clean reports | No | Offline only |
| V2 | Frozen experiment | V1 | 2026-09-11 00:00 | 2026-09-11 00:00 | Joint task route planning | `q3.offline_policy.policy_v2` | Recorded in clean reports | No | Offline only |
| V3 | Frozen experiment | V2 | 2026-09-11 00:00 | 2026-09-11 00:00 | Dynamic clear insertion | `q3.offline_policy.policy_v3` | Recorded in clean reports | No | Offline only |
| V4 | Frozen recommended | V3 | 2026-09-11 00:00 | 2026-09-12 00:00 | Rolling dynamic routing and post-episode oracle benchmarks | `q3.offline_policy.policy_v4` (offline); `main.py --mode official --strategy v4` / `q3.offline_policy.policy_v4_official` (official, practice-gated) | 100% in recorded offline suites; user reports official rehearsal passed | Yes | Frozen snapshot: `frozen/v4_n8_20260911/` |
| V5-A | Rejected experiment | V4 | 2026-09-12 00:00 | 2026-09-12 00:00 | Waits for mandatory SEARCH points using feasible-region prediction | `q3.v5_policy.policy_v5a` | 100% clear; mean -16.57s, max worse | No | Offline only |
| V5-B | Rejected experiment | V4 | 2026-09-12 00:00 | 2026-09-12 00:00 | Maximizes predicted one-supplement clearance probability | `q3.v5_policy.policy_v5b` | 100% clear; first-pass rate improved, total mean +4.06s | No | Offline only |
| V5-final | Rejected experiment | V4 | 2026-09-12 00:00 | 2026-09-12 00:00 | Conservative combination of V5-A and V5-B | `q3.v5_policy.policy_v5_final` | 100% clear; mean/P95 worse than V4 | No | Offline only |
| V6 | Frozen offline candidate; practice pending | V4 | 2026-09-12 00:00 | 2026-09-12 00:00 | Route-aware FOUND-source supplement generation using frozen V4 route marginal cost | `q3.v6_policy.policy_v6` (offline); `main.py --mode official --strategy v6` / `q3.v6_policy.policy_v6_official` (practice-gated) | 100% clear; mean -83.30s vs V4, but 12/200 paired regressions exceed 300s | Pending | Snapshot: `frozen/v6_n8_20260912/`; official practice not yet run |

`run_official_practice.py` and `main.py --mode official` both default to V4 (the former Q3_PRACTICE_ONLY confirmation gate was removed by team decision). V6 is available only through an explicit `--strategy v6` selection. Repository code and offline results do not independently prove an official run; any practice result must be recorded separately from offline evaluation, and formal testing remains out of scope.
