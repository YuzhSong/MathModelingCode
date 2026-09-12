# Windows 官方演练携带说明

当前准备带到 Windows 的候选是 `V6/n=8`。本地离线评估已经完成；本文件只描述官方“问题3演练测试/模拟测试”的人工确认后运行方式，不授权也不适用于正式测试。

## 携带内容

优先使用 `frozen/v6_n8_20260912/` 中的快照。若直接携带当前工程，至少保留：

- `main.py`
- `q3/`
- `scripts/run_official_practice.py`
- `requirements.txt`
- `docs/`

`offline_sim/` 和 `results/` 用于本地复核，不是官方 HTTP 运行的必要依赖。不要把 `logs/` 中的旧日志当作运行状态；该目录已被 Git 忽略。

## 运行前检查

1. 在官方模拟器界面人工确认当前处于“问题3演练测试/模拟测试”，不是正式测试。
2. 确认模拟器地址、端口和登录队号；不要因为默认地址存在就直接请求。
3. 先运行帮助命令和编译检查，不会调用 HTTP：

```text
python -m py_compile main.py q3/*.py scripts/*.py
python main.py --help
```

## 演练入口

确认演练模式后，在 Windows 命令行运行：

```text
python main.py --mode official --strategy v6 --search-points-n 8 --robot-id YOUR_ID --base-url http://127.0.0.1:2026
```

等价脚本入口：

```text
python scripts/run_official_practice.py --strategy v6 --search-points-n 8 --robot-id YOUR_ID --base-url http://127.0.0.1:2026
```

程序只使用官方已有的 `/enter`、`/measure`、`/clear`、`/exit` 四个接口；没有 `/move`。

## 回退与边界

- 默认策略仍是 V4；不指定 `--strategy v6` 不会运行 V6。
- V4 冻结快照和 V6 冻结快照分开保存，不能互相覆盖。
- 发现模式不明确、倒计时未结束、或地址不是模拟器本地演练地址时，停止，不运行。
- 本说明不包含正式测试命令；正式测试必须由用户本人另行明确下达。
