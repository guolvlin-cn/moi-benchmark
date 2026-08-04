# GDPval：高保真工作产物评测与开放复现缺口

日期：2026-07-28  
状态：已核验 ICLR 2026 论文、官方数据卡、GDPval v2 Parquet 和公开评测实现；未下载约 2.29 GB 的全部附件，也未组织专家 pairwise 或自建 rubric grader  
当前公开版本：`openai/gdpval@11e7900cdcac61bc4daf59e65feb238acda98fbf`

## 摘要

GDPval 是 OpenAI 构建的现实知识工作 benchmark。完整集有 1,320 个任务，覆盖美国 GDP 贡献最高的 9 个行业中的 44 个数字化知识工作职业；公开的 gold subset 为每职业 5 题，共 220 题。任务由平均拥有 14 年经验的从业者基于真实工作产物创建，要求模型阅读上下文和附件，并交付文档、表格、演示文稿、图像、音视频、代码或多文件组合。与问答型 benchmark 相比，GDPval 更能暴露指令遵循、文件格式、跨模态检查和产物可用性问题。

它的边界同样重要。**GDPval 的“经济价值”主要来自行业和职业的选择方法，以及专家自报工时乘以职业工资的估算；公开任务并未按 GDP、就业人数、工资或任务频率加权，GDPval 分数不能解释成“可自动化 GDP 的比例”。** 初始协议是上下文充分、一次性交付的 one-shot 任务，不覆盖需求澄清、组织沟通、权限、私有系统、长期反馈和物理执行。官方主评测依赖同职业专家对模型与人类产物做盲测 pairwise comparison；论文期的实验性自动 grader 人机一致度为 65.7%，低于人类间 70.8%，且排除 12 个难以自动评分的任务。当前 OpenAI 托管的 grading request 和 leaderboard 已停止，官方页面改为建议使用公开 rubric 和 gold deliverable 自行评测 [9]。

2026-02-10 发布的 GDPval v2 比论文发布时的公开包更完整：除 prompt 和 reference files 外，新增人工 rubric 和部分 expert deliverables。本地读取当前 Parquet 得到 220 个唯一任务、12 个字段、261 个被任务实际引用的 reference 路径、248 个 deliverable 路径和 10,453 个 rubric items；固定版本仓库中另有 301 个物理 reference files，即 40 个没有被当前 Parquet 引用的额外文件。但 35 个任务没有任何公开 deliverable 路径，公开 schema 也缺少 O*NET 标签、工时、价值、难度、质量和 grader-exclusion 标记。数据卡没有声明许可证，仓库根目录也未见 `LICENSE`。

对 Astra/MOI，GDPval 最适合作为**多模态文件型 Agent 的任务源和产物质量压力测试**，不宜单独作为自主性、生产率、私有数据访问或劳动替代的 headline benchmark。采用时应固定 v2 commit，把 220 题视为公开开发/审计集，采用“确定性文件检查 + rubric judge + 人工校准”的分层评分，并将 MOI 故障注入结果与官方 GDPval 分数严格分开。

## 1. 调研问题与范围

本报告回答三个问题：

1. **RQ1：** GDPval 的官方身份、版本、公开范围与可复现资产是什么？
2. **RQ2：** 公开数据的实际 schema、行业/职业组成、输入输出形态和典型任务是什么？
3. **RQ3：** GDPval 如何评分，其效度和开放复现边界是什么，Astra/MOI 应如何使用？

范围以 ICLR 2026 论文、OpenAI 官方页面和 Hugging Face 官方仓库为主。为检查外部可复现性和定位差异，还纳入 UK AISI `Inspect Evals` 的 GDPval 实现，以及 EconEvals、Remote Labor Index、APEX 和 WorkArena 的原始论文。第三方排行榜、营销转述和未能核验来源的模型分数不进入结论。

## 2. 方法与版本冻结

检索按四个相互校验的视角进行：

- **官方定义与构造：** ICLR 2026 论文和 OpenAI 发布页；
- **当前公开工件：** Hugging Face 数据卡、文件树、提交历史和固定 revision；
- **实际数据：** 只读分析固定 revision 的 Parquet；
- **评测与反证：** 官方 grader 描述、UK AISI 公开实现及相邻经济任务 benchmark。

本地统计使用 DuckDB 1.5.5。由于官方 Hugging Face 大文件端点在本环境中不可解析，1.91 MB Parquet 通过 HF Mirror 的同一 immutable revision 传输；分析文件为：

| 项目 | 冻结值 |
|---|---|
| 官方仓库 | `openai/gdpval` |
| 当前公开 revision | `11e7900cdcac61bc4daf59e65feb238acda98fbf` |
| 数据文件 | `data/train-00000-of-00001.parquet` |
| 文件大小 | 1,913,489 bytes |
| SHA-256 | `f8422fab9b21d90c0ee5f0659842ab666d418cb8940842918f9f4b0df7ae0202` |
| HF split 名 | `train` |
| 语义角色 | 公开 gold evaluation subset，而非训练集 |
| 仓库总大小 | 约 2.29 GB |

