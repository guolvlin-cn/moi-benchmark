# Terminal-Bench 2.1 任务类型、版本更新与长短任务分析

## 摘要

Terminal-Bench 2.1 完整保留了 2.0 的 89 个任务 ID、16 个作者指定类别及 4 Easy / 55 Medium / 30 Hard 的难度分布，没有新增或删除任务；因此，2.0 论文附录给出的任务类型统计仍适用于 2.1。Software Engineering 有 26 项（29.2%），是最大类别；Software Engineering、System Administration、Security、Debugging 和 File Operations 合计 53 项（59.6%）。2.1 的重点不是扩充任务类型，而是修复外部依赖漂移、资源预算不合理及 instruction 与测试不一致等质量问题，并引入持续验证。

“长任务”需要区分三种口径：人类预计工时、评测 timeout 和 Agent 实际运行时。按本文明确给出的分析阈值，88 项有估时的任务中，专家预计 53 项可在 1 小时内完成、27 项需要 1–8 小时、8 项超过 8 小时；但 89 项的 Agent timeout 中，50 项不超过 15 分钟、24 项为 20–40 分钟、只有 15 项达到 60 分钟以上。专家估时与 Agent timeout 的 Spearman 相关仅为 0.255。Terminal-Bench 2.0 的公开实验证据进一步表明，多数 Agent trial 少于 20 分钟，但长尾可达 2 小时。因而，2.1 更准确的定位是：**以中短时、可重复运行的多任务评测为主体，同时包含人类工时很长、操作链很深或运行时间很长的尾部任务**，而不是纯短任务集或严格意义上的全长时程 benchmark。

## 1. 调研问题与范围

本调研回答七个问题：

1. Terminal-Bench 2.1 包含哪些任务类别，各占多少？
2. 每类任务的典型例子是什么，Agent 实际需要完成什么？
3. 这些任务共同测量哪些能力，覆盖又有哪些偏向？
4. 2.1 相比 2.0 修改了什么，对复现和分数比较有什么影响？
5. “长任务”和“短任务”应按什么口径区分？
6. 2.1 的人类估时和评测时间预算如何分布，典型长短任务有哪些？
7. 人类估时、timeout 和 Agent 实际运行时是否一致，这对评测设计意味着什么？

任务类型部分以官方 2.0 论文的任务构造、Composition 和 Appendix H 全量任务表为基础 [1]，因为 2.1 保留了相同的 89 个任务。版本差异以 Terminal-Bench 官方 2.1 发布说明和仓库为主 [3][4]，并参考用户指定的 OpenClaw-RL Issue #20 中的仓库级对比 [5]。类别计数由 Appendix H 的 89 行任务记录程序化汇总；百分比以 89 为分母。Issue #20 的超时总量和目录操作提示属于第三方复现信息，报告将其与官方版本事实分开表述。

长短任务统计则直接解析官方 2.1 仓库提交 `5c8eadf1f393183288fa08b8f73ca9a469cc5e00` 下 89 份 `tasks/*/task.toml`，快照日期为 2026-07-27 [4]。其中 88 项有 `expert_time_estimate_min` 和 `junior_time_estimate_min`，`caffe-cifar-10` 缺失这两项；89 项均有 Agent 和 Verifier timeout。除非特别说明，人类估时百分比以 88 为分母，评测预算百分比以 89 为分母。实际运行时间只能引用 2.0 论文的公开聚合结果作为背景，因为官方尚未发布与本文元数据同口径的 2.1 全量 task-level runtime 分布。

## 2. 数据集中的“任务”是什么

Terminal-Bench 2.0 从 93 位贡献者提交的 229 个候选任务中筛选出 89 个任务，2.1 沿用了这 89 个任务并修订部分任务定义。每项任务包含：

- 一段给 Agent 的自然语言指令；
- 一个预先配置的 Docker 环境；
- 一组验证最终结果的测试；
- 一份人工编写的参考解法（oracle solution）；
- 一个执行时间限制。

测试主要检查任务结束后的容器状态，而不是限定 Agent 必须使用哪些命令。因此，它测量的是能否完成目标，而不是复现某条固定操作路径。例如，同一个软件构建任务可以通过修改源码、调整依赖或改变构建配置完成，只要最终状态满足测试 [1]。

任务难度标签也是作者给出的人工估计。Appendix H 中有 55 个 Medium、30 个 Hard 和 4 个 Easy，分别占 61.8%、33.7% 和 4.5%；2.1 保持这一分布不变 [5]。这说明数据集有意减少简单文件操作，重点放在需要多步执行、领域知识和现场调试的任务上；但这些标签表示作者对人类难度的判断，不等于 Agent 的实测难度。

## 3. 2.0 → 2.1：任务不变，评测定义得到修补

### 3.1 数据构成保持不变

