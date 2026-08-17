# Astra Agent 产品评测

状态：v0.5 总体方案草稿待审阅；Terminal-Bench 2.1 与 Toolathlon 已形成三产品常规任务 baseline 结果。本目录同时保存运行配置、进度、分析材料和可审计的轨迹记录。

当前材料：

- `../docs/progress/2026-08-14-MOI-Benchmark评测结果汇总.md`：Astra 总体评测进度；
- `plans/drafts/v0.5.md`：当前总体执行方案草稿，并记录 SWE-bench-Live Python `verified` 为第二数据集方向（执行协议待定）；
- `research`：当前技术证据；
- `research/archive/`：已过时但需追溯的研究；
- `datasets/manifest.yaml`：候选数据集及冻结门槛；
- `systems/manifest.yaml`：本地参评系统快照；
- `runners/`：Astra、Hermes、PI 的运行器、配置和辅助脚本；
- `runs/README.md`：运行批次、证据边界和最小运行记录字段；
- `runs/trajectory-index/`：从三批本地运行目录生成的 CSV/JSON 轨迹元数据索引，以及可重复生成索引的脚本。

## 当前公开基准结果

当前结果统一按常规任务完成层面比较，不将不同数据集或不同产品的指标合并为单一总分。通过率以各数据集 verifier/evaluator 为准；时间、工具调用和 token 作为独立资源指标。Terminal-Bench 不同产品的内部请求边界和 token 计量方式不完全同构，token 结果仅用于描述观测资源量级。

| 数据集             | 当前比较范围                                        |            Astra |           Hermes |               PI |
| ------------------ | --------------------------------------------------- | ---------------: | ---------------: | ---------------: |
| Terminal-Bench 2.1 | 83 个严格三方配对任务                               |   43/83（51.8%） |   47/83（56.6%） |   52/83（62.7%） |
| Terminal-Bench 2.1 | 各产品最新验证任务行                                |   44/86（51.2%） |   50/88（56.8%） |   52/84（61.9%） |
| Toolathlon         | 108 个有效任务槽；PI 另有 4 个无明确 evaluator 判定 | 61/108（56.48%） | 72/108（66.67%） | 77/108（71.30%） |

详细结果：

- [Terminal-Bench 2.1 三产品对比](reports/TerminalBench2.1-analysis/astra-hermes-pi-latest-83-task-comparison.md)
- [Terminal-Bench 2.1 指标 CSV](reports/TerminalBench2.1-analysis/terminalbench2.1-astra-hermes-pi-product-metrics.csv)
- [Toolathlon 三产品对比](reports/Toolathlon-analysis/astra-hermes-pi-toolathlon-108-task-comparison.md)
- [Toolathlon 三产品逐任务 CSV](reports/Toolathlon-analysis/astra-hermes-pi-toolathlon-108-task-results.csv)
- [整体评测结果汇总](../docs/progress/2026-08-14-MOI-Benchmark评测结果汇总.md)