此次没有把 Parquet 或 2.29 GB 附件持久化到项目 `work/` 目录；统计只用于本报告。后续若正式接入，应重新下载完整 pinned snapshot，并生成逐文件 manifest。

## 3. 数据集身份与版本演进

### 3.1 Full 与 public gold 不是同一可用范围

GDPval full set 包含 1,320 个任务，即 44 个职业各 30 题；公开 gold subset 是各职业 5 题，共 220 题 [1,2]。完整集及论文中的人工模型评测资产并未整体公开。当前 Hugging Face 仓库提供：

- 220 个 prompt；
- reference file 路径与实际附件；
- v2 新增的 rubric；
- v2 新增的部分 expert deliverable files。

因此“GDPval 有 1,320 题”描述的是论文完整集，“可以公开下载并自行运行”目前只适用于 220 题 gold subset。HF 将它命名为 `train` split 只是数据托管格式，不能据此将其当作训练数据。数据卡还放置了 canary 字符串，表明维护者明确关注训练污染 [3]。

### 3.2 v1 与 v2

| 版本 | 时间 | Parquet 字段 | 公开内容 | 复现含义 |
|---|---|---:|---|---|
| 初始公开版 | 2025-09-25 | 7 | prompt、行业、职业、reference 文件三类路径 | 只能生成产物；当时 gold comparison 和 rubric 主要依赖官方服务 |
| GDPval v2 | 2026-02-10 | 12 | 在 v1 基础上增加 deliverable 三类路径、`rubric_pretty`、`rubric_json` | 可做更多本地审计和自建评分，但仍不等于官方 grader |

初始公开版可冻结到 `4bf642692ef091918ef20797ecca070924815ec1`；其 Parquet 为 342,719 bytes，SHA-256 为 `e26aeea5542ece91356d51cfb4d2f46cdb0ac86ab311b825b8d67bc06cbe4d9f`。v2 commit 信息为 “Release GDPval v2 (rubrics + deliverables)” [3]。当前 README 仍只写“每题由 text prompt 和 supporting reference files 构成”，没有同步解释新增字段、缺失 deliverable 或 rubric 的聚合规则；使用者必须以实际 schema 为准。

### 3.3 许可证状态

截至本次核验：

- Dataset card front matter 没有 `license` 字段；
- 根目录文件树没有 `LICENSE`；
- 数据卡只有敏感内容和第三方品牌/人物的 disclosure；
- 论文的开放许可不自动构成数据、图片、音视频和第三方素材的许可授予。

因此，**公开可下载不等于存在清晰的数据再利用许可证**。内部研究前可先记录来源与固定 revision；向外再分发、公开衍生集或商业使用前，应单独确认 OpenAI 和相应素材权利方的许可边界。

## 4. 构造逻辑：GDP 决定入口，等量职业任务决定分数

### 4.1 行业与职业选择

作者先选取 Q2 2024 中各自贡献超过美国 GDP 5% 的 9 个行业，再从每个行业选择总工资与补偿较高、且以数字工作为主的职业 [1]。职业是否“predominantly digital”由 GPT-4o 对 O*NET tasks 分类，并在按 relevance、importance 和 frequency 加权后，以数字任务占比至少 60% 为门槛。

9 个行业及公开题数如下：

| 行业 | 公开题数 | 职业数 |
|---|---:|---:|
| Professional, Scientific, and Technical Services | 25 | 5 |
| Government | 25 | 5 |
| Information | 25 | 5 |
| Manufacturing | 25 | 5 |
| Real Estate and Rental and Leasing | 25 | 5 |
| Finance and Insurance | 25 | 5 |
| Wholesale Trade | 25 | 5 |
| Health Care and Social Assistance | 25 | 5 |
| Retail Trade | 20 | 4 |
| **合计** | **220** | **44** |

每个职业恰好 5 题。由此可见，公开集是**职业等权设计**：一个 employment 很小的职业与 Registered Nurses 或 Software Developers 在 micro-average 中权重相同。GDP 和工资用于筛选行业/职业，不用于对 220 个任务的最终分数加权。

### 4.2 专家与质量控制

任务作者至少具有 4 年相关职业经验，平均 14 年；还需通过视频面试、背景调查、培训和测验。论文称入选率低于 10%，每个职业至少有 5 名合格专家 [1]。

完整 1,320 题经过模型筛查和多阶段人工复核，每题平均获得 5 次、最少 3 次人工 review。流程至少包括：

1. generalist 检查项目要求；
2. 同职业专家检查代表性和上下文充分性；
3. 终审专家与作者迭代修改直至通过。

