#  NL2SQL 与 Text-to-SQL Benchmark 全景研究

## 执行摘要

从二零一七年至今，NL2SQL / Text-to-SQL 基准大致经历了四个阶段。第一阶段是 **单表、单数据库、低复杂度** 阶段，以 WikiSQL 为代表；第二阶段是 **跨数据库泛化** 阶段，以 Spider 为核心，并衍生出 SParC、CoSQL、CSpider 等多轮与多语言扩展；第三阶段是 **真实数据库与复杂 SQL** 阶段，以 KaggleDBQA、SEDE、BIRD、EHRSQL、BEAVER 为代表，开始强调真实 schema、数据库内容、行业知识、自然日志与执行效率；第四阶段则是 **Agentic、企业级、动态与安全导向** 阶段，以 Spider 2.0、LiveSQLBench、BIRD-Interact、BIRD-CRITIC、CLARITY、CORGI、EntSQL、BIRD-Ent/Spider-Ent 为代表，评测对象已不再只是“最终 SQL 字符串”，而是面向真实工作流、交互、调试、长上下文知识、业务规则漂移和数据库代理能力。citeturn41search4turn13view4turn22search0turn21search1turn13view0turn27search0turn35view1turn42search0turn37view0turn36search6turn42search2turn40search3turn40search0turn40search1turn34search1

截至二零二六年七月二十四日，**主流“综合 benchmark” 的中心已经从 Spider 单点，扩展为一个 benchmark family 生态**：Spider 家族覆盖单轮、上下文、多模态与企业工作流；BIRD 家族覆盖大规模真实数据库、效率、交互、动态环境与 SQL 调试；企业与业务侧则出现 BEAVER、CORGI、EntSQL、BIRD-Ent/Spider-Ent 这类补足“学术 benchmark 与企业现实脱节”问题的新基准。研究上已经很难再用“只测 Spider / BIRD dev 上的 EX”来代表系统是否具备生产级 NL2SQL 能力。citeturn13view4turn14view3turn15view0turn42search0turn13view0turn36search8turn37view0turn35view1turn40search0turn40search1turn34search1

二零二四年至二零二六年的最大变化有五点。其一，**从静态公开测试集转向隐藏测试、动态发布与持续演化**，代表项目是 LiveSQLBench 与其衍生的 BIRD-Interact；其二，**从只考 SELECT 转向覆盖 CRUD、运维与调试**，代表项目是 LiveSQLBench、BIRD-Interact、CRUDSQL、BIRD-CRITIC；其三，**从学术 schema 转向企业知识与长上下文 grounding**，代表项目是 Spider 2.0、BEAVER、EntSQL、BIRD-Ent/Spider-Ent；其四，**从单轮 SQL 生成转向数据库 Agent 成功率**，代表项目是 Spider 2.0、BIRD-Interact、DataAgentBench；其五，**从英语中心转向中文、多语言与低资源语言**，代表项目是 DuSQL、SeSQL、CSS、MultiSpider、MultiSpider 2.0、Ar-Spider、Dialect2SQL、PAUQ、BIRDTurk、IndicDB。citeturn37view1turn36search6turn31search0turn42search2turn42search0turn35view1turn40search1turn34search1turn25search8turn10search1turn31search14turn16search7turn10search11turn10search15turn16search18turn17search5turn18search1turn17search6turn18search2

当前最大的评测空白也很清楚。公开 benchmark 仍然显著偏向 **只读查询、英文或翻译型数据、公开数据库、无权限控制、弱安全约束、短期交互**；真正覆盖 **企业私有知识、权限边界、拒绝危险请求、跨 SQL 方言迁移、动态 schema 演化、长期用户会话、真实中文业务数据库** 的公开 benchmark 仍然稀缺。即便在最新工作中，这些方面更多是“开始被纳入”，而不是已经被充分解决。citeturn37view1turn35view1turn40search1turn34search1turn19search6turn40search3turn18search20

## 分类体系与版本关系

### 分类树

我建议把截至二零二六年七月二十四日的 NL2SQL 相关评测对象分成以下六层，而不是把所有“带 SQL 的数据集”都混为 benchmark。

**核心 benchmark**：直接以自然语言到 SQL 或到数据库任务成功为核心目标，提供公开数据、标准划分、官方评测或社区公认测试协议，如 WikiSQL、Spider、BIRD、Spider 2.0、BEAVER、LiveSQLBench。citeturn41search4turn13view4turn13view0turn42search0turn35view1turn37view0

**扩展 benchmark**：在已有 benchmark 基础上，新增对话、交互、鲁棒性、多语言、企业化、领域知识等维度，如 SParC、CoSQL、CSpider、Dr.Spider、BIRD-Interact、BIRD-Ent/Spider-Ent、MultiSpider 2.0。citeturn14view3turn15view0turn10search4turn16search8turn36search6turn34search1turn10search15

**评测框架**：给 benchmark 增添更可靠打分协议或更细粒度分析层，比如 Test Suite Accuracy、ROSE、BEAVER 的五类子任务标注、NL2SQL-BUGs 的语义错误检测。它们有的不是新数据库数据集，但会直接改变“同一个 benchmark 如何测”的结论。citeturn20search3turn20search4turn35view0turn40search2

**leaderboard 与 evaluation server**：例如 Spider/SParC/CoSQL 的官方挑战页面、BIRD leaderboard、Spider 2.0 leaderboard、LiveSQLBench leaderboard、BEAVER leaderboard、BIRD-CRITIC leaderboard、EHRSQL shared task 平台。这类资源不一定对应全新数据集，但决定了“官方结果”的产生方式。citeturn13view5turn14view3turn14view2turn13view2turn42search6turn37view2turn35view0turn42search2turn27search15

