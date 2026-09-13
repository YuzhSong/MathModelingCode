# Q4 Inventory

This inventory is an index layer only. It does not move, delete, or rename existing Q4 code or results.

| path | role | status | used_by | final? | paper relevant? | safe to archive? |
|---|---|---|---|---|---|---|
| `q4/w5_policy.py` | final policy | FINAL_CORE | official/final runner | yes | main | no |
| `q4/w5_geometry.py` | final 25-point geometry | FINAL_CORE | W5 policy and paper geometry | yes | main | no |
| `q4/w2_policy.py` | persistent lifecycle | FINAL_SUPPORT | W5 ancestry | mechanism | main | no |
| `q4/w3_policy.py` | adaptive reacquisition | FINAL_SUPPORT | W5 ancestry | mechanism | main | no |
| `q4/w4a_policy.py` | unified task pool | FINAL_SUPPORT | W5 ancestry | mechanism | main | no |
| `q4/routing.py` | Q4 routing | FINAL_SUPPORT | W4-A/W5 | yes | methods | no |
| `run_q4_final.py` | clean official runner | OFFICIAL_PRACTICE | practice/formal execution | yes | procedure | no |
| `main.py` | unified dev official adapter | OFFICIAL_PRACTICE | Q3/Q4 adapters | support | procedure | no |
| `results/q4/final_candidate_validation/` | final validation | FINAL_EVIDENCE | paper metrics | yes | main | no |
| `results/q4/final_documentation/` | current Q4 paper data package | FINAL_EVIDENCE | paper writing | yes | main | no |
| `results/q4/w0_baseline/` | direct-transfer baseline | NEGATIVE_RESULT | model motivation | no | ablation | yes |
| `results/q4/w1*/` | geometry development | CORE_EXPERIMENT | method evolution | partial | supplement | yes |
| `results/q4/w2/` | lifecycle evidence | CORE_EXPERIMENT | method mechanism | partial | main/ablation | yes |
| `results/q4/w3/` | adaptive reacquisition evidence | CORE_EXPERIMENT | method mechanism | partial | main/ablation | yes |
| `results/q4/w4a/` | rolling task pool evidence | CORE_EXPERIMENT | method mechanism | partial | main/ablation | yes |
| `results/q4/w4b/` | continuity negative result | NEGATIVE_RESULT | model selection | no | supplement | yes |
| `results/q4/w6*/` | tail robustness exploration | NEGATIVE_RESULT | model selection | no | supplement | yes |
| `results/q4/w7_macro_regret/` | shadow scheduling diagnostic | NEGATIVE_RESULT | model selection | no | archive/supplement | yes |
| `results/q4/w8_stale_repair/` | robustness candidate | NEGATIVE_RESULT | final selection comparison | no | supplement | yes |
| `offline_sim/` | local simulator | FINAL_SUPPORT | offline evaluation | support | methods | no |

Known local untracked files include W7/W8 and additional Q4 analysis scripts/results. They are retained and indexed as experimental assets; do not delete them during formal preparation.

