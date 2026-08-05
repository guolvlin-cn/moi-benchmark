# TLDR: TODO

**source chat**: https://chatgpt.com/c/6a71b41b-0038-83ea-b80e-e1373644523d

## papers
- EnterpriseRAG-Bench: A RAG Benchmark for Company Internal Knowledge
- FAB-Bench: A Framework for Adaptive RAG Benchmarking in Semiconductor Manufacturing

## blogs
- https://91aihub.com/articles/%E5%9B%9B%E5%A4%A7%E5%BC%80%E6%BA%90%E7%9F%A5%E8%AF%86%E5%BA%93%E5%B9%B3%E5%8F%B0-rag-%E5%AE%9E%E6%B5%8B-maxkb-ragflow-fastgpt-dify
- https://www.promptquorum.com/zh/power-local-llm/anythingllm-vs-privategpt-vs-openwebui-rag
- https://studiobrain.ca/docs/RAG_Benchmark?utm_source=chatgpt.com
- https://ee.dify.ai/reports/v3.9.5/benchmark-report/?utm_source=chatgpt.com


# Dify、FastGPT、RAGFlow、MaxKB 统一 RAG 评测计划

> **版本**：V1.0
> **日期**：2026-08-04
> **目标**：构建一套面向主流低代码/开源 RAG 平台的可复现评测框架，避免仅依赖单一博客、单一模型或不可公开的实验结果。
> **首批评测平台**：Dify、FastGPT、RAGFlow、MaxKB
> **核心参考**：EnterpriseRAG-Bench、FAB-Bench、91ai 四平台横评、MIRAGE、RAGPerf

---

# 1. 项目背景

现有针对 Dify、FastGPT、RAGFlow、MaxKB 等平台的公开横向评测存在明显不足：

1. 使用模型较旧，例如 Qwen2.5，难以代表 2026 年主流部署条件。
2. 不同平台使用的 Top-K、Chunk 数量或上下文预算不一致。
3. 生成模型和评测模型可能为同一个模型，存在自评偏差。
4. 测试题量通常较少，每个数据集只有几十道题。
5. 只评估最终回答，没有区分解析、检索、重排和生成阶段。
6. 没有公开完整输入、平台配置、原始回答、检索结果和运行脚本。
7. 平台版本、模型版本和默认参数持续变化，历史结论容易失效。

因此，本项目不再试图寻找一个“永久有效的平台排行榜”，而是建立一套：

- 可重复运行；
- 可替换模型；
- 可扩展平台；
- 可保存完整 Trace；
- 可分别评估检索与生成；
- 可用于持续回归测试；

的统一评测框架。

---

# 2. 核心目标

本项目需要回答以下问题：

## 2.1 平台开箱即用能力

当普通用户使用各平台推荐配置上传相同文档时：

- 哪个平台文档解析成功率更高？
- 哪个平台默认检索效果更好？
- 哪个平台默认回答更准确？
- 哪个平台对复杂 PDF、扫描件和表格支持更好？
- 哪个平台部署和自动化成本更低？

## 2.2 平台 RAG 实现能力

在统一模型、Embedding、Reranker、Chunk 和 Top-K 后：

- 各平台的检索链路是否仍存在差异？
- 各平台是否正确返回检索结果和引用？
- 各平台工作流调度是否带来额外延迟？
- 各平台是否存在上下文截断、Chunk 丢失或重排异常？

## 2.3 平台能力上限

允许每个平台使用最适合自己的能力后：

- 哪个平台调优后上限最高？
- 哪个平台适合复杂文档？
- 哪个平台适合企业内部多源知识库？
- 哪个平台适合 Agentic、多步检索和工作流编排？
- 哪个平台更适合作为长期生产系统？

---

# 3. 总体方案

推荐采用以下组合：

```text
EnterpriseRAG-Bench
        +
FAB-Bench 双模式评测
        +
自建中文企业数据集
        +
平台统一 Adapter
        +
现代模型可重放机制
```

其中：

