# Dify RAG 本地评测 Pipeline

这是一个无外部 Python 运行时依赖的最小评测器：从 JSONL 读取
Golden questions，调用已发布的 Dify Chat/Chatflow 或 Workflow，保留原始响应和
实际检索上下文，然后输出逐题结果、汇总 JSON 与 Markdown 报告。

当前版本适合先打通三个环节：

```text
Golden JSONL → Dify API adapter → 规范化结果 → 确定性指标与报告
```

它不把多个维度压成一个“总分”。现已实现请求成功率、Exact Match、token F1、
关键词召回、拒答匹配、Retrieval Hit/Recall/Precision@K、MRR、平均与 P95
延迟。Faithfulness、Answer Relevancy 等 LLM-as-a-judge 指标应在拿到真实
retrieved contexts 后，通过 Ragas/DeepEval 或仓库既有 evaluator 作为第二阶段接入。

## 0. 本次完整实操记录

本节记录 2026-07-30 实际跑通的 Dify RAG 测评链路。它既是结果摘要，也可以作为从零
复现的最短操作路径。

### 0.1 完整链路

```text
RAGBench e-manual Parquet
  ↓ prepare_ragbench.py
44 个去重 Markdown 文档 + 20 道 JSONL 问题
  ↓ Dataset/Knowledge API
Dify 知识库 ragbench-emanual-api
  ↓ Chatflow：开始 → 知识检索 → LLM → 回答
Dify Service API /chat-messages
  ↓ dify-rag-eval run
逐题结果 results.jsonl + 汇总 summary.json + 报告 report.md
```

本次使用的远端知识库：

| 项目 | 实际值 |
|---|---|
| 知识库名称 | `ragbench-emanual-api` |
| Dify Dataset ID | `41d76317-d0ab-4a19-b739-f18d4b095b7b` |
| 文档数 | 44 |
| 索引完成/失败 | 44 / 0 |
| Embedding Provider | `langgenius/siliconflow/siliconflow` |
| Embedding Model | `BAAI/bge-large-en-v1.5` |
| 检索方式 | `semantic_search` |

Dataset ID 不是 API Key，但它属于当前 Dify 工作区；换工作区或重建知识库后应以新
ID 为准。

### 0.2 本地环境和 API Key

进入项目并创建环境：

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag/dify-rag-eval
uv sync
cp .env.example .env
cp config.example.json config.local.json
```

需要两类互不通用的 Key：

| 环境变量 | 用途 | Dify 中的获取位置 |
|---|---|---|
| `DIFY_DATASET_API_KEY` | 创建知识库、上传文档、查询索引和直接检索 | Dify → 知识库 → API/知识库 API |
| `DIFY_API_KEY` | 调用已经发布的 Chatflow | Dify → 工作室 → 当前应用 → 访问 API |

`.env` 示例：

```dotenv
DIFY_API_BASE_URL=https://api.dify.ai/v1
DIFY_DATASET_API_KEY=dataset-your-key
DIFY_API_KEY=app-your-key
```

真实 Key 只能保存在本地 `.env`，不要写入 README、JSON 配置、结果文件或 Git。

### 0.3 准备 RAGBench 数据

原始数据位于：

```text
../datasets/downloads/public/ragbench/emanual/test-00000-of-00001.parquet
```

生成本次 Smoke 包：

```bash
uv run --with pyarrow tools/prepare_ragbench.py \
  --input ../datasets/downloads/public/ragbench/emanual/test-00000-of-00001.parquet \
  --output ../datasets/downloads/prepared/ragbench-emanual-smoke \
  --limit 20
```

生成结果：

```text
../datasets/downloads/prepared/ragbench-emanual-smoke/
├── upload-to-dify/   # 44 个去重后的 Markdown 文档
├── questions.jsonl   # 20 道评测问题及检索 Gold
└── manifest.json     # 数据来源、选择规则和限制
```

先校验问题集，不会调用 Dify：

```bash
uv run dify-rag-eval validate \
  --dataset ../datasets/downloads/prepared/ragbench-emanual-smoke/questions.jsonl
