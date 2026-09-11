# Q3 Strategy Versions

All times below are Beijing time (UTC+8). Dates describe the current repository governance point; Git history remains the authoritative edit history.

| Version | Status | Parent Version | Created At | Last Updated | Main Changes | Entry Point | Offline Result | Recommended | Notes |
|---|---|---|---|---|---|---|---|---|---|
| V0 | Frozen baseline | - | 2026-09-11 00:00 | 2026-09-11 00:00 | Deterministic coverage, localization, per-channel resolution | `q3.offline_policy.policy_v0` | 100% clear in recorded suites | No | Offline only |
| V1 | Frozen experiment | V0 | 2026-09-11 00:00 | 2026-09-11 00:00 | Reuses later search points for found-channel measurements | `q3.offline_policy.policy_v1` | Recorded in clean reports | No | Offline only |
| V2 | Frozen experiment | V1 | 2026-09-11 00:00 | 2026-09-11 00:00 | Joint task route planning | `q3.offline_policy.policy_v2` | Recorded in clean reports | No | Offline only |
| V3 | Frozen experiment | V2 | 2026-09-11 00:00 | 2026-09-11 00:00 | Dynamic clear insertion | `q3.offline_policy.policy_v3` | Recorded in clean reports | No | Offline only |
| V4 | Current offline candidate | V3 | 2026-09-11 00:00 | 2026-09-11 00:00 | Rolling dynamic routing and post-episode oracle benchmarks | `q3.offline_policy.policy_v4` | Best recorded offline mean; see V4 report | Yes for offline | Not yet wired to official planner |

`run_official_practice.py` runs the existing HTTP planner and requires the explicit practice confirmation gate. It is not evidence of a completed official run.