- **EnterpriseRAG-Bench** 提供企业级语料、问题分类、Gold Documents、Atomic Facts 和标准评测逻辑。
- **FAB-Bench** 提供 `native_rag` 与 `gold_context` 双模式，用于区分检索问题和生成问题。
- **自建中文数据集** 用于覆盖中文、扫描 PDF、内部术语、版本冲突和真实业务问题。
- **平台 Adapter** 屏蔽 Dify、FastGPT、RAGFlow、MaxKB 的 API 差异。
- **模型可重放机制** 使检索结果可以在不同生成模型上重复运行，避免评测被单一模型锁死。

---

# 4. 评测对象

首批平台：

| 平台 | 评测重点 |
|---|---|
| Dify | 工作流、知识库 API、默认检索、可观测性、性能 |
| FastGPT | 中文知识库、工作流、知识库检索、接口自动化 |
| RAGFlow | 文档解析、复杂 PDF、深度文档理解、检索链路 |
| MaxKB | 部署便利性、默认知识库效果、接口能力、资源成本 |

后续可扩展：

- AnythingLLM
- Open WebUI
- PrivateGPT
- Onyx
- LlamaIndex 自建 RAG
- LangChain 自建 RAG
- 自研企业知识库系统

---

# 5. 数据集设计

## 5.1 公共企业级数据集

### EnterpriseRAG-Bench

建议作为主数据集。

使用内容：

- 企业内部多源文档；
- 500 道问题；
- Gold Documents；
- Gold Answer；
- Atomic Facts；
- 10 类问题。

重点使用的题型：

- Basic
- Semantic
- Intra-document
- Project-related
- Constrained
- Conflicting Info
- Completeness
- High-level
- Info Not Found

### FAB-Bench

建议作为专业领域和多跳评测集。

重点测试：

- Needle-in-a-Haystack；
- 同文档跨段推理；
- 跨文档 Multi-hop；
- 专业技术深度；
- 上下文利用；
- 支撑证据质量。

### MIRAGE

建议用于噪声鲁棒性测试。

对同一道问题运行：

1. Base：无上下文；
2. Oracle：只提供 Gold Context；
3. Mixed：Gold Context + Noise；
4. Hard Negative：Gold Context + 高相似错误文档；
5. Contradictory：Gold Context + 冲突文档。

---

## 5.2 中文基础能力数据集

建议采用：

- CMRC2018 子集；
- 中文技术 FAQ；
- 中文产品说明书；
- 中文规章制度；
- 中文企业内部 Wiki。

主要评估：

- 中文分词与 Embedding；
- 中文同义改写；
- 中文缩写和内部术语；
- 中文长句和口语问题；
- 中英文混合实体。

---

## 5.3 文档解析数据集

建议建立一套专门的文档解析包：

| 类型 | 示例 |
|---|---|
| 普通文本 PDF | 技术手册、论文、制度文件 |
| 双栏 PDF | 学术论文、会议论文 |
| 扫描 PDF | 扫描合同、旧档案 |
| 表格 PDF | 财务表、工艺参数表 |
| 图文混排 | 产品手册、流程说明 |
| 带公式 PDF | 科研论文、工程设计文档 |
| Word | 企业制度、会议纪要 |
| Excel | 参数表、清单 |
| PPT | 汇报材料 |
| HTML/Markdown | Wiki、知识库网页 |

应分别记录：

- 是否成功上传；
- 是否成功解析；
- Chunk 数量；
- 空 Chunk 比例；
- 文本覆盖率；
- 表格保留率；
- OCR 正确率；
- 解析耗时。

---

## 5.4 自建中文企业题集

推荐首期构建 1,000 道题：

| 题型 | 数量 |
|---|---:|
| 单文档事实查询 | 180 |
| 语义改写查询 | 120 |
| 内部术语和缩写 | 80 |
| 程序性步骤问题 | 120 |
| 同文档跨段推理 | 80 |
| 跨文档多跳 | 100 |
| 完整性问题 | 60 |
| 冲突和版本问题 | 60 |
| 无答案问题 | 80 |
| PDF 表格/图示问题 | 60 |
| OCR/扫描件问题 | 40 |
| 多轮对话问题 | 20 |
| **合计** | **1,000** |

题目来源建议：

```text
30% 真实历史问题
30% 专家人工构造
30% LLM 生成后人工审核
10% 线上失败案例回流
```

---

