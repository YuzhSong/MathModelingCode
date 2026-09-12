# Q3 第二阶段：V6 诊断与 Way1/Way3 局部机制消融

## Executive Summary

- 本轮只运行本地 offline_sim/practice。没有调用官方 HTTP、正式测试或正式测试入口。
- 1,400 个正式消融 episode（7 个版本 × 200 seeds）全部 100% clear、0 clear fail；另有 400 个 V6/V6Audit 行为校验 episode。V6 重放与既有 200 局逐 seed 完全一致。
- 纯 Minimax M1 明确失败：平均慢 315.77s。M2 只快 18.46s，但最坏 paired regression 达 737.53s，不满足升级条件。
- 条件 85m 近场候选 N1 是唯一实质单模块收益：平均快 79.07s、P95 改善 64.18s、平均少走 388.73m、paired win 74%。但仍有 3 个 >300s 回退，且聚合 max 比 V6 高 160.16s。
- 精确大交角候选 N2 基本冗余；N3 与 N1 几乎相同。MN 相对 N1 平均只快 0.07s，却有更差 P95 和 8 个 >300s 回退，Minimax 与近场在当前实现下不互补。
- V6 的平均收益来自 FOUND/CLEAR 路段缩短，但主要回退来自 SEARCH/任务顺序扰动。当前建议保留 frozen V6；N1 仅作为 V6.x 离线候选，不创建 V7。

## 1. Safety And Reproducibility

- Policy 只接收 runner/API 可见信息。stage2 policy 静态检查禁止导入 offline_sim 或访问 case/engine/sources/jammers。
- Ground truth 仅在 episode 完成后用于典型路线图的 source 标注。
- V6Audit 只增加日志；200 局相对 V6 的时间和移动最大绝对差均为 0。
- 每局均验证 total = move + measure + switch + clear；最大数值误差低于 8e-6s。
- M2 beta=0.10 s/m 由固定 40-case pilot 在 0.01/0.025/0.05/0.075/0.10/0.15/0.25 中选出，随后才运行正式 200 局。

## 2. V6 Failure Diagnosis

V6 相对 V4 在 130/200 局获胜、70/200 局失败；12 局回退超过 300s。以下分解使用互斥的 phase/action 时间，能与总 delta 对账；dedicated detour proxy 与 phase move 重叠，仅作诊断。

| Population | Cases | Total Δs | SEARCH move | SEARCH info | FOUND move | FOUND info | CLEAR move | Dedicated proxy | Order remainder | Supp Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 200 | -83.30 | 166.52 | -2.94 | -175.09 | 4.77 | -76.57 | -244.99 | -6.67 | 0.68 |
| v6_wins | 130 | -222.11 | 126.83 | -7.31 | -226.15 | 2.15 | -117.63 | -307.14 | -36.64 | 0.20 |
| v6_losses | 70 | 174.49 | 240.25 | 5.19 | -80.26 | 9.64 | -0.32 | -129.58 | 49.00 | 1.57 |
| regression_gt300 | 12 | 439.38 | 272.84 | 7.50 | -18.75 | 13.25 | 164.54 | -105.93 | 251.72 | 2.17 |

全体均值中，V6 的 SEARCH 移动比 V4 多 166.52s，但 FOUND 移动少 175.09s、CLEAR 移动少 76.57s，净改善 83.30s。也就是说，V6 不是把所有阶段都变短，而是用更长的搜索共存路线换取后续定位/清除协同。

在 70 个失败局中，SEARCH 移动平均多 240.25s，是主要正损失；FOUND 移动仍平均少 80.26s。12 个 >300s 回退局中，SEARCH 移动多 272.84s，CLEAR 移动再多 164.54s，二者解释了主要长尾。
其中 CLEAR move 是 READY_TO_CLEAR 后到实际 clear 点的最后移动；Dedicated proxy 是固定 SEARCH 点之外 supplement move 的诊断量，会与 FOUND/SEARCH move 重叠；Order remainder 是总 delta 扣除互斥 phase/action 项后的剩余。大幅回退局的 Order remainder 为 +251.72s，表明多任务发现时序和排序效应不可忽略。

