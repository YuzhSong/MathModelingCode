# Q3 官方测试数据

## 目录

- `practice/`：Q3 最终入口 `run_q3_final.py` 产生的本地演练目录、`events.jsonl`、`trajectory.csv`、`summary.json`、`runs_summary.csv` 和原始 API JSONL。
- `formal/`：三次 Q3 正式测试导出的官方加密行为日志。文件名保持原样，未修改内容。
- `q3_formal_summary.csv`：根据正式日志 case code 与对应本地运行统计整理的新汇总，不改写原始 `runs_summary.csv`。

## 统计口径

`avg_time_per_cleared_s = total_virtual_time_s / cleared_count`。
`program_real_time_s` 取本地 run summary 中由 `/enter` 与 `/exit` 的真实时间戳计算得到的程序运行时间，不使用虚拟时间或 wall time。

原始 `logs/q3_final/runs_summary.csv` 中没有 formal 行；三次 formal 加密日志的 case code 与最后三次带 case code 的本地记录对应。本目录中的 formal summary 已将 `test_index` 和 formal 日志文件名明确标出。

最终代码入口：`run_q3_final.py`，内部实现为 frozen V6/n=8，论文方法名为 RARC。
