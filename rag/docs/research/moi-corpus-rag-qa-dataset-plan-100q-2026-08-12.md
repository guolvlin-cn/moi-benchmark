# 面向 `rag/corpus` 的 100 题 RAG QA 数据集构建计划

**状态**：Draft v1.0  
**更新时间**：2026-08-12  
**目标**：基于 `/Users/muuushroom/gitrepos/moi-benchmark/rag/corpus` 当前快照，构建一套可复现、可审计、面向 RAG 端到端评测的 100 题 QA 数据集。

## 1. 目标与边界

这套数据集的核心不是训练语言模型，而是回答四个评测问题：

1. 系统能否从 46 份 PDF 中找对相关文档和证据页？
2. 能否正确组合一个文档内或跨文档的完整证据集？
3. 能否基于证据给出完整、精确、范围正确的答案？
4. 能否提供真实且覆盖充分的页码、文本片段、表格单元格或图示定位？

因此，v1 应定义为 **evaluation benchmark**：不设置 train split，也不要求用 Gold QA 微调模型。可以有 `dev` 用于调参、`pilot` 用于管线验收，但不得把它们当作训练集；最终结果使用封存的 `formal` split 汇报。

所有答案必须来自这 46 份 PDF 的当前版本，不使用网页、产品常识或模型记忆补充事实。整个 46-PDF 集合作为候选检索语料；即使某份 PDF 没有直接产生题目，也可以作为真实的干扰文档。

## 2. 语料快照与针对性分析

### 2.1 当前规模

| 项目 | 当前值 | 对构建的影响 |
|---|---:|---|
| PDF 数量 | 46 | 题目不应平均分配；需要按证据密度和文档族分层 |
| 总页数 | 1,104 页 | 足以测试长文档检索、页级定位和跨文档干扰 |
| 单文档页数 | 1–196 页 | 同时存在 flyer/datasheet 与超长 user guide |
| 文件大小 | 约 58 MB | 应冻结 SHA-256，避免后续替换文件造成 Gold 漂移 |
| 主要语言 | 抽取文本以英文为主 | 推荐中文问题为主、英文问题为对照，并分语言报告 |
| 主要证据 | 正文、步骤、规格、多栏表格、性能表、少量图示/版面结构 | 不能只保存 `reference_answer`，必须保存结构化证据定位 |

### 2.2 文档族与题目预算

题目预算按“可产生稳定 Gold 的证据量”分配，而不是按文件数等权分配。所有 46 份文件仍全部进入检索候选集。

| 文档族 | 文件范围 | 目标题数 | 适合考查的能力 |
|---|---|---:|---|
| BladeCenter / IBM 传统硬件维护、安装、电源、保修 | `01GW183`、`13U`、`44R5181`、`44R5192`、`8677`、`8720_8730`、`8852`、`BCT_PM_*`、`cl1cm`、`cy1ec`、`d3sbams5`、`cable_management_arm`、`cma_installation_guide` | 38 | 安装步骤、故障排查、兼容性、部件关系、跨章节完整性 |
| Lenovo / Broadcom / NVIDIA / IBM 产品 datasheet 与 collateral | `21-LENO-*`、`a2-datasheet`、`bes_switch`、`Ultrastar`、`ds0001`、`ds0013`、`ds0019`、`ds0021`、`ds0026`、`ds0028`、`ds0029`、`ds0037`、`ds0043`、`ds0046`、`ds0047`、`ds0048`、`ds0049`、`ds0051`、`ds0058`、`ds0075` | 26 | 产品规格、术语消歧、容量/接口/特性、同类产品比较 |
| 软件与管理工具指南 | `DB15-001161-08_LSI_Storage_Authority`、`bomc_bk`、`bomc_readme`、`customized_image_reference_guide` | 18 | 版本化操作、前置条件、命令/流程、异常处理、跨版本辨析 |
| 性能、认证与技术评估 | 两份 VMmark 报告、`Cert23032`、`Demartek_*`、`c1ed5e...` | 10 | 表格读取、指标与单位、测试条件、结果可比性边界 |
| 政策与研究论文 | `Anti-Slavery_and_Human_Trafficking_Statement`、`5656-hidden-technical-debt-in-machine-learning-systems` | 8 | 非产品文档检索、定义/列表、范围与时间限定 |
| **合计** | **46 份 PDF** | **100** | |