# 6. 三条评测赛道

## 6.1 Default Track：开箱即用赛道

各平台使用官方推荐配置。

允许差异：

- 默认 Chunk 策略；
- 默认 Embedding；
- 默认 Reranker；
- 默认 Prompt；
- 默认文档解析器；
- 默认检索方式。

该赛道回答：

> 普通用户不进行复杂调优时，哪个平台默认效果最好？

主要衡量：

- 产品整体能力；
- 文档解析；
- 默认配置质量；
- 易用性；
- 平台完成度。

---

## 6.2 Controlled Track：控制变量赛道

统一以下变量：

- 生成模型；
- Embedding；
- Reranker；
- Chunk Size；
- Chunk Overlap；
- Top-K；
- Rerank Top-N；
- 最大上下文 Token；
- Temperature；
- System Prompt；
- 最大输出 Token。

该赛道回答：

> 在基础模型和关键参数一致时，平台自身的 RAG 实现有何差异？

重点观察：

- 文档 ID 和 Chunk 是否正确返回；
- Retriever 调用是否一致；
- Context 是否被平台截断；
- Reranker 是否按预期工作；
- Prompt 是否被平台额外修改；
- API 与工作流是否引入额外延迟。

---

## 6.3 Tuned Track：平台最优赛道

允许每个平台使用自身优势：

- 混合检索；
- 父子 Chunk；
- Knowledge Graph；
- Query Rewrite；
- Multi-query；
- Agentic Search；
- 自定义文档解析器；
- 自定义 Workflow；
- 自定义 Reranker。

该赛道回答：

> 在合理调优后，各平台最终能达到什么能力上限？

该赛道必须记录所有调优参数，避免形成不可复现的“专家手工比赛”。

---

# 7. 现代模型配置建议

评测不应绑定一个模型。建议至少配置三个生成模型档位。

## 7.1 开源本地模型

选择 2026 年主流、可本地或私有部署的模型，例如：

- Qwen3 系列；
- DeepSeek 系列；
- 其他主流开源指令模型。

用途：

- 测试私有化部署；
- 测试本地推理成本；
- 对比旧 Qwen2.5 结果；
- 保证部分实验可离线复现。

## 7.2 强闭源模型

选择一个主流强模型作为高能力上限。

用途：

- 检查平台检索结果在强生成模型下能否得到充分利用；
- 降低“小模型不会用上下文”对平台判断的影响；
- 作为 Gold Context 模式下的 Generator。

## 7.3 Judge 模型

Judge 与 Generator 应尽量不同模型家族。

建议：

- Generator A 对应 Judge B；
- Generator B 对应 Judge A；
- 关键样本使用第三个 Judge 或人工复核。

不建议：

```text
Qwen 生成
→ 同一个 Qwen 自己打分
```

---

# 8. 双模式评测

每道题至少运行两种模式。

## 8.1 Native RAG

```text
Question
→ 平台原生知识库
→ Retriever
→ Reranker
→ Context
→ Generator
→ Answer
```

测量完整平台效果。

## 8.2 Gold Context

```text
Question
+ Gold Context
→ Generator
→ Answer
```

绕过平台检索，只测试生成模型能否根据正确证据回答。

## 8.3 诊断逻辑

| Native RAG | Gold Context | 主要问题 |
|---|---|---|
| 低 | 高 | 文档解析、检索或重排问题 |
| 低 | 低 | 生成模型、Prompt 或问题本身过难 |
| 高 | 高 | 系统正常 |
| 高 | 低 | 需要检查 Judge、随机性或上下文构造 |

定义：

\[
Retrieval\ Gap =
Score_{GoldContext} - Score_{NativeRAG}
\]

Retrieval Gap 越大，说明平台检索链路越可能是瓶颈。

---

# 9. 平台 Adapter 设计

建议目录结构：

```text
rag-platform-benchmark/
├── adapters/
│   ├── base.py
│   ├── dify.py
│   ├── fastgpt.py
│   ├── ragflow.py
│   └── maxkb.py
├── datasets/
├── configs/
├── runners/
├── evaluators/
├── reports/
├── traces/
└── scripts/
```

统一 Adapter 接口：