论文报告公开 gold subset 覆盖 208 个 O*NET tasks、25 种 skills 和 26 种 general work activities；89.07% 任务被职业专家评为 well-specified [1]。但这些 O*NET 映射和 specificity 评分不在当前公开 Parquet 中，外部使用者无法逐题复核或据此分层。

### 4.3 工时和“经济价值”口径

专家提交并由其他专家复核任务所需时间；任务价值按估计工时乘以相应职业的 BLS median hourly wage。论文对 gold subset 给出：

| 指标 | 均值 | 中位数 | 最大值 |
|---|---:|---:|---:|
| 专家预计完成时间 | 9.49 小时 | 5 小时 | 100 小时 |
| 估算任务价值 | \$398.46 | \$174.81 | \$4,114.20 |

同一论文正文又称专家平均约 7 小时，速度/成本分析使用的 gold 平均值为 404 分钟，即约 6.73 小时和 \$361 [1]。这些数字可能来自不同筛选或聚合口径，但论文没有提供公开逐题字段供外部重算。稳妥表述是：**GDPval gold 任务的典型人类工时为数小时，论文不同口径的均值约 6.7–9.5 小时，中位数为 5 小时。**

“任务价值”不是市场成交价，也没有计入利润、风险、返工、监督和组织集成。它适合作为构造时的粗略价值 proxy，不是实际生产率或 GDP 贡献测量。

## 5. 公开 v2 的实际 Schema 与组成

### 5.1 12 个顶层字段

| 用途 | 字段 | 含义 |
|---|---|---|
| 身份 | `task_id` | UUID，当前 220 个均唯一 |
| 经济分类 | `sector`, `occupation` | 9 个行业、44 个职业 |
| 待测输入 | `prompt` | 角色、背景、约束、任务和输出要求 |
| Reference 本地路径 | `reference_files` | snapshot 内相对路径 |
| Reference 网络路径 | `reference_file_urls`, `reference_file_hf_uris` | HTTPS 与 `hf://` 地址 |
| Human deliverable 本地路径 | `deliverable_files` | v2 增加的 expert output 相对路径 |
| Human deliverable 网络路径 | `deliverable_file_urls`, `deliverable_file_hf_uris` | HTTPS 与 `hf://` 地址 |
| 评分规范 | `rubric_pretty`, `rubric_json` | 人类可读 rubric 与结构化 rubric items |

公开 schema **没有**：

- O*NET task、skill 或 work activity ID；
- 专家预计工时和任务价值；
- 质量、难度、代表性和 specification 评分；
- 哪 12 个任务被官方自动 grader 排除；
- 人类/模型 pairwise grades、grader rationales 或 paper 中的模型输出；
- 标准 Agent 轨迹、操作预算和 deterministic oracle；
- 明确的许可证字段。

### 5.2 完整性与长度

| 指标 | 本地结果 |
|---|---:|
| 行数 / 唯一 `task_id` | 220 / 220 |
| 唯一 prompt | 220 |
| 行业 / 职业 | 9 / 44 |
| Prompt 中位词数 | 324 |
| Prompt 最小 / 最大词数 | 101 / 1,133 |
| Parquet 中被任务引用的 reference 路径 | 261 |
| 仓库中的物理 reference files | 301 |
| 有 reference 的任务 | 125 / 220，56.8% |
| 每题 reference 中位数 / P90 / 最大值 | 1 / 3 / 17 |
| Deliverable files | 248 |
| 有公开 deliverable 路径的任务 | 185 / 220，84.1% |
| 每题 deliverable 中位数 / P90 / 最大值 | 1 / 2 / 6 |
| Rubric items | 10,453 |
| 每题 rubric items 中位数 / P90 / 最大值 | 47 / 67 / 137 |

261 是当前 Parquet 中去重后的被引用路径数；固定版本仓库的文件树实际包含 301 个 reference files，因此有 40 个物理文件未被当前行级路径引用。248 个 deliverable 路径则与仓库中的 248 个物理 deliverable files 一致。所有 `rubric_json` 均可解析，`author_type` 均为 `human`。Rubric item 通常含 signed integer `score`、自然语言 `criterion`、UUID、tags 等；部分 criteria 是正向得分，部分是负向惩罚。数据卡没有给出 canonical normalization、最低分截断或 pairwise aggregation 规则，因此不能把各项权重简单求和后称为“官方 GDPval 分数”。

35 个没有 `deliverable_files` 的任务并不全是 text-only：其中存在明确要求 PDF、WAV 或视频文件的 prompt。公开 v2 因而只能称为“新增了部分 human deliverables”，不能假定 220 题都有可本地比较的完整 gold output。

### 5.3 文件类型

下表只统计当前 Parquet 实际引用的路径，分别给出文件数和至少包含该类型的任务数；一个任务可含多种类型，因此任务数不能相加。仓库中未被行级路径引用的 40 个 reference files 不进入该表。