回退分类是基于动作日志的启发式归因。Primary class 互斥；overlap flags 可重叠，不能解释为严格因果。

| Class | Cases | Loss share | Mean loss s | Max loss s |
|---|---:|---:|---:|---:|
| R2_over_wait_search | 40 | 57.1% | 172.07 | 553.01 |
| R5_task_ordering | 13 | 18.6% | 231.88 | 523.12 |
| R3_dedicated_detour | 11 | 15.7% | 185.08 | 525.63 |
| R1_route_info_tradeoff | 4 | 5.7% | 61.21 | 139.56 |
| R6_other | 2 | 2.9% | 18.03 | 32.75 |
| overlap_R1 | 46 | 65.7% | 179.44 | 553.01 |
| overlap_R2 | 58 | 82.9% | 187.68 | 553.01 |
| overlap_R3 | 22 | 31.4% | 195.44 | 525.63 |
| overlap_R4 | 46 | 65.7% | 179.44 | 553.01 |
| overlap_R5 | 40 | 57.1% | 216.13 | 553.01 |

12 个大幅回退 case：

| Suite | Seed | Δ total s | SEARCH move | FOUND move | CLEAR move | Supp Δ | Primary |
|---|---:|---:|---:|---:|---:|---:|---|
| random | 70 | 553.01 | 574.26 | -371.94 | 290.70 | 3 | R2_over_wait_search |
| collinear | 10023 | 525.63 | -68.06 | 466.08 | 127.62 | 5 | R3_dedicated_detour |
| random | 83 | 523.12 | 12.12 | 370.18 | 70.81 | 0 | R5_task_ordering |
| random | 90 | 518.02 | 205.30 | 310.98 | 1.73 | 5 | R3_dedicated_detour |
| min_reff | 10017 | 466.79 | 201.56 | -15.10 | 272.33 | -2 | R5_task_ordering |
| random | 45 | 461.30 | 594.39 | -46.24 | -61.85 | 0 | R2_over_wait_search |
| random | 44 | 412.09 | 395.73 | -164.95 | 161.31 | 4 | R2_over_wait_search |
| min_reff | 10005 | 403.37 | 507.39 | -387.17 | 238.15 | 2 | R2_over_wait_search |
| random | 76 | 390.36 | -45.29 | 192.58 | 206.07 | 6 | R5_task_ordering |
| random | 40 | 385.09 | 165.46 | -29.84 | 248.47 | 0 | R5_task_ordering |
| min_reff | 10008 | 321.28 | 165.75 | -185.89 | 346.42 | 2 | R5_task_ordering |
| min_reff | 10039 | 312.55 | 565.50 | -363.64 | 72.70 | 1 | R2_over_wait_search |

### Dedicated Supplement And Future SEARCH

V6 共执行 3,482 次 FOUND 后补测，其中 2,686 次是 dedicated supplement。1,627 次 dedicated 动作发生时仍存在至少一个合法、未完成的 SEARCH 点；337 次其补测点距离未来 SEARCH 点不超过 250m，807 次不超过 500m。距离切分仅用于敏感性统计，不是策略阈值。

| Population | Cases | Dedicated | With legal SEARCH | Share | <=250m | <=500m | Marginal s |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 200 | 2686 | 1627 | 60.6% | 337 | 807 | 33.79 |
| v6_wins | 130 | 1754 | 1042 | 59.4% | 215 | 493 | 33.83 |
| v6_losses | 70 | 932 | 585 | 62.8% | 122 | 314 | 33.72 |
| regression_gt300 | 12 | 179 | 94 | 52.5% | 18 | 56 | 40.60 |

这些 dedicated 选择并非没有比较 future SEARCH：在可用时，V6 预测 future SEARCH objective 平均比已选 dedicated 高 58.02s。问题更像是 one-step future-cost 近似与后续全局任务演化不一致，而不是候选缺失。