长文档优先从正文和章节内部取证，不能把封面/目录当成主要证据。短 datasheet 可以使用首页，但首页只包含标题或宣传语的问题不应占据多数。

## 3. 100 题的主类型配额

以下七类作为互斥的 `primary_type`，总数严格为 100。为避免一题重复计数，类型优先级为：`unanswerable` → `version_conflict` → `image_layout` → `table_numeric` → `cross_document_multi_hop` → `single_doc_multi_evidence` → `single_doc_single_evidence`。

| `primary_type` | 数量 | 题目要求 |
|---|---:|---|
| `single_doc_single_evidence` | 22 | 一个文档、一个完整证据片段即可回答；覆盖事实、术语、产品属性 |
| `single_doc_multi_evidence` | 20 | 同一文档至少两个章节/片段，适合安装步骤、前置条件、故障处理和完整列表 |
| `cross_document_multi_hop` | 18 | 至少两个文档、至少两个不可替代的证据项；不能只靠标题相似度回答 |
| `table_numeric` | 14 | 表头、行列、数值、单位、测试条件必须同时保留；覆盖 VMmark、容量、规格和认证数据 |
| `image_layout` | 8 | 依赖图示、部件位置、标签、版面关系或视觉化表格；必须保存 bbox/区域定位 |
| `version_conflict` | 8 | 明确绑定版本、日期、型号或适用范围；只有源文档存在真实差异时才标“冲突”，不人为制造矛盾 |
| `unanswerable` | 10 | 从全部 46 份 PDF 中无法得到结论；覆盖信息缺失、属性缺失、错误前提、版本/范围不匹配、证据不足 |
| **合计** | **100** | |

### 3.1 交叉标签

主类型之外，为便于切片分析再加正交标签：

- `procedure_installation`：不少于 20 题；重点来自 BladeCenter、BCT 电源、CMA、BOMC 和 VMware 指南。
- `product_spec_or_compatibility`：不少于 20 题；覆盖服务器、存储、GPU、交换机、磁带和 ThinkAgile datasheet。
- `terminology_or_abbreviation`：不少于 8 题；要求答案给出全称或文档内定义，不能依赖常识展开缩写。
- `numeric_unit_or_condition`：不少于 14 题；数字必须连同单位、对象、条件和比较方向记录。
- `troubleshooting_or_failure_mode`：不少于 10 题；重点来自硬件维护手册与软件指南。
- `citation_required`：100 题均为 `true`；至少要求文档名 + 页码，视觉/表格题再要求区域或单元格。
- `multi_turn`：v1 暂不纳入，避免在 100 题中同时引入对话状态变量；可在 v1.1 追加独立扩展集。

推荐语言分布为 **70 道中文问题 + 30 道英文问题**。中文问题用于贴近实际使用，英文问题作为语料原语言对照；两种语言必须分别报告，不能把跨语言检索差异混入单一总分。若本轮目标只是英文文档抽取，可以将该比例全部切换为英文，但需在 manifest 中冻结。

## 4. split 设计：评测集，不是训练集

| split | 数量 | 用途 | 是否公开 Gold |
|---|---:|---|---|
| `dev` | 20 | 调整 chunk、召回、rerank、提示词和引用格式 | 可公开 |
| `pilot` | 20 | 只做标注质量、解析、证据链和端到端冒烟验收 | 可只公开问题，不公开完整 Gold |
| `formal` | 60 | 最终系统对比和论文/报告汇报 | 封存 |

切分必须按“问题族”分组：同一事实的改写、同一表格的不同问法、同一答案模板、近重复 PDF、同一版本族不能跨 split。由于本任务评估的是固定 46-PDF 语料，三个 split 可以共享候选语料，但不能共享问题和 Gold 证据的变体。

如后续要测“新文档泛化”，另建 `document_holdout` 任务：将文档族作为 group 做文档级留出；不要把这个结果与固定语料检索结果混成一个分数。

## 5. Gold 数据结构

`reference_answer` 只能作为展示文本，不能作为唯一评分依据。评分权威应是原子 claims 与证据集合。

