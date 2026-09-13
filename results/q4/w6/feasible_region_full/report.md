# Q4 W6 persistent-bearing certificate: full offline validation

本报告对应新的 W6 实验实现：在冻结 W5/25G-ASR 的搜索骨架、W2 持久化生命周期、W3 自适应重捕获、W4-A 动态任务池和 open-route 重规划之上，仅加入方向观测形成的保守持久化可行域。当外包区域 MEC 半径不超过 20 m 时，才插入 guaranteed-clear task；失败后证书失效并回到 W5 的重捕获路径。

## 数据与隔离

- 环境：本地 `offline_sim/practice`，未调用官方接口。
- 与既有 W5 完全相同的 200-case 矩阵：random seeds 0:100、min_reff seeds 10000:10050、collinear seeds 10000:10050。
- W6 policy 不读取 `Case`、`Engine`、source 真值、有效半径或方向真值。
- 本目录是新输出；未覆盖旧的 W6-A 历史结果或 W5 CSV。
- API 返回的示向度经过 0.01° 四舍五入，因此保守证书采用已有接口总误差界 1.005°（物理 ±1° 加量化余量），不是经验调参。

## Full-clear gate

| Metric | W5 | W6 persistent bearing |
|---|---:|---:|
| Episodes | 200 | 200 |
| Full clear | 200/200 | 200/200 |
| Clear failures | 0 | 0 |
| Unresolved at exit | 0 | 0 |
| Guaranteed-clear failures | n/a | 0 |

## Overall comparison

| Metric | W5 | W6 | W6 minus W5 |
|---|---:|---:|---:|
| Mean total time (s) | 7491.811 | 7356.162 | -135.649 |
| P95 total time (s) | 9250.087 | 9047.509 | -202.578 |
| Max total time (s) | 11528.353 | 11018.969 | -509.384 |
| Mean movement (m) | 26187.855 | 25616.812 | -571.043 |
| Mean measures | 370.440 | 366.670 | -3.770 |
| Mean reacquisition attempts | 99.745 | 95.975 | -3.770 |
| P95 reacquisition attempts | 184.000 | 195.000 | +11.000 |
| Max reacquisition attempts | 531.000 | 254.000 | -277.000 |
| Mean guaranteed-clear attempts | n/a | 11.745 | n/a |

## Interpretation

W6 satisfies the correctness gate and improves mean, P95 and maximum total time, as well as average movement. Its maximum per-case reacquisition count is substantially lower, showing relief of the most extreme stale-state tail. The P95 of reacquisition-attempt count itself is higher, so the improvement is not uniform across every tail statistic; this metric must remain visible in any final decision.

The result supports W6 as a serious long-tail candidate, but does not justify claiming that every tail measure improves. Any replacement of W5 should use the complete paired comparison, including per-case regressions, not only the aggregate means.

