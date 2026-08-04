# MatrixOne Intelligence（MOI）官方一手证据研究

> 截止日期：2026-08-04  
> 研究对象：MatrixOrigin 的 **MatrixOne Intelligence（MOI）**  
> 证据范围：MatrixOrigin/MatrixOne 官方网站、官方文档、官方 GitHub 组织及其链接的论文。本文不把 `moi-ai.com` 的 MoiAI 纳入产品事实或竞品判断。

## 证据标记

- **[事实]**：官方文档、公开代码或版本记录直接陈述/实现的内容。
- **[厂商主张]**：官方营销页或白皮书中的价值、性能、效果表述；未经独立复现。
- **[推断]**：由多个一手事实推导出的定位、用户或测试建议。
- **[检索结论]**：本次在限定官方来源中的检索结果；“未发现”不等于绝对不存在。

## 执行摘要

1. **[事实] 身份已确认。** MatrixOrigin 在官方发布中把产品全称写为 “MatrixOne Intelligence（MOI）”；当前产品页将其定义为覆盖多源数据接入、处理、治理、检索和智能应用的一站式 Data+AI 平台。它不是 `moi-ai.com` 所描述的桌面个人助理。[GTC 官方发布](https://www.matrixorigin.io/blog/martrixone-gtc-cloudsogma) · [MOI 产品页](https://www.matrixorigin.io/moi)
2. **[事实] Native RAG 边界已经能由官方材料闭合到产品级链路。** 数据进入 MOI 后，可经解析、清洗、切分、向量化与索引，在 Data Exploration 中进行跨文档/表对象检索和多轮问答；结构化表对象会走 NL2SQL。只有已完成向量化的文件参与检索，停用分块不参与召回。[工作流文档](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow.html) · [Data Exploration 文档](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/data_mgt/data_explore.html)
3. **[事实] Dify 与 DeerFlow 是集成轨，不应计入 Native MOI 成绩。** MOI 可以把处理后的 JSON 导出到 Dify 知识库，也可以把自身 RAG 服务接入 DeerFlow；但最终的 Dify 应用编排/生成，以及 DeerFlow 的模型、工具调用和交互层，分别属于外部系统。[多模态 RAG 数据准备模板](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow_template/multimodal_doc_rag_prep.html) · [DeerFlow 集成文档](https://docs.matrixorigin.cn/moi/en/4.0/develop/deerflow.html)
4. **[事实 + 未知] 已有官方流式分析 SDK，但“Native Explore 公共 API/trace 契约”仍未完全公开。** Go SDK 实现了 `/byoa/api/v1/data_asking/analyze` 的 SSE 调用，并暴露分类、分解、RAG chunk/answer chunk、NL2SQL、完成和错误事件；请求模型也支持数据库、文件及文件范围。然而事件载荷仍多为通用映射，公开材料没有给出稳定的 chunk score、页码/坐标、引用绑定、token/cost 等完整 schema，也未证明该端点与当前 Explore UI 的所有行为一一等价。[Go SDK：流式分析实现](https://github.com/matrixorigin/moi-go-sdk/blob/b28c3bbe19904b8b2d31bc6aad776bbedb954103/data_asking.go#L265-L395) · [Go SDK：请求模型](https://github.com/matrixorigin/moi-go-sdk/blob/b28c3bbe19904b8b2d31bc6aad776bbedb954103/models.go#L2029-L2105)
5. **[推断] 正确定位应是“企业多模态数据到 AI 应用/Agent 的基础设施与工作台”。** 其主要价值是把私有的结构化、半结构化和非结构化数据变成可检索、可问答、可供应用调用的 AI-ready 数据，并提供云端、私有化和本地部署选项；不是“扫描整台电脑、代写 Word/PPT、收发邮件和管日历”的桌面自动化代理。[MOI 介绍](https://docs.matrixorigin.cn/moi/en/4.0/overview/matrixone-intelligence-introduction.html) · [MOI 4.1 发布](https://matrixorigin.cn/blog/moi4-1-ai-data-zh)

## 1. 身份与产品边界

### 1.1 名称裁决

**[事实]** MatrixOrigin 于 2026-03-23 的官方 GTC 发布明确使用 “MatrixOne Intelligence（MOI）”；官方英文产品页也以 “MatrixOne Intelligence” 为标题。文档偶尔使用 “MO Intelligence” 的短写，但所描述的仍是同一套多模态数据智能平台。[GTC 官方发布](https://www.matrixorigin.io/blog/martrixone-gtc-cloudsogma) · [MOI 产品页](https://www.matrixorigin.io/moi) · [产品介绍文档](https://docs.matrixorigin.cn/moi/en/4.0/overview/matrixone-intelligence-introduction.html)

**[事实]** 本仓库两份早期稿件把 MOI 解释成 `moi-ai.com` 的 MoiAI，并据此引入“桌面 Agent、全盘本地文件、Word/PPT/邮件/日历动作”及 NotebookLM/ima/ChatDOC/AnythingLLM 竞品框架；这些内容与 MatrixOrigin 官方产品身份不一致，应视为身份污染而非待验证假设。[内部 MoiAI 定位稿](../moi-product-positioning-and-local-test.md) · [内部竞品稿](../moi-rag-competitor-landscape.md) · [MatrixOrigin MOI 产品页](https://www.matrixorigin.io/moi)

### 1.2 MOI、MatrixOne 与外部应用的关系

| 层级 | 官方可确认事实 | 本研究采用的边界 |
|---|---|---|
| MatrixOne 数据库 | **[事实]** MatrixOne 是开源分布式数据库，覆盖 OLTP、OLAP、全文与向量能力，并把 RAG 应用列为使用场景之一。[官方仓库](https://github.com/matrixorigin/matrixone) | 数据与检索底座，不等同于完整 MOI 产品。 |
| MatrixOne Intelligence | **[事实]** MOI 在数据库之上组织多模态数据接入、解析治理、索引检索、Data Exploration、数据问答与应用服务。[产品介绍](https://docs.matrixorigin.cn/moi/en/4.0/overview/matrixone-intelligence-introduction.html) | 本次原生 RAG 评测主体。 |
| Dify / DeerFlow / LangChain / MCP 客户端 | **[事实]** 官方把这些描述为可连接或消费 MOI 数据/RAG 能力的生态集成。[Dify 模板](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow_template/multimodal_doc_rag_prep.html) · [DeerFlow 集成](https://docs.matrixorigin.cn/moi/en/4.0/develop/deerflow.html) · [MCP 文档](https://docs.matrixorigin.cn/moi/en/4.0/develop/mcp/mcp.html) | 外部应用或集成轨；不得把其生成质量归因于 Native MOI。 |

## 2. 官方定义的产品架构与能力范围

### 2.1 三层产品结构

**[事实]** 官方介绍把 MOI 分为三层：底层是统一管理结构化、半结构化和非结构化数据的数据库与 AI 服务；中层负责接入、清洗、转换、解析、增强与向量化；上层提供混合检索、多路召回和工具服务，用于多模态搜索、智能问答与自动报告等应用。[产品介绍文档](https://docs.matrixorigin.cn/moi/en/4.0/overview/matrixone-intelligence-introduction.html)

**[事实]** 同一介绍还列出 OLTP/OLAP、向量和全文检索、实体/关系/摘要抽取、知识图谱、语义/关键词/元数据索引、RBAC、血缘、审计，以及 Dify、LangChain、MCP 等集成能力。这说明官方产品边界是企业数据治理与 AI 数据服务，而不是单一聊天前端。[产品介绍文档](https://docs.matrixorigin.cn/moi/en/4.0/overview/matrixone-intelligence-introduction.html)

### 2.2 部署与版本

**[事实]** 官方产品页承诺私有化部署和云服务；MOI 4.1 发布进一步写明公有云、私有云和本地部署，并强调结构化与非结构化混合问答。[MOI 产品页](https://www.matrixorigin.io/moi) · [MOI 4.1 发布](https://matrixorigin.cn/blog/moi4-1-ai-data-zh)

**[事实 + 风险]** 4.1 发布于 2026-02-27，但当前公开英文文档路径仍为 `/moi/en/4.0/`，而 2026 年发布记录持续更新到 6 月。产品版本、租户构建、功能开关与文档版本可能不同，任何基准必须记录实际 build/tenant，而不能只写“MOI 4.x”。[MOI 4.1 发布](https://matrixorigin.cn/blog/moi4-1-ai-data-zh) · [2026 Release Notes](https://docs.matrixorigin.cn/moi/en/4.0/release-notes/2026.html)

## 3. RAG 与知识库能力：证实到什么程度

### 3.1 数据进入、解析、清洗、切分与向量化

**[事实]** MOI 工作流支持文档 `doc/docx/ppt/pptx/txt/md/pdf/xls/xlsx`、图片 `jpg/jpeg/bmp/png`、视频 `mp4/mov/mkv` 和音频 `wav/mp3/aac/flac`；可按单次、定时或数据加载触发。可视化工作流包含文档/图片/音视频解析、切分、文本嵌入、抽取、清洗和增强等算子。[工作流文档](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow.html)

**[事实]** 文档解析器会抽取文本、图片、表格和标题；文档公开列出了图像描述、OCR、文本嵌入和信息抽取所用的模型/算子。切分最大长度可配置为 100–2000，默认 1024，并支持 overlap；Excel/CSV 按行切分。清洗可覆盖 PII、文本规范化、URL 等噪声去除和 N-gram 去重。[工作流文档](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow.html)

**[厂商主张]** 以上是格式、算子和配置的“支持声明”，不是解析准确率证据。官方文档没有给出这些格式上的 OCR、表格、公式、跨页语义或切分质量的可复现实验，因此不能由“支持 PDF/Excel/图片”推出“复杂文档解析准确”。[工作流文档](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow.html)

### 3.2 原生 Data Exploration 与混合问答

**[事实]** Data Exploration 被官方定义为 MOI 平台的跨模态文件检索与问答能力，可同时检索多个文档和表对象、进行摘要和多轮问答；只有已完成 embedding 的文件进入检索，禁用的 chunk 不参与召回。表对象查询会触发 NL2SQL，且可以配置业务术语、同义词、业务逻辑和示例。[Data Exploration 文档](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/data_mgt/data_explore.html)

**[事实]** 4.1 官方发布进一步宣称可把 NL2SQL 与 RAG 放在同一自然语言查询中，支持多个独立知识库、上下文记忆和数据血缘；这与“结构化 + 非结构化混合问答”的产品方向一致，但仍属于版本发布声明，需在实际租户中验证启用状态。[MOI 4.1 发布](https://matrixorigin.cn/blog/moi4-1-ai-data-zh)

### 3.3 Native RAG 链路

| 阶段 | 官方可确认输入/行为 | 可观察输出或当前缺口 |
|---|---|---|
| 数据接入 | **[事实]** 文件、表对象及多源数据进入 Catalog/Database/Volume 与工作流。[Data Center 文档](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/data_mgt/catalog.html) | 原始文件、表、目录层级。 |
| 数据准备 | **[事实]** 解析、清洗、切分、抽取、增强和 embedding 可在可视化 DAG 中配置、预览和比较。[工作流文档](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow.html) | 分块与处理结果可预览；公开材料未给解析准确率。 |
| 索引与召回 | **[事实]** 已 embedding 文件参与 Data Exploration；官方架构列出语义、关键词、元数据索引及多路召回。[Data Exploration](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/data_mgt/data_explore.html) · [产品介绍](https://docs.matrixorigin.cn/moi/en/4.0/overview/matrixone-intelligence-introduction.html) | 检索结果存在；默认 top-k、阈值、reranker 和混合权重未在公开文档中定型。 |
| 分析与回答 | **[事实]** Data Exploration 支持跨文件问答、多轮对话和表对象 NL2SQL；Go SDK 存在流式 data asking/analysis 端点。[Data Exploration](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/data_mgt/data_explore.html) · [Go SDK](https://github.com/matrixorigin/moi-go-sdk/blob/b28c3bbe19904b8b2d31bc6aad776bbedb954103/data_asking.go#L265-L395) | SDK 有 RAG chunks、answer chunks、NL2SQL 等事件；UI Explore 与 SDK 的完整行为映射未知。 |
| 证据与追踪 | **[事实]** 产品页承诺回答归因和全链路可追溯；发布记录出现 evidence citation、source binding、文件范围和证据保留相关能力/修复。[产品页](https://www.matrixorigin.io/moi) · [2026 Release Notes](https://docs.matrixorigin.cn/moi/en/4.0/release-notes/2026.html) | 精确到页/块/坐标的稳定引用 schema、检索 score、trace ID、token/cost 与导出契约未公开闭合。 |

### 3.4 证据可见性与调试

**[事实]** Data Center 支持查看解析内容，并可下载包含解析 JSON、完整 Markdown、图片/表格与 embedding JSON 的 ZIP。当前文档明确写明，解析后原文映射只支持 PDF，因此“所有格式都能逐页/逐位置引用”不能视为已证实。[Data Center 文档](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/data_mgt/catalog.html)

**[事实 + 风险]** 2026 Release Notes 报告了新的 RAG Agent Runtime、Explore Agent、A2A、工具调用、证据引用、文件检索和 SQL 等能力；同一页面也记录过多轮对话丢失所选文件范围、数据库范围串扰、表证据丢失、关键词检索和答案来源绑定等修复。这些记录证明团队在处理 trace/citation/scope，但也构成版本相关的回归风险，不是“问题已经永久消失”的证据。[2026 Release Notes](https://docs.matrixorigin.cn/moi/en/4.0/release-notes/2026.html)

### 3.5 API、SDK 与集成边界

**[事实]** Go SDK 的流式分析实现向 `/byoa/api/v1/data_asking/analyze` 发起请求并消费 SSE；事件包含初始化、分类、问题分解、步骤开始/完成、RAG `chunks`/`answer_chunk`、NL2SQL、完成与错误。请求模型支持数据库 ID、全部/不选/指定文件范围、文件 ID 列表、问题和 session 信息。[Go SDK：实现](https://github.com/matrixorigin/moi-go-sdk/blob/b28c3bbe19904b8b2d31bc6aad776bbedb954103/data_asking.go#L265-L395) · [Go SDK：模型](https://github.com/matrixorigin/moi-go-sdk/blob/b28c3bbe19904b8b2d31bc6aad776bbedb954103/models.go#L2029-L2105)

**[事实]** Python SDK 把自身描述为 MOI Catalog Service 客户端，覆盖 Catalog/Database/Table/Volume/File、连接器、用户/角色以及 GenAI/NL2SQL；API reference 列出 `analyze_data_stream`。这证明官方提供了程序化分析入口，但不等于公开了完整、版本稳定的 Explore API 契约。[Python SDK](https://github.com/matrixorigin/moi-python-sdk) · [Python API Reference](https://github.com/matrixorigin/moi-python-sdk/blob/4909a6a2ec45e0231910d6d13aed2924c58aa0ab/docs/api_reference.md#L184-L189)

**[事实]** MOI MCP 允许 AI 助手创建连接器、加载数据、创建工作流和检索解析数据；文档没有列出操控 Word/PPT、邮件、日历或整机文件系统的工具，因此不能用 MCP 的存在推导这些桌面动作能力。[MCP 文档](https://docs.matrixorigin.cn/moi/en/4.0/develop/mcp/mcp.html)

**[事实]** 多模态 RAG 数据准备模板把 MOI 处理后的 JSON 发送到 Dify 知识库，而“构建 RAG 应用”发生在 Dify Studio。DeerFlow 文档则把 MOI 明确称为 RAG service，同时要求 DeerFlow 侧配置基础模型、工具调用并选择文件。因此，这两条链路中的最终回答质量必须拆分归因。[Dify 数据准备模板](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow_template/multimodal_doc_rag_prep.html) · [DeerFlow 集成文档](https://docs.matrixorigin.cn/moi/en/4.0/develop/deerflow.html)

## 4. 目标用户与价值主张

### 4.1 官方直接表述

**[事实]** 官方把 MOI 面向对象写为企业，强调把多源、多模态数据从接入、治理转成可供 BI、Agentic RAG、微调和多模态搜索使用的数据资产；GenAI Workspace 又强调不要求使用者具备专业数据处理背景。这支持“企业平台 + 低门槛业务探索工作台”的双层用户界面。[MOI 产品页](https://www.matrixorigin.io/moi) · [GenAI Workspace 概览](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/overview.html)

**[厂商主张]** 官方方案页将价值描述为动态更新的多模态知识库、混合/向量检索、从洞察到行动和较低 TCO；这些是产品承诺，未附可复现成本或质量基线，不能直接转写成“毫秒级且更便宜”的已验证结论。[Agentic RAG 方案页](https://www.matrixorigin.io/solution/agentic-rag)

### 4.2 由事实推导的用户角色

| 用户角色 | 判断 | 依据与价值 |
|---|---|---|
| 企业数据/AI 工程团队 | **[推断：高置信]** 核心建设者 | 负责连接、解析、清洗、索引、治理和把私有数据变成 AI-ready 资产。[产品介绍](https://docs.matrixorigin.cn/moi/en/4.0/overview/matrixone-intelligence-introduction.html) |
| Agent/RAG 应用开发者 | **[推断：高置信]** 核心消费者 | 通过数据服务、SDK、Dify/DeerFlow/LangChain/MCP 集成消费检索与分析能力。[Go SDK](https://github.com/matrixorigin/moi-go-sdk) · [MCP 文档](https://docs.matrixorigin.cn/moi/en/4.0/develop/mcp/mcp.html) |
| 平台、安全和数据治理管理员 | **[推断：中高置信]** 采购/运维相关角色 | RBAC、多租户、血缘、审计以及私有/本地部署直接对应企业控制面需求。[产品介绍](https://docs.matrixorigin.cn/moi/en/4.0/overview/matrixone-intelligence-introduction.html) · [MOI 4.1 发布](https://matrixorigin.cn/blog/moi4-1-ai-data-zh) |
| 业务分析师/知识工作者 | **[推断：中高置信]** Explore 终端用户 | 可在较低数据处理门槛下跨文档和表对象检索、问答、摘要及 NL2SQL。[GenAI Workspace 概览](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/overview.html) · [Data Exploration](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/data_mgt/data_explore.html) |

**[推断]** 因此，最稳妥的价值表达是：MOI 减少企业在多模态数据接入、治理、索引、检索和 AI 应用之间的拼装成本，并用统一数据层支持混合问答与可追踪应用；不应把其价值收窄为个人桌面生产力，也不应承诺任意模型、任意文件和任意桌面动作。[产品介绍](https://docs.matrixorigin.cn/moi/en/4.0/overview/matrixone-intelligence-introduction.html) · [MOI 产品页](https://www.matrixorigin.io/moi)

## 5. GitHub、源代码与研究证据成熟度

### 5.1 公开代码面

**[事实]** 截至本次检索日期，MatrixOrigin GitHub 组织按 `moi` 过滤可见 `moi-benchmark`、`moi-python-sdk` 和 `moi-go-sdk` 三个公开仓库；两个 SDK 均为 Apache-2.0。此结果证明存在公开客户端/基准资产，但不能据此断言服务端必然闭源或没有其他名称的实现。[官方组织过滤页](https://github.com/orgs/matrixorigin/repositories?q=moi&type=all) · [Go SDK](https://github.com/matrixorigin/moi-go-sdk) · [Python SDK](https://github.com/matrixorigin/moi-python-sdk)

**[事实]** 本文对 Go SDK 的判断固定在 commit `b28c3bbe19904b8b2d31bc6aad776bbedb954103`，对 Python SDK 固定在 commit `4909a6a2ec45e0231910d6d13aed2924c58aa0ab`，以避免未来主分支变化导致证据漂移。[Go SDK 固定版本](https://github.com/matrixorigin/moi-go-sdk/tree/b28c3bbe19904b8b2d31bc6aad776bbedb954103) · [Python SDK 固定版本](https://github.com/matrixorigin/moi-python-sdk/tree/4909a6a2ec45e0231910d6d13aed2924c58aa0ab)

### 5.2 论文与白皮书

**[事实]** MatrixOne 官方仓库链接的研究论文《Version Control System for Data with MatrixOne》是 2026-04-05 提交的 arXiv 预印本，研究重点是大规模表上的 snapshot/branch/diff/merge 数据版本控制；它不评估 MOI 的检索召回、答案正确率、引用忠实度、延迟或成本。[arXiv 论文](https://arxiv.org/abs/2604.03927) · [MatrixOne 官方仓库](https://github.com/matrixorigin/matrixone)

**[事实]** MOI 官方白皮书入口与发布文章描述了架构、从数据到 Agent、混合全文/语义检索、多模态能力和行业案例，但属于厂商材料，未提供公开的 RAG benchmark 协议、测试集、逐题输出和复现脚本。[白皮书入口](https://www.matrixorigin.io/whitepaper) · [白皮书发布文章](https://www.matrixorigin.io/blog/moi-whitepaper-launch-zh)

**[检索结论]** 在本次限定的官方站点、文档、官方 GitHub 与其链接论文中，未发现同行评审或可复现的 MOI RAG 质量评估。该结论只表示“本次官方来源未发现”，不表示其他渠道绝对不存在；因此“99% 准确率”“零幻觉”“业界最佳 RAG”等说法目前均没有足够一手证据。[官方白皮书入口](https://www.matrixorigin.io/whitepaper) · [官方仓库列表](https://github.com/orgs/matrixorigin/repositories?q=moi&type=all)

## 6. 对仓库内既有定位的逐项核验

| 既有表述 | 裁决 | 官方证据与修订建议 |
|---|---|---|
| “MOI 是 MatrixOrigin 的 MatrixOne Intelligence” | **[事实：确认]** | 使用全称 MatrixOne Intelligence（MOI）。[官方发布](https://www.matrixorigin.io/blog/martrixone-gtc-cloudsogma) |
| “MOI 是桌面 AI Agent” | **[事实：反驳当前证据]** | 官方定义为企业 Data+AI/多模态数据智能平台；应删除“桌面 Agent”身份。[产品页](https://www.matrixorigin.io/moi) |
| “自动扫描整台电脑并持续索引本地文件系统” | **[未证实]** | 官方证实文件上传、连接器、Catalog/Volume、工作流和本地/私有部署，但未证实桌面文件 watcher、全盘扫描或离线客户端。私有部署不等于设备本地运行。[Data Center](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/data_mgt/catalog.html) · [MOI 4.1 发布](https://matrixorigin.cn/blog/moi4-1-ai-data-zh) |
| “RAG 只是入口，Word/PPT/邮件/日历/文件动作才是核心差异” | **[身份污染]** | 官方高层叙事确有“data-to-agent”“洞察到行动”和自动报告，但没有上述具体桌面动作。改写为“数据到 AI 应用/Agent 的链路”。[产品介绍](https://docs.matrixorigin.cn/moi/en/4.0/overview/matrixone-intelligence-introduction.html) · [Agentic RAG 方案](https://www.matrixorigin.io/solution/agentic-rag) |
| “核心用户是法律、金融、咨询桌面专业人士” | **[未证实/过窄]** | 官方案例可覆盖文档与行业数据，但直接定位面向企业数据治理、应用开发和业务探索；用户画像应以企业数据/AI 团队、开发者、管理员和 Explore 业务用户为主。[产品页](https://www.matrixorigin.io/moi) · [GenAI Workspace](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/overview.html) |
| “支持云端与私有部署” | **[事实：确认]** | 可表述为公有云、私有云/私有化和本地部署；具体功能与 SLA 仍需按版本和合同核对。[MOI 4.1 发布](https://matrixorigin.cn/blog/moi4-1-ai-data-zh) |
| “可任意选择模型” | **[部分证实，不宜泛化]** | 工作流公开了可配置/指定的模型算子，DeerFlow 侧也可配置模型；但没有证据证明所有模块、所有部署都支持任意模型无条件替换。[工作流文档](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow.html) · [DeerFlow](https://docs.matrixorigin.cn/moi/en/4.0/develop/deerflow.html) |
| “官方几乎没有引用/trace 信息” | **[部分过时]** | 产品页、Release Notes、Data Center 已出现归因、证据引用、来源绑定、文件范围、PDF 原文映射和产物下载；但稳定 API schema 与精确定位仍未知。[产品页](https://www.matrixorigin.io/moi) · [Release Notes](https://docs.matrixorigin.cn/moi/en/4.0/release-notes/2026.html) · [Data Center](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/data_mgt/catalog.html) |
| “复杂解析边界完全不清楚” | **[部分过时]** | 格式、解析内容、OCR/视觉模型、切分范围、Excel 按行、清洗算子已有文档；准确率、大小/页数上限、跨页与部署差异仍需测。[工作流文档](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow.html) |
| “Native Explore 与 Dify/DeerFlow 应分轨” | **[事实：确认]** | Native 轨以 MOI 工作流 + Data Exploration/Data Asking 为界；Dify/DeerFlow 是集成轨。[Data Exploration](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/data_mgt/data_explore.html) · [Dify 模板](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow_template/multimodal_doc_rag_prep.html) · [DeerFlow](https://docs.matrixorigin.cn/moi/en/4.0/develop/deerflow.html) |
| 基于 MoiAI 身份选择 NotebookLM/ima/ChatDOC/AnythingLLM 作为直接竞品 | **[身份污染]** | 这些比较维度来自另一个产品身份，不能直接继承到 MatrixOne Intelligence；竞品研究应重新从企业 Data+AI、数据治理、混合检索与 RAG 平台层定义候选集。[MOI 产品页](https://www.matrixorigin.io/moi) |

## 7. 对 RAG benchmark 的直接影响

### 7.1 必须分开的三条轨道

1. **[推断] Native UI 轨：** 固定 MOI 实际版本，用同一批原始文件/表，经 MOI 工作流处理后在 Data Exploration 查询；评价解析、检索、回答、引用、范围隔离和多轮一致性。这一轨最接近官方定义的原生用户路径。[工作流](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow.html) · [Data Exploration](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/data_mgt/data_explore.html)
2. **[推断] Native SDK/API 轨：** 使用固定 commit 的 Go/Python SDK，保存原始 SSE 事件；先做契约探测，再决定能否计算 retrieval recall、citation correctness、step latency 和 token/cost。不能在 schema 未闭合时假装这些指标都可得。[Go SDK](https://github.com/matrixorigin/moi-go-sdk/blob/b28c3bbe19904b8b2d31bc6aad776bbedb954103/data_asking.go#L265-L395) · [Python API Reference](https://github.com/matrixorigin/moi-python-sdk/blob/4909a6a2ec45e0231910d6d13aed2924c58aa0ab/docs/api_reference.md#L184-L189)
3. **[推断] 集成轨：** Dify 与 DeerFlow 单列；记录 MOI 只负责的数据准备/检索接口，以及外部模型、提示词、Agent 编排和 UI。结果不得作为 Native MOI 总分直接汇总。[Dify 模板](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow_template/multimodal_doc_rag_prep.html) · [DeerFlow](https://docs.matrixorigin.cn/moi/en/4.0/develop/deerflow.html)

### 7.2 推荐的最小可归因链

**[推断]** 每个测试样本至少保存：原始输入及 hash → MOI workflow/version/config → 解析产物 → chunk/embedding 状态 → 查询的数据源与文件范围 → 原始流事件/检索证据 → 最终答案与显示引用。官方已提供其中若干界面与事件，但 trace ID、稳定 locator 和成本字段仍需契约探测或厂商确认。[Data Center](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/data_mgt/catalog.html) · [Go SDK](https://github.com/matrixorigin/moi-go-sdk/blob/b28c3bbe19904b8b2d31bc6aad776bbedb954103/data_asking.go#L265-L395)

**[推断]** 首轮压力用例应优先覆盖 Release Notes 暴露过的失效面：多轮后文件范围漂移、跨数据库串扰、表证据丢失、关键词召回、答案来源绑定，以及禁用 chunk 是否仍被召回。官方修复记录为这些测试提供了风险依据。[2026 Release Notes](https://docs.matrixorigin.cn/moi/en/4.0/release-notes/2026.html) · [Data Exploration](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/data_mgt/data_explore.html)

## 8. 仍未知、必须验证或向厂商确认

| 优先级 | 未知项 | 为什么不能由现有材料推出 |
|---|---|---|
| P0 | Native Explore UI 与 `/byoa/api/v1/data_asking/analyze`、Python `analyze_data_stream` 的准确映射 | **[未知]** SDK 证明流式分析入口存在，但没有公开的兼容矩阵说明 UI、租户权限、API 版本和事件字段完全一致。[Go SDK](https://github.com/matrixorigin/moi-go-sdk/blob/b28c3bbe19904b8b2d31bc6aad776bbedb954103/data_asking.go#L265-L395) · [Python SDK](https://github.com/matrixorigin/moi-python-sdk) |
| P0 | 检索/引用/trace 完整 schema | **[未知]** 需要 chunk ID、原文 locator、score、检索器/reranker、引用到答案 span 的绑定、trace/session ID、模型/token/cost、错误码与 retention；公开 Go 模型仍大量使用通用 map。[Go SDK 模型](https://github.com/matrixorigin/moi-go-sdk/blob/b28c3bbe19904b8b2d31bc6aad776bbedb954103/models.go#L2029-L2105) |
| P0 | 实际租户版本、功能开关和修复落地情况 | **[未知/风险]** 4.1 发布与 `/4.0/` 文档并存，Release Notes 仍频繁变化；必须把 build、区域、部署形态和测试日期写入结果。[MOI 4.1](https://matrixorigin.cn/blog/moi4-1-ai-data-zh) · [Release Notes](https://docs.matrixorigin.cn/moi/en/4.0/release-notes/2026.html) |
| P1 | 默认 embedding、召回策略、top-k、阈值、hybrid 权重、reranker 与生成模型 | **[未知]** 文档列出部分可用模型和索引方向，但没有给出 Data Exploration 在每个版本/租户中的完整默认链与可调范围。[工作流](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow.html) · [产品介绍](https://docs.matrixorigin.cn/moi/en/4.0/overview/matrixone-intelligence-introduction.html) |
| P1 | 解析准确率、文件大小/页数/数量上限与各部署的一致性 | **[未知]** 支持格式和算子不等于有质量/容量保证；需用扫描 PDF、跨页表、公式、图片、音视频和超长文件实测。[工作流](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/data/processing/workflow.html) |
| P1 | 云端与私有/本地部署的功能、配额、数据保留、网络出口、价格与 SLA | **[未知]** 官方确认部署形态，但公开页面不足以证明功能等价或给出可比较总成本。[产品页](https://www.matrixorigin.io/moi) · [MOI 4.1](https://matrixorigin.cn/blog/moi4-1-ai-data-zh) |
| P1 | 独立的 RAG 效果与 TCO 验证 | **[检索结论]** 官方目前以产品页、方案页和白皮书主张为主；找到的 MatrixOne 论文并非 RAG 评估。[Agentic RAG 方案](https://www.matrixorigin.io/solution/agentic-rag) · [arXiv 论文](https://arxiv.org/abs/2604.03927) |

## 结论

**[事实]** 官方资料足以确认：MOI 是 MatrixOrigin 的 MatrixOne Intelligence，是面向企业多模态数据治理、检索、问答和 AI 应用建设的平台；Native RAG 可合理界定为“MOI 数据接入/工作流处理 → 索引与 embedding → Data Exploration/Data Asking → 检索证据与回答”，Dify/DeerFlow 必须另列为集成轨。[MOI 产品页](https://www.matrixorigin.io/moi) · [Data Exploration](https://docs.matrixorigin.cn/moi/en/4.0/genai-workspace/management/data_mgt/data_explore.html) · [Go SDK](https://github.com/matrixorigin/moi-go-sdk/blob/b28c3bbe19904b8b2d31bc6aad776bbedb954103/data_asking.go#L265-L395)

**[推断]** 当前最有价值的下一步不是继续补写营销定位，而是对实际租户做 API/trace 契约探测：确认 Explore 与 SDK 的对应关系、原始 SSE、chunk/score/locator/citation 字段、版本与权限；随后才能建立可复现且可归因的 Native RAG benchmark。[Go SDK 模型](https://github.com/matrixorigin/moi-go-sdk/blob/b28c3bbe19904b8b2d31bc6aad776bbedb954103/models.go#L2029-L2105) · [2026 Release Notes](https://docs.matrixorigin.cn/moi/en/4.0/release-notes/2026.html)
