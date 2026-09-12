"""Problem 4 offline experiments.

Q4 code is kept separate from the frozen Q3 policy code.  The W0 baseline
imports frozen-equivalent Q3 V6/n=8 behavior and only adapts the benchmark
environment to problem=4.
"""
"""Problem 4 directional-jammer strategies and local evaluation tools.

Q4 W1-W5 policies, geometry, routing, diagnostics, and benchmarks live here.
The shared transport boundary is intentionally kept at the API adapter; Q4
does not access simulator ground truth during policy execution.
"""
