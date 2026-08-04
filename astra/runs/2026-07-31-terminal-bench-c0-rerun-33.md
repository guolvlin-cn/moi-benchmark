# Terminal-Bench C0 rerun-33 运行记录

> 记录日期：2026-07-31 起；当前整理：2026-08-04  
> 状态：工程重跑记录；不等同于正式 Benchmark 结果

## 批次身份

| 字段 | 值 |
| --- | --- |
| 数据集 | Terminal-Bench 2.1 |
| 条件 | C0：生命周期包装、无故障动作（`noop`） |
| 批次 | 初始运行中需要从头重跑的 33-task cohort |
| Harbor | `0.20.0` |
| Model | `c5bde5de-9805-48d4-a016-1db6e6018fc4` |
| 并发 | `1` |
| Memory | `read_memory=false`，每个任务使用隔离身份 |
| Frozen input SHA-256 | `1163c6cbb154588e496f643426f746a8c2d58011067bd1532b4da6e36e86cbef` |
| 原始结果根目录 | `work/astra-c0-rerun-from-scratch-33/jobs/`（本地） |

## 执行约束

- 任务、镜像、权限、模型、预算、Runner 文件和 Astra Linux artifact 在运行前冻结。
- 每次只启动一个任务；Harbor 不自动重试。
- LLM fallback timeout 为 600 秒；单次 Astra invocation budget 为 900 秒。
- 第一次 stream transport retry 必须复用预登记的同一 session；后续 retry 需要满足剩余预算门槛。
- runner 记录 product identity、controller ledger、session、trajectory、cleanup 和 verifier 证据。
- timeout、cleanup、adapter、Verifier 和任务本身的失败必须分开归类。

## 运行记录结构

每个 task attempt 的最小证据集合为：

```text
config.json
result.json
agent/controller.jsonl
agent/product.identity.json
agent/product.cleanup.json
agent/astra-session.json
agent/trajectory-status.json
agent/astra-trajectory/manifest.json
verifier/reward.txt
verifier/ctrf.json（若生成）
```

这些文件仍保留在本地 raw artifact 目录；本文件只记录批次身份和可复现约束。

## 与当前分析的关系

后续汇总脚本将初始运行与本批次按 `task_id` 合并，选择最新 attempt，再纳入具有数字 Verifier reward 的任务。当前三处 raw run 的逐 attempt 轨迹元数据见 [trajectory-index](trajectory-index/README.md)。

当前批次用于工程恢复和数据链路验证。即使某个任务通过 Verifier，也不能据此宣称 lifecycle gate 或正式跨产品比较已经完成。
