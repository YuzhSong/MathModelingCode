# Final Data Index

## 1. 最终代码入口

- Q3：[`run_q3_final.py`](run_q3_final.py)，RARC，内部实现 frozen V6/n=8。
- Q4：[`run_q4_final.py`](run_q4_final.py)，W6-25PFR，论文层名称 25P-PFRC。

## 2. 三次正式测试结果文件

- Q3：
  - [`formal-p3-1-2MEW-MBMB-RNRU-9DMG.jlog`](official_results/q3/formal/formal-p3-1-2MEW-MBMB-RNRU-9DMG.jlog)
  - [`formal-p3-2-XG3E-MNVY-ZFKX-Z79E.jlog`](official_results/q3/formal/formal-p3-2-XG3E-MNVY-ZFKX-Z79E.jlog)
  - [`formal-p3-3-THSW-FG94-PJYA-3NJG.jlog`](official_results/q3/formal/formal-p3-3-THSW-FG94-PJYA-3NJG.jlog)
- Q4：
  - [`formal-p4-1-7WW2-ZAXP-SX22-8QY6.jlog`](official_results/q4/formal/formal-p4-1-7WW2-ZAXP-SX22-8QY6.jlog)
  - [`formal-p4-2-XWAC-7BTA-4XUZ-K7PX.jlog`](official_results/q4/formal/formal-p4-2-XWAC-7BTA-4XUZ-K7PX.jlog)
  - [`formal-p4-3-JG75-UXMB-2TR9-S928.jlog`](official_results/q4/formal/formal-p4-3-JG75-UXMB-2TR9-S928.jlog)

## 3. 官方原始日志位置

- Q3 practice/API：[`official_results/q3/practice/`](official_results/q3/practice/)
- Q3 formal 加密日志：[`official_results/q3/formal/`](official_results/q3/formal/)
- Q4 practice/API：[`official_results/q4/practice/`](official_results/q4/practice/)
- Q4 formal 加密日志：[`official_results/q4/formal/`](official_results/q4/formal/)

所有原始 `.jlog`、`events.jsonl`、`trajectory.csv`、`summary.json` 和 API JSONL 均只复制，未删除、覆盖或改名。

## 4. 本地 summary CSV

- Q3 formal：[`official_results/q3/q3_formal_summary.csv`](official_results/q3/q3_formal_summary.csv)
- Q4 formal：[`official_results/q4/q4_formal_summary.csv`](official_results/q4/q4_formal_summary.csv)
- 原始本地 practice 汇总副本：[`official_results/q3/practice/runs_summary.csv`](official_results/q3/practice/runs_summary.csv)、[`official_results/q4/practice/runs_summary.csv`](official_results/q4/practice/runs_summary.csv)

两份 formal summary 的 `program_real_time_s` 使用 `/enter` 到 `/exit` 的真实程序运行时间；`avg_time_per_cleared_s` 按总虚拟时间除以清除数量重新计算。

论文正式结果表：[`official_results/Q3_PAPER_TABLE.csv`](official_results/Q3_PAPER_TABLE.csv)、[`official_results/Q4_PAPER_TABLE.csv`](official_results/Q4_PAPER_TABLE.csv)。官方日志清单及 SHA-256：[`official_results/OFFICIAL_LOG_MANIFEST.csv`](official_results/OFFICIAL_LOG_MANIFEST.csv)。

## 5. 论文应使用的数据来源

正式测试结果表使用 Q3/Q4 各自的 `*_formal_summary.csv`，并以对应的官方加密 `.jlog` 作为原始凭证。离线方法对比和统计实验继续使用仓库原有 `results/q3/`、`results/q4/` 历史目录，不使用 practice 结果替代 formal 结果。

原始 `runs_summary.csv` 没有 formal 行，现有行均标为 `practice`；因此没有发现可直接判定为“formal 错标 practice”的行。新的 formal summary 依据官方 `.jlog` 的 `formal_index`、`case_code` 和文件名单独整理，并保留原始标签不变。
