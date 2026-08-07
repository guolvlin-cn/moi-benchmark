# MOI Benchmark 评测结果汇总

> 汇总日期：2026-08-07
>
> 汇总范围：Astra、RAG、NL2SQL、Memory、文档解析、文档信息提取、Morpheus
>
> 说明：本文以截至 2026-08-07 的最新本地评测报告为准。表中明确区分本地同题实测和竞品公开结果；不同数据集、模型与评测协议下的分数不能直接合并。

## 1. 总体结论

| 评测维度 | 负责人 | 当前结果 | 与竞品对比结论 |
|---|---|---|---|
| Astra | 陈雨微 | Terminal-Bench 88 个配对任务，Verify Pass Rate 51.16% | Hermes 为 56.82%，当前 Hermes 完成效果更好；Astra 工具调用更少、失败工具调用更少、Token 用量更低，但超时问题明显 |
| RAG | 周乐天 | WikiEval 基础来源召回 100%；MMDocIR Page R@1 56.17、Layout R@1 28.02 | WikiEval 与 Dify 基础召回持平；MMDocIR 检索全面领先 Dify，但下游 QA 质量略低于 Dify |
| NL2SQL | 张颖 | Spider mix50 执行准确率 66.0% | 低于 Wren AI 的 82.0% 和 Chat2DB 的 94.0%，当前主要短板是 Medium、多表稳定性和输出列控制 |
| Memory | 王雅琪 | LongMemEval-S 端到端准确率 84.60% | 低于 Zep 90.2%、Mem0 OSS 91.0% 和 Mem0 Platform v3 94.8%；基础记忆问题较强，偏好、多会话和知识更新较弱 |
| 文档解析 | 王雅琪 | OmniDocBench Overall 90.23；私有集文件内维度等权平均 84.9% | 公开集低于 MinerU-2.5、PaddleOCR-VL 等最新公开结果；私有半导体难例集明显领先 MinerU Precision 和 PaddleOCR-VL |
| 文档信息提取 | 王雅琪 | 三数据集平均 Micro F1 64.57% | LandingAI 为 69.77%，总体领先 5.20 个百分点；MOI 在 VRDU 精度、空值控制和文档全对率上更好 |
| Morpheus | 王雅琪 | 尚未开始正式评测 | 当前没有可对比精度结果；该 Track 比较内部 Base、LoRA-SFT 和完整 Replay/Gate 闭环，不做外部产品排名 |

## 2. Astra

### 数据集与实验配置

- 数据集：Terminal-Bench 2.1 常规任务，共 88 个 Astra/Hermes 最新配对任务。
- 评测对象：Astra；竞品：Hermes Agent。Goose 尚未形成有效结果。
- 统计口径：每个产品、每个任务只取最新一次记录；`verify unavailable` 不计入通过率分母；正常端到端成功定义为 Verify Pass 且无 timeout。
- 当前为产品原生运行结果，两侧模型、最大轮数、Token 采集和工具封装并非完全相同，因此适合比较当前产品表现，不适合做单一机制归因。

### 核心结果

| 指标 | Astra | Hermes |
|---|---:|---:|
| Verify Pass | 44 | 50 |
| Verify Pass Rate | **51.16%（44/86）** | **56.82%（50/88）** |
| 正常端到端成功 | 41/88 | 47/88 |
| Timeout | 39 | 10 |
| 工具调用总数 | 2,253 | 3,101 |
| 失败工具调用 | 155 | 275 |
| 可靠 Token 总量 | 32.65M | 90.12M |

### 结论

- Hermes 当前 Verify Pass Rate 高 5.66 个百分点，正常端到端成功多 6 个任务，任务完成效果暂时领先。
- Astra 的主要失败点是 LLM 流式返回异常后的容错不足：流式调用失败后仅进行一次非流式尝试，再失败即退出，对网络波动和短时服务异常较敏感。42 个 no-pass 中有 32 个与 LLM 请求超时及 stream transport 中断相关。
- Astra 当前优势是工具调用更少、失败工具调用更少、Token 用量更低。在 86 个双方均有工具数据的任务上，Astra 单任务工具调用中位数比 Hermes 少 5 次，失败工具调用中位数少 1 次。
- Token 的采集位置和缓存计量口径不同，因此只能说明当前记录中的资源足迹较低，不能直接换算为严格的跨产品成本优势。

### 后续工作

- 优先增强流式失败后的重试、断点续跑和网络波动容错，降低 timeout。
- 冻结模型、轮数、deadline、工具和 Token 计量口径后补充严格同配置实验，并完成 Goose 对比。

## 3. RAG

### 数据集与实验配置

本轮使用两个公开数据集：

- WikiEval：50 个 Wikipedia 来源、50 道问题，用于通用文本 RAG。
- MMDocIR：313 篇长文档、1,658 个问题，用于长文档、多模态页面和布局证据检索。

