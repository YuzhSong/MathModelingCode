# Project Structure

- `main.py`: unified command-line entry point.
- `q3/`: API client, geometry, planner, policies, routing, logging, and safety gate.
- `q3/run_logger.py`: passive run logger for official runs; writes `logs/q3/<run_id>/{events.jsonl,trajectory.csv,summary.json}` and appends `logs/q3/runs_summary.csv`.
- `scripts/run_official_practice.py`: official practice runner, defaulting to V4 and explicitly supporting V6; practice confirmation is mandatory.
- `scripts/run_api_smoke.py`: minimal practice API smoke test; it calls `/enter` only after confirmation.
- `scripts/run_offline_eval.py`: fixed-seed local evaluation.
- `offline_sim/`: local simulator and harness. It is the only environment used for automated evaluation.
- `results/`: retained experiment artifacts, including reports and CSV/JSON summaries.
- `docs/`: version governance and operating notes.
- `frozen/`: immutable source/result snapshots. The V4 and V6 snapshots are separate and must not be edited in place.
- `external/`: read-only copies of the Way1/Way3/evaluate reference repositories used for offline comparison.

No policy module imports the simulator case or ground truth. Oracle code is invoked by the offline harness after an episode and is not exposed through the policy runner interface.
