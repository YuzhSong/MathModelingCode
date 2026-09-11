# B题问题3代码

当前仓库只实现问题3全向干扰源；不实现问题4。策略代际见 [docs/VERSIONS.md](docs/VERSIONS.md)。

## 当前状态

- 离线推荐策略：V4，入口为 `q3.offline_policy.policy_v4`。
- 官方 HTTP 入口默认 V4（`main.py --mode official --strategy v4`，`q3.offline_policy.policy_v4_official`）；v3 基线控制器仍可用。两者均需 practice confirmation gate。V4 尚未完成官方联调。
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

## 官方演练 API

仅当官方模拟器已经由人工确认处于“问题3演练测试/模拟测试”时，才可运行。严禁在正式测试中运行，也不要把本地默认地址误认为官方地址。

```text
python main.py --mode official --strategy v4 --robot-id YOUR_ID --base-url http://127.0.0.1:2026 --confirm-practice Q3_PRACTICE_ONLY
```

`--strategy v3` 可切回基线控制器。完整参数见 `scripts/run_official_practice.py --help`（同样默认 v4，另支持 `--search-points-n`）。

最小接口 smoke test：

```text
python scripts/run_api_smoke.py --robot-id YOUR_ID --base-url http://127.0.0.1:2026 --confirm-practice Q3_PRACTICE_ONLY
```

没有确认参数时不会调用 `/enter`。日志写入 `logs/`。

## 离线评估

```text
python scripts/run_offline_eval.py --versions v3,v4 --rings 8,9 --random-seeds 0:100 --stress-seeds 10000:10050 --stress-types min_reff,collinear --out-dir results/offline_eval_v4_n8_n9
```

离线 runner 只向 policy 暴露四个 API 操作；Oracle 仅在 episode 完成后读取分析数据，不能参与策略决策。

## 目录与 Git

目录说明见 [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)，版本说明见 [docs/VERSIONS.md](docs/VERSIONS.md)。历史结果保存在 `results/`。

整理前 checkpoint：`27167c3`。建议整理完成后提交：

```text
chore: reorganize Q3 codebase and establish strategy versioning
```
