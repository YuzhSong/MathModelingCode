# B题问题3代码

当前仓库只实现问题3全向干扰源；不实现问题4。策略代际见 [docs/VERSIONS.md](docs/VERSIONS.md)。

## 当前状态

- 离线最终候选为 V6/n=8；V4/n=8 保留为冻结对照基线。离线入口分别为 `q3.offline_policy.policy_v4` 和 `q3.v6_policy.policy_v6`。
- 官方 HTTP 入口默认 V6（`main.py --mode official` 即跑 v6）；`--strategy v4` 可切回冻结基线。确认门（Q3_PRACTICE_ONLY）已按队伍决定移除，运行前请自行确认模拟器处于演练模式。
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

V6 结果见 `results/offline_eval_v6_n8/report.md`。V6 保持 100% 清除并改善聚合均值/P95/max，但仍有 12/200 个同 seed case 比 V4 慢超过 300s，因此不替换默认的冻结 V4/n=8；它只作为显式选择的官方演练候选，不会自动运行。

## 官方演练 API

仅当官方模拟器已经由人工确认处于“问题3演练测试/模拟测试”时，才可运行。严禁在正式测试中运行，也不要把本地默认地址误认为官方地址。

```text
python main.py --mode official --strategy v4 --robot-id YOUR_ID --base-url http://127.0.0.1:2026
```

`--strategy v4/v3` 可切回冻结基线。完整参数见 `scripts/run_official_practice.py --help`（默认 v6，支持 `--search-points-n`）。

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