2.1 没有增删任务：任务数仍为 89，任务 ID 与 2.0 完全重合，难度分布仍为 4 Easy、55 Medium、30 Hard [4][5]。因此，后文的 16 类任务分布和典型案例可以直接作为 2.1 的任务类型画像。更新改变的是部分任务的 instruction、Docker 环境、verifier、依赖或资源预算，而不是评测领域的覆盖范围。

| 对比维度 |                          2.0 |                          2.1 | 影响                                                                 |
| -------- | ---------------------------: | ---------------------------: | -------------------------------------------------------------------- |
| 任务数   |                           89 |                           89 | 无增删                                                               |
| 任务 ID  |                        89 个 |             与 2.0 100% 重合 | 可逐任务配对，但结果未必可直接横比                                   |
| 难度分布 | Easy 4 / Medium 55 / Hard 30 | Easy 4 / Medium 55 / Hard 30 | 类型统计不变                                                         |
| 任务目录 |           任务位于仓库根目录 |    任务位于`tasks/` 子目录 | 本地用 Harbor 的`-p` 参数时需指向 `.../terminal-bench-2-1/tasks` |
| 持续验证 |                 原始发布流程 |   新增 continuous validation | 降低依赖漂移和任务退化风险                                           |

### 3.2 修复集中在公平性和可复现性

官方发布说明将 2.0 的问题概括为三类 [3]：

- **外部依赖漂移**：有 9 个任务受包、API 或外部资源变化影响；
- **资源不匹配**：有 8 个任务的硬件、容器、网络或安全预算不足，使合法解法无法稳定完成；
- **任务定义不一致**：部分 instruction 与测试不对齐，例如 `query-optimize` 的指令要求 PostgreSQL，而测试曾期望 Spark SQL。

官方发布博客称修复了 28 个任务 [3]，而当前官方仓库 README 称修改了 26 个任务 [4]。OpenClaw-RL Issue #20 采用仓库差分口径，也报告 26 个任务有内容修改，并指出其中只有 `caffe-cifar-10` 改变了 `[agent].timeout_sec`：从 1200 秒增至 3600 秒，使 89 项顺序执行的超时总和由约 41.5 小时增至 42.2 小时 [5]。由于第一方材料本身存在“28 vs. 26”的计数差异，本文保留两种口径，不把它们强行合并成一个数字。

### 3.3 分数含义发生了口径变化

官方在多组相同 Agent–Model 配置上比较 2.0 与 2.1，发现多数配置在 2.1 上提高，但幅度并不恒定：示例中从约 +0.9 到 +12.1 个百分点不等，也有少量配置轻微下降 [3]。这不能解释为模型在版本切换时“变强”，而主要反映任务依赖、资源预算和规格公平性的变化。

因此：

- 新实验和 leaderboard 对齐应优先使用 2.1；
- 历史 2.0 分数不能直接与 2.1 分数横向排序；
- 比较模型或训练 checkpoint 时，应确保所有对象运行在同一数据集版本、Agent scaffold、资源和重复次数下；
- 若必须研究版本影响，应让同一 Agent–Model 组合分别运行两版并成对报告。

## 4. 官方任务类型及典型例子

下表使用论文 Appendix H 的作者指定类别。**类别与数量是官方数据；“主要考查”和典型性说明是本调研的归纳。**

