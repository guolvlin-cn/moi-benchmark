# MultiHop-RAG：Dify 与 MatrixFlow-style RAG 测试报告

日期：2026-07-31

## 结论

- MatrixFlow-style RAG 完成了 609 篇全文的直接摄取和冻结的 20 题 × 2 repeats，共 40 次真实问答，可形成本轮描述性质量指标。
- Dify 完成了全部语料和题集准备，但免费订阅的向量空间配额阻止知识库达到 searchable-ready，正式 40 次问答按门禁未执行。因此本轮不能给出 Dify RAG 质量分数，也不能据此做两系统质量排名。
- 用户把发布 Chatflow 重绑到目标 MultiHop 知识库后又执行了恢复运行；目标库 ID 正确且为 0 文档，但 high-quality/custom-4000 与 economy/custom-4000 两种首包上传均仍被 vector-space 403 拒绝，故结论未改变。
- 在当前部署和订阅条件下，可以得出的操作性事实是：MatrixFlow 完成了端到端测试；Dify 被知识库容量门禁阻塞。

## 公平性与冻结

- 语料：两边均以 `datasets/downloads/public/multihop-rag/corpus.json` 的 609 篇正文为来源。
- 题集：按 `question_type` 分组，对 `SHA256(query)` 升序排序，每类取 5 题，共 20 题。
- 类型：`comparison_query`、`inference_query`、`temporal_query`、`null_query` 各 5 题。
- 重复：计划每题 2 次 initial repeat，共 40 次。
- 审计：两个系统的题集 JSONL schema 和文件哈希不同，但逐题 query 集合核对完全一致。

## 结果对比

| 指标 | MatrixFlow-style RAG | Dify |
|---|---:|---:|
| 语料覆盖 | 609/609 | 609/609 已准备，未 ready |
| 建库结果 | 609 docs / 6,390 chunks | BLOCKED |
| 正式尝试 | 40/40 | 0/40 |
| 可用性 | 39/40（97.5%） | N/A：READINESS_BLOCKED |
| answerable 正确率 | 22/30（73.3%） | N/A |
| evidence-source recall，宏平均 | 52.2% | N/A |
| 完整证据源召回 | 2/30 | N/A |
| null query 拒答 | 10/10（100%） | N/A |
| P50 / P95 端到端延迟 | 19.08s / 28.03s | N/A |
| 两次 repeat 正确性一致 | 20/20 | N/A |
| 两次回答文本精确一致 | 0/20 | N/A |
| 平均答案 token Jaccard | 0.464 | N/A |
| 检索 context/rank/trace | 40/40 | formal 未执行 |
| 结构化 citation | N/A：不可用 | N/A：formal 未执行 |

## MatrixFlow 解释

- 39/40 次完成；唯一失败为生成端 HTTP 504，并保留在 initial 分母中。
- answerable 正确率采用“规范化答案包含，或 Gold 答案 token 覆盖率不低于 0.8”的确定性规则，不等同于人工 claim-level judge。
- 证据源宏平均召回为 52.2%，但只有 2/30 次完整召回全部 Gold 来源，说明多跳检索仍是主要改进点。
- null query 10/10 正确拒答；两次重复的正确/错误结论完全一致，但措辞差异明显。

## Dify 阻塞证据

1. Attempt 1：单个约 6.8MB 全量文档被接受；解析、清洗和切分完成，但 30 分钟后仍为 `indexing`，`completed_segments=0/total_segments=0`。直接 retrieve 请求成功但返回 0 records。
2. Attempt 2：将 609 篇文章确定性打包为 40 个分片。首包使用 automatic 和 custom 4000-token 分段均同步返回 HTTP 403：订阅向量空间已达上限；fallback 知识库保持 0 文档。
3. 正式 40 次按 searchable-ready 门禁未执行。仅保留 1 次不计分 smoke；其 3 条 context 全来自旧知识库文档，MultiHop evidence recall 为 0，证明已发布 Chatflow 尚未绑定可用的 MultiHop 知识库。
4. 经用户授权，删除全部非目标知识库及唯一的其他已完成文档后，workspace 只剩 0 文档的目标库。立即和 30 秒后两次重试首包仍返回相同的 vector-space 403，说明可见的其他知识库已不是阻塞来源。
4. 用户重绑 Chatflow 后的 recovery attempt 只读确认目标库与既有 ID 一致；然而目标库仍为 0 文档。`high_quality + semantic_search + custom 4000-token` 及 `economy + keyword_search + custom 4000-token` 均在首包同步收到相同 vector-capacity 403，无法进入 direct-retrieve/Chatflow-context 门禁。

### Dify 数据库最终状态

- `multihop-rag-full-609-20260731-isolated`：0 文档。
- `mh-rag-609-b40-20260731-isolated`：0 文档。
- Attempt 1 的全量文档在固化 30 分钟索引状态和检索探针后，为释放本任务占用并尝试分片 fallback，被测试流程删除。
- Attempt 2 的分片在首包创建文档时即收到 403，因此没有任何分片实际进入知识库。
- 后续已删除全部非目标知识库；当前 workspace 只保留 `mh-rag-609-b40-20260731-isolated`，仍为 0 文档。
- “609/609 语料已准备”仅表示本地 Markdown 和 bundles 已生成，不表示它们最终保留在 Dify 数据库。

Dify 的结论是 `BLOCKED`，原因是当前免费订阅容量，不是 Dify 回答质量不合格。

## 产物

- MatrixFlow 报告：`prototypes/runs/matrixflow-multihop-rag-20260731-v1/evaluation/report.md`
- MatrixFlow 指标：`prototypes/runs/matrixflow-multihop-rag-20260731-v1/evaluation/metrics.json`
- MatrixFlow 原始结果：`prototypes/runs/matrixflow-multihop-rag-20260731-v1/product-run/20260731-170525.330/results.jsonl`
- Dify 报告：`dify-rag-eval/runs/multihop-rag-20260731/report.md`
- Dify 指标：`dify-rag-eval/runs/multihop-rag-20260731/metrics.json`
- Dify 准备数据：`datasets/downloads/prepared/multihop-rag-dify/`
- Dify 重绑后恢复证据：`dify-rag-eval/runs/multihop-rag-20260731-recovery-01/attempt.json`

## 下一步

要获得可比较的 Dify 质量结果，需要先提升或清空 Dify 向量空间配额，使 40 个 bundles 全部达到 completed/searchable，并把发布 Chatflow 明确绑定到该 MultiHop 知识库；随后原样运行已经冻结的 20 题 × 2 repeats，不重新抽题。