评测对象为 MOI，竞品为本地 Dify；FastGPT 和 MaxKB 尚未通过完整评测门禁，因此不进入结果表。

- WikiEval：MOI 使用 512-token chunk、50-token overlap、`bge-m3` Embedding、`qwen3.6-flash` 生成；Dify 使用本地原生知识库链路，Top-K=10。
- MMDocIR：MOI 与 Dify 均使用 `bge-m3`，不启用 rerank；每个问题只在所属长文档内检索。页面轨 Top-5，布局轨 Top-10。
- MMDocIR QA：两边使用各自 Top-10 页面上下文，并统一使用 `deepseek-v4-flash`、相同 Prompt 和上下文预算生成答案。

### WikiEval 结果

| 系统 | Source R@1 | Source R@3/R@5 | MRR | Faithfulness | Answer Relevance | Context Precision | Context Recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| MOI | 100.0% | 100.0% | 1.000 | 0.9637 | **0.9309** | 0.7406 | **0.9927** |
| Dify | 100.0% | 100.0% | 1.000 | **0.9938** | 0.9123 | **0.8015** | 0.8817 |

两套系统都能稳定召回正确来源。MOI 的 Answer Relevance 和 Context Recall 更高，Dify 的 Faithfulness 和 Context Precision 更高。

### MMDocIR 检索结果

| 系统 | Page R@1 | Page R@3 | Page R@5 | Layout R@1 | Layout R@5 | Layout R@10 |
|---|---:|---:|---:|---:|---:|---:|
| MOI | **56.17** | **71.83** | **75.83** | **28.02** | **52.70** | **61.87** |
| Dify | 53.51 | 67.00 | 72.59 | 21.03 | 50.77 | 59.98 |
| 论文参考：Col-Phi3 → ColBERT | 57.1 | 76.8 | 83.0 | 35.3 | 58.8 | 65.4 |

MOI 在全部 Page Recall 和 Layout Recall 截点上均领先 Dify，其中 Layout R@1 领先 6.99 个百分点；但与论文级联检索参考相比，高截点页面覆盖和细粒度布局定位仍有差距。

### MMDocIR QA 结果

| 系统 | Answer Correctness | Token F1 | Faithfulness |
|---|---:|---:|---:|
| MOI | 3.98/5 | 0.1231 | 0.75 |
| Dify | **4.02/5** | **0.1651** | **0.79** |

Dify 的下游 QA 指标小幅领先，说明 MOI 的检索优势尚未完全转化为回答质量优势。

### 后续工作

- 完成 FastGPT、MaxKB 的 ingest、direct retrieval、native QA 三段式门禁后补充同题结果。
- 优化多文档高截点覆盖、细粒度布局定位，以及检索证据进入 Reader 后的利用效率。
- 增加企业与垂直领域自建数据集，覆盖多跳、冲突信息和完整性回答。

## 4. NL2SQL

### 数据集与实验配置

- Spider easy50：50 道单表简单题，用于验证基础 SQL 生成能力。
- Spider mix50：30 道 Easy、15 道 Medium、5 道 Hard，用于 MOI、Wren AI、Chat2DB 三平台对比。
- 评分器：Spider 官方 `test-suite-sql-eval`，按 SQL 执行结果判断，`keep_distinct=true`。
- 当前实验为英文、单轮、提供 Schema 的公开集，不覆盖 MOI 的中文多轮、Schema 探索和 SQL 自修复优势。

### 核心结果

| 系统 | Easy（30） | Medium（15） | Hard（5） | Overall（50） |
|---|---:|---:|---:|---:|
| MOI | 73.3% | 53.3% | 60.0% | **66.0%** |
| Wren AI | 86.7% | 66.7% | 100.0% | **82.0%** |
| Chat2DB | 96.7% | 93.3% | 100.0% | **94.0%** |

Spider easy50 中，MOI 原始 Execution Accuracy 为 78.0%，修正 `keep_distinct` 后为 82.0%。报告中的约 94%是排除数据和评测工具争议后的诊断值，不作为正式竞品对比分数。

### 结论

- 在 Spider mix50 的统一执行评分下，MOI 比 Wren AI 低 16 个百分点，比 Chat2DB 低 28 个百分点。
- MOI 的主要短板集中在 Medium、多表连接稳定性、额外返回辅助列、数据类型处理和部分 SQL 方言兼容。
- 17 道失败中包含评测规则、Gold 歧义和框架问题，因此分差不能全部解释为模型语义能力差距；但当前正式结果仍以 66.0%为准。

### 后续工作