**shared task / competition**：例如 EHRSQL 2024 shared task；Spider/CoSQL/SParC 也可视作 challenge 式 shared task。此类项目经常具有隐藏测试集与受控提交，因此比“公开 dev 集离线跑分”更抗污染。citeturn15view2turn14view3turn27search2turn27search15

**训练数据或再组合数据**：例如 Gretel 的 synthetic_text_to_sql、SQL-GEN 生成的方言数据、一些对 WikiSQL/Spider 的重制版本。它们对训练有价值，但如果没有稳定测试协议、隐藏集或社区公认 leaderboard，就不应自动视为“核心 benchmark”。citeturn31search6turn31search8turn41search11

### 版本、继承与重构关系

Spider 是最重要的祖先节点之一。SParC 是 Spider 的上下文/多轮版本；CoSQL 则在 Spider 与 SParC 基础上进一步加入了系统澄清、不可回答问题和自然语言响应；CSpider、PAUQ、Ar-Spider 都是 Spider 的语言本地化或翻译扩展；MultiSpider 是 Spider 的七语版本，MultiSpider 2.0 则把这一思路扩展到 Spider 2.0 的企业级复杂设置。换言之，这些项目绝不是完全独立的 benchmark，而是 **共享数据库骨架、共享评测理念或共享任务定义的家族分支**。citeturn13view4turn14view0turn15view0turn10search4turn18search1turn16search18turn10search11turn10search15turn42search0

BIRD 也已经形成明确 family。原始 BIRD 主打大规模真实数据库、数据库内容与效率；之后扩展出 BIRD Mini-Dev、BIRD-CRITIC、BIRD-Interact，以及基于其理念构建的 LiveSQLBench。官方站点在二零二五年至二零二六年持续发布这些分支，说明 BIRD 已从单一 benchmark 演化为 **一套面向真实数据库智能的评测生态**。citeturn13view0turn13view2turn42search2turn36search6turn37view0turn13view3

企业化新 benchmark 也有“继承—重构”关系。BIRD-Ent/Spider-Ent 明确宣称是对 BIRD 与 Spider 的企业化 refinement；CLARITY 是在 Spider 和 BIRD 上自动构造多重歧义与不可回答交互；AmbiDB 则是专门面向 schema linking 歧义的 Spider 变体。因此，文献里出现“某某新 benchmark”，并不总意味着新建了全新数据库与评测协议，有相当一部分其实是 **基于现有 benchmark 的 targeted challenge set**。citeturn34search1turn40search3turn12search1

## 全景总表

### 基础与主流综合 benchmark

| 名称 | 首发 | 定位 | 任务形式 | 规模与特点 | 与其他项目关系 | 状态 | 主要来源 |
|---|---:|---|---|---|---|---|---|
| WikiSQL | 2017 | 基础 benchmark / dataset | 单轮、单表 | 80,654 问答-SQL，24,241 表；适合低复杂度 SQL | 现代大模型时代常被视为“过易”基线；有后续 LLMSQL 重制版 | 公开；仍常用作历史基线 | citeturn41search4turn41search0turn41search11 |
| Spider | 2018 | 经典综合 benchmark | 单轮、跨数据库、跨领域 | 10,181 问题、5,693 唯一 SQL、200 DB、138 域；强调数据库级泛化 | SParC、CoSQL、CSpider、多种鲁棒性变体、Spider 2.0 的祖先 | 官网与 leaderboard 仍在线 | citeturn13view4turn13view5turn23search11 |
| KaggleDBQA | 2021 | 真实世界综合 benchmark | 单轮、跨数据库 | 来自真实 Kaggle Web 数据库，强调原始 schema、文档与现实部署差距 | 与 Spider 互补，偏“真实 schema” | 代码与测试协议公开 | citeturn22search0turn22search3turn22search6 |
| SEDE | 2021 | 真实用户日志型 benchmark | 单轮 | 12,023 对问句-SQL，来自 Stack Exchange 的自然发生查询；强调真实表达 | 不是 Spider 式人工构造，而是“in the wild” | 公开 | citeturn21search1turn21search2 |
| BIRD | 2023 | 大规模现实复杂 benchmark | 单轮、跨域、内容感知 | 12,751+ 问答-SQL，95 个大数据库，总计 33.4GB，37+ 专业域；强调数据库内容与效率 | 派生 Mini-Dev、Interact、Critic、LiveSQLBench | 官方站点与 leaderboard 活跃更新 | citeturn13view0turn18search3turn9search12 |
| Spider 2.0 | 2024 | 企业级工作流 benchmark | Agentic / workflow-oriented | 632 个真实企业 text-to-SQL workflow 问题；常含 1,000+ 列；涉及 BigQuery、Snowflake 等系统，多 SQL、多操作、超长上下文 | Spider 家族的企业级重构；又衍生 Spider2-DBT | ICLR 2025；官网 leaderboard 在线 | citeturn42search0turn42search6turn42search10 |
| BEAVER | 2024 | 企业 benchmark | 单轮为主，带细粒度子任务 | 9,128 问答-SQL、812 表、19 域；数据来自私有组织真实查询日志；含五类子任务标注 | 企业场景的重要补足，与 BIRD/Spider 2.0互补 | 官网、数据、代码与 leaderboard 在线 | citeturn35view0turn35view1 |
| LiveSQLBench | 2025 | 动态 benchmark / evaluation suite | 单轮 + Agent | contamination-free、持续演化；Base-Lite 270 任务、Base-Full v1 600 任务、Large-v1 18 个工业级 DB 与 480 任务；支持 BI 与 CRUD，有隐藏测试和业务规则漂移 | BIRD family 的动态环境底座；BIRD-Interact 基于其任务与基础设施构建 | 官网与 GitHub 二零二六年持续更新 | citeturn37view0turn37view1turn37view2turn37view3turn37view4turn37view5 |
| CORGI | 2025 | 业务智能 benchmark | 单轮到多步业务推理 | 面向 business domain；四类问题：descriptive、explanatory、predictive、recommendational；比 BIRD 更偏 BI 决策 | 不同于传统“历史记录检索型” benchmark | arXiv 与公开评测框架 | citeturn40search0 |
| EntSQL | 2026 | 长上下文企业知识 grounding benchmark | 单轮、长文档 grounding | 1,066 个中英对齐样本，覆盖五个业务域；多数需要 schema 之外的企业文档知识 | 补足“企业知识不在 schema 中”的短板 | 截至研究日主要为 arXiv 项目 | citeturn40search1turn40search5 |
| BIRD-Ent / Spider-Ent | 2026 | 企业现实 refinement benchmark | 单轮企业化评测 | 通过 refinement framework 把 BIRD、Spider 重构为 massive scope、复杂 schema、分散知识环境 | 明确属于派生 benchmark，不应与原 BIRD/Spider 简单并列 | OpenReview 论文，公开性仍需持续跟踪 | citeturn34search1turn32search1 |