```python
class RAGPlatformAdapter:
    def create_knowledge_base(self, config):
        ...

    def upload_documents(self, files):
        ...

    def wait_until_indexed(self):
        ...

    def query(self, question, conversation_id=None):
        ...

    def get_retrieval_trace(self):
        ...

    def delete_knowledge_base(self):
        ...
```

---

# 10. 统一输入输出格式

## 10.1 Benchmark 样本格式

```json
{
  "question_id": "conflict_001",
  "category": "conflicting_info",
  "language": "zh",
  "question": "当前有效的设备维护周期是多少？",
  "gold_answer": "根据2026年7月生效的规范，维护周期为90天。",
  "answer_facts": [
    "有效规范于2026年7月生效",
    "维护周期为90天"
  ],
  "gold_document_ids": [
    "maintenance_policy_v3"
  ],
  "valid_document_ids": [
    "maintenance_change_notice"
  ],
  "contradictory_document_ids": [
    "maintenance_policy_v2"
  ],
  "answerable": true
}
```

## 10.2 平台运行结果格式

```json
{
  "run_id": "20260804_dify_controlled_q001",
  "platform": "dify",
  "platform_version": "x.y.z",
  "track": "controlled",
  "question_id": "conflict_001",
  "answer": "当前维护周期为90天。",
  "retrieved_items": [
    {
      "rank": 1,
      "document_id": "maintenance_policy_v3",
      "chunk_id": "chunk_12",
      "score": 0.91,
      "rerank_score": 0.87,
      "text": "..."
    }
  ],
  "citations": [
    "maintenance_policy_v3"
  ],
  "latency_ms": {
    "total": 2210,
    "retrieval": 180,
    "rerank": 120,
    "generation": 1770
  },
  "usage": {
    "prompt_tokens": 3020,
    "completion_tokens": 180
  },
  "errors": []
}
```

---

# 11. 评测指标

## 11.1 文档解析

- File Ingestion Success Rate
- Parse Success Rate
- Effective Chunk Count
- Empty Chunk Rate
- Text Coverage
- OCR Accuracy
- Table Preservation
- Parsing Latency
- Index Build Time

## 11.2 检索

- Hit@1 / 3 / 5 / 10
- Recall@1 / 3 / 5 / 10
- Precision@K
- MRR
- nDCG@K
- Invalid Extra Documents
- Atomic Fact Context Coverage
- Gold Document Rank
- Reranker Gain

## 11.3 生成

- Answer Correctness
- Atomic Fact Completeness
- Faithfulness
- Answer Relevance
- Numerical Accuracy
- Citation Correctness
- Citation Completeness
- Technical Depth
- Support Quality

## 11.4 鲁棒性

- Unanswerable Accuracy
- False Refusal Rate
- Noise Vulnerability
- Conflict Resolution Accuracy
- Recency Accuracy
- Multi-hop Success Rate
- Completeness Query Recall
- Paraphrase Stability
- Multi-turn Stability

## 11.5 系统性能

- Indexing Throughput
- P50 / P95 / P99 Latency
- TTFT
- TPOT
- QPS
- Timeout Rate
- Error Rate
- CPU / GPU / Memory
- Vector Storage
- Token Cost
- Cost per 1,000 Queries
- Update-to-Searchable Delay

---

# 12. 执行流程

## 阶段一：环境准备

任务：

1. 固定硬件和部署环境。
2. 安装四个平台指定版本。
3. 配置统一模型服务。
4. 配置统一向量数据库条件，能统一时尽量统一。
5. 保存 Docker Compose、环境变量和版本快照。
6. 检查 API 是否可自动创建知识库和上传文档。

产物：

- 环境说明；
- 平台版本表；
- Docker 配置；
- 模型配置；
- 硬件配置；
- API 连通性测试。

---

## 阶段二：Adapter 开发

任务：

1. 实现统一建库接口。
2. 实现批量上传。
3. 实现索引完成检测。
4. 实现问题批量调用。
5. 尽可能获取检索 Trace。
6. 保存原始 API 返回。
7. 统一异常处理和重试。

产物：

- 四个平台 Adapter；
- API 示例；
- 单元测试；
- 错误码表；
- 平台能力矩阵。

---

