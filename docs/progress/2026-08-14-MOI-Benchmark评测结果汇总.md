# MOI Benchmark 评测结果汇总（2026-08-14）

> 汇报范围：Memoria、文档解析、信息提取。三项评测均已完成。Astra、RAG、NL2SQL、Morpheus 等其他评测待结果更新后另行补充。

## 1. 总览

| 评测方向 | 负责人 | 数据集 | 主要对比对象 | 当前结论 |
|---|---|---|---|---|
| Memoria | 王雅琪 | LongMemEval-S、LoCoMo、4 组 Feature 自建测试集 | Mem0、Zep | LongMemEval-S 略高于两项公开参照；LoCoMo 仍低于 Mem0、Zep；状态管理类 Feature 表现稳定，重复记忆处理弱于 Mem0 |
| 文档解析 | 王雅琪 | OmniDocBench v1.6 全量 1,651 页、半导体场景私有测试集 50 份文件 | MinerU、PaddleOCR-VL | 公开集 Overall 90.23，高于 MinerU-Pipeline、低于 MinerU-2.5 及新版 PaddleOCR-VL；私有行业集显著领先两项竞品 |
| 信息提取 | 王雅琪 | SROIE 100、VRDU 97、Kleister-NDA 100，共 297 份文档 | LandingAI ADE | LandingAI 三数据集平均 F1 领先 5.20pp；MOI 在 VRDU 上差距较小，并体现出更保守的空值处理特征 |

## 2. Memoria

### 2.1 公开数据集结果

本轮完成 LongMemEval-S 和 LoCoMo 两个公开长期记忆问答数据集的四项正式实验。Memoria 使用自身存储与检索后端，分别对齐 Mem0 的公开 Reader/Judge 协议，以及 Zep 公开的 Reader/Judge 模型配置。

| 数据集与协议 | 实验配置摘要 | Memoria | 竞品公开参照 | 差值 |
|---|---|---:|---:|---:|
| LongMemEval-S / Mem0 协议 | 500 题；GPT-5 Reader/Judge；Hybrid Top-20 | **457/500（91.40%）** | Mem0 OSS GPT-5 Extraction：91.0% | **+0.40pp** |
| LongMemEval-S / Zep 模型对标 | 500 题；GPT-5.4 medium Reader/Judge；Hybrid Top-20 | **459/500（91.80%）** | Zep：451/500（90.20%） | **+1.60pp** |
| LoCoMo / Mem0 协议 | Category 1–4，共 1,540 题；GPT-5 Reader/Judge；Hybrid Top-200 | **1,354/1,540（87.92%）** | Mem0 Platform v3 Top-200：92.5%（README）/ 91.56%（artifact） | **-4.58pp / -3.64pp** |
| LoCoMo / Zep 模型对标 | Category 1–4，共 1,540 题；GPT-5.4 medium Reader/Judge；Hybrid Top-200 | **1,393/1,540（90.45%）** | Zep：1,459/1,540（94.70%） | **-4.25pp** |

结论：Memoria 在 LongMemEval-S 上已达到并略高于 Mem0、Zep 的公开参照；在更长上下文、Top-200 检索的 LoCoMo 上仍有约 3.6～4.6 个百分点差距。以上对比对齐了主要 Reader/Judge 口径，但 Memory 构建、Embedding、检索后端和部分 Prompt 并非完全一致，因此用于判断效果量级，不应视为严格的同环境产品排名。

### 2.2 Memoria Feature 结果

Feature 评测使用自建测试集，直接验证 Memoria 的状态管理、版本管理、质量治理和重复记忆处理能力。四类测试的通过条件不同，不合并计算单一总分。

| Feature | 测试集 | Memoria 结果 | 竞品情况与结论 |
|---|---:|---:|---|
| 快照与回滚 | 自建 50 case | **50/50（100%）** | Memoria 原生特性，本轮未做同构竞品横评 |
| 分支、Diff、Merge | 自建 50 case | **48/50（96%）** | Memoria 原生特性；2 个语义等价变更被误报为冲突 |
| 低置信记忆治理 | 自建 50 case | **50/50（100%）** | Memoria 原生特性，本轮未做同构竞品横评 |
| 重复与近重复处理 | 自建 50 case | **36/50（72%）** | 在 44 个三方原生可比 case 上：Memoria **68.2%**、Mem0 Platform **100%**、Zep Cloud **68.2%** |

结论：快照回滚、分支版本管理和低置信治理已表现出较高稳定性；当前最明确的能力短板是重复与语义等价记忆处理，尤其对固定相似度阈值之外的等价改写覆盖不足，明显弱于 Mem0 Platform。

详细结果：

- [Memoria 评测总览](../../memoria/README.md)
- [LongMemEval-S 与 LoCoMo 最终综合报告](../../memoria/evaluate/memoria-longmemeval-locomo-final-summary.md)
- [Feature 实验总览及竞品对比](../../memoria/evaluate/feature/feature-evaluation-overview.md)

## 3. 文档解析

### 3.1 OmniDocBench 公开集

公开集使用 OmniDocBench v1.6 全量 1,651 页和官方 `end2end + quick_match` 评分器。MOI 被测版本为 IDC 4.1.14，实际链路为 MinerU-2.5 VLM、PP-DocLayout_plus-L 和 MOI/Qwen 后处理组成的完整解析系统。