### 多轮、交互式与 Agentic benchmark

| 名称 | 首发 | 定位 | 任务形式 | 规模与特点 | 关系与备注 | 主要来源 |
|---|---:|---|---|---|---|---|
| SParC | 2019 | 上下文依赖 benchmark | 多轮、context-dependent | 4,298 个问题序列，12k+ 个单轮问句；来自 200 个复杂数据库 | Spider 的多轮版本 | citeturn14view0turn14view3 |
| CoSQL | 2019 | 对话式 benchmark / challenge | 多轮、澄清、不可回答、NL response | 30k+ turns、10k+ SQL、3k 对话、200 DB；隐藏测试 | 建立在 Spider/SParC 之上，强调澄清与不可回答 | citeturn15view0turn15view2 |
| CHASE | 2021 | 中文多轮 benchmark | 多轮、跨数据库 | 中文 context-dependent Text-to-SQL；SeSQL 论文指出其包含 CHASE-C 人工构造部分与 CHASE-T 从 SParC 翻译部分 | 重要中文多轮基线，但本文未直接核到原始官方统计，规模字段建议复核原 ACL 2021 论文 | citeturn17search1turn17search4 |
| SeSQL | 2022/2023 | 中文多轮 benchmark | 多轮 + 可转单轮 | 5,028 sessions，27,012 问句-SQL；全部手工从零构造 | 明确针对 CHASE 中“人工+翻译混合”问题提出 | citeturn17search1turn31search14 |
| PRACTIQ | 2025 | 实用对话式 benchmark | 四轮对话、歧义/不可回答 | 面向 ambiguous 与 unanswerable user questions；含分类与澄清 SQL 预测 | 与 CoSQL 相比更聚焦真实歧义与不可回答 | citeturn38view0 |
| BIRD-Interact | 2025/2026 | 交互式 / Agentic benchmark | c-Interact 与 a-Interact | Full 600 任务，Lite 300 任务；带用户模拟器、知识库、测试用例、全 CRUD；衡量 success rate | 基于 LiveSQLBench 构建；代表“数据库 Agent”评测方向 | citeturn36search6turn36search8turn13view3turn25search9 |
| CLARITY | 2026 | 交互歧义与不可回答 benchmark | 单轮 + 多轮 | 自动从可执行 SQL 生成多源歧义问题、对话延续和 schema 元数据；面向工业交互失败模式 | 更像“交互可靠性 stress test” | citeturn40search3turn40search7turn12search0 |
| Spider2-DBT | 2025 | 数据工程 / agent workflow benchmark | repository-level task | 官方站点说明 68 个任务，面向 quick benchmarking with spider-agent-dbt | Spider 2.0 的新任务设定，不应与原始 Spider 2.0 覆盖面等同 | citeturn25search3turn9search2 |
| DataAgentBench | 2026 | 数据 Agent 相邻 benchmark | 多步 data-agent task | 54 queries、12 datasets、9 domains、4 DBMS；测的是 agent answer / pass@1，不是单纯 final SQL | 不属于纯 Text-to-SQL，但对“数据库 Agent 基准”非常相关 | citeturn25search0turn25search8 |

### 鲁棒性、安全与辅助任务 benchmark

| 名称 | 首发 | 定位 | 核心能力 | 说明 | 主要来源 |
|---|---:|---|---|---|---|
| Dr.Spider | 2023 | 鲁棒性 benchmark | 17 类扰动 | 官方仓库明确其为 text-to-SQL robustness diagnostic benchmark，覆盖问句、schema、SQL 扰动 | Spider 系列鲁棒性评测的代表作 | citeturn16search8 |
| MT-Teql | 2021/2022 | 鲁棒性评测框架 | 语义保持变换、一致性测试 | 以 metamorphic testing 检测语言与 schema 变形下的不一致 | 更接近 evaluation framework + robustness suite | citeturn22search1turn22search10 |
| AmbiDB | 2025 | schema linking 辅助 benchmark | 歧义 schema linking | LinkAlign 构造的 Spider 变体，用于模拟真实环境中的 schema linking 歧义 | 属于辅助任务 benchmark，不应与端到端 NL2SQL 主 benchmark 混淆 | citeturn12search1turn12search9 |
| NL2SQL-BUGs | 2025 | 语义错误检测 benchmark | error detection / categorization | 2,018 专家标注实例，9 大类 31 子类；首个专门检测 NL2SQL 语义错误的 benchmark | 辅助任务 benchmark，不是标准 end-to-end SQL generation 集 | citeturn40search2turn40search6turn40search14 |
| BIRD-CRITIC / SWE-SQL | 2025/2026 | SQL debugging benchmark | 用户问题修复、诊断、调试 | 官方站点称其为首个 SQL diagnostic benchmark；dev 600 任务、OOD test 200；覆盖 MySQL、PostgreSQL、SQL Server、Oracle | 非传统 Text-to-SQL；更偏 SQL issue debugging / repair | citeturn42search2turn25search17 |
| NLR-BIRD | 2025 | 输出自然语言表示 benchmark | 查询结果 verbalization / judge 框架 | 用于评价 Text-to-SQL 系统输出的自然语言 representation | 明确是辅助输出评测，不是 SQL 生成 benchmark | citeturn12search6turn12search10 |
| DIY | 2021 | 交互式 correctness assessment framework | 用户验证与纠错 | 不提供大规模标准测试集，但提供一种让用户审查 NL2SQL 正确性的交互模式 | 更像 evaluation / HCI framework | citeturn12search3turn12search7turn12search19 |
| Schema inference attack benchmark / framework | 2025 | 安全评测 | schema leakage / attack | 通过 zero-knowledge probing 重建底层 schema，指出 Text-to-SQL 系统安全风险 | 更像攻击评测框架；公共 benchmark 仍薄弱 | citeturn19search6turn19search10 |

