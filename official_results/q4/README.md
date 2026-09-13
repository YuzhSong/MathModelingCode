# Q4 官方测试数据

## 目录

- `practice/`：Q4 最终入口 `run_q4_final.py` 产生的本地演练目录、`events.jsonl`、`trajectory.csv`、`summary.json`、`runs_summary.csv` 和原始 API JSONL。
- `formal/`：三次 Q4 正式测试导出的官方加密行为日志。文件名保持原样，未修改内容。
- `q4_formal_summary.csv`：根据正式日志 case code 与对应本地运行统计整理的新汇总，不改写原始 `runs_summary.csv`。

## 统计口径

`avg_time_per_cleared_s = total_virtual_time_s / cleared_count`。
`program_real_time_s` 取本地 run summary 中由 `/enter` 与 `/exit` 的真实时间戳计算得到的程序运行时间，不使用虚拟时间或 wall time。

原始 `logs/q4_final/runs_summary.csv` 仅记录本地 practice 运行，没有 formal 行；三次 formal 加密日志的 case code 与最后三次带 case code 的本地记录对应。本目录中的 formal summary 已将 `test_index` 和 formal 日志文件名明确标出。

最终代码入口：`run_q4_final.py`，策略为 W6-25PFR（25P-PFRC）。
