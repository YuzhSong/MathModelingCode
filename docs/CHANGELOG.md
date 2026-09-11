# Changelog

## 2026-09-11

- Established a Git checkpoint before repository reorganization.
- Moved runnable scripts under `scripts/`.
- Added the unified `main.py` entry point and project structure documentation.
- Preserved Q3 strategy logic, simulator physics, and all recorded results.
- Wired V4 into the official practice entry: `policy_v4_official` adapts the official `SimulatorClient` to the policy runner shape. `main.py --mode official` and `scripts/run_official_practice.py` now support `--strategy v4` (default) with v3 baseline still selectable. No algorithm changes; no official rehearsal performed.
