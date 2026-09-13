# B题问题3/问题4代码

## FINAL COMPETITION VERSION

- Q3 final method: **RARC** (Route-Aware Rolling Coordination), internal implementation **frozen V6 / n=8**; final runner: `run_q3_final.py`.
- Q4 final method: **25P-PFRC** (25-Point Symmetric Search with Persistent Feasible-Region Clearing), internal implementation **W6-25PFR**; final runner: `run_q4_final.py`.
- 离线论文数据总入口：[docs/final/README.md](docs/final/README.md)。最终摘要见 [docs/final/OFFLINE_FINAL_SUMMARY.md](docs/final/OFFLINE_FINAL_SUMMARY.md)，结果索引见 [results/Q3_FINAL_INDEX.md](results/Q3_FINAL_INDEX.md) 和 [results/Q4_FINAL_INDEX.md](results/Q4_FINAL_INDEX.md)。
- Official formal results: `official_results/q3/q3_formal_summary.csv` and `official_results/q4/q4_formal_summary.csv`; each contains exactly 3 formal runs. See [docs/final/OFFICIAL_RESULTS_INDEX.md](docs/final/OFFICIAL_RESULTS_INDEX.md). Do not infer formal values from offline runs.
- Historical V0~V6 / W0~W8 and ablations are kept for reproducibility and are not final competition policies.
- Paper handoff package: [`paper_handoff/README.md`](paper_handoff/README.md)，包含完整最终代码附录、正式表、离线结果和图表来源索引。

本轮仅合并已完成的 Windows 正式结果并整理 Mac 归档；没有重新运行 benchmark、没有调用官方接口、没有删除历史结果。

当前 Q3 最终候选为 RARC（内部实现 frozen V6/n=8），Q4 最终冻结策略为 W6-25PFR。论文层名称为 25-Point Symmetric Search with Persistent Feasible-Region Clearing（25P-PFRC）。策略代际见 [docs/VERSIONS.md](docs/VERSIONS.md)。

## Final Competition Version

本节是比赛最终提交与复现实验的唯一入口说明。历史版本和实验目录保留用于研究、审计与复现，不作为最终提交策略。

### Q3

- Final method: **RARC**（Route-Aware Rolling Coordination）。
- Internal implementation: frozen **V6 / n=8**。
- Final runner: [`run_q3_final.py`](run_q3_final.py)，固定调用 RARC/n=8，不暴露历史版本选择。
- Official formal results: [`official_results/q3/formal/`](official_results/q3/formal/)。
- Offline experiments: [`results/q3/`](results/q3/)，保留仓库原有历史目录，不覆盖。

### Q4

- Final method: **W6-25PFR**，论文层名称为 25-Point Symmetric Search with Persistent Feasible-Region Clearing（25P-PFRC）。
- Final runner: [`run_q4_final.py`](run_q4_final.py)，固定调用 W6-25PFR。
- Official formal results: [`official_results/q4/formal/`](official_results/q4/formal/)。
- Offline experiments: [`results/q4/`](results/q4/)，保留仓库原有历史目录，不覆盖。

如果只想运行最终比赛代码，请使用：

```text
python run_q3_final.py --robot-id YOUR_ID --base-url http://127.0.0.1:2026 --test-kind practice
python run_q4_final.py --robot-id YOUR_ID --base-url http://127.0.0.1:2026 --test-kind practice
```

历史 V0～V6、W0～W5、W6-A/W7/W8 及各类消融实验仅用于研究与复现，不是最终提交策略。

最终数据索引见 [`FINAL_DATA_INDEX.md`](FINAL_DATA_INDEX.md)。

Practice runs and formal runs are stored separately. Formal results are recorded only in dedicated formal summaries.

## 当前状态

- Q3 正式冻结方案为 frozen V6/n=8；论文层名称为 Route-Aware Rolling Coordination (RARC)。V6 是内部实现标识，不改代码命名。V4/n=8 保留为冻结对照基线。离线入口分别为 `q3.offline_policy.policy_v4` 和 `q3.v6_policy.policy_v6`。
- Q4 正式冻结方案为 W6-25PFR；论文层名称为 25-Point Symmetric Search with Persistent Feasible-Region Clearing（25P-PFRC）。W0-W5、W6-A、W7、W8 仅作为历史演化、消融和鲁棒性证据。
- 官方 HTTP 入口显式支持 V6；`--strategy v4` 可切回对照基线。`main.py --mode official` 默认运行 V6/n=8。运行前必须人工确认模拟器处于演练模式；正式测试不自动运行。
- 自动化评估只使用本地 `offline_sim/`，不会连接官方服务器。
- 官方接口仅有 `POST /enter`、`/measure`、`/clear`、`/exit`。

