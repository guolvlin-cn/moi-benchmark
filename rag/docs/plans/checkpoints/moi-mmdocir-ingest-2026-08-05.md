# MMDocIR MOI 向量化入库暂停断点（2026-08-05）

## 2026-08-06 13:01 切回 TaaS（当前活动任务）

- 本地 BGE-M3 入库已在完整提交边界 `145801/311644` 安全停止；当时 MatrixOne 行数同为 145,801。
- 用户已将服务与出口 IP 加入 TaaS 白名单。切换前使用 `--noproxy '*'` 直连 `https://api-taas.moi.matrixorigin.cn/v1/embeddings` 做 smoke test，返回 HTTP 200、模型 `bge-m3`、1024 维。
- 当前使用原冻结 TaaS 配置：`/Users/muuushroom/gitrepos/moi-benchmark/rag/runs/stage1/moi-rag-native/20260805-204309.849/configs/mmdocir.json`；批量上限 1024、256 KiB 文本保护、最多 4 次重试，TaaS 传输不读取系统代理。
- 当前活动子运行：`/Users/muuushroom/gitrepos/moi-benchmark/rag/runs/stage1/moi-rag-native/20260805-204309.849/datasets/mmdocir/index-run/20260806-130104.399`，从 `20260806-121810.441/ingest-progress.json` 恢复。
- 切换后前三个批次均成功，未出现 HTTP 405；本地 `127.0.0.1:8081` BGE 服务已经停止以释放内存。

## 2026-08-06 本地吞吐优化（已结束，保留记录）

- 本机为 16 GB 统一内存；为兼顾桌面流畅度，没有继续上探容易造成 MPS 内存/调度压力的 batch 24/32。
- 本地 BGE-M3 已调整为 `BGE_BATCH_SIZE=16`、`BGE_MAX_BATCH=128`、`BGE_MAX_BATCH_BYTES=524288`；仍使用 MPS、FP32 和本地离线权重。
- MatrixFlow 入库配置已调整为 `embedding_batch_size=128`，并移除了非 TaaS 端点强制回落到 64 的旧限制；256 KiB 请求文本保护仍然保留。
- 实测真实入库连续 30 秒吞吐约 `25.6 entries/s`；优化前本轮长期平均约 `14 entries/s`，短测 batch 16 + request 64 为 `20.5 entries/s`。
- BGE 服务与 Go 入库进程以 `nice=5` 的较低后台优先级运行，为浏览器、终端和编辑器保留前台调度空间。
- 当前活动子运行：`/Users/muuushroom/gitrepos/moi-benchmark/rag/runs/stage1/moi-rag-native/20260805-204309.849/datasets/mmdocir/index-run/20260806-121810.441`，从上一子运行的 `batch_end=115977` 恢复。
- 本次恢复继续使用逐批提交和 `--resume-progress`，不会重新计算或覆盖此前已完成向量；最新状态应以该子目录的 `ingest-progress.json` 和 MatrixOne 实际行数为准。

## 2026-08-06 本地 BGE-M3 续跑

- 已找到并使用现有完整权重：`/Users/muuushroom/Documents/Codex/2026-08-05/new-chat/gitrepos/embedding/models/bge-m3/pytorch_model.bin`（约 2.2 GB）。
- 本地服务：`http://127.0.0.1:8081/v1`，`device=mps`、`local_files_only=true`、1024 维；embedding 不再请求 TaaS。
- 兼容性校验：对数据库已有文本重新执行本地 embedding，与旧 TaaS `bge-m3` 向量的 cosine 为 `0.9999993657`，可复用既有 60,617 行。
- 新配置：`/Users/muuushroom/gitrepos/moi-benchmark/rag/prototypes/local-matrixflow-rag/config.mmdocir.local-bge-m3.json`，保留原断点的 `chunk_size=512`、`chunk_overlap=50`、`section_size=5`。
- 续跑子目录：`/Users/muuushroom/gitrepos/moi-benchmark/rag/runs/stage1/moi-rag-native/20260805-204309.849/datasets/mmdocir/index-run/20260806-110604.215`。
- 新增 `--resume-progress`：校验 parsed/expanded/total 数量和 MatrixOne 行数后，从 `batch_end=60617` 后继续；没有使用 `--force`。
- 本轮只执行 MMDocIR embedding + MatrixOne 写入；DocBench、MMDocRAG 和 QA 评估仍未启动。实时进度以新子目录的 `ingest-progress.json` 与数据库行数为准。

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
