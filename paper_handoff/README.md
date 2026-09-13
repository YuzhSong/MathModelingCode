# Paper Handoff Package

这是给论文手的最终交付包：方法名称、最终代码链、正式测试表、离线结果摘要、图表来源和一致性检查集中在这里。

## Final methods

- Q3: **RARC — Route-Aware Rolling Coordination**（路径感知滚动联合调度策略），internal implementation: frozen V6/n=8，runner: `run_q3_final.py`。
- Q4: **25P-PFRC — 25-Point Symmetric Search with Persistent Feasible-Region Clearing**，internal implementation: W6-25PFR，runner: `run_q4_final.py`。

论文正文使用 RARC 和 25P-PFRC；V6、W6-25PFR 只用于代码/实验索引。

## Start here

1. [CONSISTENCY_CHECKLIST.md](CONSISTENCY_CHECKLIST.md)
2. [RESULT_APPENDIX_INDEX.md](RESULT_APPENDIX_INDEX.md)
3. [PAPER_FIGURE_TABLE_INDEX.md](PAPER_FIGURE_TABLE_INDEX.md)
4. [CODE_APPENDIX_INDEX.md](CODE_APPENDIX_INDEX.md)
5. [q3/Q3_CODE_APPENDIX.md](q3/Q3_CODE_APPENDIX.md) and [q4/Q4_CODE_APPENDIX.md](q4/Q4_CODE_APPENDIX.md)

正文建议控制在 30 页内，放模型、公式、算法流程、核心图表、三次正式测试表、必要消融、AI 使用说明和参考文献。完整最终代码和更详细计算结果放附录；完整 CSV、轨迹、官方日志和历史实验留在原仓库/支撑材料中。

Official formal summaries are separate from offline evidence:

- `official_results/q3/q3_formal_summary.csv`
- `official_results/q4/q4_formal_summary.csv`

No algorithm, frozen snapshot, official CSV or official `.jlog` was modified to create this package.