## 阶段三：小规模冒烟测试

使用 20—50 道题。

目标：

- 检查文档 ID 映射；
- 检查 Top-K；
- 检查回答和引用；
- 检查空 Chunk；
- 检查 API 限流；
- 检查结果是否可稳定重放。

只有通过冒烟测试，才开始大规模评测。

---

## 阶段四：公共数据集评测

运行：

- EnterpriseRAG-Bench；
- FAB-Bench；
- MIRAGE 子集；
- 中文基础数据集；
- 文档解析数据集。

每个平台分别运行：

- Default Track；
- Controlled Track；
- Tuned Track；
- Native RAG；
- Gold Context。

---

## 阶段五：现代模型重放

保存平台检索得到的 Context 后，分别交给不同生成模型。

目标：

- 测量检索结果对模型的稳定性；
- 判断平台排名是否依赖某一个模型；
- 对比旧模型和现代模型；
- 避免每次换模型都重新导入和检索。

建议将检索和生成拆为两个可独立运行的阶段：

```text
Retrieval Run
→ 保存 Context Snapshot
→ Generation Replay
→ Judge Replay
```

---

## 阶段六：性能压力测试

测试场景：

### 建库

- 100 文档；
- 1,000 文档；
- 10,000 文档；
- 不同总 Token 规模。

### 查询并发

- 1；
- 5；
- 10；
- 20；
- 50 并发。

### 查询更新混合

- 持续查询；
- 同时新增文档；
- 替换旧版本；
- 删除过期文档；
- 测量新知识生效时间。

### 长时间稳定性

- 连续运行；
- 监控内存增长；
- 监控失败率；
- 监控任务积压；
- 监控向量库和数据库压力。

---

# 13. 人工评测与质量控制

自动 Judge 不能完全替代人工。

建议：

1. 每个平台随机抽取至少 100 道题人工复核。
2. 对所有冲突信息和无答案问题人工复核。
3. 对 Judge 分歧样本全部复核。
4. 对高自动分但业务明显错误的样本建立黑名单。
5. 数字、日期、单位和引用使用规则校验。
6. 记录人工与 Judge 一致率。
7. Judge 输入顺序随机化。
8. 关键结果至少使用两个不同模型家族评判。

人工标签建议：

```text
完全正确
基本正确但不完整
部分正确
证据不足
事实错误
拒答错误
幻觉
引用错误
```

---

# 14. 公平性原则

## 14.1 Top-K 必须透明

必须记录：

- Retriever 实际返回数量；
- Reranker 后保留数量；
- 进入 Prompt 的 Chunk 数量；
- 进入 Prompt 的总 Token；
- 平台是否截断。

## 14.2 平台版本必须冻结

每次评测必须记录：

- Git Commit 或 Release Version；
- Docker 镜像 Tag；
- 数据库版本；
- 插件版本；
- 模型版本；
- API 版本；
- 测试日期。

## 14.3 不允许只报告平均分

必须报告：

- 各题型；
- 各文档类型；
- 各语言；
- 各难度；
- 各模型；
- 各赛道；
- 失败率；
- 置信区间。

## 14.4 不把默认赛道和调优赛道混合排名

Default、Controlled、Tuned 必须分别排名。

---

# 15. 推荐实施节奏

## 第一阶段：最小可行版本

目标：

- 四个平台 Adapter；
- 200 道题；
- 两个生成模型；
- 一个 Judge；
- Default + Controlled；
- Native RAG + Gold Context。

最小题集：

| 类型 | 数量 |
|---|---:|
| 中文事实检索 | 40 |
| 程序性回答 | 30 |
| PDF 条款/表格 | 30 |
| 扫描件 OCR | 20 |
| 多文档问题 | 25 |
| 冲突/版本 | 15 |
| 无答案 | 20 |
| 噪声鲁棒性 | 20 |
| **合计** | **200** |

最小指标：

```text
Parse Success Rate
Recall@5
MRR
Answer Correctness
Atomic Fact Completeness
Faithfulness
Unanswerable Accuracy
Noise Vulnerability
P95 Latency
Indexing Time
```

## 第二阶段：完整公开评测

扩展到：

