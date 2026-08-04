# Astra / Hermes 运行记录

本目录已保存三批运行目录中的轨迹记录：

```text
runs/astra-c0-all-jobs/
runs/astra-c0-rerun-from-scratch-33/
runs/hermes-c0-all-jobs/
```

每个目录保留对应的任务配置、运行结果、日志和轨迹文件；`trajectory-index/` 提供汇总索引，避免重复复制记录。

## 当前运行批次

| 运行批次 | 数据/条件 | 目的 | 当前状态 | 详细记录 |
| --- | --- | --- | --- | --- |
| Astra initial batch | Terminal-Bench 2.1 | Astra 首轮运行记录 | 89 个 task attempt | [轨迹索引](trajectory-index/astra-c0-all-jobs.csv) |
| Astra rerun-33 | Terminal-Bench 2.1，冻结输入 | Astra 重跑记录 | 32 个 task attempt | [冻结批次记录](2026-07-31-terminal-bench-c0-rerun-33.md) |
| Hermes batch | Terminal-Bench 2.1 | Hermes 对照运行记录 | 106 个 task attempt | [轨迹索引](trajectory-index/hermes-c0-all-jobs.csv) |

## 每次运行至少应保存的记录

```text
run_id / task_id / attempt_id
dataset_version / task_snapshot / condition
system_commit / model_id / runner_version
execution_budget / permissions / environment_image
session_id / controller_events / product_terminal_status
verifier_result / trajectory_status / artifact_manifest
failure_taxonomy
```

运行记录应把 Verifier 结果、产品终态、严格端到端结果和轨迹/审计完整性分开保存。

## 记录边界

- 运行记录：`runs/astra-c0-all-jobs/`、`runs/astra-c0-rerun-from-scratch-33/` 和 `runs/hermes-c0-all-jobs/`。
- 汇总索引：`runs/trajectory-index/` 下的三个 CSV 和一个 JSON 文件。
- 凭据、访问 token、完整 prompt、原始模型响应和未脱敏工作区不得进入仓库。
