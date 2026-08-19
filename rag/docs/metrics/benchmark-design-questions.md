# 做一个 Benchmark 必须回答哪些问题

> 适用范围：MOI RAG Benchmark，以及后续解析、检索、问答、引用与产品横评 Benchmark 的设计、评审和冻结。

## 1. 当前 MOI RAG Benchmark 的定位

当前项目不是一个单纯比较“RAG 准确率”的排行榜，而是一套面向产品决策、能力诊断和竞品比较的分层评测体系。它最终要回答的不是“MOI 得了多少分”，而是：

> MOI 在什么场景下可靠、为什么失败、与竞品差多少，以及下一步最值得改什么。

项目分为三个阶段：

1. **Public Benchmark Baseline**：使用公开 Benchmark 建立外部可比基线，判断 MOI 在社区坐标系中的位置，并定位解析、检索、Reader、引用和端到端链路的主要短板。
2. **MOI Benchmark Dataset v1**：构造符合真实产品场景、权利清晰、足够新鲜并具有完整 Gold lineage 的自有数据集，在 dev 和 pilot split 上评估 MOI。
3. **Competitive Formal Evaluation**：使用 sealed formal split，在相同原始文件、问题、预算和运行协议下，对 MOI、Dify、FastGPT 等产品进行正式 Native 横评。

该体系同时保留两个不可混淆的指标命名空间：

- **Dataset-native metrics**：严格遵循公开数据集的官方协议，用于和论文、官方实现或社区结果比较。
- **MOI unified metrics**：统一评估 readiness、retrieval、answer、citation、reliability、operability 和 TDAS，用于跨数据集、跨产品的内部判断。

两套指标不应被平均、改名或合成为一个 overall score。前者回答“是否复现了公开 Benchmark 协议”，后者回答“产品链路是否满足我们的验收要求”。

## 2. Benchmark 必须回答的十二个问题

前六个问题决定 Benchmark 是否“测对了”，后六个问题决定结果是否“可信且有用”。

### 2.1 Benchmark 服务于什么决策？

首先必须明确：结果出来以后，谁会据此做什么决定？

可能的决策包括：

- 判断 MOI 是否具备发布或交付条件；
- 决定 parser、retriever、reranker、reader 或 citation 模块的投入优先级；
- 在 MOI、Dify、FastGPT 等产品之间进行选型；
- 判断一次模型、配置或产品升级是否引入回归；
- 形成对外能力证明或内部研发诊断。

对当前项目，应明确区分：

- Stage 1 服务于能力定位和研发诊断；
- Stage 2 服务于 MOI 产品验收和错误地图构建；
- Stage 3 服务于竞品差异判断和产品决策。

如果没有明确的决策对象，Benchmark 很容易变成“收集了很多指标，但不知道如何行动”。

### 2.2 我们到底在测什么对象？

必须冻结被测系统的边界：

- 测单一模型、某个组件、受控 Pipeline，还是完整产品？
- 输入是已抽取文本、页面图像，还是原始 PDF？
- 是否允许外部 parser、统一 retriever、外部 agent 或人工预处理？
- 测官方推荐默认路径，还是专家调优后的能力上限？
- API、权限、产品配置或服务错误是否计入最终结果？

当前项目至少应区分：

- **Quick-start Native**：完整使用产品原生推荐路径，反映默认用户体验；
- **Frozen Optimized Native**：在公平调优预算内优化后冻结，反映产品可达到的实践上限；
- **Controlled / Diagnostic**：控制部分模型或组件，用于定位差异来源，不能替代 Native 产品结果。

通过统一组件实验得到的结论，只能归因于对应组件或受控 Pipeline，不能直接写成完整产品结论。

### 2.3 “能力好”具体是什么意思？

“RAG 效果好”必须拆成可观察、可判分的能力：

- 文件是否被系统接受并成功处理；
- 页面、文本、表格、图片、公式和阅读顺序是否正确解析；
- 构建完成后语料是否真正 searchable-ready；
- 回答所需的证据是否被召回；
- 多证据问题所需的完整 evidence set 是否全部召回；
- 检索上下文是否包含过多干扰内容；
- 最终答案是否正确、完整且没有关键矛盾；
- 答案是否确实由 Gold evidence 或检索上下文支持；
- 引用是否可解析、可定位并支持对应 claim；
- 信息不足时是否能够正确拒答；
- 多次运行是否稳定；
- 延迟、费用、人工干预和诊断成本是否可接受。

因此，当前六层 scorecard 应分别回答：

1. **Readiness**：原始文档能否可靠变成可搜索语料；
2. **Retrieval**：系统能否找全且尽量找准回答所需证据；
3. **Answer**：系统能否给出正确、完整的回答或正确拒答；
4. **Citation**：系统能否为回答中的 claim 提供有效、充分的引用；
5. **Reliability**：系统是否可用、稳定并可恢复；
6. **Operability**：系统是否能以可接受的时间、费用和人工成本投入使用。

TDAS 用于回答某一次端到端任务是否整体成功，六层指标用于解释其成功或失败的原因。