## 安装与入口

项目使用 Python 标准库，无第三方依赖：

```text
python -m pip install -r requirements.txt
python main.py --help
```

离线评估快捷入口：

```text
python main.py --mode offline --strategy v4
```

完整固定 seed 评估请使用 `scripts/run_offline_eval.py --help`。

V5 FOUND-source 补测任务生成实验：

```text
python scripts/run_v5_eval.py --versions v4,v5a,v5b,v5final --random-seeds 0:100 --stress-seeds 10000:10050 --out-dir results/offline_eval_v5_n8
```

V5 结果见 `results/offline_eval_v5_n8/report.md`。当前 V5-A/V5-B/V5-final 均未达到替换门槛，不接入官方入口。

V6 route-aware 补测任务生成实验：

```text
python scripts/run_v6_eval.py --versions v4,v5b,v6 --random-seeds 0:100 --stress-seeds 10000:10050 --out-dir results/offline_eval_v6_n8
```

V6 结果见 `results/q3/offline_eval_v6_n8/report.md`。它是当前 Q3 final candidate；完整历史实验（包括失败消融）见 `docs/q3_final/EXPERIMENT_INDEX.md`，不要把历史负结果删除或覆盖。

## Q3 官方演练/正式入口

推荐使用干净正式入口；它固定 RARC/n=8，不暴露历史版本选择。源码不硬编码参赛队号，运行时用参数或交互输入。

```text
python run_q3_final.py --robot-id YOUR_ID --base-url http://127.0.0.1:2026 --test-kind practice
```

正式三次测试时，把模拟器人工切到“问题3正式测试”并二次确认后，再使用：

```text
python run_q3_final.py --robot-id YOUR_ID --base-url http://127.0.0.1:2026 --test-kind formal --case-id CASE_CODE
```

`CASE_CODE` 是模拟器界面显示的测试案例编码；接口通常不返回该字段，可以先留空，结束后从模拟器日志列表补记。本地日志会输出表 1 所需的“清除干扰源个数”“平均定位清除时间 = total_virtual_time_s / cleared_count”“程序运行时间 = exit.real_timestamp_ms - enter.real_timestamp_ms”。

保留 `main.py --mode official --strategy v6` 作为开发入口，不建议正式填写表格时使用它。
`main.py --mode official` 仍默认 V6/n=8；`--strategy v3` 可切回基线控制器，`--strategy v4` 可回退冻结 V4 官方客户端适配入口。

## Q4 官方演练/正式入口

推荐使用干净正式入口；它固定 W6-25PFR，不暴露历史版本选择。

```text
python run_q4_final.py --robot-id YOUR_ID --base-url http://127.0.0.1:2026 --test-kind practice
```

正式三次测试时，把模拟器人工切到“问题4正式测试”并二次确认后，再使用：

```text
python run_q4_final.py --robot-id YOUR_ID --base-url http://127.0.0.1:2026 --test-kind formal --case-id CASE_CODE
```

结束后终端和 `logs/q4_final/` 会记录表格字段：清除干扰源个数、平均定位清除时间、程序运行时间。

最小接口 smoke test：

```text
python scripts/run_api_smoke.py --robot-id YOUR_ID --base-url http://127.0.0.1:2026
```

没有确认参数时不会调用 `/enter`。日志写入 `logs/`。

## 离线评估

```text
python scripts/run_offline_eval.py --versions v3,v4 --rings 8,9 --random-seeds 0:100 --stress-seeds 10000:10050 --stress-types min_reff,collinear --out-dir results/offline_eval_v4_n8_n9
```

离线 runner 只向 policy 暴露四个 API 操作；Oracle 仅在 episode 完成后读取分析数据，不能参与策略决策。

## 目录与 Git

目录说明见 [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)，Windows 携带说明见 [docs/WINDOWS_PRACTICE.md](docs/WINDOWS_PRACTICE.md)，版本说明见 [docs/VERSIONS.md](docs/VERSIONS.md)。历史结果按索引保存在 `results/`。

整理前 checkpoint：`27167c3`。建议整理完成后提交：

```text
chore: reorganize Q3 codebase and establish strategy versioning
```
