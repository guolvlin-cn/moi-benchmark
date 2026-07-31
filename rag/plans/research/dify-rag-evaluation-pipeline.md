# Dify RAG 本地评测 Pipeline：调研与落地建议

> 调研日期：2026-07-30。本文以 Dify 当前官方 Service API/OpenAPI、Dify 主仓库源码，以及 Ragas、DeepEval、TruLens、promptfoo 的官方文档/仓库为依据。Dify API 仍在快速演进，落地时应固定 Dify 镜像版本并保留 API contract tests。

## 结论

建议把评测器做成独立的 Python CLI，而不是把评测逻辑塞进 Dify：

```text
golden JSONL
  → Dify adapter（调用 + 重试 + 原始响应落盘）
  → normalized sample（question / answer / contexts / context IDs / reference）
  → deterministic retrieval metrics + Ragas/DeepEval LLM metrics
  → per-case JSONL + aggregate JSON/Markdown
```

首版选 **Ragas 作为评分内核**，配套自己实现的 `Recall@K / Precision@K / MRR / nDCG@K` 和运行指标。Ragas 的 `SingleTurnSample` 正好接受 `user_input`、`retrieved_contexts`、`response`、`reference`；官方列出的 RAG 指标包括 Context Precision、Context Recall、Response Relevancy、Faithfulness 等。[Ragas Evaluation Dataset](https://docs.ragas.io/en/stable/concepts/components/eval_dataset/)、[Ragas metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)

如果更看重 pytest 门禁、逐项 judge 理由和调试体验，可将同一份 normalized sample 接到 DeepEval；它把 RAG 指标明确拆成生成侧的 Answer Relevancy、Faithfulness，以及检索侧的 Contextual Relevancy、Precision、Recall。[DeepEval RAG quickstart](https://deepeval.com/docs/getting-started-rag)

## Dify 调用与证据提取

所有 Service API 请求使用 `Authorization: Bearer {API_KEY}`。应用端点使用 **app API key**，知识库检索端点使用 **dataset API key**；自托管时基址通常为 `http://localhost/v1`（以部署的公开 API 地址为准）。官方 OpenAPI 同时强调 key 应仅保存在服务端。[Dify Service API — Send Chat Message](https://docs.dify.ai/en/api-reference/chat-messages/send-chat-message)

### 路线 A：Chatflow（首选）

请求：

```http
POST /v1/chat-messages
Authorization: Bearer ${DIFY_APP_API_KEY}
Content-Type: application/json

{
  "inputs": {},
  "query": "用户问题",
  "response_mode": "blocking",
  "conversation_id": "",
  "user": "rag-eval-${case_id}"
}
```

阻塞响应中的核心字段：

```json
{
  "message_id": "...",
  "conversation_id": "...",
  "answer": "...",
  "metadata": {
    "usage": {"total_tokens": 1161, "latency": 0.768},
    "retriever_resources": [
      {
        "position": 1,
        "dataset_id": "...",
        "dataset_name": "...",
        "document_id": "...",
        "document_name": "...",
        "segment_id": "...",
        "score": 0.9845,
        "content": "..."
      }
    ]
  }
}
```

Dify 官方 OpenAPI 明确定义了以上请求体及 `metadata.retriever_resources` 示例；流式模式下，答案由 `message` 增量拼接，而最终 `message_end.metadata` 携带 `usage` 和 `retriever_resources`。[Send Chat Message](https://docs.dify.ai/en/api-reference/chat-messages/send-chat-message)

评测建议：

- 每个单轮样例使用独立且稳定的 `user`，`conversation_id` 置空，避免历史对回答和检索的污染。
- 将 `retriever_resources[*].content` 映射为 `retrieved_contexts`；将 `segment_id`（优先）或 `document_id` 映射为检索 ID；保留原始排序和 `score`。
- 原始响应完整落盘，normalized 层只做投影，避免后续因字段映射错误而无法复算。
- 若实际版本/应用设置下 `retriever_resources` 为空，立即将该样例标为 `missing_retrieval_evidence`，不要用最终答案反推上下文。

### 路线 B：Workflow

请求：

```http
POST /v1/workflows/run
Authorization: Bearer ${DIFY_APP_API_KEY}
Content-Type: application/json

{
  "inputs": {"query": "用户问题"},
  "response_mode": "blocking",
  "user": "rag-eval-${case_id}"
}
```

官方响应形态为：

```json
{
  "task_id": "...",
  "workflow_run_id": "...",
  "data": {
    "status": "succeeded",
    "outputs": {"answer": "...", "retrieved_contexts": [...]},
    "elapsed_time": 1.23,
    "total_tokens": 150,
    "total_steps": 3
  }
}
```

`POST /workflows/run` 执行的是该 app API key 所绑定应用的已发布 Workflow；`inputs` 和 `user` 必填，`response_mode` 可为 `blocking` 或 `streaming`。[Run Workflow](https://docs.dify.ai/en/api-reference/workflow-runs/run-workflow)

关键限制是：Workflow 的阻塞响应只保证返回 **Output/End 节点声明的 `outputs`**，不会自动提供 Chatflow 式的 `metadata.retriever_resources`。因此评测版 Workflow 应显式输出：

- `answer`：LLM/模板的最终回答；
- `retrieved_contexts`：Knowledge Retrieval 节点的 `result`；
- 可选 `retrieval_query`、`route`、`citations` 等诊断字段。

Dify 当前源码显示 Knowledge Retrieval 节点将结果写入 `outputs["result"]`，其中每条结果包含序列化后的检索对象；这与实际节点输出中的 `metadata`、`title`、`content` 结构一致。[Dify knowledge retrieval node source](https://github.com/langgenius/dify/blob/main/api/core/workflow/nodes/knowledge_retrieval/knowledge_retrieval_node.py)

若不方便改 Workflow，可使用 `streaming` 并捕获知识检索节点对应的 `node_finished.data.outputs`；官方 SSE 契约说明 `node_finished` 提供 `node_id`、`node_type`、`outputs`、`execution_metadata`。但这会把评测器绑到节点 ID/事件细节，稳定性不如显式 Output。[Run Workflow](https://docs.dify.ai/en/api-reference/workflow-runs/run-workflow)

执行后可用以下接口补取运行摘要：

```http
GET /v1/workflows/run/{workflow_run_id}
Authorization: Bearer ${DIFY_APP_API_KEY}
```

它返回 `status / inputs / outputs / error / total_steps / total_tokens / elapsed_time`，但不是完整节点 trace。[Get Workflow Run Detail](https://docs.dify.ai/en/api-reference/workflow-runs/get-workflow-run-detail)；批量审计可用 `GET /v1/workflows/logs`。[List Workflow Logs](https://docs.dify.ai/en/api-reference/workflow-runs/list-workflow-logs)

### 路线 C：把检索器单独测清楚

若要隔离 Dify 知识库的召回/排序质量，直接调用：

```http
POST /v1/datasets/{dataset_id}/retrieve
Authorization: Bearer ${DIFY_DATASET_API_KEY}
Content-Type: application/json

{
  "query": "用户问题",
  "retrieval_model": {
    "search_method": "hybrid_search",
    "reranking_enable": true,
    "reranking_mode": "reranking_model",
    "reranking_model": {
      "reranking_provider_name": "...",
      "reranking_model_name": "..."
    },
    "top_k": 10,
    "score_threshold_enabled": false
  }
}
```

响应为 `records[]`，每项含 `segment`（chunk ID、文档 ID、正文、文档元数据）、`child_chunks`、`score`、附件和可选 summary。此接口最适合做 `top_k / threshold / search_method / reranker` 网格实验，不受生成模型影响。[Retrieve Chunks / Test Retrieval](https://docs.dify.ai/en/api-reference/knowledge-bases/retrieve-chunks-from-a-knowledge-base-test-retrieval)

## 数据集契约

建议 `datasets/golden.jsonl` 每行至少为：

```json
{
  "id": "faq-001",
  "question": "退款期限是多少？",
  "reference_answer": "自购买日起 30 天内。",
  "reference_context_ids": ["segment-uuid-1"],
  "tags": ["refund", "zh-CN"],
  "metadata": {"difficulty": "easy"}
}
```

推荐同时维护 `reference_context_ids` 和 `reference_answer`：

- ID 标签支持确定性的 retrieval metrics，不消耗 judge token，适合 CI。
- reference answer 支持 Context Recall、正确性和业务 rubric。
- 若只标 reference answer，没有 relevant chunk IDs，仍可跑 LLM 指标，但很难精确判断问题来自召回还是 judge。

每次调用后生成统一记录：

```json
{
  "id": "faq-001",
  "user_input": "...",
  "response": "...",
  "reference": "...",
  "retrieved_contexts": ["..."],
  "retrieved_context_ids": ["..."],
  "retrieval_scores": [0.91],
  "latency_s": 1.23,
  "total_tokens": 321,
  "dify_raw_path": "artifacts/raw/faq-001.json"
}
```

## 指标组合

首版不要压成一个“总分”，至少分别报告：

| 层 | 指标 | 需要标签 | 用途 |
|---|---|---|---|
| 检索 | Recall@K | relevant chunk/doc IDs | 需要的证据是否被召回 |
| 检索 | Precision@K | relevant IDs | top-K 噪声比例 |
| 排序 | MRR、nDCG@K | relevant IDs/graded relevance | 首个正确证据位置、排序质量 |
| 检索语义 | Context Precision / Recall | reference | LLM 判断的排序纯度与信息覆盖 |
| 生成 | Faithfulness | retrieved contexts | 回答是否有上下文支撑 |
| 生成 | Response/Answer Relevancy | question | 是否直接回答问题 |
| 端到端 | answer correctness / 自定义 rubric | reference | 是否答对、是否满足业务规则 |
| 运行 | success rate、p50/p95 latency、tokens/cost | 无 | 可用性和成本 |

Ragas 对 Context Recall 的定义是“reference 中被 retrieved context 支持的 claims 比例”，因此它需要 reference；不能把它等同于基于 chunk ID 的传统 Recall@K。[Ragas Context Recall](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/)

Faithfulness 必须基于**实际检索上下文**评分。DeepEval 的官方定义同样是检查 `actual_output` 是否与 `retrieval_context` 一致；真实世界中正确但未被本次上下文支持的说法，仍应判为不忠实。[DeepEval Faithfulness](https://deepeval.com/docs/metrics-faithfulness)

可用 TruLens 的 RAG Triad 作为指标设计的交叉校验：Context Relevance、Groundedness、Answer Relevance 分别覆盖 query→context、context→answer、query→answer 三条边。[TruLens RAG Triad](https://www.trulens.org/getting_started/core_concepts/rag_triad/)

## 开源项目取舍

- **Ragas（推荐主内核）**：数据结构与离线批评测贴合，RAG 指标完整，可自带 judge/embedding。适合本项目先做 Python CLI。[Ragas repository](https://github.com/explodinggradients/ragas)
- **DeepEval（可选 CI 层）**：原生 pytest、阈值门禁、judge reason、缓存和 tracing 更方便；同一 adapter 很容易复用。[DeepEval RAG quickstart](https://deepeval.com/docs/getting-started-rag)
- **promptfoo（可选配置对比/UI）**：通用 HTTP provider 可直接 POST Dify，并用 `transformResponse` 提取回答；其 RAG 指南明确要求分别评测 retrieval 和 generation，并提供 factuality、answer relevance、context adherence/recall/relevance。[HTTP provider](https://www.promptfoo.dev/docs/providers/http/)、[RAG evaluation guide](https://www.promptfoo.dev/docs/guides/evaluate-rag/) 对 Dify SSE 需要自定义重组，因此首版应使用 blocking。
- **TruLens（可选可观测性）**：适合持续 trace 和应用版本对比；若当前目标只是可复现的离线基准，优先级低于 Ragas。[TruLens repository](https://github.com/truera/trulens)

## 建议的本地目录

```text
dify-rag-eval/
├── pyproject.toml
├── .env.example
├── README.md
├── configs/
│   ├── eval.yaml
│   └── variants.yaml
├── datasets/
│   └── golden.jsonl
├── src/dify_rag_eval/
│   ├── cli.py
│   ├── config.py
│   ├── dify_client.py
│   ├── adapters.py
│   ├── schemas.py
│   ├── metrics.py
│   ├── runner.py
│   └── report.py
├── tests/
│   ├── test_dify_contract.py
│   ├── test_adapters.py
│   └── fixtures/
└── artifacts/                 # gitignored
    ├── raw/
    ├── normalized/
    └── reports/
```

配置中每个 variant 至少固定：`base_url`、app/dataset key 的环境变量名、接口类型、Dify 镜像 tag、应用/Workflow 版本、知识库快照、embedding/reranker/LLM 名称、top-K 和 threshold。API key 不进入 YAML、日志或报告。

## 最小实施顺序

1. 在 Dify 发布一个专用 Chatflow，或为 Workflow 增加 `answer` 与 `retrieved_contexts` 输出。
2. 先做 10–20 条人工核验样例，标注 `reference_answer` 与 relevant segment IDs。
3. 实现 blocking adapter、原始响应落盘、normalized schema 和 contract tests。
4. 先跑确定性 retrieval metrics、成功率、延迟和 token；人工抽查 adapter 映射。
5. 再接 Ragas 的 Faithfulness、Response Relevancy、Context Precision/Recall。
6. 用同一数据集比较 Dify variants；逐项报告置信区间/失败样例，不用单一平均分掩盖退化。
7. CI 只跑小型稳定集和确定性指标；完整 LLM-as-a-judge 评测按需或定时运行，并固定 judge model、temperature、prompt 与依赖版本。

## 主要风险与防护

- **证据缺失**：`retriever_resources` 为空或 Workflow 未输出 retrieval result 时禁止跑 faithfulness，明确报错。
- **chunk ID 漂移**：重新切分/重建索引会改变 segment IDs；golden 必须绑定知识库快照或维护 document-level fallback。
- **judge 漂移**：固定 judge 模型和 prompt，对边界样例做人审校准；阈值由基线数据确定，不照搬示例中的 0.7/0.8。
- **线上污染**：评测使用独立 `user`；Chatflow 单轮集不复用 `conversation_id`。
- **不可复现**：保存 Dify 原始响应、应用版本、知识库版本、模型参数、代码 commit 和依赖锁文件。
- **只测端到端**：答案差不等于检索差；必须保留 retrieval-only 与 generation-only 两组指标。
