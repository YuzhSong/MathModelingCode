# Q4 指标定义与论文口径

## Episode-level

对第 `i` 个 episode，`T_i=total_time_s`，`N_i=source_count`。

- Mean：`mean(T_i)`；
- Median/P90/P95/P99：episode total time 的经验分位数；
- CVaR95：最慢 5% episodes 的平均 total time；
- Full clear：`success=1` 且 `clear_fail=0`；
- Unresolved：退出时仍有未清除目标或 `targets_remaining_at_exit>0`；
- Exceptions：`error` 非空。

## Per-source

主指标：

\[
\mathrm{PooledTN}=\frac{\sum_iT_i}{\sum_iN_i}.
\]

它按 source 数为 episode 加权，表示把所有 episode 的 source 合并后的平均每源耗时。

辅助指标：

\[
\mathrm{MacroTN}=\frac1M\sum_{i=1}^{M}\frac{T_i}{N_i}.
\]

MacroTN 是 episode-level T/N 的等权平均；不得把旧报告中名为 Mean T/N 的字段自动称为 PooledTN。最终 held-out：W5 PooledTN `571.1603 s/source`，W8 `571.4315 s/source`；W5 MacroTN `586.2917`，W8 `586.5293 s/source`。

## Movement/service

报告 mean/median/P95/P99/max movement time；mean/P95 measure count；mean switch count；mean/P95 reacquisition attempts；以及 SEARCH、FOUND、CLEAR 和 movement/measure/switch/clear time decomposition。所有数值来自 episode raw CSV 或已有 phase decomposition，不改变 logger 语义。

## Source-level tail

对 source metrics 统计：reacquisition attempts >50、>100、>200 的 source 数，最大/P95/P99 reacquisition，最大/P95 supplement measures，stable-small-step measure count，FOUND→CLEAR 的 P95/P99/max。source-level tails 与 episode-level tails 分开报告。

## Paired comparison

同一 `(suite, seed)` 定义

\[
\Delta_i=T_{W8,i}-T_{W5,i}.
\]

`Δ<0` 为 W8 win，`Δ=0` 为 tie，`Δ>0` 为 W8 loss。另报 `Δ>50/100/300/600/1000` 和对应负向 improvement thresholds。阈值只做结果描述，不用于反向调参。

## Bootstrap

held-out 600 以 episode pair 为单位重采样 10,000 次，固定 seed `20260913`。PooledTN 每次都按重采样后的 `ΣT/ΣN` 重新计算；不对 episode T/N 简单取平均。paired win rate 另报 95% Wilson CI。

