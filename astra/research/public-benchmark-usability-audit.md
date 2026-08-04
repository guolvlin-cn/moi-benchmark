# Astra 公共基准可用性审查

日期：2026-07-24<br>
状态：一轮事实审查完成，尚未完成本地冻结与 Runner 验证  
范围：仅服务 Astra 与 Hermes、Goose 的产品级比较

## 1. 结论

没有一个现成公共基准能够直接证明 Astra 的“状态可维护、可控制”。公共基准最合适的角色是提供外部可比的任务结果，Astra 的核心主张仍需由平台中立的故障、权限、审计和并发恢复 Case 证伪。

首期决策如下：

| 基准 | 决策 | 在 Astra 计划中的角色 | 不能据此声称 |
|---|---|---|---|
| Terminal-Bench 2.1 | Pilot 条件纳入，8 题 | 终端任务外部可比性 | 会话可恢复、权限安全、外部副作用 exactly-once |
| SWE-bench-Live | Pilot 条件纳入，4 题 | 真实仓库问题修复 | 长期记忆正确、状态 Owner 唯一、Crash 后可继续 |
| MCP-Universe v1.1.3 | 独立专项门禁 | MCP 发现、组合、Schema 与结果执行 | 断线重连、响应未知时的幂等、租户隔离 |
| AgentDojo v1.2.2 | 独立安全门禁 | 间接提示注入下的效用与攻击成功 | Astra 云边链路、身份传播和权限作用域安全 |
| GAIA | MVP 暂缓 | 第二阶段通用助理 sanity check | 工程 Agent 的状态控制优势 |
| τ³-bench v1.0.1 候选 | 第二阶段条件纳入 | 澄清、政策遵循、交互式状态变更 | 进程恢复和耐久 Checkpoint |
| DeepPlanning v1.1 | 保留既定的 P1 适配门禁 | 动态规划诊断 | 持久化、安全、审计和故障恢复 |

“条件纳入”表示完成版本、任务、容器、评分器与三个产品 Runner 的冻结门槛后才可计分，不表示当前已可运行。

## 2. 审查标准

每个候选基准按以下问题审查：

1. 是否存在可锁定的任务、代码、评分器和环境版本；
2. Oracle 是否尽量是规则或执行结果，而非未经校准的 LLM 主观评分；
3. 三个产品是否可获得等价的任务信息、工具语义、审批路径和预算；
4. 基准是否真的测量目标构念，还是只与目标构念弱相关；
5. 网络、账号、动态网页、用户模拟器和隐藏答案会引入什么混杂；
6. 许可与访问条款是否允许保存、复现和分发所需工件。

证据优先级为：官方代码与版本化数据 > 官方论文与文档 > 项目发布说明。项目自己的排行榜数字只描述项目报告，不作为竞品优劣证据。

## 3. 分项审查

### 3.1 Terminal-Bench 2.1

官方发布说明称 2.1 修正了 2.0 的 89 个任务中的 28 个，涉及外部依赖漂移、资源不匹配和任务说明与测试不一致；但官方数据仓库 README 写的是 26 个任务被修改。这一冲突说明“Terminal-Bench 2.1”这个名字本身不是充分的复现标识，必须保存任务仓库 commit、Harbor 数据版本、镜像 digest 和任务清单。

适用性：

- 强：容器内终端操作、结果工件和任务测试；
- 中：长执行链中的错误恢复能力，但只有自然发生的工具错误；
- 弱：产品会话恢复、审批、跨租户隔离和外部副作用一致性。

首期使用 8 个分层任务，避免全部来自同一语言、资源级别或任务类型。MOI Pilot 的每题 3 次仅用于先导研究；官方仓库要求排行榜提交每题至少 5 次，因此 Pilot 结果不得写成官方排行榜可比结果。正式外部可比复跑再使用 `k=5`。

### 3.2 SWE-bench-Live

初始 Python 数据发布包含 1,319 个任务，论文中的 Lite 为 300 个。项目随后增加多语言 Linux 和 Windows 版本；官方仓库在 2026 年列出的规模分别为 743 个和 61 个任务。不同代际使用的执行脚本、语言、平台和任务构造不完全相同，不能把它们混成一个总体分数。

