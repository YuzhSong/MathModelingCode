# Q4

Q4 code is isolated under this package. The current strategy generation is W5,
implemented by `w5_policy.py`; W0-W4 are retained as experimental parents and
diagnostic baselines.

Local evaluation:

```text
python q4/run_w5_benchmark.py --help
python offline_sim/test_q4_w5.py
```

Official practice entry, after manually confirming the simulator is in Q4
practice/simulation mode:

```text
python main.py --problem 4 --mode official --strategy w5 --robot-id YOUR_ID --base-url http://127.0.0.1:2026
```

Formal testing is out of scope. Q4 policy code must use only the runner/API-visible responses; ground truth is reserved
for post-episode benchmark scripts.
