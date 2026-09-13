# 问题四 W5Pro 详细工程评估报告

## 结论

当前 W5Pro 已修复 18 个 search point 的探索回归，并完成 16/16 干扰源清除；但性能尚未通过 W5 基准。

| 指标 | W5 | W5Pro |
|---|---:|---:|
| 清除数量 | 16/16 | 16/16 |
| 清除比例 | 100% | 100% |
| search point | 8 | 8 |
| 定位清除总时间 | 5303.34 s | 5780.96 s |
| 平均定位清除时间 | 331.46 s/source | 361.31 s/source |
| 移动距离 | 19276.68 m | 24249.81 m |
| 测量次数 | 241 | 148 |
| 频道切换次数 | 163 | 111 |

W5Pro 少 93 次测量、少 52 次切频，但多移动 4973.13 m，最终慢 477.63 s（约 9.0%）。因此结论是“机制部分完成、性能阻塞”，不是 W5Pro 优于 W5 的证明。

## 指标口径与证据

被清除干扰源比例 = 被清除干扰源个数 / 干扰源总数。

平均定位清除时间 = 定位清除总时间 / 被清除干扰源个数。

总时间来自离线演练仿真的虚拟时间，包含移动、频道切换、测量、定位和清除。主要证据：

- 当前 W5Pro trace：`results/random2_current_authoritative/traces/w5pro_random_smooth_2.json`
- W5 配对 trace：`results/q4/w5pro_paired_7case_final/traces/w5_random_smooth_2.json`
- 路线诊断：`results/fixed_random2_hardpreempt/random2_route_diagnosis.md`
- 实现：`q4/w5pro_policy.py`、`q4/w5pro_scheduler.py`、`q4/w5pro_config.py`

## random/2 逐步回归

W5 的前段先走骨干搜索点，前 8 个 search index 为 `0, 1, 7, 24, 18, 6, 5, ...`，然后集中处理 reacquire/clear。

早期 W5Pro 曾走到 18 个 search point。根因是局部 refinement 与 SEARCH 同时竞争：局部任务改变位置和频道状态后，active-channel pruning 把部分骨干点判为无有效扫描频道，未完成工作在后段形成补偿性搜索。

当前修复保持 discovery 阶段全频道语义，前 8 点使用 EARLY 模式，达到 16 个已发现源后停止 backbone 扩张，并让 cleared/absent 频道退出重复扫描。当前 W5Pro 已回到 8 点，但任务顺序仍不同于 W5，剩余差距来自局部路径。

## 移动路径归因

| 任务族 | 次数 | selected-task 移动距离 |
|---|---:|---:|
| SEARCH | 8 | 4203.45 m |
| MEASURE | 22 | 12562.39 m |
| CLEAR | 13 | 3386.68 m |
| REACQUIRE | 30 | 3541.60 m |

最大跳转是 REACQUIRE channel 13 的 1891.91 m、MEASURE channel 4 的 1153.80 m、MEASURE channel 11 的 1076.18 m。当前应优先优化 refinement/reacquire 的空间组织，而不是继续删除搜索点。

## 十项 checklist 审计

### 1. Clear-Ready 硬抢占：已实现

可达 CLEAR 在普通 score 前检查；移动加切频时间低于阈值时硬抢占，directional source 提高优先级。random/2 实际触发 `w5pro_clear_ready_hard_preempt` 13 次。

### 2. Exploration 边际停止：已实现，行为覆盖仍需扩展

探索效率为 `(max(Δuncertainty, 0) + max(certificate_gain, 0)) / Δt`。低于 threshold 或 clear/localization 竞争价值时停止可选 backbone；hard-required 不被删除。单测覆盖高低两种情况。

### 3. Search 回归：部分通过

18 点回归已修复为 8 点；但总时间仍高于 W5，性能回归未通过。

### 4. NBV：统计链已修复

候选先经过非 backbone、information gain ≥ 0.20、移动时间不超过原任务 20% 的可执行性过滤，再进入 minimax。当前 random/2 为 `selected=0, effective=0`，没有不可执行候选污染 scheduler；这表示本案例没有可负担 NBV，不表示 NBV 已产生收益。

### 5. Intersection：虚假收益已消除

只有 `applied=true` 才计入有效统计和 score。当前 random/2 没有有效 intersection probe，不能将其计为性能贡献。