### Most Expensive FOUND Sources

| Suite | Seed | Ch | FOUND-clear s | Move m | Supp | First MEC m | Final MEC m |
|---|---:|---:|---:|---:|---:|---:|---:|
| min_reff | 10035 | 4 | 4794.50 | 340.60 | 2 | 25.05 | 19.79 |
| min_reff | 10035 | 15 | 4655.38 | 1842.14 | 2 | 318.27 | 18.96 |
| random | 40 | 15 | 4447.32 | 748.78 | 1 | 16.73 | 16.73 |
| random | 1 | 3 | 4407.82 | 931.57 | 3 | 76.98 | 15.48 |
| random | 40 | 4 | 4358.56 | 1157.05 | 2 | 82.66 | 19.09 |
| min_reff | 10041 | 3 | 4241.11 | 1166.94 | 2 | 69.71 | 17.43 |
| min_reff | 10002 | 5 | 4215.71 | 687.42 | 2 | 50.15 | 13.26 |
| random | 27 | 15 | 4158.04 | 1727.62 | 2 | 60.74 | 17.53 |
| random | 40 | 3 | 4133.00 | 863.69 | 2 | 37.38 | 18.69 |
| random | 70 | 3 | 4121.28 | 1515.99 | 3 | 375.08 | 18.02 |

补测次数最高的 source：

| Suite | Seed | Ch | Supp | FOUND-clear s | Move m | 20-30m chase |
|---|---:|---:|---:|---:|---:|---:|
| random | 67 | 19 | 5 | 848.00 | 1996.93 | 1 |
| collinear | 10026 | 2 | 5 | 564.71 | 1424.19 | 3 |
| random | 7 | 9 | 4 | 2695.03 | 2420.72 | 0 |
| random | 86 | 5 | 4 | 3743.31 | 2353.34 | 2 |
| random | 99 | 20 | 4 | 676.07 | 2120.26 | 1 |
| random | 46 | 12 | 4 | 658.39 | 2006.48 | 3 |
| random | 35 | 14 | 4 | 954.59 | 1983.40 | 0 |
| random | 76 | 5 | 4 | 565.26 | 1857.97 | 1 |
| random | 90 | 18 | 4 | 1025.45 | 1799.39 | 2 |
| random | 17 | 1 | 4 | 494.15 | 1663.64 | 1 |

## 3. Mechanism Overlap

| Mechanism | Mark | Code-level conclusion |
|---|---|---|
| Way1 set-membership / feasible region | A | V6 已使用 bearing wedge 的 feasible polygon 与保守定位区域。 |
| Way1 MEC | A | V6 使用 MEC radius <=20m；Way1 内部为更保守的 19m。 |
| Way1 Minimax active localization | C | V6 原本是采样期望 future cost，不含 worst-after residual；M1/M2 是真实新增。 |
| Way1 candidate generation | B | 都有 center/ring/perpendicular 几何，但半径、点数和评分不同。 |
| Way1 task scheduling | B/D | V6 已联合 SEARCH/MEASURE/CLEAR；Way1 COVER/LOCALIZE 优先级会带来回头路，不移植。 |
| Way1 route planning | B/D | 都含 nearest/2-opt 元素；Way1 的逐频道 LOCALIZE 路线已被统一 benchmark 判定为高移动。 |
| Way3 coverage scan | A | V6 已有中心+8 外圈确定性覆盖、FOUND 退出 UNKNOWN、16 源提前停止。 |
| Way3 near-field | C | Way3 85m orbit 原本不存在于 V6 固定 500/950m ring；N1 条件加入。 |
| Way3 large intersection angle | B | V6 环候选已近似覆盖；N2 精确垂直点仅 17 次被选。 |
| Way3 homing | D | 强制顺序 homing 是 Way3 移动膨胀主因，不引入。 |
| Way3 replanning | B/D | V6 已在每次动作后全局重排；Way3 的阶段式 replanning 不是新增能力。 |