| 文件类型 | Reference 文件数 | 含该 reference 的任务数 | Deliverable 文件数 | 含该 deliverable 的任务数 |
|---|---:|---:|---:|---:|
| `.xlsx` | 86 | 57 | 65 | 62 |
| `.pdf` | 74 | 38 | 85 | 68 |
| `.docx` | 67 | 45 | 64 | 53 |
| `.pptx` | 1 | 1 | 17 | 16 |
| 常见图片（`.png` / `.jpg` / `.webp`） | 14 | 7 | 4 | 2 |
| 音频 | 10 | 5 | 0 | 0 |
| 视频 | 2 | 1 | 2 | 2 |
| `.zip` | 3 | 3 | 5 | 5 |
| 代码/Notebook/配置/查询 | 1 个 `.txt` | 1 | 6 | 4 |

Reference 还包括 `.step`、`.psd`、`.webp` 等专业格式；deliverable 中还出现 `.py`、`.ipynb`、`.yaml`、`.overpassql`、`.md` 和 `.txt`。这意味着“能回答 prompt”远远不够：Agent 还需读取、生成、渲染和自检异构文件。

### 5.4 论文与当前工件的差异

| 事项 | 论文/发布时描述 | 当前 v2 实测 | 解释 |
|---|---|---|---|
| 开放内容 | Prompt + references [1] | 增加 rubric 和部分 deliverables | v2 是发布后的实质更新 |
| 有 reference 的任务 | 67.7% [1] | 56.8% | 当前公开 artifact 无法复现论文比例 |
| Gold reference 最大值 | 正文写 17；附录表写 38 [1] | 17 | 论文内部口径或表标题存在歧义 |
| Gold deliverable 均值 / 最大值 | 1.54 / 36 [1] | 1.13 / 6 | 公开 v2 未包含论文统计中的全部产物 |
| O*NET/工时/价值 | 论文有聚合统计 | Parquet 无逐题字段 | 无法外部重算经济覆盖 |
| 自动 grader 排除 | 12 / 220 [1] | 无公开标记 | 外部无法提前得到标准有效分母 |

这些差异不妨碍把 v2 用作任务集，但要求报告结果时同时写明 paper version、HF revision 和实际评分分母。

## 6. 任务类别与典型实例

公开数据只有 `sector` 和 `occupation`，没有官方 `task_category`。下面按工作产物和能力需求给出多标签归纳，不应被写成官方 taxonomy：

| 派生类别 | 典型产物 | 主要能力 |
|---|---|---|
| 专业文档与知识整合 | 法律文本、政策、调查报告、护理/客服材料 | 多源阅读、事实约束、受众与风格控制 |
| 表格、建模与运营规划 | Payroll、预算、排班、库存、报价、财务模型 | 公式、结构化数据、业务规则、可更新性 |
| 演示与业务沟通 | PPTX、PDF briefing、培训材料 | 内容组织、视觉布局、叙事和一致性 |
| 工程分析与专业设计 | 计算脚本、图表、技术报告、CAD/图像 | 数值正确性、专业工具、跨文件一致性 |
| 音视频与创意制作 | 音频混音、视频剪辑、showreel | 时序编辑、codec、版权和审美判断 |
| 软件与数据接口 | OpenAPI、YAML、Notebook、查询文件、代码包 | 系统设计、可执行 artifact、故障恢复 |
| 多产物交付 | 多个 DOCX/XLSX/PDF/代码组合 | 文件命名、打包、交叉引用和完整性 |

### 6.1 代表性任务

下列例子直接来自固定 v2 Parquet；描述经过摘要，不复制完整 prompt：

| `task_id` | 职业 | 任务概述 | 输入 → 输出 | Rubric items |
|---|---|---|---|---:|
| `4520f882-715a-482d-8e87-1cb3cbdfe975` | Financial Managers | 根据音乐家集体协议、样例 roster 和 schedule，构建可年度更新并能提示合同冲突的周薪资模型 | DOCX + XLSX → XLSX | 88 |
| `43dc9778-450b-4b46-b77e-b6d82b202035` | Accountants and Auditors | 根据 15 份 2024 税务资料完成夫妻 Form 1040 及电子申报所需 schedules/forms | 15 PDF → 2 PDF | 67 |
| `46fc494e-a24f-45ce-b099-851d5c181fd4` | Mechanical Engineers | 用 22-node conduction model 评估 C/SiC 热盾 20 分钟暴露，生成温度曲线、等温图和结论 | PDF → Python + 3 PNG + PDF | 81 |
| `75401f7c-396d-406d-b08e-938874ad1045` | Film and Video Editors | 从 13 段视频和音效剪出不超过 80 秒、1080p H.264 的 CGI showreel | MP3 + ZIP → MP4 | 40 |
| `d025a41c-c439-4ee1-bc79-dd5c94b27a2d` | Customer Service Representatives | 分析三段低满意度银行客服聊天，定位问题表述、解释原因并给出替代表达 | 3 DOCX → DOCX | 60 |
| `2c249e0f-4a8c-4f8e-b4f4-6508ba29b34f` | Software Developers | 为多机器人、可断点续传且区分 insight/payload 优先级的数据上传流程设计 OpenAPI | 无附件 → TXT + YAML | 50 |