### 多语言、中文与领域 benchmark

| 名称 | 首发 | 语言 | 定位 | 规模与特点 | 关系 | 主要来源 |
|---|---:|---|---|---|---|---|
| CSpider | 2019 | 中文 | Spider 中文化 benchmark | 基于 Spider 翻译；官网说明是中文复杂跨域 Text-to-SQL challenge | 翻译版，不是原生中文数据库构造 | citeturn10search4turn16search15 |
| DuSQL | 2020 | 中文 | 中文跨域 benchmark | 200 DB、813 表、23,797 问答-SQL；强调“pragmatic” | 原生中文重要 benchmark | citeturn10search1turn10search5 |
| TableQA | 2020 | 中文 | 单表 / value expression benchmark | 64,891 问题、20,311 唯一 SQL、6,000+ 表；强调条件值表达不一定与表中值完全一致 | 接近 WikiSQL 范式，但更强调 value grounding 难度 | citeturn30academia28turn41search3 |
| CSS | 2023 | 中文 | 医疗跨 schema benchmark | 原始 4,340 对、2 DB；后扩展 19 新数据库与 29,280 例 | 医疗单域但跨 schema 泛化 | citeturn16search7turn16search3 |
| CRUDSQL | 2024 | 中文 | CRUD benchmark | 10,000 问答-SQL、625 表；首个同时覆盖 C/R/U/D 的中文 Text-to-SQL 数据集 | 补齐“只读查询”偏置 | citeturn31search0turn31search2turn31search10 |
| Archer | 2024 | 中英双语 | 复杂推理 benchmark | 1,042 英文 + 1,042 中文问题、521 唯一 SQL、20 个英文 DB；强调算术、常识、假设推理 | 不是大规模企业库，但适合 reasoning stress test | citeturn23search8 |
| MultiSpider | 2022 | 七语 | multilingual benchmark | 扩展 Spider 到英/德/法/西/日/中/越七语 | 翻译扩展型 | citeturn10search11 |
| MultiSpider 2.0 | 2025 | 八语 | multilingual enterprise benchmark | 扩展 Spider 2.0 到八语，保留企业级结构难度 | 多语言 benchmark 的重大升级 | citeturn10search3turn10search15turn18search16 |
| Ar-Spider | 2024 | 阿拉伯语 | cross-domain benchmark | 首个阿拉伯语跨域 Text-to-SQL 数据集；由 Spider 人工翻译 | 翻译版 | citeturn16search18 |
| Dialect2SQL | 2025 | 阿拉伯方言 | 跨域 benchmark | 9,428 问答-SQL、69 DB；首个阿拉伯方言大规模 Text-to-SQL 数据集 | 更接近原生方言数据 | citeturn17search5 |
| PAUQ | 2022 | 俄语 | 俄语 benchmark | 俄语版 Spider，并对问题、SQL 与数据库内容做本地化与补全 | 本地化增强版，而非仅直译 | citeturn18search1turn18search4turn18search11 |
| RedSQL | 2025 | 俄语 | 领域型 benchmark | 面向俄语真实业务分布；论文指出用于弥补 PAUQ 的学术通用查询局限 | 更偏行业 / 生产分布 | citeturn18search15 |
| BIRDTurk | 2026 | 土耳其语 | BIRD 适配 benchmark | 首个土耳其语 BIRD adaptation；训练与开发集公开 | 明确是翻译/适配版，不是原生土耳其企业库 | citeturn17search3turn17search6 |
| IndicDB | 2026 | 多种 Indic 语言 | multilingual benchmark | 面向多种印度语言的跨语言语义解析评测 | 代表低资源与非西方语境扩展 | citeturn18search2turn18search6 |
| MIMICSQL | 2020 | 英文医疗 | 领域 benchmark | 基于 MIMIC-III；首个医疗 Text-to-SQL 数据集；GitHub 说明基于 100 次随机住院样本，论文与后续文献普遍引用 10,000 对问答-SQL | 偏模板生成，复杂度有限 | citeturn29view2turn30search0turn30search6turn30search7 |
| EHRSQL | 2022/2023 | 英文医疗 | 实用医疗 benchmark | 24,211 text-to-SQL 对；问题来自 222 名医院工作人员；引入时间表达与不可回答问题 | 医疗领域最重要公开 benchmark 之一 | citeturn27search0turn27search3turn30search14 |
| EHR-SeqSQL | 2024 | 英文医疗 | 医疗多轮 benchmark | 首个也是最大医疗 sequential/contextual Text-to-SQL benchmark（论文表述） | 补齐 EHR 场景中的交互与效率问题 | citeturn28search2 |
| Eligibility Criteria-to-SQL | 2020 | 英文临床试验 | 领域 benchmark | 临床试验入排标准到 SQL；是医疗领域较早的专用数据集 | 专用领域、小众但不应忽略 | citeturn23search17 |