| 官方类别                   | 数量 |  占比 | 典型任务                                                                                                                                       | Agent 需要完成的工作                                                                                                                                 |
| -------------------------- | ---: | ----: | ---------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Software Engineering       |   26 | 29.2% | [`cancel-async-tasks`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/cancel-async-tasks)                             | 实现带并发上限的 Python 异步任务调度，并保证键盘中断时清理代码仍能执行。该类还包括 COBOL 现代化、编译器/解释器、形式化证明、代码高尔夫和逆向重实现。 |
| **System Administration** |    9 | 10.1% | [`configure-git-webserver`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/configure-git-webserver)                   | 配置 Git 服务与 Web 服务，使推送的内容自动部署并可通过 HTTP 访问；需要组合服务配置、端口、钩子和进程管理。                                           |
| Scientific Computing       |    8 |  9.0% | [`protein-assembly`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/protein-assembly)                                 | 按蛋白功能、波长、序列、连接肽和 GC 含量等约束设计可合成的融合蛋白 gBlock。此类还包括 Raman 光谱拟合、Bayesian Network、MuJoCo 和采样算法。          |
| Security                   |    8 |  9.0% | [`break-filter-js-from-html`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/break-filter-js-from-html)               | 构造能绕过指定 HTML/JavaScript 过滤器的 XSS 输入。与之对应的数据集中也有编写过滤器、修复漏洞、证书配置、密码恢复和 secret 清理任务。                 |
| Data Science               |    8 |  9.0% | [`rstan-to-pystan`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/rstan-to-pystan)                                   | 将 RStan 贝叶斯推断流程迁移到 PyStan，保持模型、采样参数和输出等价。该类还覆盖 embedding 检索、模型服务和图像分割。                                  |
| Debugging                  |    5 |  5.6% | [`build-cython-ext`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/build-cython-ext)                                 | 修改旧 Python/Cython 包，使其扩展模块兼容新版 NumPy 并通过测试；重点是从构建错误、版本冲突和测试结果定位根因。                                       |
| **File Operations**       |    5 |  5.6% | [`db-wal-recovery`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/db-wal-recovery)                                   | 修复或解密损坏的 SQLite WAL，恢复数据库中全部记录并输出指定 JSON。该类不是简单复制文件，而常包含恢复、解析或大规模编辑。                             |
| Model Training             |    4 |  4.5% | [`pytorch-model-recovery`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/pytorch-model-recovery)                     | 从 state dictionary 推断模型结构，只微调指定输出层，并保存为 TorchScript；要求理解模型结构、冻结参数和指标。                                         |
| Mathematics                |    4 |  4.5% | [`largest-eigenval`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/largest-eigenval)                                 | 实现主特征值与特征向量求解，并同时满足正确性和性能要求。该类还包含 FEAL 线性/差分密码分析和黑盒 ReLU 模型提取。                                      |
| Data Processing            |    4 |  4.5% | [`multi-source-data-merger`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/multi-source-data-merger)                 | 合并 JSON、CSV、Parquet 三种来源，完成字段映射、冲突优先级、类型统一和冲突报告。                                                                     |
| Machine Learning           |    3 |  3.4% | [`llm-inference-batching-scheduler`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/llm-inference-batching-scheduler) | 为不同长度的 LLM 请求设计 shape-aware batching，在形状数量、padding、延迟和成本阈值下输出批处理计划。                                                |
| Games                      |    1 |  1.1% | [`chess-best-move`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/chess-best-move)                                   | 从棋盘图片识别局面，找出白方最佳着法并以指定代数格式输出。                                                                                           |
| **Personal Assistant**    |    1 |  1.1% | [`constraints-scheduling`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/constraints-scheduling)                     | 解析多人的 ICS 日历和可用性约束，找到最早可行会议时段并生成合法日历文件。                                                                            |
| Optimization               |    1 |  1.1% | [`portfolio-optimization`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/portfolio-optimization)                     | 用 C 扩展加速大规模投资组合风险与收益计算，同时满足数值误差和速度阈值。                                                                              |
| **Data Querying**         |    1 |  1.1% | [`sparql-university`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/sparql-university)                               | 编写带地域、职级、院系和学生数量约束的 SPARQL 查询。                                                                                                 |
| Video Processing           |    1 |  1.1% | [`video-processing`](https://github.com/harbor-framework/terminal-bench-2-1/tree/main/tasks/video-processing)                                 | 分析跨栏视频，检测运动员起跳和落地帧，并输出严格格式的 TOML。                                                                                        |

该表的直接结论是：数据集确实跨越多个技术领域，但并不均衡。Software Engineering 单类占 29.2%；若再加入 System Administration、Security、Debugging 和 File Operations，工程、运维、排错、文件恢复和安全类任务合计占 59.6%。相对而言，Personal Assistant、Games 和 Video Processing 各只有一个任务。

## 5. 从实际工作流重新理解这些任务

官方 16 类按任务作者的领域标签组织。若按 Agent 实际执行的工作流观察，类别之间存在以下共性。

### 5.1 构建、实现与迁移

大量任务要求把规格变成可执行工件，包括实现异步调度器、构建旧版 POV-Ray、把 COBOL 改写为 Python、实现 MIPS 解释器和完成 Coq 证明。虽然它们都可能被标为 Software Engineering，但所需能力从阅读构建系统到语言语义、算法实现和形式化推理差异很大。共同点不是“写代码”，而是持续运行、观察和修正，直到产物满足外部测试。

### 5.2 调试、恢复与逆向

`build-cython-ext`、`custom-memory-heap-crash`、`sqlite-db-truncate`、`db-wal-recovery` 和 `path-tracing-reverse` 分属 Debugging、File Operations 或 Software Engineering，却共享同一操作模式：先从不完整证据推断故障或隐藏结构，再通过实验验证假设。由此可见，官方类别描述问题所在领域，并不能完全表达“诊断式工作流”这一跨类别能力。

### 5.3 系统编排与工具使用

Git/Nginx、Mailman/Postfix、QEMU、编译器、包服务器和本地模型 API 等任务要求 Agent 管理多个进程、配置文件和网络接口。这些任务通常不存在一条足够的单命令答案，Agent 必须理解服务之间的依赖关系，并检查端口、日志和最终可达性。

### 5.4 科学、数据与机器学习流程

Scientific Computing、Data Science、Machine Learning、Model Training、Mathematics 和 Data Processing 合计 31 项（34.8%）。它们覆盖统计采样、因果网络、分子设计、模型训练/恢复、embedding 检索、跨格式数据融合和数值算法。与纯代码生成不同，这些任务的测试经常同时约束数值正确性、统计性质、性能或输出格式。

### 5.5 安全与对抗性推理

Security 类同时包含攻击和防御：绕过 XSS 过滤器、破解加密归档、从可执行文件提取 secret、清理 Git 仓库中的凭证以及修复 Web 框架漏洞。某些密码分析任务却被作者标为 Mathematics，说明安全能力横跨官方类别。此类任务更强调发现规则中的可利用空间，而非按文档执行固定流程。

### 5.6 多模态与约束满足

只有少量任务直接处理图像、PDF 或视频，但它们往往仍以终端脚本和文件产物为操作界面。例如，`chess-best-move` 从图片恢复棋局，`video-processing` 从视频定位动作帧，`financial-document-processor` 分类 PDF/JPG 并提取金额。`constraints-scheduling` 则体现了非代码型约束满足，但只有一个 Personal Assistant 样本。

## 6. 这些任务主要测量什么

综合任务说明和验证方式，Terminal-Bench 2.1 主要测量以下能力组合：

1. **长链规划与执行**：把自然语言目标拆成安装、检查、编辑、运行和验证等多步操作。
2. **终端和工具适应**：探索陌生命令、构建系统、编译器、数据库、服务和领域软件。
3. **技术领域知识**：软件工程之外，还涉及密码学、贝叶斯统计、分子生物学、形式化证明和数值优化。
4. **基于反馈的调试**：根据编译错误、测试失败、日志和数值异常不断修正方案。
5. **严格产物交付**：文件路径、数据格式、服务端口、性能阈值和最终容器状态都可能成为测试条件。
6. **自主验证**：强任务需要 Agent 主动运行测试或设计 sanity check，而不是生成内容后立即停止。

这些能力通常同时出现。一个任务成功并不能简单归因于“模型会某个命令”，而更像是领域知识、规划、Agent scaffold、可用工具和运行预算的联合结果。

## 7. 分类与覆盖的解释边界

### 7.1 官方类别不是严格的能力本体

论文明确说明类别由任务作者指定 [1]。因此，同一能力可能分散在不同类别：数据库恢复可以是 File Operations 或 Debugging，密码分析可以是 Mathematics 或 Security，视频输入既可能是 Video Processing，也可能出现在 File Operations。类别统计适合回答“任务主题分布”，不适合单独回答“Agent 为什么失败”。

### 7.2 “多样”主要发生在技术任务内部

16 个类别看起来很宽，但 59.6% 的任务集中在软件工程、系统管理、安全、调试和文件操作；日常办公、沟通协作和个人助理工作覆盖很薄。数据集因此更适合衡量高技能终端技术工作，而不是泛化到所有桌面或知识工作。

### 7.3 最终状态通过不代表过程安全或高效

测试关注最终容器状态，而非 Agent 使用的具体命令 [1]。这种 outcome-driven 设计允许多种有效解法，但一次通过并不能自动证明操作过程安全、成本低、解释充分或可维护。评测成绩首先表示“在给定 Agent、环境和预算下完成了测试定义的目标”。

### 7.4 公开环境带来污染与外部依赖风险

论文承认任务和 oracle solution 公开，且 Agent 可联网，因此存在在线找到答案或训练污染的可能。虽然仓库放置了 canary string，任务仍不是私有 held-out set。网络下载、API、硬件和容器资源差异也会影响可复现性 [1]。

## 8. 长短任务分析：三种“长度”不可混用

### 8.1 本文如何定义长短

Terminal-Bench 2.1 没有官方的 Short / Medium / Long 标签。它提供的是人类完成时间估计、难度标签和评测 timeout；论文另行报告部分 Agent 运行的墙钟时间、模型调用和 token。它们测量的不是同一件事。

| 长度口径 | 直接回答的问题 | 2.1 可用字段或证据 | 主要限制 |
| --- | --- | --- | --- |
| 人类预计工时 | 熟悉或不熟悉该领域的人完成任务要多久？ | `expert_time_estimate_min`、`junior_time_estimate_min` | 由任务作者主观估计，不是实测工时，也不是 Agent 耗时 |
| 评测时间预算 | 一次 Agent / Verifier 最多允许运行多久？ | `[agent].timeout_sec`、`[verifier].timeout_sec` | 是上限而非实际用时；也可能为编译、下载、训练或测试预留 |
| Agent 实际运行时 | 某个 Model–Agent–Task trial 真正用了多久、多少轮和多少 token？ | trajectory、trial 日志和论文聚合统计 | 强依赖模型、Agent scaffold、机器、网络、提前停止和成功与否 |
| 操作依赖长度 | 任务需要维持多少个相互依赖的中间状态？ | 只能从 instruction、轨迹或里程碑人工/程序化标注 | 墙钟时间短的高密度操作链仍可能很“长”；目前 2.1 没有统一字段 |

为让 89 项任务可以重现地分组，本文采用两个**分析者定义而非官方定义**的阈值：

- 人类工时：短任务 `≤1 小时`；中任务 `>1–8 小时`；长任务 `>8 小时`。8 小时近似一个完整工作日。
- Agent 预算：短预算 `≤15 分钟`；中预算 `20–40 分钟`；长预算 `≥60 分钟`。这不是任意等分，而是顺应 2.1 timeout 的实际取值间隙：没有 16–19 分钟或 41–59 分钟的任务。

难度与长度也必须分开。一个需要巧妙算法的任务可能只允许 15 分钟，一个主要耗在下载、构建或训练上的任务可能给 60 分钟以上；Easy / Medium / Hard 不能替代时间口径。

### 8.2 人类估时：专家中位数 1 小时，仍有 8 项超过一个工作日

2.1 当前元数据中，88 项同时提供专家和初级工程师估时；`caffe-cifar-10` 是唯一缺失项 [4]。

| 人类估时统计 | 专家 | 初级工程师 |
| --- | ---: | ---: |
| 短：`≤1 小时` | 53（60.2%） | 13（14.8%） |
| 中：`>1–8 小时` | 27（30.7%） | 50（56.8%） |
| 长：`>8 小时` | 8（9.1%） | 25（28.4%） |
| 中位数 | 60 分钟 | 240 分钟 |
| 四分位区间 | 30–180 分钟 | 120–790 分钟 |
| 均值 | 206.7 分钟 | 1,425.4 分钟 |
| 最大值 | 2,400 分钟（40 小时） | 19,200 分钟（320 小时） |
| 缺失 | 1 | 1 |

均值远高于中位数，说明分布有明显长尾。专家和初级工程师估时的 Spearman 相关为 0.845，方向高度一致，但后者整体更长。这里使用 2.1 当前 `task.toml` 重新统计，而没有直接复用 2.0 论文 Table 1：该表公开的分箱计数只合计 74 项，与当前 88 项非缺失元数据并非同一完整口径 [1][4]。

专家估时超过 8 小时的 8 项是：

| 任务 | 专家估时 | 初级估时 | Agent timeout |
| --- | ---: | ---: | ---: |
| `gpt2-codegolf` | 40 小时 | 160 小时 | 15 分钟 |
| `fix-ocaml-gc` | 24 小时 | 240 小时 | 60 分钟 |
| `regex-chess` | 24 小时 | 80 小时 | 60 分钟 |
| `write-compressor` | 24 小时 | 320 小时 | 15 分钟 |
| `circuit-fibsqrt` | 16 小时 | 40 小时 | 60 分钟 |
| `feal-linear-cryptanalysis` | 16 小时 | 320 小时 | 30 分钟 |
| `sparql-university` | 13 小时 20 分钟 | 166 小时 40 分钟 | 15 分钟 |
| `sam-cell-seg` | 10 小时 | 20 小时 | 120 分钟 |

这些任务的“长”也并非同一种长：`fix-ocaml-gc` 要修复编译器自举时崩溃的垃圾回收器，`regex-chess` 和 `circuit-fibsqrt` 是高度受约束的构造问题，`sam-cell-seg` 需要安装并运行图像分割模型，而 `sparql-university` 的最终交付物只是一个查询。工时估计同时吸收了领域陌生度、设计与调试难度、机器执行时间和产物规模。

### 8.3 评测预算：56.2% 的任务最多给 Agent 15 分钟

| Agent / Verifier 预算统计 | Agent | Verifier |
| --- | ---: | ---: |
| 短预算：`≤15 分钟` | 50（56.2%） | 50（56.2%） |
| 中预算：`20–40 分钟` | 24（27.0%） | 25（28.1%） |
| 长预算：`≥60 分钟` | 15（16.9%） | 14（15.7%） |
| 中位数 | 15 分钟 | 15 分钟 |
| 第三四分位数 | 30 分钟 | 30 分钟 |
| 最大值 | 200 分钟 | 200 分钟 |
| 89 项预算总和 | 42.2 小时 | 41.4 小时 |

48 项的 Agent timeout 恰好是 15 分钟；另外 1 项为 10 分钟、1 项为 12.5 分钟。长预算中，`build-pov-ray` 为 200 分钟，`sam-cell-seg` 为 120 分钟，其余 13 项为 60 分钟。`caffe-cifar-10` 的 Agent timeout 为 60 分钟，但 Verifier 只有 20 分钟，因此两列的长预算任务数相差 1。

这里的 42.2 小时是把 89 项 Agent 上限顺序相加得到的**预算总量**，不是一次 benchmark 的预期墙钟时间。正式 leaderboard 至少要求每项运行 5 个 trial，通常还会并行执行 [4]；成功任务也常在 timeout 前结束。不能用 `timeout × 任务数 × trials` 直接推算真实成本。

### 8.4 人类工时与 Agent 预算只有弱对齐

下表把 88 项有专家估时的任务交叉分组，并单列缺失估时的 `caffe-cifar-10`：

| 专家工时 / Agent 预算 | 短 `≤15m` | 中 `20–40m` | 长 `≥60m` | 合计 |
| --- | ---: | ---: | ---: | ---: |
| 短 `≤1h` | 33 | 15 | 5 | 53 |
| 中 `>1–8h` | 14 | 8 | 5 | 27 |
| 长 `>8h` | 3 | 1 | 4 | 8 |
| 缺失 | 0 | 0 | 1 | 1 |
| 合计 | 50 | 24 | 15 | 89 |

专家估时与 Agent timeout 的 Spearman 相关只有 `ρ=0.255`，初级工程师估时与 Agent timeout 的相关为 `ρ=0.236`。相比之下，把作者难度编码为 Easy=1、Medium=2、Hard=3 后，其与专家估时的相关为 `ρ=0.669`，与 Agent timeout 的相关仅为 `ρ=0.308`。涉及人类估时的相关使用 88 项，难度与 timeout 的相关使用全部 89 项。这些是描述性相关，不说明因果，但足以表明 timeout 不是人类工时的线性压缩版。

错位尤其体现在两端：

- 8 项专家长任务中，只有 4 项得到长预算；`gpt2-codegolf` 和 `write-compressor` 的专家估时分别为 40、24 小时，却都只有 15 分钟，`sparql-university` 也从 13 小时 20 分钟压缩到 15 分钟。
- 反过来，`mteb-leaderboard` 的专家估时只有 5 分钟，却有 60 分钟 Agent 预算；`build-pov-ray` 的专家估时为 60 分钟，Agent 预算达到 200 分钟。后者需要寻找、下载并构建 1990 年代的软件，长预算很可能主要覆盖依赖和机器执行的不确定性。
- 因此，“短预算”不表示任务简单，“长预算”也不自动表示需要更长的认知链。

### 8.5 哪些任务占据长预算尾部

15 项长预算任务按主要耗时机制可粗略分为三组。该分组是对 instruction 的分析性归纳，不是官方类别。

1. **构建、训练、数据和多媒体执行**：`build-pov-ray`、`caffe-cifar-10`、`distribution-search`、`reshard-c4-data`、`sam-cell-seg`、`train-fasttext`、`video-processing`。
2. **深度工程、受约束构造和系统操作**：`circuit-fibsqrt`、`fix-ocaml-gc`、`install-windows-3.11`、`regex-chess`、`winning-avg-corewars`。
3. **科学计算、优化与外部信息获取**：`bn-fit-modify`、`portfolio-optimization`、`mteb-leaderboard`。

从官方类别看，15 项中 Software Engineering 有 5 项、Data Science 有 3 项、Machine Learning 有 2 项，其余 5 项分散在 Scientific Computing、System Administration、Optimization、Model Training 和 Video Processing。长预算并未覆盖所有人类长任务，短预算里也仍有复杂工程和数学构造。

若观察任务量较大的类别，中位数同样显示这种分离：

| 官方类别 | 任务数 | 专家估时中位数 | Agent 预算中位数 |
| --- | ---: | ---: | ---: |
| Software Engineering | 26 | 120 分钟 | 15 分钟 |
| System Administration | 9 | 30 分钟 | 15 分钟 |
| Scientific Computing | 8 | 60 分钟 | 22.5 分钟 |
| Security | 8 | 25 分钟 | 15 分钟 |
| Data Science | 8 | 45 分钟 | 30 分钟 |
| Mathematics | 4 | 480 分钟 | 22.5 分钟 |

Mathematics 的人类估时中位数高达 8 小时，但 Agent 预算中位数只有 22.5 分钟；Software Engineering 也从 2 小时压缩到 15 分钟。类别规模较小时中位数容易受单项任务影响，因此这些数字用于描述构成，不应解释为稳定的领域规律。

### 8.6 实际运行时：主体较短，但有明显长尾

Terminal-Bench 2.0 论文在 32,155 个 trial 上报告：多数 Agent 尝试少于 20 分钟，但极端单任务可运行约 2 小时、调用 API 数百次并消耗接近 1 亿 token [1]。这同时支持两个判断：

- 典型 trial 的实际墙钟时间比“专家完成该任务的工时”短得多；
- Terminal-Bench 的格式能够承载长链和高成本长尾，但不能据此把全部 89 项称为长任务。

这一证据来自 2.0 的多 Model–Agent 聚合实验。2.1 沿用任务 ID，但修改了部分依赖、资源和 timeout，所以它只能作为 2.1 的邻近背景，不能替代 2.1 的 task-level runtime 统计。当前官方 2.1 发布说明和仓库未给出全量 task-level runtime 分布 [3][4]，因此公开材料不足以回答“每个 2.1 任务的成功/失败运行时中位数”“多少 trial 因 timeout 结束”或“长预算是否真的转化为更多有效步骤”。

目前 Terminal-Bench 生态本身也开始把两种 horizon 分开：

| 评测 | 典型规模与时间 | 评分方式 | 与 2.1 的关系 |
| --- | --- | --- | --- |
| Terminal-Bench 2.1 | 89 个可重复任务；Agent timeout 中位数 15 分钟；2.0 实验多数 trial 少于 20 分钟 | 最终容器状态的 outcome-driven 测试 | 本文分析对象 |
| Terminal-Bench Challenges | 当前 3 个单任务项目；官方定位为 days、约 1,000 美元以上、约 1 万–50 万行解法；无统一时间和资源上限 | 按任务定制 correctness / performance 指标 | 同一团队推出的互补长时程格式 [6] |
| Long-Horizon-Terminal-Bench | 46 项；独立论文报告平均 239 episodes、88.9 分钟，统一 90 分钟预算 | rollout 结束后按语义子任务计算部分进度，不是在线奖励 | 外部研究对 Terminal-Bench 风格的长时程扩展 [7] |

不同评测的模型、Agent、任务、预算和计分函数均不同，表中数字不能作为直接 leaderboard 对比。它们更适合解释设计空间：Terminal-Bench 2.1 用较低成本、多任务和终态可验证性换取快速、稳定的能力信号；Challenges 扩展到多日完整项目；Long-Horizon-Terminal-Bench 则强调持续执行和失败时的部分进展。

### 8.7 对后续实验的建议

若要研究 Agent 的“长任务能力”，只报告 89 项总体 pass rate 不够，至少应增加：

1. 按专家工时三档和 Agent 预算三档分别报告 pass rate，避免多数短预算任务掩盖尾部。
2. 对每个 task 记录实际墙钟时间、Agent turns / episodes、输入输出 token、API 调用数、退出原因和是否命中 timeout。
3. 将成功与失败 trial 分开统计运行时；失败很快可能表示无法启动，失败很慢可能表示接近完成或反复试错。
4. 对专家长任务增加 milestone 或 post-hoc partial-progress grader，区分“完全未启动”“完成大部分但未通过最终检查”和“完整通过”。
5. 跨 benchmark 比较时固定 Model–Agent–资源，或明确说明无法同口径；不要把人类估时、timeout 和 Agent 实测时间混成一个 horizon 数字。

## 9. 结论

**RQ1：有哪些任务类型？** Terminal-Bench 2.1 沿用的 89 个任务分为 16 个作者指定类别，从 Software Engineering（26）到 System Administration（9），再到 Scientific Computing、Security、Data Science（各 8），并包含少量游戏、个人助理、查询、优化和视频任务。

**RQ2：典型任务是什么？** 代表性任务不是简单问答，而是实现异步并发控制、配置 Git/Web 服务、恢复损坏数据库、迁移统计程序、设计蛋白序列、绕过或修复安全过滤器，以及从图像/视频提取并交付结构化结果。它们通常需要多步终端操作和最终状态验证。

**RQ3：覆盖重点是什么？** 核心重心是可在容器中程序化验证的高技能技术工作。其广度体现在技术领域内部，但类别和样本数不均衡，不能据此直接外推到 GUI 操作、办公沟通或通用数字助理能力。最合理的使用方式是把它视为“复杂终端工作流完成能力”的基准，而不是所有计算机使用能力的总分。

**RQ4：2.1 更新意味着什么？** 任务类型和数量不变，但部分任务的依赖、资源、instruction、测试和抗 reward-hacking 能力得到修补。2.1 更适合作为新实验口径；2.0 与 2.1 分数应分开报告，跨版本差异不能归因于模型能力。

**RQ5：如何定义长短？** Terminal-Bench 2.1 没有官方二分。人类预计工时、Agent / Verifier timeout、Agent 实际运行时和相互依赖的操作链分别回答不同问题，必须分轴报告。本文的 1 小时、8 小时和 15 / 40 / 60 分钟边界是透明、可复现的分析阈值，不是 benchmark 规范。

**RQ6：长短任务如何分布？** 专家估时中 60.2% 不超过 1 小时、9.1% 超过 8 小时；Agent 预算中 56.2% 不超过 15 分钟、16.9% 达到 60 分钟以上。长预算主要出现在构建、训练、数据/多媒体执行和少数深度工程任务，但若干专家长任务仍只有 15–30 分钟。

**RQ7：三种时间一致吗？** 不一致。专家估时与 Agent timeout 只有弱相关，2.0 实验也显示多数 trial 少于 20 分钟而存在约 2 小时长尾。最稳妥的概括是：Terminal-Bench 2.1 以中短时多任务评测为主体，含有人类工时长任务和运行时长尾；若要严格测量持续数小时到数日的自主执行，应补充 task-level 轨迹统计、部分进度评分或使用专门的长时程评测。

## 附录：2.1 的 89 个任务按官方类别索引

- **Software Engineering（26）**：`build-pmars`、`build-pov-ray`、`cancel-async-tasks`、`circuit-fibsqrt`、`cobol-modernization`、`code-from-image`、`fix-git`、`fix-ocaml-gc`、`git-leak-recovery`、`gpt2-codegolf`、`headless-terminal`、`kv-store-grpc`、`make-doom-for-mips`、`make-mips-interpreter`、`path-tracing`、`path-tracing-reverse`、`polyglot-c-py`、`polyglot-rust-c`、`prove-plus-comm`、`pypi-server`、`regex-chess`、`schemelike-metacircular-eval`、`torch-pipeline-parallelism`、`torch-tensor-parallelism`、`winning-avg-corewars`、`write-compressor`。
- **System Administration（9）**：`compile-compcert`、`configure-git-webserver`、`git-multibranch`、`install-windows-3.11`、`mailman`、`nginx-request-logging`、`qemu-alpine-ssh`、`qemu-startup`、`sqlite-with-gcov`。
- **Scientific Computing（8）**：`adaptive-rejection-sampler`、`bn-fit-modify`、`dna-assembly`、`dna-insert`、`modernize-scientific-stack`、`protein-assembly`、`raman-fitting`、`tune-mjcf`。
- **Security（8）**：`break-filter-js-from-html`、`crack-7z-hash`、`filter-js-from-html`、`fix-code-vulnerability`、`openssl-selfsigned-cert`、`password-recovery`、`sanitize-git-repo`、`vulnerable-secret`。
- **Data Science（8）**：`hf-model-inference`、`mcmc-sampling-stan`、`mteb-leaderboard`、`mteb-retrieve`、`query-optimize`、`reshard-c4-data`、`rstan-to-pystan`、`sam-cell-seg`。
- **Debugging（5）**：`build-cython-ext`、`custom-memory-heap-crash`、`merge-diff-arc-agi-task`、`overfull-hbox`、`sqlite-db-truncate`。
- **File Operations（5）**：`db-wal-recovery`、`extract-elf`、`extract-moves-from-video`、`gcode-to-text`、`large-scale-text-editing`。
- **Model Training（4）**：`count-dataset-tokens`、`pytorch-model-cli`、`pytorch-model-recovery`、`train-fasttext`。
- **Mathematics（4）**：`feal-differential-cryptanalysis`、`feal-linear-cryptanalysis`、`largest-eigenval`、`model-extraction-relu-logits`。
- **Data Processing（4）**：`financial-document-processor`、`log-summary-date-ranges`、`multi-source-data-merger`、`regex-log`。
- **Machine Learning（3）**：`caffe-cifar-10`、`distribution-search`、`llm-inference-batching-scheduler`。
- **Games（1）**：`chess-best-move`。
- **Personal Assistant（1）**：`constraints-scheduling`。
- **Optimization（1）**：`portfolio-optimization`。
- **Data Querying（1）**：`sparql-university`。
- **Video Processing（1）**：`video-processing`。

## 参考资料

[1] Mike A. Merrill, Alexander G. Shaw, et al., “[Terminal-Bench: Benchmarking Agents on Hard, Realistic Tasks in Command Line Interfaces](https://arxiv.org/html/2601.11868),” arXiv:2601.11868, 2026。重点参见 §2.1–2.4、§5 和 Appendix H。

[2] Terminal-Bench Team, “[Terminal-Bench 2.0 Official Task Repository](https://github.com/harbor-framework/terminal-bench-2),” GitHub repository。

[3] Terminal-Bench Team, “[Terminal-Bench 2.1](https://www.tbench.ai/news/terminal-bench-2-1),” official release note, 2026-05-06。

[4] Terminal-Bench Team, “[Terminal-Bench 2.1 Official Task Repository](https://github.com/harbor-framework/terminal-bench-2-1/tree/5c8eadf1f393183288fa08b8f73ca9a469cc5e00),” GitHub repository，本文统计固定于提交 `5c8eadf1f393183288fa08b8f73ca9a469cc5e00`。

[5] HansBug / OpenClaw-RL, “[Terminal-Bench 2.1 配置 + 评测指南（clean-env，与 v2.0 增量对比）](https://github.com/HansBug/OpenClaw-RL/issues/20),” GitHub Issue #20, updated 2026-06-23。该来源用于本地路径、超时总量和仓库差分口径；版本发布事实仍以 [3][4] 为准。

[6] Terminal-Bench Team, “[Introducing Terminal-Bench Challenges](https://www.tbench.ai/news/terminal-bench-challenges),” official release note, 2026-06-18。

[7] Zongxia Li, Zhongzhi Li, Yucheng Shi, et al., “[Long-Horizon-Terminal-Bench: Testing the Limits of Agents on Long-Horizon Terminal Tasks with Dense Reward-Based Grading](https://arxiv.org/html/2607.08964),” arXiv:2607.08964v2, 2026-07-13。该来源是独立外部研究，不属于 Terminal-Bench 官方 2.1 结果。
