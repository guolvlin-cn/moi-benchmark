> ⚠️ **WARNING / 身份污染 / DO NOT CITE**：本稿将 moi-ai.com 的 **MoiAI** 误识别为 MatrixOrigin 的 **MOI**，因此不得作为 MOI 的产品定位、竞品、能力或评测依据。仅保留作历史记录；身份以 [canonical identity decision](../../decisions/moi-identity.md) 为准。

# MoiAI RAG / 知识库问答竞品清单

更新日期：2026-08-04

## 比较边界

MoiAI 是桌面专业助手，官方能力包括本地文件语义搜索、内置知识库、文档导入、多模型和企业私有部署。因此竞品不应只选底层向量数据库或 RAG 开发库，而应优先选择能完成“导入同一批文档 → 建库 → 连续问答 → 展示来源”的完整产品。

## 核心实测组（建议第一轮）

| 产品 | 类型 | 为什么值得与 MoiAI 比 | 官方网址 |
|---|---|---|---|
| Google NotebookLM | 云端个人知识库 / 研究助手 | 多来源问答和逐条引用体验成熟，适合作为成品质量上限 | https://workspace.google.com/products/notebooklm/ |
| 腾讯 ima.copilot | 云端个人/共享知识库 | 中文用户体验、知识库组织和搜读写一体化，是国内直接竞品 | https://ima.qq.com/ |
| ChatDOC | 云端文档问答 | 强调扫描件、表格、公式、跨文档问答和页码级溯源，适合复杂 PDF 压测 | https://www.chatdoc.com/ |
| AnythingLLM | 桌面端 / 自部署 | 本地优先、桌面应用、私有文档、可切换模型，与 MoiAI 产品形态最接近 | https://anythingllm.com/ |
| RAGFlow | 开源自部署 RAG 平台 | 深度文档理解、可干预解析、引用完整，适合验证解析与检索上限 | https://ragflow.io/ |
| FastGPT | 开源/云端企业知识库 | 中文企业知识库、混合检索、复杂文档解析、工作流与 API 完整 | https://fastgpt.io/ |
| MaxKB | 开源/商业企业知识库 | 开箱即用的知识库问答、网站同步和私有部署，容易搭建公平对照组 | https://maxkb.pro/ |
| Dify | 开源/云端 LLM 应用平台 | 可控切分、检索和模型配置，适合作为可调参数的工程基线 | https://dify.ai/ |

## 第二轮补充组

| 产品 | 适用目的 | 官方网址 |
|---|---|---|
| QAnything（网易有道） | 中文/跨语言、本地离线、多格式与大规模语料对照 | https://github.com/netease-youdao/QAnything |
| PandaWiki | 面向产品文档、FAQ、博客的知识库问答与 AI 搜索 | https://github.com/chaitin/PandaWiki |
| ChatGPT Projects | 通用大模型带文件上下文的非专用 RAG 基线 | https://help.openai.com/en/articles/10169521-projects-in-chatgpt |
| 百度千帆 Agent / AppBuilder | 国内公有云企业 RAG、解析策略与知识库命中调试 | https://ai.baidu.com/ai-doc/index/AppBuilder |
| Coze / 扣子 | 国内低代码 Agent + 知识库产品基线 | https://www.coze.cn/ |
| AWS Bedrock Knowledge Bases | 云原生托管 RAG/API 基线 | https://aws.amazon.com/bedrock/knowledge-bases/ |
| Azure AI Search | 企业搜索与 RAG 工程基线 | https://azure.microsoft.com/products/ai-services/ai-search |
| Google Vertex AI Search | Google Cloud 托管企业搜索/RAG 基线 | https://cloud.google.com/enterprise-search |

## 建议分组

- **必须跑的直接竞品**：NotebookLM、ima.copilot、ChatDOC、AnythingLLM。
- **必须跑的工程/私有部署基线**：RAGFlow、FastGPT、MaxKB、Dify。
- **资源有限时的最小集合**：NotebookLM、ima.copilot、AnythingLLM、RAGFlow、FastGPT，加上 MoiAI，共 6 个系统。
- **不宜混排总分**：AWS、Azure、Vertex AI 等开发服务需要自行选择模型和检索参数，应单独列为“可配置工程组”；否则与开箱即用 SaaS 比较不公平。

## 公平实测建议

固定同一批源文件、建库等待时间、问题与多轮上下文；分别记录答案正确性、证据召回、引用定位、拒答/幻觉、跨文档综合、表格/图片/扫描件、中文能力、延迟、建库耗时和成本。对于可配置平台，同时报告“默认配置”和“调优配置”，避免只用调优后的开源系统对比默认 SaaS。

## 主要官方依据

- MoiAI 官方介绍与快速指南：https://moi-ai.com/ 、https://moi-ai.com/introduction-chs
- NotebookLM 官方产品页：https://workspace.google.com/products/notebooklm/
- ChatDOC 官方产品与文档：https://www.chatdoc.com/ 、https://doc.chatdoc.com/guide/what-is-chatdoc/
- AnythingLLM 官方产品与文档：https://anythingllm.com/ 、https://docs.anythingllm.com/
- RAGFlow 官方文档与代码：https://ragflow.net/docs 、https://github.com/infiniflow/ragflow
- FastGPT 官方文档：https://doc.fastgpt.io/en/faq/app
- MaxKB 官方文档：https://docs.maxkb.pro/user_manual/dataset/dataset/
- Dify 官方文档：https://docs.dify.ai/
- QAnything、PandaWiki 官方代码库：https://github.com/netease-youdao/QAnything 、https://github.com/chaitin/PandaWiki
