# Results Index

`results/` 保留完整离线评估产物，不删除历史实验。目录按用途分为以下几类：

| Category | Directories | Role |
|---|---|---|
| Final candidate | `q3/offline_eval_v6_n8`, `q3/offline_eval_ring_count_200` | V6/RARC final metrics and n selection |
| Frozen comparison | `q3/offline_eval_v4_n8_n9`, `q3/offline_eval_v5_n8` | V4/V5 evolution comparison |
| Final stage analysis | `offline_eval_stage2_200`, `offline_eval_stage2_analysis`, `offline_eval_stage2_mn_200` | V6 regression、M/N/MN 消融 |
| Earlier experiments | `q3/offline_eval_v0`, `q3/offline_eval_v0_v3`, `q3/offline_eval_clean_v0_v3_n6_n9` | V0-V3 历史实验 |
| Cross-strategy benchmark | `offline_eval_way1_way3_200` | Way1/Way3/V4/V6 统一 benchmark |
| Smoke tests | `offline_eval_*_smoke`, `offline_eval_way_smoke*` | 小规模回归检查，不作为正式结论 |

主要报告：

- 最终 n 扫描：[offline_eval_ring_count_200/report.md](../results/q3/offline_eval_ring_count_200/report.md)
- Way1/Way3 对照：[offline_eval_way1_way3_200/report.md](../results/offline_eval_way1_way3_200/report.md)
- V6 阶段报告：[offline_eval_v6_n8/report.md](../results/q3/offline_eval_v6_n8/report.md)

Q3 最终归档入口：[docs/q3_final/README.md](q3_final/README.md)。负结果（ring-only、no_signal、SEARCH-backbone bundle）保留在原路径，并由该入口统一索引。

评估均来自本地 `offline_sim`。结果文件不能替代官方演练，也不能证明已经运行过正式测试。
