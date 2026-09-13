# Q4 内部版本到论文模块对应表

内部版本号只用于实验资产追踪；论文正文采用建模含义名称。最终正式算法是内部 W5，对外称 **25-point Geometry-Guided Adaptive Search and Reacquisition (25G-ASR)**，中文为 **25点几何引导自适应搜索与重捕获策略**。

| Internal | Paper-facing name | 解决的问题 / 核心机制 | 实验结论 | Final method? | Paper role |
|---|---|---|---|---|---|
| W0 | Q4 直接迁移基线 | Q3 V6/n=8 直接用于 Q4；无 Q4 专用几何和生命周期 | directional source 下仅 8/200 full clear，说明问题不能按 Q3 处理 | 否 | 问题动机/失败基线 |
| W1 | Triangular geometric coverage backbone | 用 triangular grid 替换 detection backbone | 几何覆盖改善搜索结构，但没有解决 FOUND 后 directional visibility | 否 | 几何过渡实验 |
| W2 | Persistent Target Lifecycle | UNKNOWN/FOUND 后保持 target；ACTIVE、REACQUIRE、DEFERRED、RESOLVED | full clear 达到 200/200，但固定细粒度 reacquisition 代价很高 | 核心思想保留 | 生命周期模型 |
| W3 | Adaptive Coarse-to-Fine Reacquisition | bearing-feasible region 上先粗后细，失败时保留 5m fallback | 相比 W2 显著降低 measurement/reacquisition 代价；adaptive formal variant 被保留 | 核心思想保留 | 局部重捕获 |
| W4-A | Dynamic Unified Task Pool + Open-Route Replanning | SEARCH、LOCALIZE、REACQUIRE、CLEAR 动态交织；每个 action 后重建任务池并规划 open route | 相比 W3 显著减少全局移动；成为 W5 的行为底座 | 是 | 动态调度/路由底座 |
| W4-B | Backbone-continuity insertion alternative | 试图保持 backbone 连续并延迟局部插入 | continuity 增加 movement、measurement 和总时间；作为负结果 | 否 | 负结果/消融 |
| W5 | **25G-ASR** | 固定 25 点几何 + W4-A 动态任务池 + W3 adaptive local reacquisition + MEC/clear logic | 历史 200：200/200；held-out 600：600/600；最终综合效率与回归风险最稳健 | **是，唯一正式方法** | 正文主方法 |
| W6-A1 | MEC-only local variant | 只改变局部 MEC/clear 相关机制 | 作为分离消融，不能解释为完整 tail 解决方案 | 否 | 消融 |
| W6-A2 | Aggressive Geometry Acceleration | 加速局部 geometry/reacquisition step | 极端 tail 可下降，但 completion timing/location 改变，造成 global movement/scheduling regression | 否 | 负结果/长尾机制分析 |
| W6-A3 | Combined tail variant | 将 acceleration 与其他局部机制合并 | 局部收益不能稳定转化为整体收益；不进入正式方法 | 否 | 负结果/消融 |
| W7 | Shadow Macro Completion-Regret Scheduling | 用静态 macro regret proxy 预测动态任务生成代价 | shadow calibration 中 DelayRegret 与真实 other-work regret 反向相关，未启动正式 policy benchmark | 否 | 简短负结果，可放附录 |
| W8 | Stale-State Tail Repair candidate | 对 stale shrink 的少数 A2 eligibility 事件做局部 repair | 历史/既有 stress tail 改善；held-out 600 中 W8 mean +3.50s、Pooled T/N +0.271s/source，48 个 >100s regressions，最坏 +2309.82s | 否 | robustness comparison |

## 版本叙事规则

正文直接从 19-point regular skeleton 推导 6 个 boundary compensation points，得到 25 points；不要把 27 点写成正文方法演化主线。W4-B、W6、W7、W8 只用于解释备选机制、负结果和最终选择，不应被写成最终算法组成。

