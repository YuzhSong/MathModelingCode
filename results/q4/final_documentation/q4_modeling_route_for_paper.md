# Q4 论文建模路线

## 1. 问题分析

Q4 的核心不是单纯“用探测圆覆盖区域”。目标源可能是 directional source，发射方向存在约 ±90° 的可见性影响。因此，机器人经过距离上可探测的位置，并不等价于 source 已经被定位、可持续观测或能够立即清除。总时间同时受到 movement、direction measurement、channel switching、clear service 和动态任务顺序影响。

因此模型需要同时描述：最坏情形空间覆盖、方向观测不确定性、目标生命周期和在线路径耦合。

## 2. 最坏情形几何模型

设目标区域为圆盘

\[
\mathcal A=\{x\in\mathbb R^2:\|x\|\le R\},\quad R=1800\text{ m},
\]

最小有效接收半径取 `r_min=1000 m`。最终搜索骨架直接采用中心六角/三角晶格：中心 1 点、第一圈 6 点、第二圈 12 点，共 19 点。对圆周边界的 6 个对称缺口，在 6 个方向各增加一个补偿检测点，得到 `19+6=25` 点。

代码中的最终参数为 `a=970 m`、`p=140 m`，其中

\[
\rho=\sqrt3a+p=1820.0893\text{ m}.
\]

补偿点允许位于目标圆外，因为检测点是机器人位置，接收覆盖圆可以覆盖目标区域边界；`rho>1800 m` 本身并不违反模型。

可行约束为

\[
a^2+(1800-\sqrt3a)^2\le 1000^2,
\]

代码给出的上界为

\[
a\le450\sqrt3+50\sqrt{19}\approx997.37\text{ m}.
\]

`a=970` 是在该可行区间内结合离线路线性能选择的稳定参数；不能称为全局解析最优，也不能声称 25 点是任意布置下的全局最少点数。严格结论是：在所采用的中心 19 点规则骨架下，6 个剩余边界缺口各需要补偿，因此形成 25 点构型。

## 3. 从几何覆盖到目标生命周期

对尚未发现的 channel，`no_signal` 只表示当前位置没有得到有效观测。对已经 FOUND 的 source，后续 `no_signal` 不能解释为 source 不存在，也不能据此反推 source 位置、接收半径或方向；它只说明当前点暂时不可观测，可能是距离或 directional visibility 造成的。

因此，发现后的 target 必须持久化到 clear success。代码实际状态为 `TargetLifecycle.ACTIVE`、`REACQUIRE`、`DEFERRED`、`RESOLVED`，而 UNKNOWN 由底层 `ChannelStatus.UNKNOWN` 表示。论文可将其表述为：

`UNKNOWN → ACTIVE → REACQUIRE/DEFERRED → ACTIVE/REACQUIRE → RESOLVED`，其中只有 clear success 才允许进入 RESOLVED。

## 4. 自适应粗到细重捕获

固定 5m 步长会产生大量局部动作和重复运动。最终局部机制根据最近 bearing、可行定位区域和历史观测计算粗搜索步长；成功后更新 bearing/步长，失败后逐步缩小，必要时退回 5m fallback。这样把局部搜索资源集中在接近可行区域或重新失去可见性的阶段，降低 measurement count、reacquisition count 和局部运动距离。

## 5. 统一动态任务池与路径重规划

任务池不采用“先搜完、再定位、再清除”的严格分阶段流程，而是动态包含：`SEARCH`、`measure/LOCALIZE`、`REACQUIRE` 和 `CLEAR`。每个实际 action 后读取 response、更新 target state，再重建当前任务池。

最终 W5 使用 `q4/routing.py` 的 `open_route`：在当前任务集合上调用 open-route optimization（底层为 cheapest-insertion/2-opt 路线优化），只执行当前路线的首任务，下一步再次重规划。W4-B 的 continuity 实验说明，过强的固定 backbone commitment 会延迟重要 localization，并引入 global movement/scheduling 代价。

## 6. 最终联合策略

论文正式方法 25G-ASR 由以下模块组成：

1. 25-point worst-case geometric search backbone；
2. persistent target lifecycle；
3. adaptive coarse-to-fine reacquisition；
4. dynamic unified task pool；
5. dynamic open-route replanning；
6. 基于定位置信度/最小包围圆（MEC）的 clear-on-confidence logic。

### 伪代码草案

```text
construct 25-point geometric backbone
initialize every channel as UNKNOWN
enter task service
while not all targets are RESOLVED:
    update UNKNOWN/ACTIVE/REACQUIRE/DEFERRED states
    build current tasks:
        remaining SEARCH points
        feasible LOCALIZE tasks for found targets
        REACQUIRE probes for temporarily invisible targets
        CLEAR tasks whose confidence/MEC condition is satisfied
    optimize an open route through the current task pool
    execute only the first task
    read the API response
    if a new direction is observed:
        store target state and update localization region
    if a FOUND target returns no_signal:
        retain the target and schedule REACQUIRE or DEFER
    if clear succeeds:
        mark the target RESOLVED
    rebuild the task pool and replan
exit after all targets are resolved
```

## 7. 鲁棒性与备选机制

W6-A2 的 aggressive acceleration 验证了一个重要诊断：局部极端 reacquisition tail 可以下降，但 completion timing/location 改变会扰动后续全局路径，因而增加 movement 或 scheduling regression。W7 的 shadow 验证则说明静态 macro completion regret 不能可靠预测动态任务生成代价。W8 对少量 stale-state shrink 事件做 repair，在历史数据和部分 tail 指标上有效，但 held-out 600 的 paired regression 风险仍然过大。

最终因此选择 25G-ASR，而不是把局部 tail repair 或 aggressive acceleration 合入正式方法。

## 8. 实验验证逻辑

验证顺序为：历史 200 复核 → 新 seed 的 9-case smoke → random/min_reff/collinear 各 200 的 held-out 600 → 既有 stress 24 → combined 800。主要指标同时报告 Mean、Median、P95、P99、CVaR95、Max、Pooled T/N、MacroTN、movement、measure、switch、reacquisition 和 full-clear rate。

Pooled T/N 定义为 `ΣT_i/ΣN_i`，是论文主 per-source 指标；MacroTN 定义为 `mean(T_i/N_i)`，只作为辅助。最终选择以 held-out 600 的安全性、平均效率、尾部、source-level tail 和 same-seed severe regression 综合判断，而不是按单一 Mean 排名。

