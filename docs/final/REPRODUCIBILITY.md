# Reproducibility

## Environment and boundary

- Repository root: `/Users/rainy/大学/个人/竞赛/数学建模9/Code`
- Python: standard-library project; see `requirements.txt`.
- Offline simulator: `offline_sim/`; policies receive API-visible responses only.
- This archive did not call an official simulator and did not run a new benchmark.
- Do not treat the following commands as part of this archive round; they are the recorded historical benchmark recipes.

## Final offline recipes

Q3 final evaluation record:

```text
python scripts/run_v6_eval.py --versions v4,v5b,v6 --random-seeds 0:100 --stress-seeds 10000:10050 --out-dir results/q3/offline_eval_v6_n8
```

Q3 ring-count selection record:

```text
python scripts/run_ring_count_eval.py --help
```

Q4 final evaluation record:

```text
python q4/run_w6_benchmark.py --help
```

The authoritative frozen outputs are the existing directories indexed in [Q3_FINAL_INDEX.md](Q3_FINAL_INDEX.md) and [Q4_FINAL_INDEX.md](Q4_FINAL_INDEX.md); do not overwrite them during a rerun.

## Final runtime entries

- Q3: `python run_q3_final.py ...` fixed to RARC/frozen V6/n=8.
- Q4: `python run_q4_final.py ...` fixed to W6-25PFR.

Official practice/formal execution is outside this offline archive and must be handled separately on the designated test machine.

## Frozen and metric conventions

- Q3 snapshot: `frozen/v6_n8_20260912/SHA256SUMS`.
- Historical Q3 comparison snapshot: `frozen/v4_n8_20260911/SHA256SUMS`.
- Q3 suites: random 0--99, min_reff 10000--10049, collinear 10000--10049.
- Q4 final suite: random 0--99, min_reff 10000--10049, collinear 10000--10049.
- `Mean(T/N)` = first compute each case's `T_i/N_i`, then average across cases.
- ClearRate, clear failures and unresolved counts must remain separate fields.