A=等价包含，B=部分包含，C=真正新增，D=不值得引入。

## 4. Ablation Definitions

所有版本继承 frozen V6 的 n=8 搜索、状态机、20m MEC 判据与 online router，只覆盖 supplement candidate ranking/generation。固定预测设置为 feasible polygon 内 12 个确定性样本、bearing error {-1,0,+1} degree、V6 ring 半径 {500,950}m、合法接收上限 995m、与旧测点最小间距 10m。

- M1: 候选集合完全不变，选择使 R_worst-after(S) 最小的点；R_worst-after 是样本及离散 bearing outcome 更新后 MEC 半径的最大值。它有意隔离纯 Minimax 信息准则，完全不看 route cost。
- M2: 候选集合完全不变，最小化 J_M2(S)=route_marginal(S)+5s+E[remaining time|S]+beta*R_worst-after(S)。beta 单位为 s/m，因此各项统一为秒。
- N1: 仅对 MEC>20m 且已有至少 2 次 direction 的困难源，在当前 MEC 中心周围增加 8 个均匀 85m near-field 点；仍由原 V6 objective 与全部原候选共同竞争，不强制选择。
- N2: 同一困难源门控下，在 MEC 中心沿最新观测点到 MEC 中心连线的法向两侧，按 500m/950m 生成 exact large-angle 候选；仍由 V6 objective 竞争。
- N3: N1 与 N2 候选并集。MN: N1 加 M2(beta=0.10)，仅在单模块完成后作为互补性验证。

M2 beta 使用固定 40-case pilot，不使用正式 200 局挑参：

| Pilot | Mean s | P95 | Max | Move m |
|---|---:|---:|---:|---:|
| v6 | 3459.41 | 4361.96 | 4424.82 | 13444.20 |
| m1 | 3777.26 | 4686.21 | 4943.53 | 15121.95 |
| m2_b0p01 | 3461.84 | 4248.01 | 4369.20 | 13442.81 |
| m2_b0p025 | 3470.09 | 4248.01 | 4369.20 | 13484.18 |
| m2_b0p05 | 3465.38 | 4248.01 | 4369.20 | 13466.15 |
| m2_b0p1 | 3441.14 | 4268.30 | 4369.20 | 13360.07 |
| m2_b0p25 | 3460.98 | 4268.30 | 4323.50 | 13482.01 |
| m2_b0p075 | 3463.51 | 4259.01 | 4369.20 | 13464.31 |
| m2_b0p15 | 3451.82 | 4268.30 | 4340.65 | 13397.00 |

beta=0.10 在该 pilot 上 mean 最低；0.075/0.15 是同一批 case 的局部细化。正式 200 局中 beta 不再调整。

## 5. Controlled Ablation Results

| Version | Clear | Mean s | Median | P95 | Max | Move m | Measure | Fail |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v6 | 100.0% | 3496.69 | 3534.23 | 4244.83 | 4817.50 | 13554.13 | 121.31 | 0 |
| m1 | 100.0% | 3812.46 | 3882.07 | 4789.43 | 5096.28 | 15198.80 | 119.00 | 0 |
| m2_b0p1 | 100.0% | 3478.23 | 3538.07 | 4239.97 | 4720.05 | 13469.58 | 121.05 | 0 |
| n1 | 100.0% | 3417.62 | 3457.64 | 4180.65 | 4977.66 | 13165.40 | 121.08 | 0 |
| n2 | 100.0% | 3497.40 | 3534.23 | 4244.83 | 4817.50 | 13557.64 | 121.32 | 0 |
| n3 | 100.0% | 3419.04 | 3457.64 | 4180.65 | 4977.66 | 13173.08 | 121.06 | 0 |
| mn | 100.0% | 3417.55 | 3479.54 | 4241.60 | 4768.18 | 13169.28 | 120.94 | 0 |

分组结果：