### 训练数据、重组数据与候选项目

严格按纳入标准看，下列项目不应自动归入“核心 NL2SQL benchmark”，但值得放入候选池。

Gretel 的 synthetic_text_to_sql 明确是合成数据集，定位是大规模 synthetic training data，而不是稳定测试 benchmark。SQL-GEN 也是方言特定 synthetic data 生成框架。LLMSQL 则是对 WikiSQL 的“升级版”重制，属于典型的 **由已有 benchmark 重新构造的 evaluation candidate**。这些工作很有研究价值，但至少在截至研究日的公开信息里，它们更适合归入“训练数据 / 重制 benchmark / 候选 benchmark”，而不是与 Spider、BIRD、BEAVER 并列。citeturn31search6turn31search8turn41search11

另外，Text-to-SQL Benchmarks for Enterprise Realities、CORGI、EntSQL、BIRDTurk、IndicDB、CLARITY 等工作中，有些截至研究日仍主要以 arXiv、OpenReview、项目页或 GitHub 形式存在。根据用户要求，这些项目**不应因未正式期刊化而被排除**，但在“是否已有稳定 leaderboard、是否完全开放、是否长期维护”三个维度上，必须与 Spider/BIRD 这类成熟 benchmark 明确区分。citeturn34search1turn40search0turn40search1turn17search6turn18search2turn40search7

## 重点 benchmark 深入分析

### Spider 及其家族

Spider 的核心贡献不是“规模最大”，而是首次把 **数据库级泛化** 作为主要评测目标：训练和测试在不同数据库、不同 SQL、不同领域上分离。它因此长期成为跨数据库泛化研究的基础 benchmark。它的优点在于规范、可复现、社区共识强、历史结果丰富；局限则在于数据库规模与企业现实仍有差距，且长期公开使用带来了明显的数据污染风险。这里的“污染风险”是推断：因为 Spider 自二零一八年起持续公开、广泛镜像和复用，进入大模型预训练或 instruction tuning 语料的概率显著高于隐藏或动态 benchmark。citeturn13view4turn13view5turn23search11turn37view1

SParC 与 CoSQL 让 Spider 从单轮扩展到上下文与对话。SParC 强调上下文依赖 SQL 预测；CoSQL 进一步加入系统澄清、不可回答、自然语言响应与隐藏测试。因此，若研究目标是“用户会话下的 SQL 生成”，Spider 只能做预热，SParC/CoSQL 才是更直接的评测集。citeturn14view0turn14view3turn15view0turn15view2

Spider 2.0 则是家族中最关键的一次范式升级。它不再把任务定义为“给定 schema，生成一条 SQL”，而是把问题改写成 **真实企业 text-to-SQL workflow**：数据库可能在 BigQuery 或 Snowflake 中，schema 超长，metadata、文档和代码库都可能是必要上下文，最终答案常常需要多条 SQL 与多种操作。官方评测显示，基于 o1-preview 的 Spider-Agent 在 Spider 2.0 上只能解决 17.0% 任务，而在 Spider 1.0 与 BIRD 上分别可达 91.2% 和 73.0%，这个对比非常直观地表明：**旧 benchmark 的高分已经不能说明系统具有企业可用性**。citeturn42search0turn25search14

### BIRD、LiveSQLBench 与 BIRD-Interact 家族

BIRD 的定位与 Spider 不同。Spider 更偏 schema generalization；BIRD 更偏 **大规模数据库内容、外部知识与执行效率**。官方站点给出的概要是 12,751+ 对问答-SQL、95 个大数据库、33.4GB、37+ 专业域，而且官方明确把“Text-to-Efficient-SQL”作为设计目标之一。此后 BIRD 站点又先后发布 Mini-Dev、R-VES、BIRD-Interact、LiveSQLBench 等扩展，说明 BIRD 已经从单个 dataset 演化为面向现实数据智能的一整套评测家族。citeturn13view0turn18search3turn13view2turn13view3

BIRD 的一个重要启发是：**只看 EX 不够，SQL 还要高效**。因此 BIRD 社区引入过 VES 与后来的 R-VES，并把效率纳入排行榜考量。这一点对企业 BI 场景特别重要，因为两个都能返回正确结果的 SQL，在查询成本、延迟和资源消耗上可能天差地别。citeturn13view2turn18search3

LiveSQLBench 把 BIRD 家族进一步推进到“动态 benchmark”形态。官方项目页强调它是 contamination-free、continuously evolving 的 benchmark，并且每个 release 都会加入新数据库；更关键的是，它采用 **开放 dev / 隐藏 test 滚动轮换**：上一版的隐藏集会成为下一版公开 dev 集，新的隐藏测试再继续生成。这种设计明显针对静态公开 benchmark 的记忆化与泄漏问题。它还覆盖 BI 与 CRUD，加入 hierarchical knowledge base、business rule drift 与 test cases，已经更接近企业数据助手的持续测评平台，而不是一次性发表的数据集。citeturn37view0turn37view1turn37view3

BIRD-Interact 则代表单轮 Text-to-SQL 向 **交互式数据库代理评测** 的跃迁。该 benchmark 提供用户模拟器、知识库、文档、函数式环境，以及 c-Interact 和 a-Interact 两种设置；前者有预定义对话协议，后者让模型自主决定何时求助、探索与修复。官方摘要给出 Full 600 任务、Lite 300 任务，并指出即便到 GPT-5 这一代模型，c-Interact 成功率也只有 8.67%，a-Interact 只有 17.00%。这说明在真实多步数据库交互中，**“能写 SQL”与“能完成任务”仍是两回事**。citeturn36search6turn36search8

### 企业与业务场景 benchmark