```

### 0.4 通过 API 构建知识库

本次实际使用下面的命令创建或复用知识库、上传 44 个文档、等待索引完成，并执行一次
直接召回探针：

```bash
uv run --env-file .env dify-rag-eval ingest \
  --source ../datasets/downloads/prepared/ragbench-emanual-smoke/upload-to-dify \
  --knowledge-name ragbench-emanual-api \
  --output runs/ingest-ragbench-emanual-api \
  --embedding-model BAAI/bge-large-en-v1.5 \
  --embedding-provider langgenius/siliconflow/siliconflow \
  --search-method semantic_search \
  --top-k 5 \
  --upload-interval 6.5 \
  --wait \
  --probe "I want to enter into Ambient mode. How can I do that?"
```

预期结果：

- 44 个文档最终均为 `completed`；
- `retrieval-probe.json` 返回 5 条记录；
- Top K 中包含 `To enter Ambient Mode, press the button.`；
- 重复运行相同命令时复用知识库，并按文件名跳过已经上传的文档。

运行证据保存在：

```text
runs/ingest-ragbench-emanual-api/
├── ingest-state.json
└── retrieval-probe.json
```

#### 可选：本地确定性分块

需要可复现的本地分块时，显式加入 `--local-chunks`（默认仍是整文件上传）。例如：

```bash
export DIFY_API_BASE_URL=https://api.dify.ai/v1
uv run dify-rag-eval ingest \
  --base-url "$DIFY_API_BASE_URL" \
  --source ../datasets/downloads/prepared/ragbench-emanual-smoke/upload-to-dify \
  --knowledge-name ragbench-emanual-local-chunks \
  --output runs/ingest-ragbench-local-chunks \
  --local-chunks --chunk-size 2000 --chunk-overlap 200 \
  --wait
```

该模式在输出目录生成 `chunks/` 和 `chunk-manifest.json`；manifest 保存源文件、块序号、
字符偏移和内容哈希，文件名也稳定绑定源文件、内容与序号，因此可安全恢复/重复运行。
每个本地 chunk 会作为一个独立的 Dify 文档上传；Dify 的 automatic 模式仍可能继续对
这些文档做二次分段。

### 0.5 编排并发布 Chatflow

在 Dify `https://cloud.dify.ai` 的“工作室”中创建或打开 Chatflow：

```text
开始 → 知识检索 → LLM → 回答
```

各节点的关键设置：

1. “开始”节点使用系统问题变量 `sys.query`；
2. “知识检索”节点选择 `ragbench-emanual-api`，查询变量选择 `sys.query`；
3. “LLM”节点顶部的 Context 通过变量选择器绑定“知识检索 → result”；
4. System Prompt 中插入 LLM 的 Context 变量，不要只手写空的
   `<context></context>`；
5. User 消息只传 `sys.query`，无需再次拼接知识检索结果或文件变量；
6. “回答”节点输出 LLM 的文本；
7. 关闭不需要的对话记忆，避免不同评测题之间相互污染；
8. 预览成功后点击“发布 → 更新发布”。

推荐的 System Prompt：

```text
请只根据以下知识库上下文回答问题。
请使用与用户问题相同的语言回答。
优先使用与问题最直接相关的上下文。
如果上下文包含可以推导出答案的明确操作步骤，请直接回答。
只有当所有上下文都无法支持答案时，才回答“根据现有资料无法回答”。

<context>
{{ 在 Dify 变量选择器中插入 LLM Context }}
</context>
```

发布后进入“访问 API”创建 App API Key，并写入本地 `.env` 的
`DIFY_API_KEY`。

### 0.6 先跑单题探针

完整评测前，先用一条问题确认发布版本确实返回检索上下文：

```bash
head -n 1 \
  ../datasets/downloads/prepared/ragbench-emanual-smoke/questions.jsonl \
  > /tmp/dify-rag-probe.jsonl

uv run --env-file .env dify-rag-eval run \
  --config config.local.json \
  --dataset /tmp/dify-rag-probe.jsonl \
  --output runs/chatflow-probe
```

检查结果：

```bash
jq '{
  id: .case.id,
  answer,
  context_count: (.contexts | length),
  context_names: [.contexts[].document_name],
  metrics
}' runs/chatflow-probe/results.jsonl
```

`context_count` 必须大于 0。若知识检索节点在 Dify 预览中有结果，但 API 的
`retriever_resources` 为空，通常是 LLM Context 未绑定，或修改后没有重新发布。

### 0.7 运行 20 题完整 Smoke