```json
{
  "question_id": "moi100-q001",
  "split": "formal",
  "primary_type": "table_numeric",
  "subtypes": ["numeric_unit_or_condition", "performance"],
  "question": "……",
  "question_language": "zh",
  "answerability": "answerable",
  "reference_answer": "……",
  "accepted_answers": ["……"],
  "claims": [
    {"claim_id": "c1", "text": "……", "critical": true}
  ],
  "evidence_sets": [
    {
      "set_id": "e1",
      "logic": "AND",
      "items": [
        {
          "doc_id": "doc-…",
          "source_file": "2023-05-16-Dell-PowerEdge-R7625.pdf",
          "sha256": "…",
          "pdf_page": 1,
          "printed_page": null,
          "section": "Performance",
          "modality": "table",
          "bbox_norm": [0.03, 0.08, 0.96, 0.62],
          "row_or_cell": "…",
          "evidence_text": "…"
        }
      ]
    }
  ],
  "citation_required": true,
  "gold_version": "v1.0",
  "status": "frozen"
}
```

规则：

- `evidence_sets` 之间是 OR；同一 set 内的 evidence item 是 AND。多跳题必须把所有不可替代证据放进同一个完整 set。
- 每个答案拆为原子 claim，并标记 `critical`。数值 claim 要拆出数值、单位、对象、条件和方向。
- 证据定位至少包含 PDF SHA-256、文件名、1-based PDF 页码和 section；文本题保存 span，表格题保存表头/行/列，图示题保存 bbox 或区域截图索引。
- `unanswerable` 题保存 `negative_reason`、检索范围、已排除的文档/版本和可能的干扰证据，不能只写“没有答案”。
- 需要允许多个等价答案：单位换算、大小写、产品全称/缩写、同义表达分别写入 `accepted_answers` 或规范化规则。

## 6. 构建流程

### Phase 0：冻结语料与 manifest

为每个 PDF 建立 `doc_id` 和 SHA-256，记录页数、文件名、文档族、类型、语言、发布日期/版本、是否扫描、表格/图示页、近重复 cluster、授权/来源信息。生成：

`rag/datasets/moi-corpus-100q-v1/corpus_manifest.jsonl`

manifest 必须能在不依赖文件名猜测的情况下重建本次语料快照。

### Phase 1：解析与证据可用性检查

对每个 PDF 保留页边界、阅读顺序、标题层级、表格结构、图像/版面区域和原始页图。至少抽查以下代表性文件：

- `8720_8730_hmm.pdf`：长篇维护手册与章节级流程；
- `DB15-001161-08_LSI_Storage_Authority_Software_User_Guide.pdf`：长篇软件指南、版本和操作步骤；
- `2023-05-16-Dell-PowerEdge-R7625.pdf`：密集 VMmark 表格；
- `ds0001.pdf`：多栏产品宣传/规格文本；
- `Anti-Slavery_and_Human_Trafficking_Statement.pdf` 与 `5656-hidden-technical-debt-in-machine-learning-systems.pdf`：普通政策文本和论文排版。

若解析文本与源 PDF 的视觉内容冲突，以源 PDF 为准；解析器输出只能用于定位候选，不能直接当作 Gold。对表格跨页、页眉页脚混入、两栏阅读顺序和脚注归属做专项检查。

### Phase 2：候选证据池与配额分配

按文档族、章节、页面模态先选 claim 候选，再写问题。候选池至少覆盖：

- 安装/拆卸/电源/故障排查步骤；
- 产品规格、兼容性、接口、容量与特性；
- VMmark/认证报告的数值、单位、测试配置和日期；
- 软件版本、前置条件、命令或操作顺序；
- 政策的时间范围、适用法律/承诺，以及论文中的定义和分类；
- 真实缺失属性、错误前提和版本范围不匹配。

题目作者先填写证据和 claims，再生成自然问题；LLM 可以用于提出改写候选，但不能自主决定答案、证据页或负例结论。

### Phase 3：问题编写

每题必须自包含，明确型号、版本、对象和比较范围；避免“它”“该设备”等无法独立解析的指代。问题应真正需要检索，不能只靠文件名或常识猜出答案。

跨文档比较只比较可比字段，并同时记录测试日期、软件版本、主机数、tile 数等条件。对于性能报告，不把不同实验配置下的分数直接表述为“谁更好”，除非 Gold 证据明确支持这种比较。

### Phase 4：双人标注与仲裁

100 题全部由作者 A 标注、作者 B 独立复核；出现分歧时由仲裁者根据原始 PDF 定稿。复核重点：