BEAVER 的价值在于它公开承认并处理了一个长期被学术 benchmark 回避的问题：**企业查询日志与 schema 很难开放**。作者从私有组织中收集真实查询与数据库，构建了 9,128 个问答-SQL、812 张表、19 个域的 benchmark，并额外提供五个子任务标注：多表检索、join key 检测、列映射、领域知识抽取、查询分解。相比多数 benchmark 只给 final SQL，BEAVER 更利于诊断“系统到底卡在 schema linking、business knowledge 还是 decomposition”。citeturn35view0turn35view1

CORGI 与 EntSQL 代表两种新的企业化方向。CORGI 把业务问题按 descriptive、explanatory、predictive、recommendational 四层组织起来，正式把预测和建议型业务问题纳入 Text-to-SQL benchmark；EntSQL 则把重点放在 **长上下文企业知识 grounding**，用中英对齐样本衡量系统是否能从业务文档、内部指标口径与组织规则中补足 schema 之外的知识。前者凸显“业务智能推理”，后者凸显“私有知识 grounding”，二者都指向企业场景里最难也最缺 benchmark 的部分。citeturn40search0turn40search1turn40search5

BIRD-Ent / Spider-Ent 则更像对既有 benchmark 的企业现实化 stress test。OpenReview 摘要直接说明，两者是通过对 BIRD 和 Spider 的 refinement 构建出来，用于覆盖 massive scope、复杂 schema 与分散知识。它们的意义不只是“再出一个新榜单”，而是帮助研究者把“在公开 benchmark 上高分”与“在企业环境里可靠”这两件事系统地区分开。citeturn34search1turn32search1

### 多语言、中文与医疗 benchmark

中文 benchmark 目前最成体系。CSpider 是 Spider 的中文化版本，适合和英文 Spider 平行对照；DuSQL 是原生中文跨域 benchmark；TableQA 更接近单表/值表达难题；CHASE 与 SeSQL覆盖中文多轮；CSS 提供医疗跨 schema 场景；CRUDSQL 则补上数据库写操作。这意味着中文 NL2SQL 研究已经不应再只靠 CSpider 一项指标，否则会同时忽略 **原生中文表达、真实值 grounding、多轮上下文、医疗 schema 与数据库写操作**。citeturn10search4turn10search1turn30academia28turn17search1turn31search14turn16search7turn31search0

多语言方向需要区分三类资源。第一类是 **翻译/本地化型**，如 CSpider、Ar-Spider、PAUQ、BIRDTurk；第二类是 **多语言并行型**，如 MultiSpider 与 MultiSpider 2.0；第三类是 **低资源语族原生导向型**，如 Dialect2SQL 与 IndicDB。前两类适合研究跨语言迁移和 prompt/localization，后一类更能暴露“英语中心 benchmark 无法覆盖的语言结构困难”。citeturn10search4turn16search18turn18search1turn17search6turn10search11turn10search15turn17search5turn18search2

医疗方向则已经形成独立分支。MIMICSQL 是早期医疗 Text-to-SQL 数据集，但偏模板生成；EHRSQL 来自 222 名医院工作人员的真实需求，加入时间表达与不可回答问题，明显更贴近实际；EHR-SeqSQL 把医疗场景推进到 sequential/contextual benchmark；与此同时，EHRSQL 还衍生出二零二四 shared task 和 Codabench 受控评测。若你的目标是医疗应用，Spider/BIRD 只能提供通用能力信号，**EHRSQL 家族才是更高优先级**。citeturn29view2turn30search7turn27search0turn27search2turn27search15turn28search2

## 评测框架、指标与排行榜

EM、EX、Test Suite、VES/R-VES、Success Rate 这几种指标分别回答的是不同问题。Spider 传统 leaderboard 长期使用 set-based exact match 与后来的 Test Suite Accuracy；BIRD 体系则在 EX 之外强调效率；LiveSQLBench 与 BIRD-Interact 则把成功率定义为通过测试用例的任务比例；ROSE 则干脆把评测目标从“与参考 SQL 一致”转向“是否真正回答了用户意图”。因此，今天谈 NL2SQL 评测，已经不能只问“这个 benchmark 上最高分是多少”，还必须问“**它到底在测什么**”。citeturn13view5turn13view6turn20search3turn13view2turn37view2turn36search6turn20search4

Exact Match 容易低估语义等价 SQL。Test Suite Accuracy 论文的出发点正是：不同 SQL 可能语义等价，但如果只看结构匹配，会把一些正确但写法不同的 SQL 判错；相反，也可能存在看上去接近 gold、却在其他数据库实例上表现错误的 SQL。Test Suite Accuracy 通过在蒸馏出的多组数据库上测试 denotation，尽可能逼近 semantic accuracy，因此比单纯 exact match 更稳健。Spider、SParC、CoSQL 官方也在二零二零年宣布把 Test Suite Accuracy 作为正式评测指标。citeturn20search0turn20search3turn13view6turn15view2

Execution Accuracy 比 EM 更接近“结果是否正确”，但它也会出现两类问题。第一类是假阳性：错误 SQL 恰好在当前数据库状态下返回了正确结果；第二类是假阴性：预测 SQL 其实回答了用户意图，但因为 gold SQL 标注本身有误、或参考 SQL 只是多种合理解释之一而被判错。ROSE 论文正是因为认为 EX “对句法变化敏感、忽略问题可能存在多种合理解释、并且容易被错误 gold SQL 误导”，才提出 intent-centered 评价；NL2SQL-BUGs 还进一步指出，在 BIRD Dev 中发现了 6.91% 的 ground-truth SQL 标注错误。citeturn20search4turn40search2turn19search2

