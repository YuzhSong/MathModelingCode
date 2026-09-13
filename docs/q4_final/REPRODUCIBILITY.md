# Q4 Reproducibility

## Environment

- Repository root: `/Users/rainy/大学/个人/竞赛/数学建模9/Code`.
- Automated evaluation uses local `offline_sim/`.
- Official simulator access must be started manually by the user in the simulator UI.
- No formal test is run by documentation generation.

## Final benchmark artifacts

Use the recorded outputs under `results/q4/final_candidate_validation/`. The final validation includes:

- smoke 9;
- historical 200;
- held-out 600;
- stress 24;
- combined summaries and source-tail analysis.

The current final code paths are `q4/w5_policy.py` and `q4/w5_geometry.py`.

## Clean official runner

Practice:

```bash
python3 run_q4_final.py --robot-id YOUR_TEAM_ID --base-url http://127.0.0.1:2026 --test-kind practice
```

Formal:

```bash
python3 run_q4_final.py --robot-id YOUR_TEAM_ID --base-url http://127.0.0.1:2026 --test-kind formal --case-id CASE_CODE
```

The source code must not hard-code the team number. Pass it through `--robot-id`, `ROBOT_ID`, or the interactive prompt. `CASE_CODE` is shown by the simulator UI and may not be returned by the API.

The official table fields are recorded as:

- `cleared_count`: count of accepted `/clear` responses with `clear_result="success"`;
- `avg_time_per_cleared_s`: `total_virtual_time_s / cleared_count`;
- `program_real_time_s`: `(exit.real_timestamp_ms - enter.real_timestamp_ms) / 1000`.

## Metric definitions

For paper reporting, distinguish:

- Macro T/N: mean of per-case `T_i/N_i`;
- Pooled T/N: `sum(T_i)/sum(N_i)`.

The Q4 final documentation recommends pooled T/N for main per-source reporting and records metric definitions in `results/q4/final_documentation/q4_metric_definitions.md`.