| Version | Group | Mean s | P95 | Max | Move m |
|---|---|---:|---:|---:|---:|
| v6 | random | 3674.42 | 4238.90 | 4720.05 | 14427.11 |
| v6 | min_reff | 3764.08 | 4365.77 | 4817.50 | 14595.68 |
| v6 | collinear | 2873.83 | 3315.17 | 3668.78 | 10766.64 |
| m1 | random | 4013.62 | 4785.25 | 5096.28 | 16205.21 |
| m1 | min_reff | 4136.18 | 4872.06 | 5005.79 | 16522.82 |
| m1 | collinear | 3086.41 | 3701.20 | 3969.33 | 11861.95 |
| m2_b0p1 | random | 3654.02 | 4235.89 | 4720.05 | 14318.09 |
| m2_b0p1 | min_reff | 3778.85 | 4391.72 | 4657.31 | 14707.74 |
| m2_b0p1 | collinear | 2826.02 | 3157.92 | 3320.45 | 10534.41 |
| n1 | random | 3559.37 | 4126.10 | 4472.12 | 13851.79 |
| n1 | min_reff | 3732.42 | 4351.71 | 4977.66 | 14447.62 |
| n1 | collinear | 2819.32 | 3252.89 | 3621.55 | 10510.41 |
| n2 | random | 3674.47 | 4238.90 | 4720.05 | 14427.49 |
| n2 | min_reff | 3765.77 | 4366.23 | 4817.50 | 14603.54 |
| n2 | collinear | 2874.91 | 3315.17 | 3668.78 | 10772.06 |
| n3 | random | 3561.53 | 4126.10 | 4472.12 | 13863.80 |
| n3 | min_reff | 3733.54 | 4352.61 | 4977.66 | 14453.22 |
| n3 | collinear | 2819.54 | 3252.89 | 3621.55 | 10511.50 |
| mn | random | 3557.37 | 4196.10 | 4768.18 | 13835.60 |
| mn | min_reff | 3746.63 | 4318.04 | 4647.90 | 14554.83 |
| mn | collinear | 2808.84 | 3221.94 | 3655.37 | 10451.08 |

同 seed paired comparison，相对 V6 的 delta 为 target - V6：

| Target | Win | Mean Δs | Median | P95 Δ | Worst | Best | >300s |
|---|---:|---:|---:|---:|---:|---:|---:|
| m1 | 12.0% | 315.77 | 309.40 | 763.22 | 969.32 | -502.81 | 103 |
| m2_b0p1 | 37.0% | -18.46 | 0.00 | 187.79 | 737.53 | -714.17 | 6 |
| n1 | 74.0% | -79.07 | -67.44 | 145.50 | 419.76 | -764.10 | 3 |
| n2 | 4.0% | 0.72 | 0.00 | 2.48 | 196.24 | -186.07 | 0 |
| n3 | 73.0% | -77.65 | -67.44 | 145.50 | 419.76 | -764.10 | 3 |
| mn | 72.5% | -79.14 | -71.17 | 180.29 | 737.09 | -906.56 | 6 |

分 random/min_reff/collinear 的 paired 结果：