```bash
uv run --env-file .env dify-rag-eval run \
  --config config.local.json \
  --dataset ../datasets/downloads/prepared/ragbench-emanual-smoke/questions.jsonl \
  --output runs/ragbench-emanual-smoke-001
```

本次实测结果：

| 指标 | 结果 |
|---|---:|
| API 请求成功 | 20/20 |
| 返回非空上下文 | 20/20 |
| 每题返回上下文 | 4 |
| `retrieval_hit_at_k` | 0.95 |
| `MRR` | 0.8875 |
| 平均延迟 | 36.16 秒 |
| P95 延迟 | 96.73 秒 |
| `token_f1` | 0.0339 |

结果目录：

```text
runs/ragbench-emanual-smoke-001/
├── results.jsonl   # 原始响应、回答、真实检索上下文和逐题指标
├── summary.json    # 汇总指标
├── report.md       # 自动生成的简要报告
└── analysis.md     # 本次人工分析和异常样本
```

本次 `token_f1` 很低，主要因为参考答案是英文，而当时 Chatflow 大多用中文回答，
不代表所有回答都错误。RAGBench 的 `response` 也是已有模型生成的答案，并非人工
canonical answer，因此这 20 题用于验证 Pipeline 和发现问题，不应用作
decision-grade 模型排名。

两个值得继续调试的样本：

- `emanual_64`：Gold 文档排名第 1，但模型仍拒答，属于生成侧问题；
- `emanual_473`：正确语义出现在第 3 条上下文，但文件名与 Gold 不一致，且模型采用了
  另一条不相关证据。它同时暴露了去重文档的 Gold 对齐问题和生成选证问题。

如只调整指标实现或 Gold 标签，可直接离线重算，无需再次请求 Dify：

```bash
uv run dify-rag-eval score \
  --results runs/ragbench-emanual-smoke-001/results.jsonl \
  --output runs/ragbench-emanual-smoke-001-rescored \
  --top-k 5
```

## 1. 在 Dify 中准备应用

### Chatbot / Chatflow（推荐起点）

在 Dify Cloud 打开 `https://cloud.dify.ai`，按以下顺序操作：

1. 进入“知识库”，创建名为 `ragbench-emanual-api` 的知识库，或使用本文的
   `ingest` 命令通过 API 创建；
2. 上传本 README 后文生成的 `upload-to-dify/*.md`；
3. 使用“高质量”索引、通用分段和已配置的 Embedding 模型；
4. 等待全部文档进入“可用/Available”状态；
5. 进入“工作室”，从空白创建 Chatflow；
6. 将画布连接为 `开始 → 知识检索 → LLM → 回答`；
7. 知识检索节点选择上述知识库，查询变量选择 `sys.query`；
8. LLM 节点的 Context 必须引用“知识检索 → result”；
9. 预览测试成功后点击“发布/更新发布”；
10. 进入“访问 API/API Access”，创建 App API Key。

第一轮建议知识检索使用 `Top K=5` 并关闭 Score Threshold。可用下面的问题做召回
探针：

```text
I want to enter into Ambient mode. How can I do that?
```

知识检索节点的运行结果应该非空，并包含：

```text
To enter Ambient Mode, press the button.
```

发布使用知识检索的应用并创建 App API Key 后，评测器调用
`POST /v1/chat-messages`，从阻塞响应的
`metadata.retriever_resources` 读取实际上下文。每次尝试使用独立 `user` 且
`conversation_id` 为空，避免对话历史污染。

### Workflow

在 End/Output 节点显式暴露两个变量：

- `answer`：最终回答；
- `contexts`：Knowledge Retrieval 节点的 `result`。

评测器调用 `POST /v1/workflows/run`。如果变量名不同，在配置的
`workflow.answer_path` 和 `workflow.contexts_path` 中修改 JSON 路径。Workflow
阻塞 API 只返回声明为输出的值，不会自动提供 Chatflow 的
`retriever_resources`。

## 2. 本地运行

需要 Python 3.11+。推荐使用 `uv`：

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag/dify-rag-eval
uv sync
cp config.example.json config.local.json
cp .env.example .env

uv run dify-rag-eval validate --dataset data/sample.jsonl
uv run --env-file .env dify-rag-eval run \
  --config config.local.json \
  --dataset data/sample.jsonl \
  --output runs/smoke-001