因此，建议把指标理解为一个层级体系。**EM / clause match** 适合快速诊断结构学习；**EX / result equivalence** 适合衡量实际返回结果；**Test Suite Accuracy** 适合缓解偶然正确；**VES / R-VES** 适合补充效率；**Success Rate** 适合多步 Agent；**错误类型检测指标** 适合辅助任务 benchmark；而 **ROSE** 则是当 benchmark 本身开始出现 gold 错误、歧义与多解时，对传统 reference-based 评测的修正。没有任何一种单一指标能覆盖全貌。citeturn20search3turn13view2turn37view2turn40search2turn20search4

排行榜与评测服务器方面，截至研究日最成熟的仍是 Spider / SParC / CoSQL 官方 challenge 页面和 BIRD 官方 leaderboard；二零二四之后最活跃的新增阵地则是 Spider 2.0、LiveSQLBench、BIRD-CRITIC、BEAVER，以及 EHRSQL shared task 的 Codabench。这里需要特别注意：**有 leaderboard 不等于 benchmark 成熟，也没有 leaderboard 不等于 benchmark 不重要**。例如 EntSQL、CORGI、CLARITY 等仍然很有研究价值，但截至研究日更接近“公开论文 + 数据/代码”阶段。citeturn13view5turn14view3turn14view2turn13view2turn42search6turn37view2turn42search2turn35view0turn27search15turn40search0turn40search1turn40search7

## 近年趋势与推荐组合

### 近年趋势

过去三年的最鲜明趋势，是从 **“学术 SQL 解析”转向“企业数据库智能”**。Spider 2.0、BEAVER、BIRD-Ent/Spider-Ent、EntSQL 都明确把超大 schema、分散文档知识、方言差异、项目级代码与私有业务规则纳入评测前提。与之对应，旧式 benchmark 的高分开始越来越难作为工程可用性的代理指标。citeturn42search0turn35view1turn34search1turn40search1

第二个趋势，是从 **最终 SQL 评测转向 Agent 轨迹和任务完成率**。BIRD-Interact、LiveSQLBench、Spider 2.0、DataAgentBench 都把“探索 schema、澄清问题、执行修复、调用工具、通过测试用例”纳入核心流程。对于 agentic NL2SQL，最终 SQL 只是中间产物；若系统在交互环节、权限边界或错误恢复中失败，仅凭最终 SQL accuracy 很难反映真实能力。citeturn36search6turn37view2turn42search0turn25search8

第三个趋势，是从 **正确性** 走向 **效率、可靠性与质量审计**。BIRD 系列把效率做进指标；BEAVER 用五类子任务标注支持误差定位；NL2SQL-BUGs 和 ROSE 则开始质疑旧 benchmark 自身的标注质量和度量可靠性；CIDR 2026 的分析甚至直接提出“Text-to-SQL Benchmarks are Broken”，说明 benchmark 质量本身已经成为研究对象。citeturn13view2turn35view0turn40search2turn20search4turn18search20

第四个趋势，是从 **英语公开静态集** 转向 **多语言、行业集、隐藏集与动态集**。MultiSpider 2.0、Dialect2SQL、BIRDTurk、IndicDB 体现了多语扩展；EHRSQL、CSS、BEAVER、CORGI、EntSQL 体现了行业与企业化；LiveSQLBench 则体现了动态 release 与隐藏测试。这些变化都可以理解为对同一问题的不同回应：**如何避免 benchmark 被“学会格式”和“记住测试集”之后失去判别力**。citeturn10search15turn17search5turn17search6turn18search2turn27search0turn16search7turn35view1turn40search0turn40search1turn37view1

### 面向研究目标的推荐组合

如果你的目标是 **经典跨数据库泛化**，推荐用 **Spider + KaggleDBQA + SEDE**。Spider 是学术主线基准；KaggleDBQA 检验真实 schema 与文档利用；SEDE 则补足自然发生的真实用户表达。缺口是企业私有知识和动态环境。citeturn13view4turn22search0turn21search1

如果目标是 **复杂 SQL 推理**，推荐 **BIRD + Spider 2.0 + Archer**。BIRD 强调数据库内容与复杂性，Spider 2.0 提供企业工作流与长上下文，Archer 则把算术、常识与假设推理显式拉高。缺口是权限控制与长期会话。citeturn13view0turn42search0turn23search8

如果目标是 **大规模真实数据库**，推荐 **BIRD + BEAVER + LiveSQLBench-Large-v1**。这三个基准分别覆盖公开大库、真实企业日志与持续更新工业级大 schema。若做企业落地，仍建议补一套私有测试库，因为公开 benchmark 很难覆盖你自己的业务口径与命名习惯。citeturn13view0turn35view1turn37view5

如果目标是 **数据库内容理解与 value grounding**，推荐 **BIRD + TableQA + EHRSQL**。BIRD 强调 DB contents 与外部知识；TableQA 强调条件值表达不一致；EHRSQL 则把时间表达、医疗缩写与不可回答问题带入结构化医疗数据。citeturn13view0turn30academia28turn27search0

如果目标是 **中文 NL2SQL**，不要只用 CSpider。更合理的组合是 **DuSQL + CSpider + SeSQL + CRUDSQL**；如果是医疗中文，再加 **CSS**。这样才能同时覆盖原生中文、翻译设定、多轮交互与写操作。citeturn10search1turn10search4turn31search14turn31search0turn16search7

如果目标是 **多语言 NL2SQL**，推荐 **MultiSpider + MultiSpider 2.0 + Dialect2SQL + BIRDTurk + IndicDB**。其中 MultiSpider 家族适合做多语言并行比较，Dialect2SQL 和 IndicDB 则更能暴露低资源语言和地域化表达难点。citeturn10search11turn10search15turn17search5turn17search6turn18search2

