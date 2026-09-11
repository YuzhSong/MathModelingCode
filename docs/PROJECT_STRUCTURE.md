# Project Structure

- `main.py`: unified command-line entry point.
- `q3/`: API client, geometry, planner, policies, routing, logging, and safety gate.
- `scripts/run_official_practice.py`: official practice runner, defaulting to the V4 dynamic routing policy; practice confirmation is mandatory.
- `scripts/run_api_smoke.py`: minimal practice API smoke test; it calls `/enter` only after confirmation.
- `scripts/run_offline_eval.py`: fixed-seed local evaluation.
- `offline_sim/`: local simulator and harness. It is the only environment used for automated evaluation.
- `results/`: retained experiment artifacts, including reports and CSV/JSON summaries.
- `docs/`: version governance and operating notes.

No policy module imports the simulator case or ground truth. Oracle code is invoked by the offline harness after an episode and is not exposed through the policy runner interface.
