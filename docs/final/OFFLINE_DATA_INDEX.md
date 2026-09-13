# Offline Data Index

本表是当前 Mac 仓库的离线代码、结果和支撑材料索引。`FINAL` 表示最终方案；`paper` 表示论文正文或主表可直接使用；`ablation/negative` 表示应保留为模型选择证据。

| Path | Problem | Experiment / role | Final | Paper | Ablation | Negative | Development only | Recommended retention |
|---|---|---|---|---|---|---|---|---|
| `q3/v6_policy.py` | Q3 | RARC policy | yes | main | no | no | no | keep as final source |
| `run_q3_final.py` | Q3 | clean final runner | yes | reproducibility | no | no | no | keep |
| `frozen/v6_n8_20260912/` | Q3 | frozen snapshot and hashes | yes | reproducibility | no | no | no | immutable |
| `results/q3/offline_eval_v6_n8/` | Q3 | final V6 200-case benchmark | yes | main | no | no | no | keep unchanged |
| `q3/offline_policy.py`, `q3/v5_policy.py`, `q3/routing.py` | Q3 | shared/core evolution | support | methods | no | no | no | keep |
| `results/q3/offline_eval_v4_n8_n9/`, `offline_eval_v5_n8/` | Q3 | staged/rolling evolution | no | comparison | no | no | no | keep unchanged |
| `results/q3/offline_eval_ring_count_200/` | Q3 | n=6..12 selection | no | sensitivity | yes | no | no | keep unchanged |
| `q3/stage2_policy.py`, `results/q3/offline_eval_stage2*` | Q3 | stage-2 mechanisms | no | ablation | yes | often | no | keep unchanged |
| `q3/v6_l2_policy.py`, `results/q3/offline_eval_v6_l2_200/` | Q3 | deep lookahead | no | negative ablation | yes | yes | no | keep unchanged |
| `q3/ring_only_policy.py`, `results/offline_eval_ring_only_center_ablation_200/` | Q3 | ring-only center ablation | no | optional ablation | yes | yes | no | keep unchanged |
| `q3/v6_nosignal_policy.py`, `results/offline_eval_v6_nosignal_200/` | Q3 | historical no_signal | no | supplement | yes | yes | no | keep unchanged |
| `q3/v6_backbone*.py`, `results/offline_eval_v6_backbone_bundle_200/` | Q3 | SEARCH-backbone bundle | no | negative ablation | yes | yes | no | keep unchanged |
| `q4/w6_policy.py` | Q4 | W6-25PFR final policy | yes | main | no | no | no | keep as final source |
| `q4/final_policy.py` | Q4 | thin final policy wrapper | yes | reproducibility | no | no | no | keep |
| `run_q4_final.py` | Q4 | clean final runner | yes | reproducibility | no | no | no | keep |
| `results/q4/w6/feasible_region_full/` | Q4 | final W6 200-case offline validation | yes | main | no | no | no | keep unchanged |
| `q4/w5_geometry.py`, `w2_policy.py`, `w3_policy.py`, `w4a_policy.py`, `routing.py` | Q4 | final supporting mechanisms | support | methods | no | no | no | keep |
| `results/q4/w0_baseline/` through `w5/` | Q4 | core evolution | no | comparison | no | no | no | keep unchanged |
| `results/q4/w6a_decomposition/` | Q4 | acceleration/MEC ablation | no | ablation | yes | yes | no | keep unchanged |
| `results/q4/w7_macro_regret/` | Q4 | failed macro-regret calibration | no | negative | yes | yes | no | keep unchanged |
| `results/q4/w8_stale_repair/`, `results/q4/final_candidate_validation/` | Q4 | stale repair and candidate comparison | no | ablation | yes | yes | no | keep unchanged |
| `offline_sim/` | Q3/Q4 | local simulator and harness | no | reproducibility | no | no | no | keep; do not modify physics |
| `scripts/` | Q3/Q4 | benchmark and analysis scripts | no | reproducibility | no | no | some | keep; do not run in archive round |
| `docs/q3_final/`, `docs/q4_final/` | Q3/Q4 | prior detailed archives | no | support | no | no | no | keep; this directory is combined entry |

存在大量未跟踪但有科研价值的历史脚本和结果；本轮不移动、不删除、不合并。