```

把 `.env` 中的占位符替换成真实 Dify App API Key。`.env` 与
`config.local.json` 均已加入 `.gitignore`。`uv run` 会在执行前自动检查 lockfile
和项目环境是否同步；也可以先执行 `uv sync`，方便编辑器发现 `.venv`。

`.env` 的正确内容为：

```dotenv
DIFY_API_KEY=app-your-real-key
```

`config.local.json` 中的 `api_key_env` 必须是环境变量名，不能填写 Key 本身：

```json
{
  "base_url": "https://api.dify.ai/v1",
  "app_type": "chat",
  "api_key_env": "DIFY_API_KEY"
}
```

如果是自托管 Dify，将 `base_url` 改成实际 Service API 地址，例如
`http://localhost/v1`。

产物：

```text
runs/smoke-001/
├── results.jsonl   # 每次 attempt、原始响应、上下文与逐项指标
├── summary.json    # 机器可读的 macro 汇总
└── report.md       # 人类可读报告
```

失败请求不会被删除，会以 `request_success=0` 留在分母中。重新计算指标不需要再次
调用 Dify：

```bash
uv run dify-rag-eval score \
  --results runs/smoke-001/results.jsonl \
  --output runs/smoke-001-rescored \
  --top-k 5
```

## 3. 配置

复制 `config.example.json` 后修改：

| 字段 | 说明 |
|---|---|
| `base_url` | Dify Service API 基址；本地常见为 `http://localhost/v1` |
| `app_type` | `chat` 或 `workflow` |
| `api_key_env` | 存放 App API Key 的环境变量名 |
| `concurrency` | 并发请求数；先从 1–2 开始 |
| `repeats` | 每题独立重复次数 |
| `top_k` | 计算 retrieval metrics 时截取的上下文数量 |
| `inputs` | 每次请求共有的 Dify 应用输入 |
| `workflow.query_input` | Workflow 开始节点的问题变量名 |
| `workflow.answer_path` | Workflow 响应中答案的点分 JSON 路径 |
| `workflow.contexts_path` | Workflow 响应中检索结果的点分 JSON 路径 |

API Key 只从环境变量读取，不能放入配置、数据集或 Git。

## 4. 数据集格式

每行一个 JSON 对象：

```json
{
  "id": "refund-001",
  "question": "退款期限是多少？",
  "references": ["自购买日起 30 天内。"],
  "required_keywords": ["30 天"],
  "answerable": true,
  "gold_document_ids": ["document-uuid"],
  "gold_document_names": ["退款政策"],
  "gold_evidence": ["自购买日起 30 天内可申请退款"],
  "inputs": {"language": "zh-CN"},
  "tags": ["refund", "smoke"]
}
```

`id` 与 `question` 必填，其余可选。检索 Gold 按以下优先级选择一种标签计算，
避免同一证据被重复计数：

1. `gold_document_ids`
2. `gold_document_names`
3. `gold_evidence`

推荐正式数据优先标 Dify document/segment 的稳定 ID，并绑定知识库快照；重建索引
可能导致 segment ID 漂移。不可回答题设置 `answerable=false`，并提供
`refusal_keywords`。没有所需 Gold 的指标会报告 `N/A`，不会伪装成 0 或通过。

### 从本地 RAGBench 准备 Smoke 包

RAGBench 下载内容是 Parquet 评测表，不是 Dify 可直接导入的文档。可先从
`emanual/test` 生成 20 题 Smoke 包：

```bash
uv run --with pyarrow tools/prepare_ragbench.py \
  --input ../datasets/downloads/public/ragbench/emanual/test-00000-of-00001.parquet \
  --output ../datasets/downloads/prepared/ragbench-emanual-smoke \
  --limit 20
```

当前仓库已经生成好一份：

```text
../datasets/downloads/prepared/ragbench-emanual-smoke/
├── upload-to-dify/   # 44 个去重 Markdown 文档，共约 216 KiB
├── questions.jsonl   # 20 道 Smoke questions
└── manifest.json     # 来源、选择规则和限制
```

将输出目录中的 `upload-to-dify/*.md` 上传到同一个 Dify 知识库，运行时使用
`questions.jsonl`。该转换包从每行已有的 retrieved documents 重建语料；
`response` 是 RAGBench 中已有模型的生成回答，不是人工 canonical answer，因此仅适合
验证导入、调用、上下文提取和指标链路，不应用于 decision-grade 产品排名。

