# Changelog

## 2026-09-11

- Established a Git checkpoint before repository reorganization.
- Moved runnable scripts under `scripts/`.
- Added the unified `main.py` entry point and project structure documentation.
- Preserved Q3 strategy logic, simulator physics, and all recorded results.
- Wired V4 into the official practice entry: `policy_v4_official` adapts the official `SimulatorClient` to the policy runner shape. `main.py --mode official` and `scripts/run_official_practice.py` now support `--strategy v4` (default) with v3 baseline still selectable. No algorithm changes; no official rehearsal performed.

## 2026-09-12

- Froze V4/n=8 code and recorded results under `frozen/v4_n8_20260911/` with SHA-256 checksums.
- Added policy-visible FOUND-source diagnostics and policy wall-time measurement without changing simulator physics.
- Added reproducible feasible-polygon prediction and V5-A/V5-B/V5-final task-generation experiments.
- Added the fixed-seed V5 evaluation runner and source-level diagnostic exports.
- Rejected all V5 variants as replacements after 800 offline practice episodes; V4/n=8 remains recommended.
- Added V6 route-aware supplement generation without changing the frozen V4 router or official entry point.
- Evaluated V4/V5-B/V6 on 200 identical offline practice cases each. V6 retained 100% clearance and improved aggregate mean/P95/max, but was not promoted because 12 paired cases regressed by more than 300 seconds.
- Added an explicit, practice-gated official HTTP adapter for V6 and froze the portable `frozen/v6_n8_20260912/` snapshot. The default official entry remains V4; no official endpoint was called while preparing this snapshot.