### 6. Route repair：日志语义已收紧，物理收益未证明

当前只在路线实际变化且 `repair_needed=true` 时计数；random/2 为 38 次，而不是旧的每次 route choice 都算 repair。future-cost 消融对物理耗时无影响，说明 route repair 尚未成为改变执行路径的独立规划器。

### 7. Tail fallback：预算机制已实现

当前配置为 `per_channel_budget=8`、`per_state_budget=3`。超过预算返回 `switch_strategy`，同一状态切换后停止重复 fallback。random/2 为 55 次，远低于旧版 2552 次，但仍需在 paired suite 检查长尾。

### 8. Early 20-channel scan：已改为早期 8 点、发现后剪枝

早期保持全频道发现语义，发现 16 个源后切换 MID/verification，cleared/absent 频道退出重复扫描。该项解释了 search point 从 18 降到 8，但不能单独证明总时间优于 W5。

### 9. 时间型目标：部分实现

当前任务 score 显式包含移动、测量、切频、future cost，并减去有界 information/certificate reward；收益项不能压过 CLEAR/SEARCH 硬优先级和移动成本。但 refinement 空间路径仍未通过性能验证。

### 10. 扩展测试门槛：已遵守

在 random/2 达到 `W5Pro <= W5` 前，没有运行 7-case paired 或 74-case Hard matrix。

## 消融实验

所有结果使用同一 random/2、同一离线 simulator/case generator 和 smooth error field。

| 配置 | 总时间 | 清除 | 结论 |
|---|---:|---:|---|
| 完整 W5Pro | 5780.96 s | 16/16 | 当前基线 |
| 关闭 task-pool | 5780.96 s | 16/16 | 无物理路径影响 |
| 关闭 future-cost | 5780.96 s | 16/16 | 主要为诊断/重排 |
| 关闭 spatial-stop | 6016.49 s | 16/16 | 变慢，应保留 |
| 关闭 wait-for-route | 6594.39 s | 16/16 | 变慢，应保留 |
| 仅 adaptive scan | 5769.52 s | 16/16 | 仍慢于 W5 |
| 仅 hypothesis | 6164.66 s | 16/16 | 退化到 13 点 |
| 近距离 refinement 惩罚 | 5801.81 s | 16/16 | 破坏定位顺序，已撤销 |
| 候选最大偏移 500 m | 7091.13 s | 16/16 | 删除必要候选，已撤销 |
| W5 open-route selector | 6092.11 s | 16/16 | 整体恶化，已撤销 |
| route-consequence selector | 7932.36 s | 16/16 | 整体恶化，已撤销 |

## 测试证据

当前覆盖 W2、W3、W4-A、scheduler、Clear-Ready、NBV/intersection/repair 统计和 tail fallback 的回归测试为 `36 passed`，`git diff --check` 通过。

这些测试证明接口契约和既有行为未被明显破坏，不等价于性能验收通过。

## 阻塞与下一步

## Local Task Bundle 诊断结果

已加入 cluster-first、区域驻留 hysteresis 和跨轮 bundle channel identity，并新增 `w5pro_local_bundle_decision` 事件。random/2 共记录 22 次簇决策，最多同时存在 4 个候选簇、选中簇最多包含 4 个任务。第一次选中 3 个频道的局部簇，但进入距离仍为 767.35 m、簇内服务跨度为 378.69 m；后续多次簇退化为单成员簇。持久化成员身份后的最新消融为 5759.50 s、24142.48 m，较 5780.96 s 基线节省 21.47 s，同时保持 8 个 search point 和 16/16 全清。

因此当前问题不是“完全没有空间簇”，而是簇的进入成本仍很高，且每轮重建任务池会使簇连续性丢失。简单扩大簇内 bonus 不足以解决问题；下一步应让簇级 route marginal time 和已进入区域的剩余服务价值直接参与选择，并保持跨轮的簇成员身份。

## Oracle 任务排序诊断

新增脚本 `scripts/w5pro_refinement_oracle.py` 对当前 trace 做了反事实分析：固定已经生成的 73 个 selected-task 点，只重排点的执行顺序，不重放 simulator，也不改变观测结果。当前 selected-task 路径为 23694.13 m；nearest-neighbor + 2-opt 反事实顺序为 13522.73 m，减少 10171.39 m，按 5 m/s 折算约 2034.28 s 的移动时间。

