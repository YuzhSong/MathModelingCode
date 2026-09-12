# Q3 V6 Route-aware Supplement Generation 离线评估

## 1. 安全与实验边界

- 本轮仅运行本地 `offline_sim` practice case，未调用官方 HTTP 接口，未运行官方正式测试。
- V4/n=8 快照 `frozen/v4_n8_20260911/` 未修改；200 case 重放与冻结结果的时间、移动和操作计数逐 case 完全一致。
- V6 policy 仅使用 API 可见的 feasible polygon、MEC、bearings、当前位置和任务集；静态 AST 检查禁止 `offline_sim` 导入及 `.case/.engine/.sources/.jammers` 访问。
- V4 router 未修改；V6 只在 `q3/v6_policy.py` 中改变 FOUND source 的补测任务生成和候选点选择。

## 2. A. V6 决策公式与流程

对每个 FOUND 且 `MEC_radius > 20m` 的频道，候选集沿用 V5-B：V4 原补测点、MEC center、500/950m ring candidates（每 30 deg）、未完成且保证可接收的 SEARCH 点。可行域固定采样 12 点，seed=20260911，bearing error 枚举 `-1/0/+1 deg`。

当前其他任务集记为 `T`，其中包含 SEARCH、可清除 CLEAR，以及其他 FOUND source 的 V4 原补测任务。使用冻结 V4 router 求开放路线移动时间：

```text
C(T) = frozen_v4_open_route_length(T) / 5
route_marginal(S) = max(0, C(T + M(S)) - C(T))
J_approx(S) = route_marginal(S) + 5 + E[future localization/clear time | S]
S* = argmin J_approx(S)
```

`max(0, ...)` 仅消除启发式 router 的非单调数值伪影，不改变 20m 物理阈值。未引入 alpha/lambda。`E[future...]` 是可见几何采样下的 V5 局部近似：过线时估算到 MEC center 并 clear，未过线时估算一个 V4-style fallback 补测再 clear。它不是对每个 outcome 进行完整的全任务重规划，因此统一称为 `J_approx`。

如果 `S*` 是未完成 SEARCH 点，频道被挂载到该 SEARCH task；否则生成专门 MEASURE task。生成后仍由原 V4 online router 执行和滚动重规划。

## 3. B. 整体结果

200 个完全同 seed case：100 random + 50 min_reff + 50 collinear。

| Version | ClearRate | Mean (s) | Median | P95 | Max | Move (m) | Measure | Switch | Clear fail | Mean avg/source | Pooled avg/source |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| V4 | 100% | 3579.99 | 3605.04 | 4372.36 | 4886.33 | 13979.83 | 121.04 | 115.13 | 0 | 285.01 | 281.00 |
| V5-B | 100% | 3584.05 | 3611.89 | 4392.78 | 4844.31 | 14065.08 | 118.71 | 113.81 | 0 | 285.21 | 281.32 |
| V6 | 100% | **3496.69** | **3534.23** | **4244.83** | **4817.50** | **13554.13** | 121.32 | 115.59 | 0 | **278.69** | **274.47** |

V6 相对 V4 平均快 83.30s（2.33%），P95 降低 127.53s，全局 max 降低 68.83s。但这不代表逐 case 稳定占优，见 paired comparison。

## 4. 分组结果

| Version | Group | Mean (s) | Median | P95 | Max | Move (m) | ClearRate |
|---|---|---:|---:|---:|---:|---:|---:|
| V4 | random | 3793.41 | 3769.09 | 4380.83 | 4886.33 | 15000.00 | 100% |
| V5-B | random | 3759.72 | 3789.90 | 4434.18 | 4844.31 | 14891.66 | 100% |
| V6 | random | **3674.42** | **3711.70** | **4238.90** | **4720.05** | **14427.11** | 100% |
| V4 | min_reff | 3798.02 | 3778.06 | 4380.28 | 4850.69 | 14814.70 | 100% |
| V5-B | min_reff | 3885.85 | 3879.05 | 4470.49 | 4736.74 | 15322.27 | 100% |
| V6 | min_reff | **3764.08** | **3731.94** | **4365.77** | 4817.50 | **14595.68** | 100% |
| V4 | collinear | 2935.12 | 2883.71 | 3389.47 | 3802.53 | 11104.61 | 100% |
| V5-B | collinear | 2930.88 | 2953.62 | 3434.75 | **3569.74** | 11154.72 | 100% |
| V6 | collinear | **2873.83** | **2837.69** | **3315.17** | 3668.78 | **10766.64** | 100% |

