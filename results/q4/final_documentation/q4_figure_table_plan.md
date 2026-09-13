# Q4 论文图表计划

## 正文优先

1. **Figure 1：25 点几何布局**。画 `R=1800` 圆、19 点规则骨架、6 个 boundary compensation points，并标注 `a=970`、`ρ=1820.09`；不声称全局最少。
2. **Figure 2：Persistent Target Lifecycle**。UNKNOWN/ACTIVE/REACQUIRE/DEFERRED/RESOLVED 状态图，突出 FOUND 后 no_signal 不删除 target。
3. **Figure 3：25G-ASR workflow**。几何搜索、response 更新、任务池重建、open-route 首任务、clear/resolve 的闭环。
4. **Table 1：建模模块与消融**。正文名称为几何覆盖、生命周期、粗到细重捕获、动态任务池；内部 W 号仅放括号或附录 crosswalk。
5. **Table 2：最终 benchmark**。W5/25G-ASR 在 historical 200、stress 24、combined 800 的 Full clear、Mean、P95、P99、CVaR95、Pooled T/N、movement、measures、reacquisition。
6. **Table 3：held-out candidate selection**。W5 与 W8 的 paired win/tie/loss、Mean Δ、PooledTN Δ、tail、回归阈值及最终选择。

## 附录优先

- Figure 4：典型 trajectory 与动态任务插入；
- Figure 5：W5 与 aggressive acceleration/W8 的 tail distribution 或 source-level reacquisition tail；
- oracle lower-bound 与 conditional route-gap 图；
- W4-B continuity、W6-A2 global regression、W7 shadow calibration 诊断；
- source-count 10–16 与 generator-group 表。

图表均应在图注中标明 offline benchmark、case 数和指标口径；不要把 official practice 与 offline 数据混合。