该结果不是可执行策略成绩，因为实际观测具有顺序依赖；但它强有力地表明，W5Pro 的主要问题是 state-aware task ordering / spatial continuity，而不是任务点本身全部不可避免地偏远。输出文件为 `results/random2_current_authoritative/refinement_oracle.json`。

## 总纲跟进：候选任务路线边际诊断

按照 W5Pro V3 总纲，新增 `w5pro_route_marginal_candidates` 事件。每次调度在执行前记录候选总数、前 8 个候选的任务类型/频道、候选点距当前位置、预计移动时间、切频时间和排序得分；该记录不参与排序，因此不会改变物理行为。它用于区分“候选点生成过远”和“候选点排序错误”两类问题。

新增诊断后的 `random/2` 复测结果为 5759.50 s、16/16 全清、8 个搜索点、约 24142.48 m 移动距离，共记录 52 次候选排序事件。首个局部决策中 3 个候选的移动时间为 153.47–186.78 s，实际选择最近的 ch15，说明该轮的长距离主要已经存在于候选任务池，而非简单的最近候选排序失效。该证据支持下一阶段继续做“簇级服务路线”而不是继续扩大 NBV/交点机制。

当前阻塞是 refinement/reacquire 的空间路径：W5Pro 比 W5 多移动约 4973 m，造成 477.63 s 时间差。已验证无效或会恶化的方向包括降低 age bonus、简单 detour penalty、删除早期 refinement、强行补回 SEARCH、缩小定位候选半径、直接替换 open-route 或 route-consequence selector。

本轮进一步尝试了簇内一步 continuation（以“当前任务到簇内最近下一个任务”的距离近似服务路线边际），但 random/2 从 5759.50 s 退化到 5801.81 s，已回滚，未进入生产路径。该结果说明单步几何前视不足以代表带观测顺序依赖的定位收益。

随后对候选生成进行了受控验证：将定位候选的移动惩罚从 `distance/5000` 提高到 `distance/1000`，总时间升至 5951.13 s，已回滚；加入满足几何可行性的当前位置候选后，总时间升至 7324.74 s，也已回滚。长跳审计显示多数严重跳转只有单一候选，因此简单排序惩罚或无条件近点候选都不是可靠修复。相关审计产物为 `results/random2_route_marginal_v2/long_jump_audit.json`。

下一步只接受同时满足以下条件的修改：保持 16/16 全清、不重新引入超过 8 个 search point、降低移动距离和总时间，并记录每个 refinement/reacquire 候选的 route marginal time、切频时间和定位收益。达到 `W5Pro <= 5303.34 s` 后才运行 7-case paired；7-case 全部通过后才运行 Hard matrix。

## 最终判定

| 验收项 | 判定 |
|---|---|
| 清除比例与平均时间计算 | 已通过 |
| Clear-Ready 硬抢占 | 已实现并有 trace 证据 |
| exploration 边际停止 | 已实现并有单测 |
| 18 点探索回归 | 已修复为 8 点 |
| NBV 虚假 selected/effective | 已修复 |
| intersection 虚假收益 | 已修复统计语义；当前无有效 probe |
| route repair 语义 | 已修复；物理收益未证明 |
| tail fallback 无限重复 | 已加入预算和策略切换 |
| W5Pro ≤ W5 | 未通过 |
| 7-case / Hard matrix | 未运行，符合门槛 |

综合结论：**W5Pro 的工程机制大部分已落地，但问题四性能尚未验收通过；本报告不能作为 W5Pro 优于 W5 的证明。**

## Pareto 候选生成更新

按照新总纲，新增 `localization_pareto_candidates()`，在每个频道的几何可行域内构造“移动距离—crossing quality”非支配候选。为防止候选池膨胀，生产规则仅在基础定位候选距离当前位置至少 700 m 时触发，最多保留 2 个替代点，且替代点必须至少近 100 m；原候选始终保留。

同一 `random/2` 复测中，受限 Pareto 版本总时间由 5759.50 s 降至 5621.44 s，保持 16/16 全清和 8 个搜索点。700 m 与 800 m 触发阈值结果一致，说明本轮收益来自候选自由度而非阈值微调。该版本仍比 W5 的 5303.34 s 慢 318.10 s，尚未达到 7-case/Hard 运行门槛。完整回归测试为 39 passed。
