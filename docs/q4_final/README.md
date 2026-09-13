# Q4 Final Archive

```yaml
Final frozen policy: W6-25PFR
Paper name: 25-Point Symmetric Search with Persistent Feasible-Region Clearing (25P-PFRC)
Chinese name: 25点几何引导自适应搜索与重捕获策略
Clean runner: run_q4_final.py
```

Q4 的最终冻结实现是内部 W6-25PFR；论文正文使用 25P-PFRC，不把内部 W6 写进方法名。W0-W5、W6-A、W7、W8 仅作为演化、消融和鲁棒性证据。

论文手建议按以下顺序阅读：

1. [FINAL_CANDIDATE.md](FINAL_CANDIDATE.md)
2. [PAPER_DATA_INDEX.md](PAPER_DATA_INDEX.md)
3. [METHOD_MAP.md](METHOD_MAP.md)
4. [EXPERIMENT_INDEX.md](EXPERIMENT_INDEX.md)
5. [NEGATIVE_RESULTS.md](NEGATIVE_RESULTS.md)
6. [REPRODUCIBILITY.md](REPRODUCIBILITY.md)

最终离线验证主入口是 `results/q4/final_candidate_validation/report.md`，论文数据索引来自 `results/q4/final_documentation/`。完整历史结果保留在 `results/q4/`，不复制、不移动、不合并。

官方演练/正式测试建议使用干净入口 `run_q4_final.py`。它固定 W6-25PFR，不暴露历史版本选择，不硬编码参赛队号，并在结束时直接输出表格需要的清除干扰源个数、平均定位清除时间和程序运行时间。
