# Q3/Q4 离线实验最终归档

```yaml
scope: Mac local offline experiments and paper support materials
Q3_final: frozen V6 / n=8 == RARC
Q4_final: W6-25PFR == 25P-PFRC
official_interface_called_in_this_archive: false
historical_results_deleted: false
```

这是论文写作和复现的总入口。原始 CSV、报告和轨迹仍保留在 `results/` 原路径；本目录只提供方法层级、数据索引、最终摘要和清理候选。

优先阅读：

1. [OFFLINE_FINAL_SUMMARY.md](OFFLINE_FINAL_SUMMARY.md)
2. [PAPER_DATA_INDEX.md](PAPER_DATA_INDEX.md)
3. [Q3_FINAL_INDEX.md](Q3_FINAL_INDEX.md)
4. [Q4_FINAL_INDEX.md](Q4_FINAL_INDEX.md)
5. [REPRODUCIBILITY.md](REPRODUCIBILITY.md)

正式测试数据单独索引于 [OFFICIAL_RESULTS_INDEX.md](OFFICIAL_RESULTS_INDEX.md)。Windows 正式结果已经合并到 `official_results/`；离线结果与正式结果仍严格分开。

最终离线策略代码与入口：

- Q3：`q3/v6_policy.py`，`run_q3_final.py`；内部标识 frozen V6/n=8，论文名 RARC。
- Q4：`q4/w6_policy.py`，`q4/final_policy.py`，`run_q4_final.py`；内部标识 W6-25PFR，论文名 25P-PFRC。

所有 V0--V6、W0--W8、消融、失败实验和旧报告均按原路径保留。