| Target | Group | Win | Mean delta s | P95 delta | Worst | >300s |
|---|---|---:|---:|---:|---:|---:|
| m1 | random | 10.0% | 339.20 | 733.27 | 969.32 | 58 |
| m1 | min_reff | 6.0% | 372.11 | 767.72 | 883.26 | 29 |
| m1 | collinear | 22.0% | 212.58 | 599.19 | 907.25 | 16 |
| m2_b0p1 | random | 35.0% | -20.40 | 176.87 | 329.81 | 2 |
| m2_b0p1 | min_reff | 38.0% | 14.77 | 296.79 | 737.53 | 3 |
| m2_b0p1 | collinear | 40.0% | -47.81 | 68.27 | 320.00 | 1 |
| n1 | random | 82.0% | -115.05 | 137.55 | 419.76 | 2 |
| n1 | min_reff | 62.0% | -31.65 | 150.76 | 182.65 | 0 |
| n1 | collinear | 70.0% | -54.51 | 125.81 | 321.80 | 1 |
| n2 | random | 7.0% | 0.05 | 5.83 | 196.24 | 0 |
| n2 | min_reff | 0.0% | 1.69 | 2.21 | 71.32 | 0 |
| n2 | collinear | 2.0% | 1.08 | 0.00 | 43.25 | 0 |
| n3 | random | 81.0% | -112.89 | 137.55 | 419.76 | 2 |
| n3 | min_reff | 62.0% | -30.53 | 150.76 | 182.65 | 0 |
| n3 | collinear | 68.0% | -54.29 | 125.81 | 321.80 | 1 |
| mn | random | 75.0% | -117.05 | 162.40 | 484.08 | 2 |
| mn | min_reff | 68.0% | -17.45 | 276.75 | 737.09 | 3 |
| mn | collinear | 72.0% | -64.99 | 128.60 | 317.71 | 1 |

### M1 / M2

M1 在 1927 次实际补测中改变 V6 选择，占 70.9%。它平均少 2.31 次 measure/case、少 1.61 次 switch/case，仅省 13.16s 信息时间，却多走 1,644.66m（328.93s），净慢 315.77s。Way1 的信息优势不能通过纯 Minimax 原样迁移。

M2 只在 128 次补测改变选择，占 3.8%。总体平均快 18.46s，但 min_reff 平均反而慢 14.77s，且最坏 paired regression 737.53s。因此 M2 不通过稳定性门槛。

### N1 / N2 / N3

N1 的 85m near-field 候选实际被选择 884 次。它不明显减少首次补测后过线率（34.90% -> 34.94%），但把 >=3 次补测源占比从 7.42% 降到 5.53%，FOUND 后移动从 662.44m/source 降到 631.79m/source。总收益 98% 来自移动。

N2 的 exact perpendicular 候选只被选择 17 次，平均慢 0.72s，可视为被 V6 原候选集合覆盖。N3 中 large-angle 只被选择 4 次，且比 N1 平均慢 1.42s。

### MN Complementarity

| Target | Win vs N1 | Mean Δs | P95 Δ | Worst | >300s |
|---|---:|---:|---:|---:|---:|
| mn | 37.5% | -0.07 | 273.38 | 680.85 | 8 |

MN 相对 N1 平均仅快 0.07s，属于数值上的平局；其 P95 从 4180.65s 恶化到 4241.60s，paired worst 为 +680.85s，8 局回退超过 300s。Minimax 不为 N1 提供可接受的互补收益。

## 6. Time And Source Decomposition

Episode-level 完整指标与策略计算开销：

| Version | Mean avg/source s | Pooled avg/source s | Std s | Move time s | Measure time s | Switch time s | Clear time s | Policy CPU s | CPU P95 s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v6 | 278.69 | 274.47 | 505.40 | 2710.83 | 606.58 | 115.58 | 63.70 | 1.466 | 2.726 |
| m1 | 303.26 | 299.25 | 588.89 | 3039.76 | 595.02 | 113.97 | 63.70 | 1.799 | 2.973 |
| m2_b0p1 | 277.23 | 273.02 | 521.01 | 2693.92 | 605.25 | 115.36 | 63.70 | 1.992 | 3.366 |
| n1 | 272.21 | 268.26 | 502.63 | 2633.08 | 605.40 | 115.44 | 63.70 | 1.928 | 3.565 |
| n2 | 278.73 | 274.52 | 507.34 | 2711.53 | 606.60 | 115.58 | 63.70 | 1.811 | 3.171 |
| n3 | 272.32 | 268.37 | 503.92 | 2634.62 | 605.30 | 115.42 | 63.70 | 2.052 | 3.615 |
| mn | 272.38 | 268.25 | 512.22 | 2633.86 | 604.73 | 115.27 | 63.70 | 2.242 | 3.573 |

Phase-level：

