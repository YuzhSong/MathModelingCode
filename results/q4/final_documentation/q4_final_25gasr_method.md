# Final 25G-ASR Method

## 正式名称

**25-point Geometry-Guided Adaptive Search and Reacquisition (25G-ASR)**  
中文：**25点几何引导自适应搜索与重捕获策略**

论文正文不使用内部编号 W5。

## 方法输入与状态

- 圆形任务区域：`O=(0,0)`，`R=1800 m`；
- 最坏有效接收半径：`r_min=1000 m`；
- 25 个固定搜索点：中心 1 点、两圈规则点 18 点、六个边界补偿点；
- 每个 channel 的可观测 response、bearing、定位可行域和 clear 置信度；
- 目标状态：UNKNOWN、ACTIVE、REACQUIRE、DEFERRED、RESOLVED。

## 25 点构型

令 `a=970 m`、`p=140 m`，`h=√3a`，`ρ=h+p`。点集由代码 `w5_detection_points()` 生成：

\[
\mathcal P=\{(0,0)\}\cup\bigcup_{r\in\{a,2a,h,\rho\}}
\left\{r(\cos(30^\circ k+\phi_r),\sin(30^\circ k+\phi_r)):k=0,\ldots,5\right\},
\]

其中 `φ_r=0°` 对 `r=a,2a`，`φ_r=30°` 对 `r=h,ρ`。前 19 点来自 `r=0,a,2a,h`，最后 6 点来自 `r=ρ`。论文应强调这是固定 19 点骨架下的条件性 25 点构型，不是任意布点全局最小证明。

## 在线决策

每次实际动作结束后，策略只依据 API response 更新状态：

1. 对 UNKNOWN channel，首次有效 direction 使其进入 ACTIVE；
2. 对 ACTIVE target，更新 bearing 与定位区域；
3. 对 FOUND 后的 no_signal，保留 target，不删除 source 假设，进入 REACQUIRE 或 DEFERRED；
4. 对满足 MEC/置信度的 target 建立 CLEAR task；
5. clear success 后进入 RESOLVED；
6. 重新构造全部当前任务并优化 open route，只执行下一首任务。

## 局部重捕获

从最近有效观测点和 bearing 出发，在可行区域内计算 adaptive step。粗步探测成功则更新局部状态；失败则改变角度偏移并逐步缩小步长；局部策略失效时使用保守 fallback。该机制的目的不是追求局部动作数的单独最小，而是在 correctness 保持下减少长尾局部搜索对总时间的影响。

## 可复现实现定位

- 几何：`Code/q4/w5_geometry.py`；
- 正式入口：`Code/q4/w5_policy.py`；
- 生命周期/重捕获基础：`Code/q4/w2_policy.py`、`Code/q4/w3_policy.py`；
- 动态任务池：`Code/q4/w4a_policy.py`；
- 路由：`Code/q4/routing.py`；
- 离线 physics/service：`Code/offline_sim/engine.py`。

