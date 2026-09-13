# Q3 Final Archive

```yaml
Final candidate: frozen V6 / n=8
Paper name: Route-Aware Rolling Coordination (RARC)
Internal implementation name: V6
```

Q3 的最终候选是 frozen V6/n=8；论文层建议称为 RARC（路径感知滚动联合调度策略）。RARC 不是新的代码版本，也不改写代码中的 V6 标识。

论文手建议按以下顺序阅读：

1. [FINAL_CANDIDATE.md](FINAL_CANDIDATE.md)
2. [PAPER_DATA_INDEX.md](PAPER_DATA_INDEX.md)
3. [EXPERIMENT_INDEX.md](EXPERIMENT_INDEX.md)
4. [NEGATIVE_RESULTS.md](NEGATIVE_RESULTS.md)
5. [REPRODUCIBILITY.md](REPRODUCIBILITY.md)

最终离线主结果：`results/q3/offline_eval_v6_n8/report.md`；n 扫描：`results/q3/offline_eval_ring_count_200/report.md`。完整历史结果保留在 `results/`，不复制、不移动、不合并。

核心实现入口是 `q3/v6_policy.py:policy_v6`，frozen snapshot 是 `frozen/v6_n8_20260912/`。本地复现使用 `scripts/run_v6_eval.py`；官方 practice 入口仅在人工确认演练环境后显式使用，正式测试不自动运行。

目录状态说明：当前仓库中未发现已保存的 V6 官方 raw practice 数据；因此文档不填入官方指标。