这些例子说明 GDPval 同时测量内容正确、工具能力和产物质量。表格任务若只给出正确数字但公式不可更新，视频任务若内容合理但 codec/时长不符，或报告正确但版面溢出，都可能被判为较差。

## 7. 评分机制与可复现性

### 7.1 官方主指标是专家 pairwise preference

每道任务的人类基线是 task writer 自己制作的 professional deliverable。评测时，同职业 expert grader 在尽量盲化的情况下查看 prompt、references 和未标记来源的产物，判断模型产物相对人类产物为：

- better / win；
- as good as / tie；
- worse / loss。

论文对每个模型、每个 prompt 采样 3 次，再由 3 位不同专家评分，理论上每题每模型形成 9 个 comparisons [1]。主结果以 win rate 和 wins + ties 表达。Claude Opus 4.1 在公开 gold subset 中有 47.6% 的 deliverables 被评为 win 或 tie；这说明当时最强系统在相当一部分**充分上下文化、一次性交付**任务上接近人类产物，不等于可以替代对应职业或完成整个岗位。

盲测也不是完全不可识别：论文明确承认模型可因 em dash、第一人称或自报模型名等风格被猜出。不同模型的工具条件也不一致：OpenAI 模型使用 web search、code interpreter 和后台采样，Claude 经产品 UI 使用文件创建能力。因此 GDPval 论文分数是 **model + product surface + scaffold + sampling budget** 的系统级结果，不是裸模型能力。

论文的 GPT-5 scaffold 改进还使 human-preference 指标提高约 5 个百分点，并显著增加 Agent 对生成产物的自检比例 [1]。这进一步说明 GDPval 对 prompt、文件工具和质量控制回路敏感；跨系统比较必须同时冻结这些条件。

### 7.2 实验性自动 grader

官方自动 grader 基于 GPT-5-high，对模型和人类 deliverable 做 pairwise 判断。论文定义的 agreement 为：

```text
1 - |human_score - automated_score|
```

其中 win/tie/loss 映射为 1/0.5/0。这个 65.7% 是带 ordinal partial credit 的一致度，不是普通三分类 accuracy。三轮 grader sweep 中：

- human–automated agreement：65.7%；
- human–human agreement：70.8%；
- 12 / 220 题因网络、非 Python 软件任务、字体或音频能力等问题被排除；
- grader 对较强 OpenAI 模型的一致度更低，论文将其与模型偏好自身回答的已知问题联系起来 [1]。

因此官方仍推荐职业专家评分。自动 grader 适合快速迭代，不应当作无误差 oracle。

### 7.3 v2 rubric 不等于开放了 canonical grader

v2 的 10,453 条人工 rubric 提高了透明度，可以支持：

- 文件存在、扩展名、页数、分辨率等 deterministic checks；
- 针对 criterion 的本地 LLM/VLM judge；
- 对 signed penalties 的错误诊断；
- 与公开 expert deliverable 的 pairwise comparison。

但官方没有在 dataset repo 中发布完整 grader code、标准 prompt、模型版本锁定、所有工具链和 rubric aggregation 规则。即使使用相同 rubric，不同 renderer、office suite、字体、OCR、视频/audio parser 和 judge model 也可能产生不同分数。

截至 2026-07-28，OpenAI 的 GDPval grading 页面明确表示不再接收 grading requests，托管 leaderboard 也已停止；页面建议使用公开 rubrics 和 gold deliverables 自行运行评分，并强调同职业专家 pairwise preference 才是标准，LLM judge 只能给出粗略估计 [9]。因此当前不存在一个可提交结果并获得 canonical 官方分数的远程服务。

### 7.4 UK AISI 的历史运行路径揭示了复现差异

UK AISI `Inspect Evals` 实现了 GDPval generation harness：在 Docker 中向 Agent 提供 bash/python 和文件工具，将结果上传 Hugging Face，再由用户通过 OpenAI 网页提交自动评分 [4]。这是托管 grader 仍在线时的历史工作流；当前 OpenAI 已停止接收请求，不能再把该提交路径视为可用的官方复现入口。该实现曾报告：

- GPT-5 low 的一次运行有 219 / 220 题成功评分；
- 自动 grader 平均分为 47.3% ± 6.2%；
- 同一 README 记录官方 leaderboard 的 GPT-5 low 为 31.9% wins、34.6% wins + ties。

这几个数字的聚合和运行条件不同，不能直接横比，但差距本身说明：scaffold、工具替代、采样、上传格式、grader 重复和指标定义都会显著影响结果。正式 benchmark 必须保存这些条件，而不能只记录模型名。