- 建设中文合同、发票、银行流水业务集，覆盖单表、多表、子查询、歧义澄清和 SQL 自修复。
- 在统一数据库、Prompt、权限和评分器下重跑 MOI、Wren AI、Chat2DB，并优先修复大表多表稳定性与输出列控制。

## 5. Memory

### 数据集与实验配置

- 数据集：LongMemEval-S cleaned/oracle，全量 500 题，覆盖单会话用户、单会话助手、偏好、知识更新、时间推理和多会话六类问题。
- 被评测系统：Memoria 0.4.0；竞品参考：Zep、Mem0 OSS、Mem0 Platform v3。
- Memoria：`bge-m3` 1024 维 Embedding，原生 hybrid Top-20 检索，Reader 为 `gpt-5.6-luna`，Judge 为 `gpt-5.5`，temperature=0。
- 最终结果采用两阶段 Reader Prompt：全量首轮后，仅对首轮输出 IDK 的 51 题使用 calibrated Prompt 重跑并替换同题结果。
- 竞品数字来自官方公开结果，Memory Extraction、Embedding、Top-K、Reader、Judge 和 Prompt 未完全统一，因此属于公开横向参考，不是严格同配置排名。

### 核心结果

| 系统 | LongMemEval-S Overall | 结果性质 |
|---|---:|---|
| Memoria | **84.60%（423/500）** | 本地完整实测 |
| Zep | 90.2%（451/500） | 官网公开结果 |
| Mem0 OSS + GPT-5 Extraction | 91.0% | 官方 OSS 对照实验 |
| Mem0 Platform v3 Top-50 | 94.8%（474/500） | 官方托管平台结果 |

| 问题类型 | Memoria | Zep | Mem0 OSS GPT-5 | Mem0 Platform v3 |
|---|---:|---:|---:|---:|
| Single-Session User | 97.1% | 94.3% | 95.7% | 98.6% |
| Single-Session Assistant | 96.4% | 96.4% | 92.9% | 98.2% |
| Single-Session Preference | 63.3% | 90.0% | 93.3% | 93.3% |
| Knowledge Update | 79.5% | 93.6% | 91.0% | 93.6% |
| Temporal Reasoning | 88.0% | 90.2% | 94.7% | 94.0% |
| Multi-Session | 77.4% | 83.5% | 83.5% | 93.2% |

### 结论

- Memoria 单会话用户和助手类问题已达到 96% 以上，与竞品接近或局部领先。
- 总体差距主要来自 Preference、Knowledge Update 和 Multi-Session；Memoria 相对 Zep 低 5.6 个百分点，相对 Mem0 OSS 低 6.4 个百分点，相对 Mem0 Platform v3 低 10.2 个百分点。
- Memoria Top-20 Complete Recall 已达到 94.04%，高于端到端准确率，说明下一步瓶颈不仅是检索，还包括 Reader 对分散证据的利用和拒答策略。

### 后续工作

- 在冻结检索结果下继续比较 Reader Prompt、Reader 模型和信息抽取阶段，重点改善 Preference、Knowledge Update、Multi-Session 和 Abstention。
- 完成 LoCoMo 全量实验，并与 Mem0、Zep 的公开结果进行对比。
- 开展针对 Memoria 产品特性的专项实验，重点验证快照与回滚、分支、Diff、Merge、矛盾处理和记忆隔离等能力。

## 6. 文档解析

### 6.1 OmniDocBench 公开集

#### 数据集与实验配置

- 数据集：OmniDocBench v1.6 全量 1,651 页。
- MOI 配置：IDC 4.1.14，MinerU 2.7.4 / MinerU2.5-2509-1.2B VLM、本地 `PP-DocLayout_plus-L`、`qwen3.5-27b` 后处理，1,651/1,651 配置一致。
- 评分：OmniDocBench 官方 `end2end`，`quick_match`；Overall 由 Text、Formula CDM 和 Table TEDS 三项组成。
- 竞品为 OmniDocBench 官方 `v1.6_full` 榜单公开结果，不是本地同环境重跑。

#### 核心结果

| 系统/模型 | Overall↑ | Text Edit↓ | Formula CDM↑ | Table TEDS↑ | Reading Order Edit↓ |
|---|---:|---:|---:|---:|---:|
| MOI IDC 4.1.14 | **90.23** | 0.1002 | 94.04 | 86.66 | 0.3135 |
| MinerU-Pipeline 3.4.0 | 86.47 | 0.055 | 83.07 | 81.88 | 0.153 |
| MinerU-2.5 | 93.04 | 0.045 | 95.77 | 87.88 | 0.130 |
| MinerU2.5-Pro | 95.75 | 0.036 | 97.45 | 93.42 | 0.120 |
| PaddleOCR-VL | 94.18 | 0.040 | 95.91 | 90.65 | 0.135 |
| PaddleOCR-VL-1.5 | 94.93 | 0.038 | 96.89 | 91.67 | 0.130 |
| PaddleOCR-VL-1.6 | 96.34 | 0.0326 | 97.53 | 94.76 | 0.1278 |