适用性：

- 强：理解真实 issue、浏览仓库、修改代码、通过 fail-to-pass 与 pass-to-pass 测试；
- 中：长上下文和多轮工具使用；
- 弱：状态所有权、Crash 恢复、权限边界和跨会话记忆。

首期必须从一个冻结发布和一个明确 split 中选择 4 题，并冻结基础 commit、测试 patch、镜像和评估代码。持续更新的 `full` split 不进入可复现 Pilot。若选择 Python、MultiLang 或 Windows，必须单独成层并使用其对应评估路径。

### 3.3 MCP-Universe v1.1.3

官方材料列出 231 个任务、6 个领域、11 个 MCP Server、133 个工具和 84 个独立 evaluator。评分包含格式、静态和动态执行式检查，并明确不以 LLM-as-judge 为主评分器。这使其适合做 MCP 能力专项。

主要问题是很多任务依赖真实服务、账号、API Key 和动态状态。成功率会同时受 Agent、服务可用性、鉴权、配额、网络和时间窗口影响。首期必须把本地或静态任务与 live-service 任务分榜，并记录每个服务的版本、权限、速率限制和采集时间。

官方任务改造为断线、超时、响应丢失或重复副作用后，得到的是 **MOI-derived** 故障 Case，不再是官方 MCP-Universe 分数。该派生层才可能触及 Astra 的状态控制主张。

### 3.4 AgentDojo

官方包的候选发布为 v0.1.35，而代码默认基准版本为 v1.2.2；两者是独立版本轴，必须同时冻结。论文发布快照含 97 个正常任务和 629 个安全测试 Case，但不能把论文数字直接当作当前 v1.2.2 的任务数，本地 checkout 后需要重新枚举。

AgentDojo 适合比较间接提示注入下的：

- clean utility；
- utility under attack；
- injection goal 是否达成。

这三者必须分别报告，不能与普通任务成功率平均成一个“安全总分”。它的环境是基准模拟环境，不能替代 Astra 特有的路径、身份、租户和子 Agent 权限继承测试。三个产品还必须使用同样的工具描述、恶意内容、审批交互、模型和重试预算；否则测到的是适配器或额外防御预算。

### 3.5 GAIA

论文报告 466 个问题，并包含网页、文件附件和多模态任务。数据访问需要接受 Hugging Face 的 gated 条款，数据卡未声明一个可直接据此再分发的标准开源许可证。公共验证答案可见，存在污染风险；测试答案隐藏，需要官方评分路径。

官方 scorer 不是一般意义上的严格 exact match，而是对答案归一化后做边界匹配，并对数值 token 做 bag-of-words 检查。因此必须锁 scorer commit，不能在报告中简写为“完全一致评分”。

GAIA 还强依赖实时网页、浏览器和附件能力，三个产品很难在首期获得真正相等的环境。它与 Astra 核心主张的距离较远，故从 MVP 暂缓；未来只作为通用助理 sanity check，且不进入 P0 总结。

### 3.6 τ³-bench

仓库已从 τ²-bench 演进为 τ³-bench。当前候选冻结点为 v1.0.1；项目说明该版本修订了 `banking_knowledge` 的评分，相关领域的旧结果不能直接与新版混用。仓库的任务和评分持续修复，所以最终任务数必须从冻结 checkout 枚举，不能引用旧论文数量替代。

它通过 LLM 用户模拟器与 Agent 交互，并按数据库状态、动作和任务结果评分，适合测量澄清、政策遵循和共享状态变更。但用户模拟器本身是第二个随机 Agent，会显著放大方差。

第二阶段只使用 airline、retail、telecom 的文字半双工任务；冻结用户模拟器模型、版本、Prompt、温度、Seed 策略和轮次预算。语音全双工与 `banking_knowledge` 暂不混入首个比较。它不直接制造进程 Crash，也不验证耐久恢复。

#### 3.6.1 `banking_knowledge` 的先验性与相关工作审计

本节按 **2025-06-01 之前公开** 的工作审计其研究先验性；2025-06-01 之后至 τ-Knowledge v1 于 2026-03-04 公开之间的论文不用于主先验结论。CRMArena-Pro 于 2025-05-24 公开，仅比截止日期早 8 天，因此更适合作为同期最近邻，而不能据此推断思想来源。

