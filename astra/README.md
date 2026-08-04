# Astra Agent 产品评测计划

状态：v0.5 总体方案草稿待审阅；当前 Terminal-Bench 数据仅为其中一条轨道的工程预运行证据。本目录同时保存运行配置、进度、分析材料和可审计的轨迹记录。

当前材料：

- `progress/2026-07-31-benchmark-progress.md`：Astra 总体评测进度，以及 Terminal-Bench 2.1 阶段性工程运行结果；
- `plans/drafts/v0.5.md`：当前总体执行方案草稿，并记录 SWE-bench-Live Python `verified` 为第二数据集方向（执行协议待定）；
- `plans/drafts/v0.4.md`：上一版执行方案草稿，保留少量 Terminal-Bench/SWE-bench/τ³ 混合 Pilot 设计供追溯；
- `plans/drafts/v0.3.md`：上一版方案草稿，保留六个手工长任务族的历史设计供追溯；
- `plans/drafts/v0.2.md`：更早版本方案草稿，保留追溯；
- `research/technical-differences-and-benchmark-design.md`：当前技术证据；
- `research/astra-git4data-architecture-and-boundaries.md`：Astra 与 Git4Data 的架构关系、状态和回滚边界；
- `research/deepplanning-and-openviking-usability.md`：DeepPlanning 数据与 OpenViking 的适用性审查；
- `research/public-benchmark-usability-audit.md`：六个公共基准的版本、评分器、效度与准入决策；
- `research/terminal-bench-2.1-task-survey.md`：Terminal-Bench 2.1 全部 89 题的类别、难度、时间和长度口径；
- `research/swe-bench-live-verified-dataset-analysis.md`：已选第二数据集的冻结工件、执行式 Oracle 与接入门禁；
- `research/gdpval-dataset-analysis.md`：GDPval 的专业产物覆盖与当前评分、许可和复现阻塞；
- `research/hermes-goose-competitor-and-adapter-audit.md`：Hermes/Goose 状态能力、Runner 公平性与冻结风险；
- `research/archive/`：已过时但需追溯的研究；
- `datasets/manifest.yaml`：候选数据集及冻结门槛；
- `systems/manifest.yaml`：本地参评系统快照，不代表正式冻结版本；
- `runners/`：Astra、Hermes 的运行器、配置和辅助脚本；
- `runs/README.md`：运行批次、证据边界和最小运行记录字段；
- `runs/trajectory-index/`：从三批本地运行目录生成的 CSV/JSON 轨迹元数据索引，以及可重复生成索引的脚本。

## 运行记录范围

本次整理已将以下三批运行记录复制到本目录：

```text
runs/astra-c0-all-jobs/
runs/astra-c0-rerun-from-scratch-33/
runs/hermes-c0-all-jobs/
```

每批目录保留对应的任务运行文件；`runs/trajectory-index/` 额外提供用于定位和审计的 CSV/JSON 索引。对应索引如下：

- [Astra initial batch](runs/trajectory-index/astra-c0-all-jobs.csv)：89 个 task attempt；
- [Astra rerun-33](runs/trajectory-index/astra-c0-rerun-from-scratch-33.csv)：32 个 task attempt；
- [Hermes batch](runs/trajectory-index/hermes-c0-all-jobs.csv)：106 个 task attempt；
- [合并索引](runs/trajectory-index/trajectory-index.json)：三批共 227 条记录。

需要重新生成索引时，在仓库根目录执行：

```bash
python3 astra/runs/trajectory-index/build_index.py
```

索引字段和运行记录要求见 [`runs/README.md`](runs/README.md) 与 [`runs/trajectory-index/README.md`](runs/trajectory-index/README.md)。

后续资产必须保存在本目录下：`plans/`、`research/`、`benchmark/`、`datasets/`、`systems/`、`runs/`、`reports/`、`decisions/`、`progress/`。

方案批准前不创建正式排名或发布结论。