| 产品/流程 | Overall↑ | Text Edit↓ | Formula CDM↑ | Table TEDS↑ | Reading Order Edit↓ |
|---|---:|---:|---:|---:|---:|
| **MOI IDC 4.1.14（本地实测）** | **90.23** | 0.1002 | 94.04 | 86.66 | 0.3135 |
| MinerU-Pipeline 3.4.0 | 86.47 | 0.055 | 83.07 | 81.88 | 0.153 |
| MinerU-2.5 | 93.04 | 0.045 | 95.77 | 87.88 | 0.130 |
| MinerU2.5-Pro | 95.75 | 0.036 | 97.45 | 93.42 | 0.120 |
| PaddleOCR-VL | 94.18 | 0.040 | 95.91 | 90.65 | 0.135 |
| PaddleOCR-VL-1.5 | 94.93 | 0.038 | 96.89 | 91.67 | 0.130 |
| PaddleOCR-VL-1.6 | 96.34 | 0.0326 | 97.5304 | 94.7619 | 0.1278 |

结论：MOI Overall 高于 MinerU-Pipeline 3.4.0，但低于 MinerU-2.5、MinerU2.5-Pro 和 PaddleOCR-VL 系列。公式能力已接近 MinerU-2.5，主要差距集中在表格、文本保留和阅读顺序。竞品数据来自 OmniDocBench 官方榜单，并非与 MOI 在同一服务环境中重跑。

### 3.2 半导体场景私有集

私有集使用 50 份 PDF、PPTX、DOCX、DOC 文件，覆盖复杂表格、跨页表、标题层级、页眉页脚、公式和图文混排等行业问题。评分先在每个文件内部聚合，再对 50 个文件等权平均。

| 产品 | 文件内维度等权平均 | 文件内维度按数量加权平均 | 单文件领先数 | 有效解析失败 |
|---|---:|---:|---:|---:|
| **MOI IDC 4.1.14** | **84.5%** | **89.4%** | **42/50** | **0** |
| PaddleOCR-VL 在线服务 | 58.6% | 70.5% | 6/50 | 1 |
| MinerU Precision | 56.8% | 66.7% | 2/50 | 0 |

结论：MOI 在该行业私有集上形成显著领先，文件内维度等权平均比最优竞品高 25.9pp，且在 42/50 个文件上取得最高分。优势在多页文档、长文档和跨页表格场景中保持或进一步扩大。该结论代表本批私有行业 case，不与 OmniDocBench 官方分数混合为一个总分。

详细结果：

- [文档解析评测总览](../../document-parsing/README.md)
- [OmniDocBench 完整分析与竞品榜单对比](../../document-parsing/evaluate/MOI_OmniDocBench评测分析.md)
- [OmniDocBench 最终全量评分与复现说明](../../document-parsing/evaluate/moi-omnidocbench-final/summary.md)
- [半导体场景私有数据集评测报告](../../document-parsing/evaluate/半导体场景私有数据集评测报告.md)

## 4. 信息提取

本轮比较 MOI 信息提取工作流与 LandingAI ADE。数据集包括 SROIE 收据 100 份、VRDU 注册表单 97 份和 Kleister-NDA 合同 100 份，共 297 份有效文档。主指标为三个数据集标准化字段级 Micro F1 的等权平均。

### 4.1 总体结果

| 产品 | 三数据集平均 F1 | 平均文档全对率 | 完成数 | 成功率 | Schema 合规率 |
|---|---:|---:|---:|---:|---:|
| MOI | 64.57% | 20.81% | 297/297 | 100.00% | 100.00% |
| **LandingAI ADE** | **69.77%** | **27.10%** | 297/297 | 100.00% | 100.00% |

### 4.2 分数据集结果

| 数据集 | MOI Micro F1 | LandingAI Micro F1 | MOI - LandingAI | 结果判断 |
|---|---:|---:|---:|---|
| SROIE | 79.45% | **90.11%** | -10.66pp | LandingAI 优势明显，主要差距在多行地址等字段 |
| VRDU | 68.54% | **70.76%** | -2.22pp | 总体接近；MOI Precision 和文档全对率更高，空字段误提更少 |
| Kleister-NDA | 45.71% | **48.42%** | -2.71pp | 双方均低于 50%，合同多实体和管辖地仍是共同难点 |

结论：LandingAI 的整体开箱准确率更高，三数据集平均 F1 领先 5.20pp，文档全对率领先 6.29pp。MOI 在 VRDU 上已接近 LandingAI，并呈现更保守的填值策略：Precision 为 70.26%（LandingAI 66.01%），空字段误提率为 20.83%（LandingAI 49.31%）；LandingAI 则以更高 Recall 取得略高的总体 F1。两项产品对 Kleister-NDA 均未达到可直接无人审核入库的水平。

详细结果：

- [MOI vs LandingAI 最终多维评测报告](../../document-extracting/evaluation/latest/report.md)

## 5. 汇总结论

1. **Memoria**：LongMemEval-S 已达到或略高于公开竞品参照，LoCoMo 仍有约 3.6～4.6pp 差距；产品 Feature 中，重复与语义等价记忆处理是最明确的改进方向。
2. **文档解析**：MOI 在 OmniDocBench 上处于 MinerU-Pipeline 之上、MinerU-2.5 和新版 PaddleOCR-VL 之下；在半导体行业私有集上则显著领先 MinerU Precision 和 PaddleOCR-VL，体现出复杂、多页和跨页文档场景优势。
3. **信息提取**：LandingAI 目前整体领先；MOI 在 VRDU 监管表单上差距较小，并在 Precision、文档全对率和空值控制上具有局部优势。

以上三项评测均已完成；本汇总后续仅在其他评测方向产生正式结果后继续补充范围。