## 5. 时间分项

| Version | Move time | Measure time | Switch time | Clear time | Total time | Max identity error |
|---|---:|---:|---:|---:|---:|---:|
| V4 | 2795.97 | 605.20 | 115.13 | 63.70 | 3579.99 | 6.8e-6s |
| V5-B | 2813.02 | 593.53 | 113.81 | 63.70 | 3584.05 | 6.8e-6s |
| V6 | 2710.83 | 606.58 | 115.59 | 63.70 | 3496.69 | 6.8e-6s |

V6 对 V4 的平均移动时间减少 85.14s，而 measure/switch 合计增加约 1.84s，clear 不变；所以平均改进几乎全部来自移动。

## 6. C. Same-seed paired comparison

`delta = T(V6) - T(base)`，负数代表 V6 更快。

| Base | Group | V6 win | Mean delta | Median delta | P95 delta | Max delta | Worse >300s |
|---|---|---:|---:|---:|---:|---:|---:|
| V4 | random | 70% | -118.99 | -98.78 | 391.45 | 553.01 | 7 |
| V4 | min_reff | 62% | -33.94 | -53.89 | 317.35 | 466.79 | 4 |
| V4 | collinear | 58% | -61.29 | -52.18 | 236.93 | 525.63 | 1 |
| V4 | overall | **65%** | **-83.30** | **-84.63** | 324.47 | 553.01 | **12** |
| V5-B | random | 57% | -85.30 | -74.69 | 364.56 | 474.96 | 8 |
| V5-B | min_reff | 74% | -121.78 | -107.24 | 206.24 | 410.73 | 2 |
| V5-B | collinear | 52% | -57.06 | -35.49 | 284.13 | 330.45 | 2 |
| V5-B | overall | **60%** | **-87.36** | **-80.67** | 320.18 | 474.96 | **12** |

虽然聚合 P95/max 优于 V4，V6 仍在 12/200 局中比 V4 慢超过 300s，最大 paired regression 为 553.01s。因此不能只凭 mean 宣布稳定胜出。

## 7. D-F. 补测与 route marginal

| Metric | V4 | V5-B | V6 |
|---|---:|---:|---:|
| Supplements/source | 1.680 | **1.582** | 1.734 |
| First supplement clearable | 38.75% | **45.39%** | 34.90% |
| Off-search supplement count | 3638 | 2991 | **2686** |
| FOUND-after movement/source | 788.65m | 780.35m | **662.44m** |
| Off-search supplement movement/source | 489.44m | 522.90m | **393.29m** |
| 20-30m threshold chasing | 675 | **623** | 648 |

V6 比 V4 每源 FOUND 后少移动 126.20m（16.0%），off-search 补测少 952 次。但它的补测次数更多、首次过线率更低，20-30m 追阈值仅比 V4 少 27 次。因此 V6 的收益是“把补测放到路线上”，不是“一次补测过线”。

首次补测后 MEC 分布：

| Version | <=20m/near | 20-25m | 25-30m | 30-50m | >50m |
|---|---:|---:|---:|---:|---:|
| V4 | 38.75% | 17.12% | 11.27% | 23.24% | 9.62% |
| V5-B | **45.39%** | 18.45% | 10.84% | 17.20% | **8.13%** |
| V6 | 34.90% | 14.88% | 10.09% | 22.93% | 17.20% |

