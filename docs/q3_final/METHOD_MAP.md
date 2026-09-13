# Q3 Method Map

| Internal version | Paper role | Core idea | Final? |
|---|---|---|---|
| V0–V3 | Early staged baselines | 分阶段搜索/定位/清除与早期 route 优化 | No |
| V4 | Rolling joint scheduling | SEARCH/MEASURE/CLEAR 联合滚动调度 | Core |
| V5-A/B/final | Local-information experiment | 用局部定位预测改变补测任务生成 | No |
| V6 | RARC | route-aware rolling coordination | **YES** |
| V6-L2 | Deep lookahead ablation | 两步未来展开 | No |
| ring-count n=6..12 | Parameter selection | 在 V6 下选择外围搜索点数 n=8 | Selection |
| ring-only | Negative ablation | 删除 mandatory center SEARCH | No |
| historical no_signal | Optional negative ablation | 使用历史 API-visible no_signal 信息 | No |
| SEARCH-backbone + bundle | Negative ablation | 固定 SEARCH 主干并插入 MEASURE/CLEAR bundle | No |
| Minimax / N1/N2/N3/MN | Exploratory ablations | 其他局部排序或目标变体 | No |

论文主叙事按“建模思想 → 机制 → 消融验证”，而不是按内部版本号平铺。V0–V3 仅作为 Early Baselines / Development Baselines 归档。