MOI Overall 高于 MinerU-Pipeline 3.4.0，但低于独立 MinerU-2.5、MinerU2.5-Pro 和 PaddleOCR-VL 系列。MOI 的公式能力接近 MinerU-2.5，主要差距在文本、表格和阅读顺序。上述竞品为公开榜单结果，适合判断量级，不是严格同环境 A/B。

### 6.2 半导体场景私有集

#### 数据集与实验配置

- 数据集：50 份 PDF、PPTX、DOCX、DOC，包含跨页表格、复杂合并单元格、标题、页眉页脚、公式、流程图和图文混排。
- 对比对象：MOI IDC 4.1.14、MinerU Precision API、百度智能云 PaddleOCR-VL。
- 评分：每个文件先计算维度等权分或按元素数量加权分，再对 50 个文件等权平均；不是将全体文件元素直接池化。

#### 核心结果

| 系统 | 文件内维度等权平均 | 文件内维度按数量加权平均 | 单文件领先数 | 解析失败 |
|---|---:|---:|---:|---:|
| MOI IDC 4.1.14 | **84.9%** | **89.6%** | **42/50** | 0 |
| PaddleOCR-VL | 58.6% | 70.5% | 6/50 | 1 |
| MinerU Precision | 56.8% | 66.7% | 2/50 | 0 |

MOI 在全部八个有效维度领先：Layout 96.6%、Formula 91.9%、Title 87.0%、Table 85.3%、Header/Footer 84.7%、Image 84.7%、Text 82.5%、Table TEDS 74.0%。优势在 Office、多页和跨页表格场景中尤其明显。

### 后续工作

- 当前公开集和私有集评分均已完成。如继续优化，优先聚焦 OmniDocBench 暴露的表格、文本和阅读顺序问题，并用现有私有难例做回归。
- 如需要形成严格竞品 A/B，可在时间允许时统一版本、硬件和配置重跑 MinerU/Paddle。

## 7. 文档信息提取

### 数据集与实验配置

- 数据集：SROIE 100 份收据、VRDU Registration 97 份有效表单、Kleister-NDA 100 份合同，共 297 份。
- 对比对象：MOI 与 LandingAI Agentic Document Extraction。
- 两边使用相同原始文档、固定业务字段 Schema、Golden 和标准化评分规则；均从原始文档端到端运行。
- 主指标：三个数据集的 normalized Micro F1 平均值；同时报告文档全对率。VRDU 中 3 份供应商内容安全失败样本对双方对称排除。

### 核心结果

| 系统 | 三数据集平均 Micro F1 | 平均文档全对率 | 完成率 | Schema 合规率 |
|---|---:|---:|---:|---:|
| MOI | **64.57%** | 20.81% | 100% | 100% |
| LandingAI | **69.77%** | 27.10% | 100% | 100% |

| 数据集 | MOI F1 | LandingAI F1 | 结果判断 |
|---|---:|---:|---|
| SROIE | 79.45% | **90.11%** | LandingAI 明显领先，MOI 主要短板是多行地址 |
| VRDU | 68.54% | **70.76%** | 总分接近；MOI Precision、空值控制和文档全对率更高，LandingAI Recall 更高 |
| Kleister-NDA | 45.71% | **48.42%** | 双方均低于 50%，复杂 party 数组和 jurisdiction 是共同难点 |

### 结论

- LandingAI 综合 Micro F1 高 5.20 个百分点，文档全对率高 6.29 个百分点，当前开箱准确率更好。
- MOI 在 VRDU 上更偏保守策略：Precision 70.26%对 66.01%，空字段误提率 20.83%对 49.31%，文档全对率 14.43%对 10.31%；适合错误填值代价高的场景。
- LandingAI 在召回优先场景更有优势，其 VRDU Recall 为 76.26%，MOI 为 66.89%。
- 本轮信息提取评测已经完成，不再安排后续评测工作。

## 8. Morpheus

### 当前状态

- 当前只有评测方案，尚未形成数据集、正式运行结果或精度分数。
- Morpheus 不做外部竞品排名，计划在相同基础模型和冻结数据下比较 Base、LoRA-SFT、LoRA-SFT + Replay/Gate，以及后续完整自进化版本。
- 核心目标是验证结构化任务精度提升，以及训练、评估、Replay、Gate、发布和回滚闭环能否稳定运行并阻止退化版本上线。

### 后续工作

- 在其他 Track 收尾后启动，先冻结 train、holdout、regression 和 replay 数据集。
- 完成内部 Baseline、Adapter 和完整闭环的第一轮对比，再决定是否扩展 GRPO 和多轮自进化实验。