### 2.4 结果要推广到哪些真实场景？

必须定义 Benchmark 所代表的目标总体：

- 面向哪些用户、行业和业务任务；
- 文档类型、长度、语言和质量的真实分布；
- 扫描件、表格、图片、图表和复杂版式分别占多少；
- 单文档、多文档和多跳问题分别占多少；
- 数值计算、版本冲突和时效性问题分别占多少；
- 真实任务中有多少问题本来就不可回答；
- 是否包含需要精确引用或具有较高风险的专业任务。

数据配额不能只追求表面均衡，应尽量来源于产品流量、客户需求、线上失败案例或明确的战略目标。

如果题型配额表达的是“企业 RAG 通用能力模型”，应使用宏平均和分层能力画像；如果题型权重来自目标客户的真实流量，才可以用加权结果预测上线后的总体任务成功率。两种口径不能混淆。

### 2.5 数据是否合法、独立并且足够新？

必须回答：

- 数据是否允许用于商业研发和产品评测；
- 是否允许上传到目标 MOI 租户或第三方竞品；
- 文档、问题、答案和 evidence 分别具有什么许可；
- 是否允许重新分发样本或公开聚合结果；
- 内容是否可能已经进入模型训练语料；
- 答案是否能通过公开搜索或模型记忆直接获得；
- dev、pilot、formal 是否存在同源文档、模板或 question family 泄漏；
- 是否包含 fresh、private 或 fictional control，用来检测记忆和污染。

每份正式文档至少应保存来源所有者、许可、允许用途、重新分发条件、训练许可、获取时间和审核人。任何关键权利字段不明时，不得进入 formal split。

### 2.6 Ground truth 到底是什么？

RAG 的 Gold 不能只有一段 `reference_answer`。每道题至少需要定义：

- 问题是否可回答；
- 不可回答的具体原因和正确拒答边界；
- 必须回答的原子 `scored_reference_claims`；
- 哪些 claims 属于 `critical_required_claims`；
- 每个 claim 可由哪些替代 evidence sets 支持；
- 不同 evidence set 之间的 OR 关系；
- 同一 evidence set 内证据的 AND 关系；
- 精确的 document、page、span、bbox、section 和版本 hash；
- 可接受的答案变体；
- 明确禁止或构成关键矛盾的 claims；
- question family、lineage、review 和 adjudication 记录。

Gold 必须在查看 scored output 前冻结。系统输出、Judge 结果和失败案例不得反向改写同一版本的 Gold；修订必须创建新版本并保留 lineage。

### 2.7 比较条件公平吗？

正式横评必须回答：

- 所有系统是否从相同原始文件开始；
- 是否使用相同问题、数据版本和候选范围；
- context、输出、时间和费用预算是否语义等价；
- 默认配置与优化配置是否分表报告；
- dev trials、人工时间、配置动作数和厂商支持预算是否公平；
- 运行顺序是否会受到时间、服务负载或缓存影响；
- 某个平台无法导出 retrieval trace 时如何处理；
- 无法统一的隐藏默认参数是否被完整披露。

公平不等于强行把所有参数设成一样。产品默认行为本身也是产品能力。合理做法是分别报告 Native 产品比较和 Controlled 组件诊断，不把两种结果混成同一排名。

### 2.8 什么指标直接对应最终任务成功？

指标应具有清晰层级：

- **主指标**：端到端任务是否成功，例如 TDAS；
- **次指标**：Evidence Recall、claim correctness、Gold-evidence Support、citation coverage；
- **诊断指标**：Token F1、BLEU、ROUGE、context precision 等；
- **运营指标**：availability、latency、cost、人工时间和干预次数。

每个指标还必须明确：

- 定义、单位和取值方向；
- 分子、分母和排除规则；
- initial failure、empty、timeout 和 retry 的处理；
- `N/A` 的允许原因；
- macro、micro 和 slice 的聚合方式；
- 是否容易被投机优化；
- 指标变化是否与真实用户价值单调一致。

不建议用一个加权总分宣布“总冠军”。TDAS 可以作为端到端 gate，六层 scorecard 和切片结果负责解释差异。官方指标与 MOI unified metrics 必须独立报告。

### 2.9 自动 Judge 可信吗？

LLM Judge 本身也是需要评估和冻结的测量工具：

- Judge 与人工评分的一致性如何；
- 在不同系统、语言、答案长度和表达风格上是否存在偏置；
- 同一回答重复判分是否稳定；
- model、version、prompt、temperature 和输出约束是否冻结；
- 是否能区分“答案正确但证据不足”和“证据存在但答案不完整”；
- 是否能识别错误拒答、无依据 claim、矛盾 claim 和伪造引用；
- 人工 audit 的抽样方式、双审比例和 adjudication 流程是什么。

Judge 不能被视为评测体系之外的天然真理。正式运行前，应在 dev/pilot 和人工标注样本上完成校准，并保存一致性指标和主要偏差类型。

### 2.10 差异是稳定信号，还是随机波动？

统计设计需要回答：