| Version | Phase | Move s | Measure s | Switch s | Clear s | Total s |
|---|---|---:|---:|---:|---:|---:|
| v6 | search | 931.02 | 496.15 | 95.92 | 0.00 | 1523.09 |
| v6 | found | 1094.01 | 110.42 | 19.66 | 0.00 | 1224.10 |
| v6 | clear | 685.80 | 0.00 | 0.00 | 63.70 | 749.50 |
| m1 | search | 932.01 | 492.73 | 95.23 | 0.00 | 1519.97 |
| m1 | found | 1349.28 | 102.30 | 18.75 | 0.00 | 1470.33 |
| m1 | clear | 758.46 | 0.00 | 0.00 | 63.70 | 822.16 |
| m2_b0p1 | search | 920.39 | 495.23 | 95.73 | 0.00 | 1511.34 |
| m2_b0p1 | found | 1099.48 | 110.03 | 19.63 | 0.00 | 1229.14 |
| m2_b0p1 | clear | 674.05 | 0.00 | 0.00 | 63.70 | 737.75 |
| n1 | search | 930.02 | 496.52 | 95.98 | 0.00 | 1522.53 |
| n1 | found | 1094.01 | 108.88 | 19.46 | 0.00 | 1222.34 |
| n1 | clear | 609.05 | 0.00 | 0.00 | 63.70 | 672.75 |
| n2 | search | 928.37 | 496.15 | 95.92 | 0.00 | 1520.44 |
| n2 | found | 1097.22 | 110.45 | 19.66 | 0.00 | 1227.32 |
| n2 | clear | 685.94 | 0.00 | 0.00 | 63.70 | 749.64 |
| n3 | search | 931.06 | 496.52 | 95.98 | 0.00 | 1523.56 |
| n3 | found | 1093.03 | 108.78 | 19.44 | 0.00 | 1221.24 |
| n3 | clear | 610.54 | 0.00 | 0.00 | 63.70 | 674.24 |
| mn | search | 937.89 | 496.43 | 95.95 | 0.00 | 1530.27 |
| mn | found | 1094.67 | 108.30 | 19.32 | 0.00 | 1222.29 |
| mn | clear | 601.30 | 0.00 | 0.00 | 63.70 | 665.00 |

FOUND -> CLEAR source-level：

| Version | Elapsed s/source | Move m/source | Dedicated move m/source | Supp/source | First clearable | >=2 | >=3 | >=4 | 20-30m chase |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v6 | 1269.67 | 662.44 | 393.29 | 1.734 | 34.9% | 65.1% | 7.4% | 0.8% | 648 |
| m1 | 1528.62 | 796.87 | 499.20 | 1.606 | 42.8% | 57.2% | 3.4% | 0.0% | 728 |
| m2_b0p1 | 1304.64 | 660.17 | 395.63 | 1.727 | 35.5% | 64.5% | 7.4% | 0.8% | 683 |
| n1 | 1231.27 | 631.79 | 392.76 | 1.709 | 34.9% | 65.0% | 5.5% | 0.4% | 606 |
| n2 | 1266.18 | 663.60 | 394.39 | 1.734 | 34.9% | 65.1% | 7.4% | 0.8% | 650 |
| n3 | 1231.82 | 631.83 | 392.21 | 1.708 | 35.0% | 65.0% | 5.4% | 0.4% | 602 |
| mn | 1268.29 | 630.61 | 394.62 | 1.700 | 35.6% | 64.4% | 5.3% | 0.3% | 636 |

首次 supplement 后 MEC 分布（分母为发生过 supplement 的 source）：