## 8. “100× 更快更便宜”应如何理解

OpenAI 发布页概括称 frontier models 可约 100× 更快、更便宜，同时明确这只是纯推理时间和 API 费用，不含监督、迭代和集成 [2]。论文附录给出更可操作的对照：

| GPT-5 口径 | 速度改进 | 成本改进 |
|---|---:|---:|
| 只比 API 生成与专家从头完成 | 90× | 474× |
| 模型试 1 次，专家 review，不合格则重做 | 1.12× | 1.18× |
| 可反复采样，仍不合格则专家完成 | 1.39× | 1.63× |

Gold subset 中专家平均完成成本按该分析为 \$361，首次 review 平均还需 109 分钟和 \$86 [1]。当把质量门槛、review 和失败后的人工完成计入，headline 中的两个数量级优势降到约 1–2×。该模型还没有计入：

- 灾难性错误的非对称损失；
- 合规、审计和责任成本；
- 数据接入、权限与系统集成；
- prompt/工具工程和人工培训；
- 人类产物本身的复核成本。

GDPval 提供的是“在给定工作包上生成可比产物的潜力”，不是部署后的因果生产率估计。

## 9. 效度、偏差与污染

### 9.1 它确实测到了什么

| 构念 | 覆盖 | 依据 |
|---|---|---|
| 长上下文与多附件理解 | 强 | Prompt 中位 324 词，最多 17 个公开 reference files |
| 异构工具与文件生成 | 强 | 文档、表格、幻灯片、代码、图像、音视频和专业格式 |
| 专业内容与业务规则遵循 | 强 | 同职业专家创建并评分，rubric 中位 47 项 |
| 产物审美与可用性 | 中到强 | Human pairwise 会考虑结构、格式、审美和相关性 |
| 一次性交付的长任务 | 中到强 | 专家任务工时以数小时计，但 Agent rollout 时间不等于人类工时 |
| 真实市场成交与部署收益 | 弱 | 价值由工时 × median wage 估算，不是市场成交或现场实验 |

### 9.2 它没有测到什么

- **交互式需求形成：** Prompt 已给出大量上下文；89% 任务被评为 well-specified。
- **多轮协作与反馈：** 当前协议是 one-shot，不测试与客户、同事或主管迭代。
- **私有数据与权限：** Reference files 是打包工件，不测试 credential、ACL、审批和最小权限。
- **专有软件和现场系统：** 需要 PII、专有系统、实时通信或物理执行的任务被排除。
- **过程安全与恢复：** 最终产物评分不要求 checkpoint、审计日志、崩溃恢复或可撤销操作。
- **完整劳动市场：** 只覆盖 44 个数字知识工作职业，且以美国经济结构为准。

论文的 under-contextualized 实验把 prompt 缩短到原 token 数的 42%，GPT-5 表现随之下降 [1]。这说明正式 GDPval 的高上下文化既提高可评分性，也减少了真实工作中“发现需要做什么、向谁询问、去哪里取数据”的难度。

### 9.3 Human preference 的可靠性上限

Human–human agreement 为 70.8%，且约 23% 的 GPT-5 failure 复核者反而认为模型更好；约 29% 被评为 bad 或 catastrophic，其中约 3% 为 catastrophic [1]。因此：

- 单次 pairwise judgement 噪声不可忽略；
- 只报告点估计会掩盖 grader variance；
- 高风险领域不能用总体 win rate 替代逐项安全审查；
- “模型与专家持平”是偏好统计，不是客观正确率。

### 9.4 污染与 gold 泄漏

公开集目前暴露 prompt、rubric、reference files 和 185 题的 deliverables，并在 HF 中使用 `train` split。对 2026 年以后训练或带搜索能力的模型，它已不是强 contamination-resistant 测试集。Canary 能帮助检测部分直接摄取，但不能证明模型没有从网页、派生仓库或生成轨迹中见过任务。

稳妥做法是：

- 把公开 220 题定位为 development、adapter QA 和 regression set；
- 报告模型训练/知识截止日期、是否联网和是否能访问 HF；
- 正式泛化结论使用私有任务、时间后移任务或未公开变体；
- 禁止 Agent 访问 `deliverable_file_urls`、`rubric_*` 和 grader metadata。

## 10. 与相邻 benchmark 的关系

下表的结论是：GDPval 在公开跨职业 benchmark 中提供了罕见的多文件 professional deliverables，但 interactive execution、完整项目、劳动市场覆盖和 canonical local scoring 需要其他 benchmark 补足。