- 样本量是否足以检测业务关心的最小差异；
- 为什么使用当前文档数和问题数；
- 每题为什么运行一次、两次或三次；
- 比较是否采用 paired design；
- bootstrap 或重采样单位是 question、document、question family 还是 analysis cluster；
- 置信区间跨零时如何表述；
- 多个指标和切片同时比较时如何避免选择性报告；
- 平均分是否掩盖了 `pass/pass/pass`、翻转和 `fail/fail/fail` 三类稳定性差异。

正式冻结前，最好补充 power analysis 或 minimum detectable effect，解释样本规模能够支持多大的产品结论。

### 2.11 结果能否独立复算和审计？

一个可审计 Benchmark 至少应冻结并保存：

- dataset revision、split 和文件 SHA-256；
- 代码 commit 和 adapter/scorer 版本；
- 产品身份、部署方式、tenant、region 和权限；
- 模型、prompt、chunking、embedding、top-k 和 reranker 配置；
- 每次 initial attempt 和额外 retry；
- 原始检索结果、rank、回答、引用、错误和时间；
- Judge 输入、输出和版本；
- 样本排除及 `N/A` 原因；
- 从逐题 ledger 重建所有主表的脚本。

理想验收标准是：

> 一个不了解实验执行过程的人，只使用冻结数据、配置和 immutable artifacts，就能够重建报告中的每一个数字。

### 2.12 结果如何转化为行动？

最终必须回答：

- 什么结果算通过、失败或无法判断；
- 多大的差异才具有产品意义，而不只是统计显著；
- 每类失败属于 ingest、parse、retrieval、reader、citation 还是 product/API；
- 对应的修复 owner 是谁；
- 哪些问题可以通过配置解决，哪些需要新增产品能力；
- 修复后进入哪个固定回归集；
- Benchmark 多久更新一次；
- 新样本来自真实事故、客户反馈还是人工设计；
- 如何防止团队针对已公开的 formal 样本过拟合。

一个可执行的结论应类似：

> 在扫描版中文表格的多证据问题中，MOI 的 complete evidence-set recall 明显偏低；主要失败发生在解析和 chunk provenance；应优先修复对应链路，并将相关样本加入固定 release gate。

## 3. RAG Benchmark 最终应回答的产品问题

完成上述设计后，当前 MOI RAG Benchmark 应能够稳定回答以下产品问题：

1. MOI 能否把目标类型的原始文件可靠地转化为可搜索语料？
2. MOI 能否召回回答所需的全部证据，而不只是命中其中一条？
3. 在证据已召回时，MOI 能否生成正确、完整且无关键矛盾的回答？
4. 回答中的重要 claim 是否都得到可解析、可定位且充分的引用支持？
5. 当知识库证据不足或问题包含错误前提时，MOI 能否正确拒答？
6. 系统在重复运行、服务波动和失败重试下是否稳定？
7. 从上传文档到获得可信回答，需要多少时间、费用和人工操作？
8. 一次任务失败时，能否判断失败来自解析、检索、生成、引用还是产品/API？
9. MOI 在公开 Benchmark 上相对论文和社区基线处于什么位置？
10. 在公平的 Native 产品条件下，MOI 与 Dify、FastGPT 的差异有多大，这一差异是否稳定？
11. 哪些文档类型、语言、版式和问题类型是 MOI 的优势或短板？
12. 下一阶段研发投入在哪个环节能够带来最大的端到端任务成功率提升？

## 4. 当前项目冻结前检查表

在任何一次正式 Benchmark 冻结前，应逐项确认：

- [ ] 已明确结果消费者、产品决策和通过条件；
- [ ] 已冻结系统身份、Native 边界和允许使用的外部组件；
- [ ] 已定义目标场景及文档、语言、题型分布依据；
- [ ] 所有数据均完成许可、敏感信息和允许用途审核；
- [ ] dev、pilot、formal 按 document family 隔离且无近重复泄漏；
- [ ] Gold 包含 answerability、原子 claims、critical claims 和精确 evidence sets；
- [ ] Gold 已完成独立复核、adjudication、版本冻结和 hash；
- [ ] 主指标、诊断指标、分母、失败和 `N/A` 规则已预注册；
- [ ] Quick-start Native、Optimized Native 和 Controlled 结果不会混报；
- [ ] 各系统调优预算、运行预算和执行顺序已经冻结；
- [ ] Judge 已在人工样本上校准，并冻结模型、版本和 prompt；
- [ ] 样本量、repeat 数和统计方法能够支持目标结论；
- [ ] timeout、空响应、产品错误和 citation 缺失保留在 initial 分母；
- [ ] 所有逐题输出、trace、citation、timing、error 和 retry 均写入 ledger；
- [ ] 报告中的所有主指标均可从 immutable artifacts 独立重算；
- [ ] 已定义 failure taxonomy、修复 owner 和进入回归集的规则。

## 5. 核心原则

> 一个 Benchmark 不仅要回答谁更强，还必须回答强在哪里、弱在哪里、结论是否可信、能否推广到真实场景，以及团队下一步应该做什么。
