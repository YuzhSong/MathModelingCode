# Final Official Test Report

正式测试完成时间记录：2026-09-13 17:11:40（Q4 第三份官方日志文件时间）；材料核验随后完成。

## Q3

Final runner：`run_q3_final.py`；最终方法 RARC，内部实现 frozen V6/n=8。

| 测试案例编码 | 清除干扰源个数 | 平均定位清除时间 | 程序运行时间 | clear fail |
|---|---:|---:|---:|---:|
| 2MEW-MBMB-RNRU-9DMG | 15 | 253.255992 s | 6.569 s | 0 |
| XG3E-MNVY-ZFKX-Z79E | 12 | 257.098977 s | 4.151 s | 0 |
| THSW-FG94-PJYA-3NJG | 14 | 280.209810 s | 5.127 s | 0 |

官方日志：

- `formal-p3-1-2MEW-MBMB-RNRU-9DMG.jlog`
- `formal-p3-2-XG3E-MNVY-ZFKX-Z79E.jlog`
- `formal-p3-3-THSW-FG94-PJYA-3NJG.jlog`

## Q4

Final runner：`run_q4_final.py`；最终方法 25P-PFRC，内部实现 W6-25PFR。

| 测试案例编码 | 清除干扰源个数 | 平均定位清除时间 | 程序运行时间 | clear fail |
|---|---:|---:|---:|---:|
| 7WW2-ZAXP-SX22-8QY6 | 12 | 566.781394 s | 7.179 s | 0 |
| XWAC-7BTA-4XUZ-K7PX | 10 | 695.000584 s | 7.157 s | 0 |
| JG75-UXMB-2TR9-S928 | 13 | 544.908490 s | 10.906 s | 0 |

官方日志：

- `formal-p4-1-7WW2-ZAXP-SX22-8QY6.jlog`
- `formal-p4-2-XWAC-7BTA-4XUZ-K7PX.jlog`
- `formal-p4-3-JG75-UXMB-2TR9-S928.jlog`

## 数据来源与口径

表格数据只来自 `q3_formal_summary.csv` 和 `q4_formal_summary.csv`，不使用 practice 数据补齐。`avg_time_per_cleared_s` 按总虚拟时间除以清除数量计算；`program_real_time_s` 使用真实 `/enter` 到 `/exit` 程序运行时间。官方加密日志位于各题 `formal/` 子目录，原文件未修改。

Practice runs and formal runs are stored separately. Formal results are recorded only in dedicated formal summaries.
