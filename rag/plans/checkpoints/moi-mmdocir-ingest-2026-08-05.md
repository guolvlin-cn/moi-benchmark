# MMDocIR MOI 向量化入库暂停断点（2026-08-05）

## 当前状态

- 任务：仅 MMDocIR 全量向量化入库；DocBench、MMDocRAG 没有启动。
- 主运行目录：`/Users/muuushroom/gitrepos/moi-benchmark/rag/runs/stage1/moi-rag-native/20260805-204309.849`
- 入库子运行目录：`/Users/muuushroom/gitrepos/moi-benchmark/rag/runs/stage1/moi-rag-native/20260805-204309.849/datasets/mmdocir/index-run/20260805-204316.716`
- 状态：用户主动暂停；所有 benchmark/Go 入库进程已停止。
- 原始 MOI-ready 输入：`/Users/muuushroom/gitrepos/moi-benchmark/rag/outputs/parsed-documents/moi-ready-v1/datasets/mmdocir/moi-documents.jsonl`
- 解析输入规模：205,978 个 parsed blocks，经 MatrixFlow split + multi-level 后为 311,644 个可索引条目。

## 已完成进度

- Embedding 模型：TaaS `bge-m3`，1024 维；TaaS 走直连，不经过 `127.0.0.1:6478` 代理。
- 请求策略：目标批量 1024，实际仍受单请求 256 KiB 输入上限约束；响应上限 64 MiB。
- 已生成并成功写入 MatrixOne：60,617 / 311,644 条；剩余 251,027 条。
- 进度文件：`.../20260805-204316.716/ingest-progress.json`，当前 `stage=writing`、`batch_end=60617`。
- 数据库：`moi_stage1_mmdocir.embedding_results` 当前行数为 60,617。
- 本轮使用 `--force`，因此之前失败轮遗留的 45,000 行已被清理后重新开始；当前表不是旧轮次与新轮次的混合。

## 尚未完成

- 尚未完成剩余 251,027 条 embedding 与写入。
- 尚未执行最终 `EnsureVectorTableForLocalRAG`；当前没有 IVFFLAT 向量索引，只有主键、全文及标量辅助索引。
- 尚未生成本轮 `ingest-state.json`，也没有开始 QA/benchmark 检索评估。

## 以后继续

继续前先读取本文件、运行目录中的 `ingest-progress.json` 和 MatrixOne 当前行数，确认数据库仍为 60,617 行且没有其他入库进程。不要同时启动第二个 MMDocIR 任务。当前实现会把每个已完成 batch 立即提交，但命令行尚未自动跳过已提交 batch；恢复时应先实现/使用 resume-batch 逻辑以免重复调用 TaaS，或明确接受从头重算。不要直接再次使用 `--force`，否则会清空这 60,617 行。

恢复完成后应验证：

1. `SELECT COUNT(*)` 为 311,644；
2. `SHOW INDEX` 中出现 embedding 列的 IVFFLAT 索引；
3. 子运行 `ingest-progress.json` 为 `stage=committed`，并存在 `ingest-state.json`；
4. 再开始 MMDocIR 检索评估，仍不启动 DocBench/MMDocRAG，除非另行授权。