- EnterpriseRAG-Bench 500 题；
- 中文自建 1,000 题；
- FAB-Bench 200 题；
- 多 Judge；
- Tuned Track；
- 性能压力测试；
- 完整原始结果发布。

## 第三阶段：持续 Benchmark

建立：

- 月度或版本级回归；
- 平台版本更新重测；
- 新模型重放；
- 新失败案例加入题库；
- 公开结果看板；
- 可下载原始 Trace。

---

# 16. 预期产物

最终应公开或内部沉淀以下产物：

```text
1. 平台 Adapter 代码
2. 数据集下载和预处理脚本
3. 平台配置文件
4. Docker Compose
5. Benchmark 问题集
6. Gold Answer 和 Gold Documents
7. 原始回答
8. 原始检索 Trace
9. Judge 输入输出
10. 汇总指标
11. 失败案例报告
12. 环境和版本快照
13. 一键运行脚本
14. 可视化报告
```

推荐仓库结构：

```text
rag-platform-benchmark/
├── README.md
├── LICENSE
├── adapters/
├── datasets/
├── configs/
├── docker/
├── evaluators/
├── judges/
├── runners/
├── traces/
├── results/
├── reports/
├── scripts/
└── docs/
```

---

# 17. 风险与应对

## 风险一：平台 API 无法返回检索详情

应对：

- 标记为 Black-box Retrieval；
- 只计算端到端指标；
- 通过引用和回答文本做有限诊断；
- 在报告中明确指标不可比范围。

## 风险二：平台难以统一 Chunk

应对：

- Controlled Track 尽量统一；
- Default Track 保留平台差异；
- 同时报告实际 Chunk 和 Token；
- 不强行把无法统一的结果解释成纯算法差异。

## 风险三：模型快速过时

应对：

- 保存 Context Snapshot；
- 分离 Retrieval 和 Generation；
- 支持新模型重放；
- 不把结论绑定到单一模型。

## 风险四：LLM Judge 不稳定

应对：

- 多 Judge；
- 人工抽检；
- 结构化 Rubric；
- 规则指标；
- 保存完整 Judge Trace。

## 风险五：数据集泄漏

应对：

- 公共数据集用于横向比较；
- 自建私有题集用于最终验收；
- 为部分测试题保留隐藏集；
- 定期轮换题目。

## 风险六：平台版本更新导致结果失效

应对：

- 版本冻结；
- 定期回归；
- 结果绑定版本；
- 不发布脱离版本的永久性结论。

---

# 18. 最终推荐

建议按以下优先级推进：

## 优先级 1：先实现统一 Adapter

没有 Adapter，就无法建立持续评测。首要工作不是增加更多指标，而是保证四个平台可以：

- 自动建库；
- 自动上传；
- 自动等待索引完成；
- 自动查询；
- 自动保存 Trace；
- 自动清理环境。

## 优先级 2：先完成 200 题最小版本

不要一开始直接运行 50 万文档和 1,000 道题。先用 200 题验证：

- 数据结构；
- 平台 API；
- 指标；
- Judge；
- Gold Context；
- 报告流程。

## 优先级 3：采用两阶段架构

必须拆成：

```text
Retrieval Benchmark
        +
Generation Replay
```

这是避免模型过时和提高可比性的关键。

## 优先级 4：采用三赛道

必须同时保留：

- Default；
- Controlled；
- Tuned。

任何单一赛道都无法完整回答平台选型问题。

## 优先级 5：将 EnterpriseRAG-Bench 作为主框架

推荐直接复用其：

- 问题分类；
- Gold Documents；
- Atomic Facts；
- Correctness；
- Completeness；
- Document Recall；
- Invalid Extra Documents；
- JSONL 结果结构。

## 优先级 6：采用 FAB-Bench 的双模式诊断

为每道题同时运行：

- Native RAG；
- Gold Context。

这可以显著提高错误归因能力。

---

# 19. 一句话项目定义

> 构建一套面向 Dify、FastGPT、RAGFlow、MaxKB 的平台无关 RAG Benchmark，通过统一 Adapter、企业级数据集、三赛道控制、Native RAG / Gold Context 双模式和可重放生成评测，实现可复现、可解释、可持续更新的平台能力对比。