| Benchmark | 任务单位与规模 | 环境 / 产物 | 评分 | 相对 GDPval 的增益与代价 |
|---|---|---|---|---|
| **GDPval** [1] | 1,320 full；220 public；44 职业 | 充分上下文化 one-shot，多文件产物 | 同职业专家 pairwise；托管自动 grader 已停止 [9] | 产物真实、职业广；公开评分不完全自包含 |
| **APEX 1.0** [7] | 200 cases；投行、咨询、法律、初级医疗 4 领域 | 专家高价值知识任务 | Rubric + LM judge | 领域更集中、评分更易批量；职业广度和文件多样性较低 |
| **Remote Labor Index** [6] | 240 个完整 freelance projects；10 public、230 private | Brief + inputs + human deliverable；平均 28.9 小时 | 人工 automation rate + Elo | 更接近端到端市场项目和真实成交；公开覆盖小、成本高 |
| **WorkArena** [8] | ServiceNow 中 33 类知识工作任务 | 可交互 enterprise web environment | 环境状态 / execution checks | 测真实软件操作与多步交互；只覆盖一个软件生态 |
| **EconEvals** [5] | 226 个报告 benchmark；扩展到 2,087 DWAs、1,016 职业 | 真实查询映射 + synthetic query，偏 text/chat | Reference-model pairwise judge | 覆盖与成本显著改善；作者也承认 GDPval 的产物对齐和数据质量更高 |

GDPval 与 RLI 的“接近人类”与“最高自动化率仅 2.5%”并不直接矛盾。GDPval 评估充分指定的职业任务产物，RLI 评估平均更长的完整 freelance project，并以是否达到可接受委托交付为绝对门槛 [1,6]。两者分别更接近 augmentation potential 和 end-to-end automation。

EconEvals 则呈现另一组权衡：它批评 GDPval 只覆盖少量美国职业且生成成本高，同时明确承认 GDPval 更贴近真实 work deliverables、数据质量更高 [5]。因此“扩大任务经济覆盖”和“保持每题高保真产物”目前仍是成本与可扩展性之间的张力。

## 11. 对 Astra/MOI 的接入建议

### 11.1 适用性判定

| 维度 | 判定 | 说明 |
|---|---|---|
| 任务真实性 | 高 | 专家基于真实工作产品创建 |
| 文件和工具压力 | 高 | 多格式读写、计算、渲染和自检 |
| 公开任务可得性 | 中到高 | 220 题可取，但 full 私有、完整 snapshot 约 2.29 GB |
| Canonical 本地评分 | 低 | 官方人评昂贵，托管 grader 已停止；自建 rubric judge 非 canonical |
| Gold 完整性 | 中 | 185 题有 deliverable 路径，35 题没有 |
| Agent 交互与状态治理 | 低 | one-shot，非 credentialed environment |
| 污染控制 | 低 | Public prompt/rubric/多数 deliverable 已开放 |
| 许可清晰度 | 低 | 数据仓库未声明 license |

### 11.2 推荐实施路径

1. **冻结工件。** 下载完整 `11e7900…` snapshot，记录所有 Parquet、reference 和 deliverable 的 SHA-256；禁止跟随 `main`。
2. **区分 Agent input 与评测 secret。** Agent 只看到 `prompt`、`reference_files` 和允许的通用工具；隐藏 `deliverable_*`、`rubric_*` 和所有 gold URL。
3. **建立统一文件协议。** 固定工作目录、文件名提取、最大文件数/大小、字符编码、压缩包策略、超时、网络和字体。
4. **先做确定性检查。** 文件存在、扩展名、可打开、页数、sheet 名、公式、codec、分辨率和结构化 schema 应由程序评分。
5. **再做 rubric judge。** 对内容、视觉和专业判断使用固定 VLM/LLM，多次采样并输出逐 criterion 证据；不要直接把 signed rubric weights 求和当官方分。
6. **做人工校准。** 从行业、职业和文件类型分层抽样，测本地 judge 与专家的一致度、偏差和置信区间。
7. **单列无 gold 的 35 题。** 它们可用于 instruction-following 或 rubric-only 评测，但不能与 185 题的 pairwise-to-human 指标混为一个分数。
8. **把公开集当开发集。** 正式产品比较应使用未公开的内部衍生任务或新的时间后移任务。
9. **报告系统而非裸模型。** 同时记录模型版本、reasoning、工具、renderer、联网、sampling、token、wall time 和成本。

### 11.3 适合的 MOI fault injection

GDPval 的文件型任务适合构造以下受控故障：

- reference file 缺失、重命名或损坏；
- 多个 reference 互相冲突或版本过期；
- Office/PDF renderer、字体或 codec 不可用；
- 长任务中断后从 checkpoint 恢复；
- 输出文件写入成功但上传/注册失败；
- 网络检索失败或来源不可访问；
- 临时磁盘不足、压缩包解压失败；
- 生成的文档可打开但存在截断、重叠或公式断链。

这些都是 **MOI-derived cases**。它们可以复用 GDPval 的职业语义和 rubric，但必须使用独立 ID、manifest 和指标，不能计入或宣称为官方 GDPval score。