V6 共执行 3482 次 route-scored 补测，1534 次（44.06%）放弃当前候选集中最高 `P_clear` 点。所有已执行候选的平均 route marginal 为 26.07s；在放弃事件中，被拒的最高 `P_clear` 候选平均为 88.20s，V6 所选候选为 15.01s。

发生放弃的 200 局相对 V5-B 合计少 17471.82s，平均 -87.36s，胜率 60%。由于每局均有放弃事件，而且两个 policy 的后续状态轨迹不同，这只是 episode-level 经验关联，不是每次放弃的严格因果节省。

## 8. E. random seed 83 复盘

| Version | Total | Move | Measures | Supplements | Off-search supplements | FOUND-after move | 20-30m chasing |
|---|---:|---:|---:|---:|---:|---:|---:|
| V4 | 3400.28s | 13166.39m | 118 | 25 | 18 | 9733.95m | 4 |
| V5-B | 4433.65s | 17908.27m | 132 | 23 | 20 | 13690.14m | 5 |
| V6 | 3923.39s | 15431.96m | 130 | 25 | 17 | 10708.47m | 2 |

V6 相对 V5-B 快 510.26s，少移动 2476.31m，且将追阈值从 5 次降到 2 次，说明 route marginal 确实修复了部分“少测却多走几公里”。但 V6 仍比 V4 慢 523.12s、多移动 2265.58m，所以未修复到冻结基线水平。

代表性决策（均是 V6 当时可见状态下的反事实候选比较，不是 V5-B 实际轨迹上的同一状态）：

| Channel | Highest P_clear: P / marginal | V6 selected: P / marginal | Reason |
|---|---:|---:|---|
| 13 | 0.889 / 294.16s | 0.667 / 20.74s | 显著避免路线绕行 |
| 17 | 0.361 / 61.43s | 0.000 / 0.16s | 总目标仅优 0.92s，预测误差敏感 |
| 5 | 0.722 / 96.09s | 0.500 / 16.86s | 用较低首次过线率换路线协同 |
| 15 | 1.000 / 235.93s | 0.972 / 109.11s | 拒绝过远的满过线率点 |

## 9. G-H. 典型成功、失败与去留判断

典型成功：

| Comparison | Group/seed | Delta time | Delta move | Delta supplements |
|---|---|---:|---:|---:|
| V6 - V4 | random/72 | -814.43s | -3967.17m | -4 |
| V6 - V4 | random/95 | -745.25s | -3401.24m | -1 |
| V6 - V5-B | min_reff/10030 | -716.47s | -3667.36m | 0 |

典型失败：

| Comparison | Group/seed | Delta time | Delta move | Delta supplements |
|---|---|---:|---:|---:|
| V6 - V4 | random/70 | +553.01s | +2465.06m | +3 |
| V6 - V4 | collinear/10023 | +525.63s | +2628.17m | +5 |
| V6 - V5-B | random/90 | +474.96s | +2124.80m | +7 |

V6 对“局部最高 `P_clear` 破坏全局路线”是**部分解决**：平均时间、移动、聚合 P95/max 都改善，seed 83 也明显恢复。但近似 future cost 仍会选到低信息点，导致更多后续补测；12 个 >300s paired regressions 表明新长尾仍存在。

**结论：本轮不建议用 V6 替换冻结 V4/n=8，也不建议现在将 V6 带到 Windows 官方演练。** V6 是有效的离线研究分支，但尚未达到“稳定优于 V4”的升级条件。官方演练候选仍保持 V4/n=8。

## 10. 运行开销与产物

V6 policy 本地 wall time：mean 1.388s/case，P95 2.443s，max 3.524s；V4 对应为 0.206/0.275/0.297s。虚拟任务时间不包含这部分计算开销。

主要数据文件：`summary.csv`、`details.csv`、`source_diagnostics.csv`、`route_decisions.csv`、`paired_comparison.csv`、`abandonment_effect.csv`、`typical_cases.csv`和 `metadata.json`。