1. 问题是否只有一个明确解释；
2. answerability 是否正确；
3. 每个 critical claim 是否被完整证据支持；
4. 数字、单位、版本、日期、负号和比较方向是否正确；
5. 页码、section、bbox/table cell 是否能在源 PDF 中复现；
6. 负例是否真的检查过全部 46 份 PDF，而不是只看了候选文档；
7. 是否与其他题重复或形成跨 split 泄漏。

### Phase 5：一致性检查与冻结

自动检查 question ID、文件 hash、页码范围、bbox 范围、空 evidence set、重复问题、重复答案模板、split 泄漏和未使用的 type quota。通过后冻结：

- `questions.all.jsonl`：内部完整 Gold；
- `questions.dev.jsonl`：问题与可公开 Gold；
- `questions.pilot.jsonl`：问题及必要的审计信息；
- `questions.formal.jsonl`：封存 Gold；
- `annotation_guidelines.md`：标注规范；
- `review_ledger.jsonl`：作者、复核者、仲裁、修改历史；
- `README.md`：版本、语料 hash、字段、评测协议和已知限制。

建议数据根目录：`rag/datasets/moi-corpus-100q-v1/`。

## 7. 评测协议与指标

至少运行两种模式，避免把检索问题和生成问题混为一谈：

1. **Native mode**：系统面对全部 46 份 PDF，自行解析、切分、召回、生成和引用。
2. **Gold-context mode**：注入 Gold evidence，单独评估答案生成、完整性、数值准确性和引用表达。

建议主指标按层报告，不做异构指标的简单加权总分：

| 层 | 指标 |
|---|---|
| 语料/解析 | 文件和页可用率、Gold 页可定位率、文本/表格/图示结构保留率 |
| 检索 | Doc Recall@K、Evidence Recall@K、Complete Evidence Set Recall、MRR/nDCG、Context Precision、无效干扰比例 |
| 答案 | atomic claim precision/recall、critical claim coverage、答案正确率、完整性、数值/单位准确率、范围/版本正确率 |
| 拒答 | `unanswerable success`、false refusal、无依据补全率 |
| 引用 | 定位有效率、citation entailment precision、required-claim coverage、伪造/越界引用率 |
| 可靠性 | 运行成功率、超时/错误率、重复运行稳定性、P50/P95 延迟、token/cost |

最终可以汇报一个门槛式的 `Trusted Answer Rate`，但必须保留上述分层指标。对可回答题，只有“答案正确且完整、critical claims 全覆盖、Gold-supported、引用有效（若要求引用）”才算 trusted；对不可回答题，只有正确拒答且不编造事实才算 trusted。

## 8. v1 验收门槛

- 100/100 题均有合法 ID、split、primary type、answerability 和版本信息。
- 90 道可回答题均有至少一个完整 evidence set；多证据题的每个不可替代证据均已标注。
- 10 道不可回答题均有负例理由和全语料检查记录。
- 100% critical claims 可由源 PDF 的页/片段/表格单元格/图示区域复核。
- 100% 数值题保留单位和测试条件；表格题不允许只引用孤立数字。
- 100% 题经过独立双人复核，分歧全部有仲裁记录。
- 近重复问题、同一 claim 的改写和同一表格变体不得跨 split；正式集 Gold 在评测前不可见。
- 至少 32/46 份 PDF 产生直接 Gold 证据，所有五个文档族均有题目；其余 PDF作为候选干扰文档保留。
- 封面/目录单独作为唯一证据的题目不超过 20%；正文、表格、图示和流程证据必须占主体。

## 9. 首轮执行顺序

1. 生成并审阅 `corpus_manifest.jsonl`，完成 hash、页数、文档族、版本和重复族标记。
2. 对长手册、软件指南、datasheet、性能表、政策和论文各抽查解析与视觉定位。
3. 建立 140–160 个候选 claim，按七类主类型和五个文档族配额筛至 100 题。
4. 先完成 20 道 `dev`，用它验证字段、证据 set 逻辑、评分脚本和引用协议。
5. 完成剩余 80 题，双人复核并仲裁；冻结 `pilot` 与 `formal`。
6. 在 Native / Gold-context 两种模式各跑一次基线，输出按主类型、文档族、语言和证据模态切片的结果。

这套 v1 的重点是“可追溯的 100 道题”，而不是题目数量本身。后续扩展到 300/1000 题时，可以沿用同一 schema 和文档族配额，新增多轮对话、更新/删除泄漏和更强的视觉问答子集，而不需要重写 Gold 规范。