如果目标是 **对话式与交互式 NL2SQL**，推荐 **CoSQL + PRACTIQ + BIRD-Interact + CLARITY**。CoSQL 是传统对话基线；PRACTIQ 和 CLARITY 更强调歧义与不可回答；BIRD-Interact 则检验完整代理式交互。缺口是长期多会话记忆与真实用户在线反馈。citeturn15view0turn38view0turn36search6turn40search3

如果目标是 **鲁棒性**，推荐 **Dr.Spider + MT-Teql + AmbiDB**，再在主 benchmark 上报告 Test Suite Accuracy。这样才能同时看扰动鲁棒性、变形一致性与 schema linking 歧义。citeturn16search8turn22search1turn12search1turn20search3

如果目标是 **企业 BI 与业务智能**，推荐 **BEAVER + CORGI + EntSQL + Spider 2.0**。BEAVER 测真实日志和子任务，CORGI 测描述/解释/预测/建议，EntSQL 测企业文档 grounding，Spider 2.0 测工作流执行。即便如此，生产部署前仍然建议自建私有测试集，因为权限、业务定义和容错要求通常无法公开 benchmark 充分覆盖。citeturn35view1turn40search0turn40search1turn42search0

如果目标是 **Agentic NL2SQL 与 SQL 修复**，推荐 **Spider 2.0 + BIRD-Interact + LiveSQLBench + BIRD-CRITIC + DataAgentBench**。前四者分别覆盖 repository/workflow、交互、多步任务和 SQL debugging，DataAgentBench 则提供更宽的数据代理视角。citeturn42search0turn36search6turn37view2turn42search2turn25search8

如果目标是 **安全与权限**，公开基准仍明显不足。当前更现实的做法是以 **CLARITY、PRACTIQ、schema inference 攻击框架、EHRSQL 可靠性 shared task** 作为相邻信号，再配自建红队集，专门测越权、敏感字段泄露、写操作拒绝与 destructive SQL 防护。公开 benchmark 目前还没有形成像 Spider / BIRD 那样成熟的安全标准集。citeturn40search3turn38view0turn19search6turn27search2

## 缺口、候选项目与方法边界

当前 benchmark 的首要缺口，是 **真实企业数据与权限语义仍然不足**。Spider 2.0、BEAVER、EntSQL、BIRD-Ent/Spider-Ent 虽然都明显朝企业现实推进，但公开数据天然受隐私和知识产权约束，无法完整复现真实组织中的数据字典、访问控制、数据租户隔离与语义层治理。企业部署要达到可信程度，几乎一定仍需要私有 benchmark。citeturn42search0turn35view1turn40search1turn34search1

第二个缺口，是 **SQL 方言与数据库系统覆盖仍然偏弱**。新 benchmark 已开始覆盖 BigQuery、Snowflake、PostgreSQL，以及 BIRD-CRITIC 中的 MySQL、PostgreSQL、SQL Server、Oracle；但“真正把相同任务跨方言迁移当作主要评测目标”的 benchmark 仍然不多。也就是说，今天对 SQL dialect transfer 的公开衡量，仍然更多依赖带方言 support 的复杂 benchmark，而非专门的系统化方言 leaderboard。citeturn42search0turn37view3turn42search2

第三个缺口，是 **benchmark 质量与污染问题本身**。LiveSQLBench 通过 contamination-free 与 hidden/open 滚动机制正面回应这一点；NL2SQL-BUGs 和 ROSE 则从标注错误与度量失真入手；CIDR 2026 的工作进一步指出 annotation errors 已经会影响 leaderboard 有效性。对用户而言，这意味着老 benchmark 上的高分，尤其是在长期公开的 Spider / WikiSQL dev/test 上，应该越来越被看作“方向性信号”，而不是部署保证。citeturn37view0turn37view1turn40search2turn20search4turn18search20

第四个缺口，是 **中文真实业务 benchmark 仍偏少**。中文资源很多，但大量是 Spider 翻译、单表任务、医疗单域或教学性质数据；像 EntSQL 这样真正把企业知识 grounding 与中英并行结合起来的工作，才刚在二零二六年出现。对中文企业应用而言，公开 benchmark 还远未达到英语社区 Spider/BIRD 生态的成熟度。citeturn10search4turn10search1turn30academia28turn16search7turn31search0turn40search1

候选或尚未完全验证的项目中，我认为最值得持续跟踪的有五类。第一类是 **重制 benchmark**，如 LLMSQL；第二类是 **企业 refinement benchmark**，如 BIRD-Ent/Spider-Ent；第三类是 **新业务域 benchmark**，如 CORGI；第四类是 **长上下文企业知识 benchmark**，如 EntSQL；第五类是 **安全评测套件**，例如 schema inference 攻击框架。它们都很可能在未来两年成为主流研究常用集，但截至研究日，部分项目在 leaderboard 稳定性、官方数据镜像、长期维护方式上仍未完全定型。citeturn41search11turn34search1turn40search0turn40search1turn19search6

本报告的完整性边界如下。检索时使用了用户给出的关键词族，并在查漏阶段扩展到 benchmark family、企业现实、interactive、agentic、robustness、multilingual、business domain、schema linking、semantic error detection 等别名；来源优先采用 ACL Anthology、arXiv、OpenReview、官方 GitHub、官方站点、官方 leaderboard 和 shared task 页面；去重时把 Spider/SParC/CoSQL、BIRD/BIRD-Interact/LiveSQLBench/BIRD-CRITIC、CSpider/MultiSpider/Ar-Spider/PAUQ/BIRDTurk 这类具有明显继承关系的项目按 family 处理。仍有不确定性的地方主要在两类：一类是只以 arXiv/GitHub 形式公开的新项目，另一类是我未能直接访问到原始主页细节而只能通过高质量二手学术来源交叉确认的项目，如 CHASE 的部分统计。基于公开互联网来源，本报告已经尽量做到高召回，但不能保证绝对穷尽。citeturn16search10turn21search8turn11search6