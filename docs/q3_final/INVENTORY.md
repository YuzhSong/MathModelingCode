# Q3 Repository Inventory (read-only scan)

Inventory date: 2026-09-13. No files were moved or deleted during this scan.

| path / pattern | role | status | used_by | final | paper | safe_to_archive |
|---|---|---|---|---|---|---|
| `q3/models.py`, `geometry.py`, `planner.py`, `offline_policy.py`, `routing.py` | core models, geometry, task state, route heuristic | FINAL_CORE | V0–V6 and offline policies | Yes | Yes | No |
| `q3/v6_policy.py`, `q3/v5_policy.py`, `q3/v5_prediction.py` | final V6/RARC and V5 lineage | FINAL_CORE / CORE_EXPERIMENT | final and V5 scripts | Yes / Core | Yes | No |
| `q3/api_client.py`, `q3/external_policies.py`, `q3/logger.py`, `q3/run_logger.py`, `q3/safety.py` | API adapter, logging, safety support | FINAL_SUPPORT | official adapters and runs | Supporting | Procedure | No |
| `q3/offline_policy.py:policy_v0..policy_v4` | Early baselines and V4 rolling policy | CORE_EVOLUTION | legacy/offline scripts | V4 core | Yes | No |
| `q3/v6_l2_policy.py` | deep-lookahead ablation | ABLATION | `scripts/run_v6_l2_eval.py` | No | Supplement | Yes, only as archive |
| `q3/ring_only_policy.py` | center-search ablation | NEGATIVE_RESULT | `scripts/run_ring_only_eval.py` | No | Optional | Yes, only as archive |
| `q3/v6_nosignal_policy.py`, `v6_nosignal_prediction.py` | historical no_signal ablation | NEGATIVE_RESULT | `scripts/run_v6_nosignal_eval.py` | No | Optional | Yes, only as archive |
| `q3/stage2_policy.py` | stage-2 task-organization experiment | ABLATION | stage2 scripts | No | Ablation | Yes, only as archive |
| `q3/v6_backbone.py`, `v6_backbone_policy.py` | SEARCH-backbone bundle negative experiment | NEGATIVE_RESULT | `scripts/run_v6_backbone_eval.py` | No | Supplement | Yes, only as archive |
| `frozen/v6_n8_20260912/` | immutable V6 snapshot, hashes, practice instructions | FROZEN | final audit/reproduction | Yes | Yes | No |
| `frozen/v4_n8_20260911/` | immutable V4 snapshot and historical results | FROZEN | comparison and provenance | No | Yes | No |
| `scripts/run_v6_eval.py`, `run_offline_eval.py` | final/legacy benchmark entry points | FINAL_BENCHMARK | final reproduction | Yes | Yes | No |
| `scripts/run_ring_count_eval.py` | n=6..12 sensitivity | CORE_EXPERIMENT | parameter selection | No | Yes | No |
| `scripts/run_v5_eval.py`, `run_stage2_eval.py`, `analyze_stage2.py`, `run_v6_l2_eval.py` | core evolution and ablation evaluators | CORE_EXPERIMENT / ABLATION | corresponding result families | No | Yes | No |
| `scripts/run_ring_only_eval.py`, `run_v6_nosignal_eval.py`, `run_v6_backbone_eval.py` | negative ablation evaluators | NEGATIVE_RESULT | corresponding result families | No | Supplement | Yes, only as archive |
| `scripts/plot_stage2_typical.py`, `render_stage2_report.py` | plotting/report rendering | ANALYSIS | stage2 outputs | No | Supplement | Yes |
| `scripts/run_official_practice.py`, `run_api_smoke.py`, `update_run_metadata.py` | official practice adapters and metadata | OFFICIAL_PRACTICE | manual practice only | No | Procedure | No |
| `offline_sim/case.py`, `engine.py`, `fields.py`, `harness.py`, `client.py`, `server.py`, `run.py` | local simulator and API-shaped harness | SIMULATOR | all offline experiments | Supporting | Methods | No |
| `offline_sim/test_v6.py`, `test_v5.py`, `test_v6_l2.py`, `test_ring_only.py`, `test_v6_nosignal.py` | policy/smoke tests | TEST | corresponding variants | No | QA | Yes, keep |
| `offline_sim/test_q4_*.py` | Q4 tests outside Q3 scope | Q4 | Q4 only | No | No | No |
| `results/q3/offline_eval_v6_n8/` | frozen final V6 offline evidence | FINAL_CORE | final paper metrics | Yes | Yes | No |
| `results/q3/offline_eval_ring_count_200/` | n sensitivity evidence | CORE_EXPERIMENT | n=8 selection | No | Yes | No |
| `results/q3/offline_eval_v4_n8_n9/`, `offline_eval_v5_n8/` | V4/V5 evolution | CORE_EXPERIMENT | evolution comparison | No | Yes | No |
| `results/q3/offline_eval_stage2_*/`, `offline_eval_v6_l2_*/` | stage2/lookahead experiments and smoke/pilot/refine outputs | ABLATION | mechanism evidence | No | Supplement | No |
| `results/offline_eval_ring_only_center_ablation_*/` | ring-only full/smoke outputs | NEGATIVE_RESULT | negative ablation | No | Optional | No |
| `results/offline_eval_v6_nosignal_200/` | no_signal full/smoke outputs | NEGATIVE_RESULT | negative ablation | No | Optional | No |
| `results/offline_eval_v6_backbone_bundle_200/` | backbone full/smoke, paired/tail/trajectory outputs | NEGATIVE_RESULT | final negative experiment | No | Supplement | No |
| `results/q4/`, `q4/` | Q4 project, not Q3 | OUT_OF_SCOPE | Q4 only | No | No | No |
| `README.md`, `docs/PROJECT_STRUCTURE.md`, `docs/RESULTS_INDEX.md`, `docs/VERSIONS.md` | top-level governance/current summaries | GOVERNANCE | human entry points | Yes, after current-summary update | Yes | No |

Potential duplicate/debug material is retained: smoke, pilot, refine, `.DS_Store`, ignored logs, `__pycache__`, and parallel result naming (`results/q3/...` versus top-level `results/...`). They are not silently consolidated because scripts and provenance may depend on their paths.

Official scan: official adapter code exists, but no saved V6 official raw practice CSV/JSON result was found. The frozen snapshot's historical “practice pending” wording is snapshot provenance, not the current archive conclusion.
