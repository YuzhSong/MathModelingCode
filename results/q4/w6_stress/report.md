# W6 Persistent Bearing Feasible-Region Replay

本报告只读取既有 W5 离线 trace，不执行 policy、不修改 simulator，也不调用官方接口。

- 输入：`/Users/rainy/大学/个人/竞赛/数学建模9/Code/results/q4/w6a_decomposition/traces` 中 `w5_random_25/26/28.json`；
- Run 数：3；记录了 179 次历史 direction 后的可行域更新；
- 首次 `MEC<=20m` 的 channel 数：31；详细数据见 `replay_summary.csv`。

## 解释边界

可行域使用圆盘外接多边形与精确 bearing wedge half-plane clipping，MEC 只对外逼近多边形顶点求解。`no_signal` 未进入观测集合；空集或数值异常不会产生 clear-ready。

本阶段是证书几何的 trace replay；新的 certificate 已接入 `q4/w6_policy.py`，但 replay 本身不重新执行 policy。Run 标签是存储的 `w5_random_25/26/28.json` 代理，当前资产中未找到能独立证明官方 Run 26 ch12 或 Run 28 ch10 的原始文件，因此不能把缺失 focus channel 当作零现象。
