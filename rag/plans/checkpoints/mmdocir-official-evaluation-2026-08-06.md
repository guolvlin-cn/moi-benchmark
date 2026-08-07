# MMDocIR 官方口径 MOI 检索评估断点（2026-08-06）

## 当前状态

- 状态：`COMPLETE`
- 全量 run：`runs/stage1/mmdocir/20260806-161153-full-1658`
- 数据规模：313 文档、1,658 questions、20,395 pages、170,338 layouts。
- Page 全量索引：20,395 / 20,395，已完成；IVFFLAT 已存在。
- Layout 全量索引：170,338 / 170,338，已完成；IVFFLAT 已构建。
- Page 全量 query evaluation：1,658 / 1,658，成功 1,658，失败 0。
- Layout 全量 query evaluation：1,658 / 1,658，成功 1,658，失败 0。
- 全部评估、watcher 和 embedding 进程均已完成；run root 已写入 `DONE`。

## MatrixOne 持久化状态

- database：`moi_stage1_mmdocir_official`
- page table：`pages_bge_m3_vlm`，20,395 rows，IVFFLAT 已构建。
- layout table：`layouts_bge_m3_vlm`，170,338 rows，IVFFLAT 已构建。
- layout IVFFLAT 当前不存在，这是中断 bulk ingest 的预期状态；恢复完成后会统一重建。
- 原先错位的 `moi_stage1_mmdocir.embedding_results` 不用于本次评估。

## 恢复边界

- Progress：以 `runs/stage1/mmdocir/20260806-161153-full-1658/layout` 下按字典序最新的 `progress.json` 为准。
- 最新失败 progress：`layout/resume-20260806-201120/20260806-201123.839/progress.json`，内容为 `embedded=committed=23179,total=170338,stage=failed`。
- 恢复器会验证：候选总数为 170,338、数据库当前行数=23,179。
- 验证通过后从 candidate offset 23,179 开始，不重新 embedding 前 23,179 行。

## 冻结输入哈希

- `manifest.json`：`de42da8fd1655fc74c9dee5b21bfb81ab6e43ae8c77572f99d84accd6acc7c4d`
- `questions.jsonl`：`8957a84c8a2e53d6d02fdb522735649f0328b0cc3fe27234166a8dbf1c76570f`
- `pages.jsonl`：`70cba2c34db06313d6d2f13018a0b8ee9b97bb0f46c55116ce0083475ede9cd6`
- `layouts.jsonl`：`cf99e90179cd8f5a7535ee1f9e51cf4e337c1df92299cc9bc5667e7326462cbe`

## 已通过的 smoke gate

Smoke run：`runs/stage1/mmdocir/20260806-155228-smoke-50`

- 50 questions，覆盖 10 domains、42 documents。
- Page：50/50 successful，Recall@1/3/5 = 43.33% / 63.67% / 71.00%。
- Layout：50/50 successful，Recall@1/5/10 = 28.45% / 53.21% / 62.11%。
- API / retrieval failures：0。

## 协议说明

- 论文/官方仓库口径：每个 query 只在所属长文档的候选范围内检索。
- Page 指标：Recall@1/3/5。
- Layout 指标：bbox overlap-area Recall@1/5/10。
- 模型条件：MOI/MatrixOne + TaaS `bge-m3`，结果标记为 adapted protocol，不冒充论文的 `bge-large-en-v1.5` baseline。
- 官方数据中的空文本候选在 embedding 输入层使用不可见 U+2060 占位符，MatrixOne 中仍保留原始空 content；这是因为 TaaS 拒绝空字符串，需在最终 protocol 中披露。
- 运行期间 TaaS embedding 请求 timeout 为 600 秒；为降低长批次读超时风险，layout ingest 的 `embedding_batch_size` 已降至 256，并设置 `retry_max_attempts=3`、`retry_backoff_seconds=5`；页面评估同样启用 3 次请求重试。

## 全量结果

- Page metrics：`runs/stage1/mmdocir/20260806-161153-full-1658/page/eval/20260806-221922.385/metrics.json`
  - Recall@1/3/5：`0.434901 / 0.658524 / 0.739274`
  - macro-domain Recall@1/3/5：`0.436337 / 0.663848 / 0.740378`
  - latency P50/P95：`272.339 / 360.977 ms`
- Layout metrics：`runs/stage1/mmdocir/20260806-161153-full-1658/layout/eval/20260806-222713.393/metrics.json`
  - bbox-overlap Recall@1/5/10：`0.280193 / 0.526977 / 0.618662`
  - macro-domain Recall@1/5/10：`0.273019 / 0.513124 / 0.599744`
  - latency P50/P95：`284.884 / 407.208 ms`
- 结果仍属于 `adapted protocol`：MOI/MatrixOne + TaaS `bge-m3`，不与论文的 `bge-large-en-v1.5` baseline 直接等同。

## 下次恢复命令

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag/prototypes/local-matrixflow-rag
./resume_mmdocir_official_full.sh
```

该脚本将（本次已执行完成）：

1. 从最新 layout checkpoint（当前为 23,179 / 170,338）继续 embedding 与写入；
2. 完成后构建 layout IVFFLAT；
3. 运行 page 的 1,658-query evaluation；
4. 运行 layout 的 1,658-query evaluation；
5. 写出 attempts、metrics、report 和 `DONE` 标记；
6. 自动打开实时 watcher Terminal。