完成 Chatflow 发布后，运行正式的 RAGBench Smoke：

```bash
uv run --env-file .env dify-rag-eval run \
  --config config.local.json \
  --dataset ../datasets/downloads/prepared/ragbench-emanual-smoke/questions.jsonl \
  --output runs/ragbench-emanual-smoke-001
```

2026-07-30 的已验证基线：

- 20/20 API 请求成功，20/20 均返回 4 条检索上下文；
- `retrieval_hit_at_k = 0.95`，`MRR = 0.8875`；
- 平均延迟 36.16 秒，P95 延迟 96.73 秒；
- `token_f1 = 0.0339` 暂不可用于判断回答质量，因为参考答案是英文，而 Chatflow
  当前大多输出中文。正式答案评测前，请在 System Prompt 中要求“使用与用户问题相同
  的语言回答”，并重新运行，或接入语义型/LLM judge 指标。

完整机器可读结果位于
`runs/ragbench-emanual-smoke-001/{summary.json,results.jsonl}`。

### 通过 API 创建知识库并上传文档

知识库 API 使用 Dataset/Knowledge API Key，与 Chatflow App API Key 不同：

```dotenv
DIFY_API_BASE_URL=https://api.dify.ai/v1
DIFY_DATASET_API_KEY=dataset-your-key
DIFY_API_KEY=app-your-key
```

`ingest` 命令会查询当前工作区的可用 Embedding 模型，创建或复用同名知识库，按文件名
跳过已经存在的文档，逐个上传新文件，轮询索引状态，并可在全部完成后执行召回探针。

本项目 RAGBench e-manual 的已验证命令：

```bash
uv run --env-file .env dify-rag-eval ingest \
  --source ../datasets/downloads/prepared/ragbench-emanual-smoke/upload-to-dify \
  --knowledge-name ragbench-emanual-api \
  --output runs/ingest-ragbench-emanual-api \
  --embedding-model BAAI/bge-large-en-v1.5 \
  --embedding-provider langgenius/siliconflow/siliconflow \
  --search-method semantic_search \
  --top-k 5 \
  --upload-interval 6.5 \
  --wait \
  --probe "I want to enter into Ambient mode. How can I do that?"
```

关键参数：

| 参数 | 说明 |
|---|---|
| `--source` | 待上传文件目录；只读取该目录第一层的普通文件 |
| `--knowledge-name` | 创建或复用的知识库名称 |
| `--output` | 本地状态与召回证据目录 |
| `--embedding-model/provider` | 可选；不指定时从工作区 active models 中选择 |
| `--upload-interval` | 两次上传间隔；Cloud Sandbox 建议约 6.5 秒 |
| `--wait` | 等到所有文档为 `completed` 或发现 `error` |
| `--probe` | 索引完成后执行的知识库召回问题 |

产物：

```text
runs/ingest-ragbench-emanual-api/
├── ingest-state.json       # dataset ID、每个文档 ID/batch/status 和运行汇总
└── retrieval-probe.json    # Dify /datasets/{dataset_id}/retrieve 原始证据
```

状态文件和 Dify 文档列表共同保证可恢复性。相同命令重复执行时会复用同一知识库并跳过
同名文档；本地状态文件中不保存任何 API Key。

本次真实验证结果：

```text
知识库：ragbench-emanual-api
Embedding：langgenius/siliconflow/siliconflow / BAAI/bge-large-en-v1.5
源文件：44
索引完成：44
索引错误：0
召回探针：返回 5 条记录，目标证据位于 Top K
重复运行：0 个重复上传
```

## 5. 指标怎么看

| 指标 | 解释 |
|---|---|
| `request_success` | Dify 请求是否返回可评分响应 |
| `exact_match` / `token_f1` | 回答与 reference 的严格/宽松词面一致性 |
| `keyword_recall` | 必需业务要点覆盖率 |
| `refusal_match` | 不可回答题是否出现预定义的合规拒答表达 |
| `retrieval_recall_at_k` | K 内覆盖了多少 Gold 证据项 |
| `retrieval_precision_at_k` | 返回的前 K 个上下文中有多少命中 Gold |
| `mrr` | 首个相关上下文排名的倒数 |

