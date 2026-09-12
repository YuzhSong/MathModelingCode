# Results Index

`results/` 保留完整离线评估产物，不删除历史实验。目录按用途分为以下几类：

| Category | Directories | Role |
|---|---|---|
| Frozen comparison | `offline_eval_v4_n8_n9`, `offline_eval_v6_n8`, `offline_eval_ring_count_200` | V4/V6 基线、V6 分析、n 扫描 |
| Final stage analysis | `offline_eval_stage2_200`, `offline_eval_stage2_analysis`, `offline_eval_stage2_mn_200` | V6 regression、M/N/MN 消融 |
| Earlier experiments | `offline_eval_v0`, `offline_eval_v0_v3`, `offline_eval_clean_v0_v3_n6_n9`, `offline_eval_v5_n8` | V0-V5 历史实验 |
| Cross-strategy benchmark | `offline_eval_way1_way3_200` | Way1/Way3/V4/V6 统一 benchmark |
| Smoke tests | `offline_eval_*_smoke`, `offline_eval_way_smoke*` | 小规模回归检查，不作为正式结论 |

主要报告：

- 最终 n 扫描：[offline_eval_ring_count_200/report.md](../results/offline_eval_ring_count_200/report.md)
- Way1/Way3 对照：[offline_eval_way1_way3_200/report.md](../results/offline_eval_way1_way3_200/report.md)
- V6 阶段报告：[offline_eval_v6_n8/report.md](../results/offline_eval_v6_n8/report.md)

评估均来自本地 `offline_sim`。结果文件不能替代官方演练，也不能证明已经运行过正式测试。