不建议把真实 PII、客户数据或企业凭据直接注入公开任务。若要评估 private-data interaction，应使用合成身份、可撤销权限和隔离系统，并额外测量授权边界、数据最小化和审计日志；这不是 GDPval 原生覆盖的能力。

## 12. 开放问题

1. **版本和许可：** v2 缺正式 schema/version 文档与数据许可证。
2. **本地 grader：** 官方托管 grader 和 leaderboard 已停止，尚无完全开放、可固定模型和工具版本的 canonical grader。
3. **Gold 完整性：** 35 题无公开 deliverable，论文文件统计与当前 artifact 不一致。
4. **逐题经济元数据：** 工时、价值、O*NET 映射和质量标签未公开，阻碍经济加权与分层复现。
5. **交互式工作：** 尚未覆盖需求发现、反馈、审批、私有系统和跨人协作。
6. **全球代表性：** 行业与职业选择绑定美国 GDP、BLS 和 O*NET，不能直接外推其他经济体。
7. **污染：** v2 开放 rubric 和 human deliverable 后，公开集更适合开发而非长期隐藏测试。
8. **风险敏感评分：** 平均 win rate 会掩盖少量 catastrophic failures，医疗、法律和财务任务需要更高权重的安全门槛。

## 13. 结论

**RQ1：** GDPval full set 有 1,320 题，但当前公开可用范围是 220 题 gold subset。应冻结到 GDPval v2 revision `11e7900…`；v2 比发布版新增 rubric 和部分 human deliverables。公开仓库没有明确数据许可证，正式再利用前仍需确认权利边界。

**RQ2：** 当前 Parquet 有 220 个唯一任务、9 个行业、44 个职业和 12 个字段。它引用 261 个 reference 路径、248 个 deliverable 路径，并包含 10,453 个人工 rubric items；仓库另有 40 个未被 Parquet 引用的 reference files。文件形态以 PDF、XLSX、DOCX 和 PPTX 为主，并覆盖代码、图像和视频。职业各 5 题，分数是职业等权，不是 GDP 加权；公开 schema 也没有 O*NET、工时或任务价值字段。

**RQ3：** GDPval 的 canonical evidence 仍是同职业专家 pairwise preference；论文期自动 grader 只是 65.7% 一致度的代理，而当前官方托管 grader 和 leaderboard 已停止。它强测多文件专业产物、工具使用和 instruction following，弱测交互、私有数据、权限、过程恢复和真实部署收益。Astra/MOI 应把它作为高保真 artifact benchmark 与任务构造源，采用分层评分、隐藏 gold、固定环境并单列 fault cases，不应据此宣称岗位自动化率或经济影响。

本报告的核心判断是：**GDPval 把 benchmark 从“回答是否正确”推进到了“工作产物是否可用”，但尚未把公开任务、完整 gold、grader、版本、许可和经济权重封装成一个可离线复现的端到端标准。**

## 参考文献

[1] T. Patwardhan et al., “[GDPval: Evaluating AI Model Performance on Real-World Economically Valuable Tasks](https://iclr.cc/virtual/2026/poster/10008039),” ICLR, 2026；[全文 HTML](https://arxiv.org/html/2510.04374).

[2] OpenAI, “[Measuring the performance of our models on real-world tasks](https://openai.com/index/gdpval/),” 2025-09-25.

[3] OpenAI, “[openai/gdpval](https://huggingface.co/datasets/openai/gdpval/tree/11e7900cdcac61bc4daf59e65feb238acda98fbf),” Hugging Face Datasets, GDPval v2 revision, 2026-02-10；[提交历史](https://huggingface.co/datasets/openai/gdpval/commits/main).

[4] UK AI Security Institute et al., “[Inspect Evals: GDPval](https://github.com/UKGovernmentBEIS/inspect_evals/tree/main/src/inspect_evals/gdpval),” 2025–2026.

[5] A. Wan, S. Hatgis-Kessell, T. Aguirre, P. Liang, and R. Bommasani, “[Economic Evaluations of Language Models](https://arxiv.org/abs/2607.19375),” arXiv:2607.19375, 2026.

[6] M. Mazeika et al., “[Remote Labor Index: Measuring AI Automation of Remote Work](https://arxiv.org/abs/2510.26787),” arXiv:2510.26787, 2025.

[7] B. Vidgen et al., “[The AI Productivity Index (APEX)](https://arxiv.org/abs/2509.25721),” arXiv:2509.25721, 2025.

[8] A. Drouin et al., “[WorkArena: How Capable Are Web Agents at Solving Common Knowledge Work Tasks?](https://arxiv.org/abs/2403.07718),” ICML, 2024.

[9] OpenAI, “[GDPval Grading](https://evals.openai.com/gdpval/grading)” and “[GDPval Leaderboard](https://evals.openai.com/gdpval/leaderboard),” accessed 2026-07-28.