| Version | <=20m/near | 20-25m | 25-30m | 30-50m | >50m | Unknown |
|---|---:|---:|---:|---:|---:|---:|
| v6 | 34.9% | 14.9% | 10.1% | 22.9% | 17.2% | 0.0% |
| m1 | 42.8% | 20.4% | 11.2% | 16.6% | 9.1% | 0.0% |
| m2_b0p1 | 35.5% | 16.4% | 10.9% | 22.9% | 14.3% | 0.0% |
| n1 | 34.9% | 14.6% | 10.1% | 22.8% | 17.5% | 0.0% |
| n2 | 34.9% | 14.9% | 10.1% | 22.9% | 17.2% | 0.0% |
| n3 | 35.0% | 14.7% | 10.0% | 22.8% | 17.5% | 0.0% |
| mn | 35.6% | 16.5% | 10.6% | 22.9% | 14.5% | 0.0% |

N1 的平均收益并非来自首次补测更容易直接过线，而是减少了多次补测和最终 clear 路段的空间错位。其 CLEAR phase 平均从 749.50s 降到 672.75s，是 79.07s 总收益中的 76.75s。

## 7. Typical Cases

| Case | Group | Seed | Base | Target | Total Δs | SEARCH Δ | FOUND Δ | CLEAR Δ | Supp Δ |
|---|---|---:|---|---|---:|---:|---:|---:|---:|
| v6_big_win_v4 | random | 72 | v4 | v6 | -814.43 | 29.17 | -743.00 | -100.61 | -4 |
| v6_big_loss_v4 | random | 70 | v4 | v6 | 553.01 | 617.26 | -354.94 | 290.70 | 3 |
| m2_best_improvement | random | 81 | v6 | m2_b0p1 | -714.17 | -286.86 | -76.11 | -351.19 | -2 |
| n1_best_improvement | random | 90 | v6 | n1 | -764.10 | -56.68 | -664.81 | -42.62 | -5 |
| n1_worst_regression | random | 95 | v6 | n1 | 419.76 | 534.44 | 83.45 | -198.12 | 3 |

- [V6 大胜 V4: random seed 72](figures/v6_big_win_v4_random_72.svg)：V6 少走约 3,967m、少 4 次补测；FOUND 阶段节省 743.00s。
- [V6 大输 V4: random seed 70](figures/v6_big_loss_v4_random_70.svg)：SEARCH 多 617.26s，尽管 FOUND 少 354.94s，最终仍慢 553.01s；这是典型等待/排序回退。
- [M2 最佳改善: random seed 81](figures/m2_best_improvement_random_81.svg)：少走约 3,346m、少 2 次补测，三个阶段都改善；但该收益不是普遍现象。
- [N1 最佳改善: random seed 90](figures/n1_best_improvement_random_90.svg)：少走约 3,581m、少 5 次补测，FOUND 阶段节省 664.81s。
- [N1 最坏回退: random seed 95](figures/n1_worst_regression_random_95.svg)：FOUND 后累计移动其实少 658m，但 SEARCH 路线多 534.44s，说明新增近场任务改变了全局共存顺序，造成另一种 route coupling。

完整事件见 typical_timelines.csv；每个动作保留时间、位置、频道、SEARCH/FIRST_FOUND/SUPPLEMENT/CLEAR 和移动距离。

## 8. Final Recommendation

1. 保留 frozen V6 作为当前正式候选，不覆盖、不改名。
2. 将 N1 保留为 V6.x experimental：它在均值、P95、移动和 74% paired seeds 上显著优于 V6，但 3 个 >300s 回退和更高聚合 max 尚未满足替换门槛。
3. 淘汰 M1、M2、N2、N3、MN；不形成 V7。
4. 当前剩余主要问题不是缺少 Minimax 或大交角候选，而是候选任务加入后对 SEARCH/CLEAR 全局顺序的耦合与 one-step future-cost 误差。这个结论来自分解与路线图，不是新的策略设计。

## 9. Reusable Pipeline

- run_stage2_eval.py：统一 case/seeds、episode/phase/source/paired 输出及 V6 重放校验。
- analyze_stage2.py：回退分类、future SEARCH audit、source 极值、典型 seed 选择。
- plot_stage2_typical.py：只对典型 seed 事后读取 ground truth 生成路线图和 timeline。
- 原始与派生 CSV 均位于本目录；所有后续 V6.x 候选可复用相同口径。