词面分数只适合稳定的事实型答案，不能替代事实正确性、引用有效性与
Faithfulness 人审/LLM Judge。阈值应先用人工校准集确定，不应直接照搬开源项目示例。

## 6. 常见问题与调试

### Cloudflare 403 / Error 1010

旧版本客户端使用 Python `urllib` 默认 User-Agent 时，Dify Cloud 可能返回：

```text
403 Error 1010: Access denied
browser_signature_banned
```

当前客户端已显式发送 `User-Agent: Dify-RAG-Eval/0.1`。如果仍出现该错误，确认使用
的是当前源码与 `uv.lock`：

```bash
uv sync
uv run python -m unittest discover -s tests -v
```

### 请求成功，但 `retriever_resources` 为空

表现通常是：

```text
request_success = 1
context_count = 0
retrieval_recall_at_k = 0
```

按顺序检查：

1. 44 个知识文档是否全部是“可用/Available”；
2. Chatflow 知识检索节点是否选择了正确知识库；
3. 查询变量是否为 `sys.query`；
4. LLM 的 Context 是否引用了“知识检索 → result”；
5. 知识检索节点是否实际处在 `开始 → 知识检索 → LLM → 回答` 链路上；
6. 是否在修改后重新发布应用；
7. 使用上面的 Ambient Mode 探针，在 Dify 预览中检查知识检索节点 `result`。

不能用最终答案反推检索上下文；`retriever_resources=[]` 应视为没有可评分的真实检索
证据。

### API Key 配置错误

- `401/403`：确认使用当前应用的 App API Key，而不是 Dataset API Key；
- `missing API key`：使用 `uv run --env-file .env ...`；
- 不要把 `app-...` 填进 `api_key_env`；
- 如果 Key 曾写入配置、日志或 Git，应立即在 Dify “访问 API”中撤销并重建。

### 回答中出现 `<think>...</think>`

这是应用所选推理模型或模型输出格式造成的，不是检索证据。优先在 Dify 的 LLM 节点
中启用分离 reasoning 的输出模式，或改用不向最终回答暴露思考内容的模型。正式评分前
应冻结该设置，不能对某个系统临时人工删除 reasoning。

### `data/sample.jsonl` 为什么检索为 0

`data/sample.jsonl` 只用于验证 CLI，其中的“Dify 是什么”与 RAGBench e-manual 语料
无关。测试已上传的知识库必须使用
`../datasets/downloads/prepared/ragbench-emanual-smoke/questions.jsonl`。

## 7. 为什么这样设计

- [Dify Send Chat Message](https://docs.dify.ai/en/api-reference/chat-messages/send-chat-message)
  定义了 `/chat-messages` 请求以及 `metadata.retriever_resources`。
- [Dify Run Workflow](https://docs.dify.ai/en/api-reference/workflow-runs/run-workflow)
  定义了 `/workflows/run` 与 `data.outputs`。
- [Ragas](https://github.com/explodinggradients/ragas) 适合离线
  question/context/answer/reference 指标；下一阶段可接 Faithfulness、Response
  Relevancy、Context Precision/Recall。
- [DeepEval RAG 指南](https://deepeval.com/docs/getting-started-rag) 适合把 judge
  阈值做成 pytest/CI 门禁。
- [promptfoo RAG 指南](https://www.promptfoo.dev/docs/guides/evaluate-rag/)
  适合多配置对比和可视化。
- [TruLens RAG Triad](https://www.trulens.org/getting_started/core_concepts/rag_triad/)
  可用于持续可观测性和 query→context→answer 三条边的诊断。

更完整的 API 契约、项目选型和风险说明见
[`../research/dify-rag-evaluation-pipeline.md`](../research/dify-rag-evaluation-pipeline.md)。

## 8. 下一阶段

1. 扩展 retrieval-only runner，批量调用 `/datasets/{dataset_id}/retrieve` 做
   top-K、threshold、hybrid/reranker 网格实验。
2. 增加 Ragas/DeepEval 可选 extra，并冻结 judge 模型、prompt、temperature 与版本。
3. 将结果投影到仓库已有 TDAS/claim/citation evaluator，而不是另造不可比的总分。
4. 加入 variant manifest、Dify 镜像/app/知识库版本、Git commit 与成本字段。
5. 对 paired variants 做 question-level 聚合与 bootstrap 置信区间。

## 测试

```bash
uv run python -m unittest discover -s tests -v
```
