# Q4

Q4 code is isolated under this package. The final frozen policy is
`W6-25PFR`, implemented by `w6_policy.py` and exposed through
`final_policy.py` / `run_q4_final.py`.

Paper-facing name: **25-Point Symmetric Search with Persistent Feasible-Region
Clearing** (25点对称搜索与持续可行域清除策略, 25P-PFRC). W0-W5 are retained
as historical method-evolution evidence; W6-A, W7 and W8 remain historical
robustness/negative-result assets.

Final geometry: center 1 + first ring 6 + second ring 12 + cap points 6 = 25;
`a=970 m`, `p=140 m`, `rho=sqrt(3)*a+p=1820.089... m`. The theoretical
conditional bound is `a <= 997.367811 m`; `a=970, p=140` is a feasible offline
selection, not a claim of arbitrary-geometry global optimality.

Local evaluation:

```text
python q4/run_w6_benchmark.py --help
python3 -m py_compile q4/final_policy.py q4/w6_policy.py q4/w6_feasible_region.py
```

Clean official practice/formal entry, after manually confirming the simulator
is in the intended Q4 module:

```text
python run_q4_final.py --robot-id YOUR_ID --base-url http://127.0.0.1:2026 --test-kind practice
python run_q4_final.py --robot-id YOUR_ID --base-url http://127.0.0.1:2026 --test-kind formal --case-id CASE_CODE
```

The legacy W5 development adapter is still available:

```text
python main.py --problem 4 --mode official --strategy w5 --robot-id YOUR_ID --base-url http://127.0.0.1:2026
```

Q4 policy code must use only runner/API-visible responses. Ground truth is
reserved for post-episode benchmark scripts. The final offline validation is
`results/q4/w6/feasible_region_full/`; its historical source CSV is retained
without rewriting.

Final archive: `docs/q4_final/README.md`.