τ-Knowledge 原文没有宣称 “first benchmark” 或 “largest benchmark”。其较克制的主张是：多数既有基准分别评估 retrieval 或 tool use，很少同时覆盖专有非结构化知识、动态用户、政策推理和可验证行动。把该表述扩大为“此前鲜少研究 Agent 与私有数据交互”“首次结合知识检索与工具调用”或“首次评测多轮有状态工具 Agent”均不成立。

这里还必须区分两种 “private”：

- τ-Banking 的知识库由结构化规格生成并公开，模拟的是组织专有、预训练时不可见的非参数知识；
- 它不使用真实客户私密数据，也不直接评测授权、访问控制、信息泄露或数据最小化，因此不是严格意义上的隐私基准。

截至该日期的主要最近邻如下：

| 既有工作 | 已经覆盖的能力 | 相比 τ-Banking 缺少的关键维度 |
|---|---|---|
| [ToolLLM / ToolBench（2023）](https://arxiv.org/abs/2307.16789) | 从 16,464 个 API 的文档中检索相关工具，再进行多工具调用 | 无持久状态、动态用户和企业政策语料；先占了宽泛的“工具检索/发现”，但不是文档门控的状态改变工具 |
| [WorkArena++（2024）](https://proceedings.neurips.cc/paper_files/paper/2024/file/0b82662b6c32e887bb252a74d8cb2d5e-Paper-Datasets_and_Benchmarks_Track.pdf) | L3 任务要求从企业知识库检索流程，再在 ServiceNow 执行，包括修改数据库记录并由后端验证 | 无 on-policy 模拟用户；浏览器动作空间始终已知；知识库不是密集互联的客户政策与产品语料 |
| [τ-bench（2024）](https://arxiv.org/abs/2406.12045) | 动态模拟用户、政策遵循、API 状态改变、最终数据库状态验证和重复试验可靠性 | 政策和全部工具预先提供，无知识库检索或工具发现 |
| [ToolSandbox（2024）](https://arxiv.org/abs/2408.04682) | on-policy 用户模拟、有状态工具执行、隐式状态依赖和任意轨迹的里程碑评测 | 无大型专有式非结构化知识库，也无文档门控工具 |
| [AgentDojo（2024）](https://arxiv.org/abs/2406.13352) | Agent 读取邮件、云端文件和银行等用户特定状态，通过工具读写可变环境，并按执行前后状态确定性检查 | 无在线用户模拟；工具文档预先放入 Prompt；重点是间接提示注入安全而非知识密集政策推理 |
| [TheAgentCompany（2024）](https://arxiv.org/abs/2412.14161) | 内部文档、Wiki、企业网站、终端和通信工具，含模拟同事、长程任务及状态/Checkpoint 检查 | 模拟同事不是持续交互的任务用户；没有统一的大型政策库或检索门控动作空间 |
| [CRMArena-Pro（2025-05-24）](https://arxiv.org/abs/2505.18878) | Salesforce 企业环境、知识文章/邮件/通话记录检索、政策与保密判断，以及多轮 LLM 用户模拟 | Agent 主要通过 SOQL/SOSL 做读取和搜索，最终多为 ID 或文本答案；没有目标数据库写入或工具发现/解锁 |

由此得到三层结论：

1. **“过去少有工作关注 Agent 与私有或企业数据交互”不成立。** WorkArena++、AgentDojo、TheAgentCompany 和 CRMArena(-Pro) 已直接覆盖企业内部或用户特定数据。
2. **“检索和工具调用通常被分开评测”作为总体趋势可以成立，但不能作为无例外的 novelty 叙事。** WorkArena++ 已把“从企业知识库取流程 → 执行状态改变 → 后端验证”放在同一任务链；CRMArena-Pro 已把企业非结构化文本检索、政策判断和动态用户放在同一环境。
3. **τ-Banking 的完整机制组合仍有较强新颖性。** 本次审计未发现 2025-06-01 前有其他公开基准在同一实时模拟客户支持对话中，同时要求大型专有式非结构化语料检索、跨文档政策推理、从文档发现并解锁状态改变工具，以及目标后端状态验证。

因此，其稳妥定位不是任何单项能力的首次，而是以下交集和评测机制的贡献：

> 既有基准已经分别覆盖企业知识库驱动的系统操作、多轮有状态工具使用，以及企业文本检索与政策判断。τ-Knowledge 将这些能力统一到一个可执行的客户支持环境中：Agent 需在与模拟用户的长程交互中检索非结构化知识，依据跨文档政策决定行动，发现并解锁文档中描述的状态改变工具，最终由后端目标状态验证任务是否完成。

τ-Knowledge v1 的 Related Work 引用了 TheAgentCompany，但未纳入 WorkArena++、CRMArena-Pro、ToolSandbox 和 AgentDojo；这不会自动推翻上述完整交集的新颖性，却使“多数检索与工具使用彼此独立”的论证不够完整。

对 Astra 而言，`banking_knowledge` 若后续纳入，能支持的构念应限定为“知识检索 → 政策推理/工具发现 → 对话式状态改变”的端到端能力。它不能单独支持真实私有数据安全、权限边界、耐久 Checkpoint 或 Crash 恢复主张。

#### 3.6.2 τ² / τ³ 的任务类别与典型例子

**版本关系。** τ³ 不是一套与 τ² 完全分离的数据；它是同一仓库中的总升级，保留并修订 τ² 的 Airline、Retail、Telecom 核心任务，同时加入 τ-Knowledge 的 `banking_knowledge`，并用 τ-Voice 在同一批核心任务上增加全双工语音评测。因此，“τ³ 有多少类任务”必须分别回答业务领域、任务意图和交互模态，不能把它们相加成一个互斥 taxonomy。

| 冻结口径 | Airline | Retail | Telecom | Banking | 解释 |
|---|---:|---:|---:|---:|---|
| [τ² 论文](https://arxiv.org/pdf/2506.07982) Table 1 | 50 | 115 | 114；完整组合池 2,285 | — | 论文总数 279 |
| [τ² `v0.1.0`](https://github.com/sierra-research/tau2-bench/releases/tag/v0.1.0) 实际 JSON | 50 | 114 | 114 | — | 发布版实际总数 278；未找到 Retail 相差 1 题的官方解释 |
| τ³ [`v1.0.1`](https://github.com/sierra-research/tau2-bench/releases/tag/v1.0.1) | 50 | 114 | 114 | 97 | 核心三域取 `base`、Banking 取全量，共 375 题；其 97 个 ID 有间断，不能据编号端点推算数量 |
| τ-Voice | 50 | 114 | 114 | — | 复用 278 个业务任务，不是新增 278 个语义任务 |

`v1.0.1` 数量来自 [Airline](https://github.com/sierra-research/tau2-bench/blob/v1.0.1/data/tau2/domains/airline/split_tasks.json)、[Retail](https://github.com/sierra-research/tau2-bench/blob/v1.0.1/data/tau2/domains/retail/split_tasks.json)、[Telecom](https://github.com/sierra-research/tau2-bench/blob/v1.0.1/data/tau2/domains/telecom/split_tasks.json) 的 split 文件与 [Banking 任务目录](https://github.com/sierra-research/tau2-bench/tree/v1.0.1/data/tau2/domains/banking_knowledge/tasks)。任务 Schema 没有全局 `category`、`intent` 或 `task_type` 字段。只有 Telecom 把官方 intent 和根因编码进任务 ID；Airline、Retail 和 Banking 下文的业务类别均是本次根据用户指令、参考动作和成功状态做的 **multi-label 归纳**，不是项目发布的互斥标签。Banking 论文所称的 21 类是知识文档/产品类别，也不是 21 类任务；Voice 的 clean/realistic 等是评测条件，也不是任务类别。

**τ²：Airline。** 该域测的是在航空政策约束下查询、预订和修改同一数据库。按 [`v0.1.0` Airline 任务文件](https://github.com/sierra-research/tau2-bench/blob/v0.1.0/data/tau2/domains/airline/tasks.json) 的参考写动作归纳如下；同一题可能同时涉及多类。

| 归纳类别 | 含该参考动作的题数 | 典型例子与成功条件 |
|---|---:|---|
| 新订票 | 7 | task `8`：按指定日期预订 ORD→PHL、两名乘客、经济舱，无行李和保险，并使用 certificate；成功要求生成字段完全正确的 reservation |
| 改航班/日期/舱位 | 14 | task `11`：不能只删除同行乘客时，按 fallback 把全员降为 basic economy；成功要求预订终态符合 fallback，而不是迎合非法首选 |
| 取消预订 | 9 | task `9`：处理两个取消请求，同时查询另一个直飞改签选项；成功同时依赖正确取消状态和应告知的信息 |
| 行李变更 | 6 | task `12`：升级超出预算，但仍应加入两件免费托运行李；成功要求只执行政策允许且用户仍需要的部分 |
| 乘客信息变更 | 3 | task `40`：把 Mei Lee 更名为 Mei Garcia；成功要求乘客记录正确更新 |
| 延误补偿 | 3 | task `2`：核对实际乘客数和延误资格后发放相应 certificate |
| 转人工 | 1 | task `13`：目的地变更超出可自助修改政策，正确结果是转人工 |
| 查询、资格判断或拒绝；无参考写动作 | 19 | task `0`：出票已超过 24 小时且无保险，应拒绝退款取消并保持数据库不变；task `3` 则需纠正用户的会员等级认知并告知 4 件行李额度 |

**τ²：Retail。** 该域测订单生命周期、商品规格和付款/地址政策。按 [`v0.1.0` Retail 任务文件](https://github.com/sierra-research/tau2-bench/blob/v0.1.0/data/tau2/domains/retail/tasks.json) 归纳：

| 归纳类别 | 含该参考动作的题数 | 典型例子与成功条件 |
|---|---:|---|
| 已送达商品换货 | 29 | task `0`：同时把键盘换为指定规格、恒温器换为兼容 Google Home 的版本；成功要求两个 SKU 和差价处理均正确 |
| 已送达商品退货 | 32 | task `2`：退回多件商品，同时回答另一件 T-shirt 的选项信息；成功兼有数据库终态与沟通要求 |
| 修改 pending order 商品 | 35 | task `3`：把未发货 T-shirt 改成目标颜色/规格；只允许修改仍为 pending 的订单 |
| 取消 pending order | 18 | task `38`：若多种降价替代方案都不可行，执行用户给定的取消 fallback |
| 修改订单地址或用户默认地址 | 24 | task `17`：修正指定订单的 suite；有些题同时要求改订单地址和 profile 默认地址 |
| 修改 pending order 支付方式 | 1 | task `40`：先查询礼品卡余额，若不能追加礼品卡则把最近订单改用指定 Visa |
| 转人工 | 4 | task `10`：用户要求的跨订单退款支付方式不受支持，正确结果是转人工 |
| 纯查询/无参考写动作 | 7 | task `24`：保留 grill，仅回答另一个订单中两件 T-shirt 的材料 |

**τ²：Telecom。** 这是三域中唯一有官方原生意图分类、也是唯一真正双控制的领域：Agent 操作 CRM、账单或线路工具，模拟用户操作自己的手机设置。其 114 题按任务 ID 的 intent 分为：

| 官方 intent | 题数 | 真实典型例子与成功条件 |
|---|---:|---|
| `service_issue` | 29 | [`[service_issue]airplane_mode_on\|unseat_sim_card[PERSONA:None]`](https://github.com/sierra-research/tau2-bench/blob/v0.1.0/data/tau2/domains/telecom/tasks.json)：用户关闭飞行模式并重新插拔 SIM；最终 `assert_service_status("connected")` |
| `mobile_data_issue` | 36 | [`[mobile_data_issue]data_mode_off\|data_usage_exceeded[PERSONA:None]`](https://github.com/sierra-research/tau2-bench/blob/v0.1.0/data/tau2/domains/telecom/tasks.json)：用户开启数据，Agent 精确补充 2 GB；最终数据开启、网速为 200/`excellent` 且补量正确 |
| `mms_issue` | 49 | [`[mms_issue]break_app_sms_permission\|data_mode_off[PERSONA:None]`](https://github.com/sierra-research/tau2-bench/blob/v0.1.0/data/tau2/domains/telecom/tasks.json)：用户恢复短信权限并开启数据；最终 `assert_can_send_mms(true)` |

每个 intent 还由多个根因组合而成，例如飞行模式、SIM 松动、欠费停机、流量耗尽、VPN、APN 和 App 权限。论文按一题包含的子任务数统计复杂度：2/3/4/5/6/7/8/9 个子任务分别有 25/26/21/13/11/8/4/6 题；persona 分布为 None 40、Easy 38、Hard 36。

**τ³ 对核心任务的变化。** [`v1.0.0` 发布说明](https://github.com/sierra-research/tau2-bench/releases/tag/v1.0.0)称修复了 27 个 Airline 和 26 个 Retail 任务；这主要是 gold 动作、断言和可实现性修订，不代表新增业务领域。用“参考解是否包含该动作”的 multi-label 口径比较 `v0.1.0 → v1.0.1`，Airline 的订票为 7→8、改航班 14→13、取消 9→7、行李 6→5、乘客 3→3、发补偿 certificate 3→0、无写动作 19→23；Retail 的换货 29→29、退货 32→31、改商品 35→35、取消 18→18、地址变更 24→24、支付变更 1→1。数字移动表示参考终态被修正，不能当成 τ³ 删除了一类业务。一个直观例子是 Airline task `27`：新版要求确认延误补偿资格，但用户不愿改签或取消时不应立即发 certificate。

**τ³ 新增的 Banking / τ-Knowledge。** 其 97 题把非结构化知识检索、跨文档政策推理、按文档发现工具、长程对话和后端状态验证串在一起。论文明确用三种能力原型展示代表题；其余行是本次对真实任务的非互斥归纳。

| 能力/业务族 | 典型真实任务 | 用户请求、关键难点与成功条件 |
|---|---|---|
| 多约束产品推荐与开户 | [`task_071`](https://github.com/sierra-research/tau2-bench/blob/v1.0.1/data/tau2/domains/banking_knowledge/tasks/task_071.json) | 在 8 个商业 checking 与 7 个商业 savings 候选中，结合 2025-11-14 仍有效的促销筛选并开户；需查 30 篇必需文档，最终开户状态正确 |
| 程序化政策执行/挽留 | [`task_043`](https://github.com/sierra-research/tau2-bench/blob/v1.0.1/data/tau2/domains/banking_knowledge/tasks/task_043.json) | 用户要关信用卡；Agent 须验资格、偿还 \$75、检查历史、记录原因，并按政策改为一年年费减免；成功是正确挽留终态而非机械关卡 |
| 有依赖的操作排序 | [`task_062`](https://github.com/sierra-research/tau2-bench/blob/v1.0.1/data/tau2/domains/banking_knowledge/tasks/task_062.json) | 四个账户的开立、关闭和转账若照用户口述顺序执行会互相阻塞；Agent 必须按依赖关系重排 13 条参考动作（含身份验证） |
| 信用额度与交易争议 | [`task_053`](https://github.com/sierra-research/tau2-bench/blob/v1.0.1/data/tau2/domains/banking_knowledge/tasks/task_053.json) | 同时提额到 \$22,500 并争议 \$1,247.99 未收货交易；若先报争议会使提额不合格，故必须先完成提额，再立案，最终两项 DB 状态都正确 |
| 卡片丢失/冻结/替换生命周期 | [`task_077`](https://github.com/sierra-research/tau2-bench/blob/v1.0.1/data/tau2/domains/banking_knowledge/tasks/task_077.json) | 跨信用卡和借记卡完成冻结、发现、补卡、解冻/关闭、新卡订购与激活；成功依赖长动作链的最终状态 |
| 奖励、推荐、费用与利息纠错 | [`task_093`](https://github.com/sierra-research/tau2-bench/blob/v1.0.1/data/tau2/domains/banking_knowledge/tasks/task_093.json)、[`task_098`](https://github.com/sierra-research/tau2-bench/blob/v1.0.1/data/tau2/domains/banking_knowledge/tasks/task_098.json) | 代表 savings 利息纠错/报告，以及比较推荐收益后提交 referral；相关题还覆盖 cashback、ATM fee 和奖励争议 |

**τ³ 的 Voice 是模态层。** [τ-Voice](https://arxiv.org/html/2603.13686)把上述 278 个 Airline、Retail、Telecom 任务改为 audio-native full-duplex：双方可同时说话，用户可以打断、让步或等待。clean/control 条件使用干净电话音频；realistic/regular 还加入多口音、背景噪声、掉帧、含混、口头禅、旁白、插话和 backchannel。论文的具体例子仍是 Retail task `41`：把 1000 片中等难度拼图改成最简单且片数最少的选项，并修正两个订单地址和默认地址。业务成功状态与文字版相同，额外评估响应/让步延迟、打断处理和选择性聆听，不能把语音条件算成新业务类。

**评分决定“典型任务做成了什么”。** `evaluation_criteria.actions` 通常只是用于生成目标终态的一条参考轨迹；只有 `ACTION` 出现在 `reward_basis` 中时才要求命中特定调用。在冻结的 `v1.0.1` `base` split 中：

| 域 | reward basis 分布 | 实际成功语义 |
|---|---|---|
| Airline | 50/50 为 `DB + COMMUNICATE` | 数据库终态正确，并说出指定关键信息 |
| Retail | 112 为 `DB + NL_ASSERTION`，2 为 `DB` | 数据库终态正确；绝大多数题还由 LLM 判断自然语言要求 |
| Telecom | 94 为 `ENV_ASSERTION`，20 为 `ACTION + ENV_ASSERTION` | 手机/线路断言成立；转人工类还必须出现指定动作 |
| Banking | 88 为 `DB`，9 为 `ACTION` | 多数按最终后端状态，少数强制关键工具调用 |

这里存在一处应在复现报告保留的代码/论文差异：τ² 论文称 Telecom 只用 assertion functions，但 `v0.1.0` 和 `v1.0.1` 的 114 题中均有 20 题启用 `ACTION + ENV_ASSERTION`。因此 Astra 不能只按自然语言“任务类别”分层抽样；还应同时按领域、是否双控制、写操作链长度、检索负担、依赖重排、reward basis 和语音条件建采样矩阵。

## 4. 与 Astra 核心主张的覆盖关系

| 基准 | G：状态可追溯/可版本化 | O：运行可观测/可干预 | P：权限/身份边界 | 任务结果外部可比 |
|---|---:|---:|---:|---:|
| Terminal-Bench 2.1 | 弱 | 弱 | 弱 | 强 |
| SWE-bench-Live | 弱 | 弱 | 弱 | 强 |
| MCP-Universe | 弱 | 中 | 弱 | 中 |
| AgentDojo | 弱 | 中 | 中，但不是产品基础设施边界 | 中 |
| GAIA | 弱 | 弱 | 弱 | 中 |
| τ³-bench | 弱 | 中 | 中，偏业务政策 | 中 |
| DeepPlanning | 弱 | 弱 | 弱 | 中 |

这张表直接否定一个危险推理：在上述公共榜单上任务成功率高，不能推出“状态更可维护、更可控制”。反过来，Astra 的状态机制更丰富，也不能推出任务结果更好。两类结果必须并列而非互相代替。

## 5. MVP 落地方式

### 5.1 主 Pilot

- 公开层保持 12 Case：Terminal-Bench 2.1 为 8 个，冻结版 SWE-bench-Live 为 4 个；
- 产品工程层保持 12 Case，独立覆盖会话/记忆、多 Agent、故障恢复、MCP、安全、审计；
- MCP-Universe、AgentDojo 和 τ³-bench 可提供任务与 Oracle 设计方法，但修改后的 Case 标为 MOI-derived；
- DeepPlanning 保持独立的 12 Case Runner 等价性门禁；
- GAIA 不进入 MVP。

### 5.2 专项扩展门禁

只有满足以下条件才新增专项计分：

1. 三个产品的输入、工具 Schema、结果语义、审批通道和预算已形成对照表；
2. 冻结版本能在离线 fixture 上重复评分；
3. live-service 失败可与产品失败分开归因；
4. 修改过的任务不冒充官方分数；
5. 安全结果、正常效用和恢复结果分别报告。

## 6. 尚未关闭的阻塞项

- 六个项目均尚未在本地保存 commit、任务清单和哈希；
- Terminal-Bench 2.1 的任务修改计数存在官方来源冲突；
- SWE-bench-Live 的首期 split 尚未决定；
- GAIA 的分发边界尚未完成许可审查；
- τ³-bench 的 v1.0.1 `base` 任务数已从 tag 枚举，但永久本地冻结、文件哈希和评分回放尚未完成；
- 三个产品的公共基准 Adapter 均未通过等价 Smoke Test。

因此，本文件只能支持“候选选择与实验设计”，不能支持任何产品排名。

## 7. 主要来源

- Terminal-Bench：[2.1 发布说明](https://www.tbench.ai/news/terminal-bench-2-1)、[2.1 数据仓库与提交规则](https://github.com/harbor-framework/terminal-bench-2-1)、[论文](https://arxiv.org/abs/2601.11868)
- SWE-bench-Live：[官方仓库](https://github.com/microsoft/SWE-bench-Live)、[论文](https://arxiv.org/abs/2505.23419)
- MCP-Universe：[官方仓库](https://github.com/SalesforceAIResearch/MCP-Universe)、[使用文档](https://mcp-universe.github.io/usage.html)、[任务说明](https://mcp-universe.github.io/tasks.html)、[论文](https://arxiv.org/abs/2508.14704)
- AgentDojo：[官方仓库](https://github.com/ethz-spylab/agentdojo)、[文档](https://agentdojo.spylab.ai/)、[论文](https://arxiv.org/abs/2406.13352)
- GAIA：[数据卡](https://huggingface.co/datasets/gaia-benchmark/GAIA/blob/main/README.md)、[官方 scorer](https://huggingface.co/spaces/gaia-benchmark/leaderboard/blob/main/scorer.py)、[论文](https://arxiv.org/abs/2311.12983)
- τ³-bench：[官方仓库](https://github.com/sierra-research/tau2-bench)、[`v0.1.0` 发布版](https://github.com/sierra-research/tau2-bench/releases/tag/v0.1.0)、[`v1.0.0` 发布说明](https://github.com/sierra-research/tau2-bench/releases/tag/v1.0.0)、[`v1.0.1` 修订说明](https://github.com/sierra-research/tau2-bench/releases/tag/v1.0.1)、[任务修复说明](https://taubench.com/blog/tau3-task-fixes.html)、[τ² 论文](https://arxiv.org/abs/2506.07982)、[τ-Knowledge 论文](https://arxiv.org/abs/2603.04370)、[τ-Voice 论文](https://arxiv.org/abs/2603.13686)、[领域数据说明](https://github.com/sierra-research/tau2-bench/blob/v1.0.1/src/tau2/domains/README.md)、[评分说明](https://github.com/sierra-research/tau2-bench/blob/v1.0.1/docs/evaluation.md)
- τ-Knowledge 先验性对照：[ToolLLM / ToolBench](https://arxiv.org/abs/2307.16789)、[WorkArena++](https://proceedings.neurips.cc/paper_files/paper/2024/file/0b82662b6c32e887bb252a74d8cb2d5e-Paper-Datasets_and_Benchmarks_Track.pdf)、[τ-bench](https://arxiv.org/abs/2406.12045)、[ToolSandbox](https://arxiv.org/abs/2408.04682)、[AgentDojo](https://arxiv.org/abs/2406.13352)、[TheAgentCompany](https://arxiv.org/abs/2412.14161)、[CRMArena-Pro](https://arxiv.org/abs/2505.18878)
- DeepPlanning 与 OpenViking：见 [deepplanning-and-openviking-usability.md](./deepplanning-and-openviking-usability.md)

## 8. AI 使用说明

本审查由 AI 辅助检索、归纳和交叉核对。版本、规模、许可和评分器描述优先取自项目官方仓库、文档与论文；存在冲突或尚未本地复核的内容已显式标记。正式执行前仍需由负责人完成版本冻结、许可确认和评分回放。
