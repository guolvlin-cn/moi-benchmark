# SWE-bench-Live `verified`：冻结工件审计与 Astra 可用性分析

日期：2026-07-28  
状态：数据文件与数据卡已下载并校验；评测代码、Docker 镜像和 gold replay 尚未冻结  
本地快照：[`work/SWE-bench-Live-verified`](../../work/SWE-bench-Live-verified/)

## 摘要

本报告审计 SWE-bench-Live Python 数据集中的 `verified` split，而不是原始 SWE-bench 的 `SWE-bench_Verified`。本地冻结文件包含 500 行、100 个仓库和 2024-07 至 2025-04 的真实 issue–PR 任务。它的主要优势是：任务来自较新的真实仓库、每题带 `base_commit`、gold/test patch、FAIL_TO_PASS、PASS_TO_PASS 和可执行测试信息，且该 split 已由官方冻结，适合可复现实验。其主要限制也很明确：`verified` 是 LLM 自动过滤而非人工逐题验证；公开文件实际只有 499 个唯一 `instance_id`；仓库分布明显集中；Docker 环境仍可能随机器和时间失效；冻结 split 自 2025 年公开后不再具备“持续新鲜”的强污染保证。

对 Astra，稳妥用法是将它作为真实软件修复结果层，而不是状态治理、权限或恢复能力的直接测量。首期抽样应先按唯一 ID 去重，按仓库和 gold patch 复杂度分层，再对候选题执行同机 gold patch 3/3 回放。未经镜像、Harness 和 gold replay 冻结的本地 Parquet 只能用于选题和静态分析，不能直接支持产品分数。

## 1. 调研问题与范围

本报告回答三个问题：

1. **RQ1：** `verified` 的官方身份、冻结版本和可复现下载工件是什么？
2. **RQ2：** 该 split 的实际字段、规模、仓库/时间分布、结构复杂度和典型任务是什么？
3. **RQ3：** 它如何判定任务完成，存在哪些 artifact 风险，Astra 应如何使用？

范围限定为 Hugging Face 仓库 `SWE-bench-Live/SWE-bench-Live` 的 Python `verified` split。2026 年后新增的 MultiLang 和 Windows 数据不混入统计，也不把原始 `SWE-bench/SWE-bench_Verified` 当作同一数据集。

## 2. 方法与冻结口径

检索分为三个相互校验的视角：

- **工件与版本：** Hugging Face 数据卡、文件历史、revision、文件大小和哈希；
- **构造与质量：** NeurIPS 2025 camera-ready 论文中的爬取、RepoLaunch、测试验证和 LLM 过滤；
- **执行与可用性：** 官方代码仓库、Python-only 分支和评测说明中的镜像、资源、gold replay 与分母口径。

仅采用项目官方数据仓库、官方代码仓库和 NeurIPS 论文。静态统计直接读取下载后的 Parquet，使用 DuckDB 1.5.5；没有用网页 Viewer 的聚合值替代本地结果。

### 2.1 本地工件

| 项目 | 冻结值 |
|---|---|
| 官方 HF repo | `SWE-bench-Live/SWE-bench-Live` |
| Split | `verified` |
| Snapshot revision | `a637bd46829f3132e12938c8a0ca93173a977b8e` |
| Verified 文件最后变更 commit | `a7fb0f20bd3b946ee3a22a8b63145a48092340bc` |
| 本地文件 | [`data/verified-00000-of-00001.parquet`](../../work/SWE-bench-Live-verified/data/verified-00000-of-00001.parquet) |
| 文件大小 | 24,696,977 bytes |
| SHA-256 | `080e36e46198bf9c177a6b077624d4028baf6ff04d661c332cc1fe1e5dfa50b2` |
| 数据卡 | [`DATASET_CARD.md`](../../work/SWE-bench-Live-verified/DATASET_CARD.md) |
| 校验清单 | [`MANIFEST.sha256`](../../work/SWE-bench-Live-verified/MANIFEST.sha256) |
| 下载日期 | 2026-07-28 |

官方 Hugging Face 大文件端点在本环境中超时，因此实际传输经过 HF Mirror 的同一 immutable revision。镜像响应中的 `X-Repo-Commit` 和 `X-Linked-ETag` 分别匹配上述官方 revision 与 SHA-256；下载后又在本地逐字节校验。**数据来源仍是官方 HF 工件，镜像只承担传输。**

本地目录只包含 Parquet 和数据卡，不包含任何实例镜像、上游源码仓库或评测 Harness。

## 3. `verified` 的身份：冻结的是自动过滤子集，不是人工 Verified

当前数据卡列出四个 split：`test=1,000`、`lite=300`、`verified=500`、`full=1,888`，并说明 `lite` 与 `verified` 保持冻结，后续月度新增进入 `full` [2]。这给 `verified` 带来稳定分母，但也意味着它从冻结之日起就不再继续吸收新任务。

名称上最容易发生的错误是把以下两者混淆：

| 数据集 | 来源 | 验证方式 | 本报告是否分析 |
|---|---|---|---|
| SWE-bench-Live `verified` | `SWE-bench-Live/SWE-bench-Live` | LLM 自动质量过滤 | 是 |
| SWE-bench Verified | `SWE-bench/SWE-bench_Verified` | 专家人工验证 | 否 |

NeurIPS camera-ready 附录 F 说明：过滤器看到 issue description、gold patch 和 FAIL_TO_PASS tests，将任务按八类常见质量问题判断，只保留 well-posed、evaluable 实例；文中列出的失败类型包括问题描述含糊或误导、测试约束不足、修复过于 trivial 和环境失败 [1]。作者用 o3 在原 SWE-bench Full 上对人工 Verified 标签做校准，报告 72% precision、40% recall；排除 trivial case 后为 92% precision、35% recall [1]。因此：

- `verified` 比未经该过滤的候选池更强调可判定性；
- 它并不等价于人工逐题审查；
- 较低 recall 表明过滤较保守，不能把未入选任务都解释为错误任务。

还存在一个 paper–artifact 计数差异：camera-ready 正文写 `full=1,890`、223 个仓库 [1]，当前 HF 工件写 `full=1,888` [2]。本报告的下载和统计以冻结 HF artifact 为准，不以论文总数替代。

## 4. 字段模型与任务成功语义

### 4.1 实际 Parquet Schema

本地文件有 18 个顶层字段，可按用途分为五组：

| 用途 | 字段 | 含义 |
|---|---|---|
| 身份与来源 | `repo`, `pull_number`, `instance_id`, `issue_numbers`, `created_at` | 仓库、PR、任务 ID、关联 issue 和时间 |
| 代码基线 | `base_commit`, `commit_url`, `commit_urls` | 待修复仓库状态及关联提交 |
| 问题与辅助线索 | `problem_statement`, `hints_text`, `all_hints_text` | 标准问题陈述以及不同范围的 issue/讨论辅助材料 |
| 参考解与测试 | `patch`, `test_patch`, `test_cmds`, `log_parser` | gold patch、测试修改、执行命令和日志解析器 |
| Oracle 与结构难度 | `FAIL_TO_PASS`, `PASS_TO_PASS`, `difficulty.{files,hunks,lines}` | 目标测试、回归测试和 gold patch 规模 |

数据卡 prose 表格和论文都描述了 `image_key` [1,2]，但数据卡 YAML schema 与本地 Parquet 都没有该字段；实际镜像名由 `instance_id` 和 DockerHub namespace 推导 [4]。因此 Adapter 不应访问不存在的 `row.image_key`。

`difficulty` 是 gold patch 的结构统计，不是人类工时、运行耗时或语义难度标签。数据中也没有 bug type、业务领域或官方任务类别字段；若后续要区分 bug fix、feature、API behavior、documentation 等类别，需要另做有审计记录的标注，不能把关键词归类冒充官方标签。

标准待测输入应限于 `problem_statement` 和 `base_commit` 对应的代码库。`patch`、`test_patch`、FAIL_TO_PASS、PASS_TO_PASS、PR/commit URL 以及两种 hints 字段都属于评测或辅助元数据，不应把 Parquet 整行交给 Agent；尤其 `all_hints_text` 可能含 issue 后续讨论，可能直接泄露修复方向。

### 4.2 成功判据

任务从 `base_commit` 启动，Agent 根据 `problem_statement` 修改仓库。评测应用 `test_patch` 并执行 `test_cmds`：

- `FAIL_TO_PASS` 中的目标测试应由失败转为通过；
- `PASS_TO_PASS` 中原本通过的测试应继续通过；
- 官方主指标是 Resolved Rate，论文还报告 Patch Apply Rate 和文件级 Localization Success Rate [1]。

Gold `patch` 是参考修复和构造/验证依据，不应暴露给待测 Agent。文件级 localization 与 gold patch 重合只是论文的诊断指标，不是要求生成与 gold 完全相同的补丁。

## 5. 本地数据组成

### 5.1 行数、唯一性与完整性

| 指标 | 本地结果 |
|---|---:|
| Parquet 行数 | 500 |
| 唯一 `instance_id` | 499 |
| 重复 ID 数 | 1 |
| 唯一仓库 | 100 |
| 时间范围 | 2024-07-07 至 2025-04-30 |
| `log_parser=pytest` | 500 |

数据卡把 `instance_id` 描述为唯一标识，但 `conan-io__conan-18153` 实际出现两次。两行的 repo、PR、base commit、gold patch 和 test patch 相同，区别在于：

- `test_cmds` 分别为 `pytest -rA` 与 `python -m pytest -rA .`；
- 第二行的 `all_hints_text` 追加了 issue 后续讨论。

这不是逐字段完全重复。它可能使同一真实 PR 被双重加权，也会给以 `instance_id` 为 key 的 prediction/result 序列化造成歧义。复现官方 500-row artifact 时不能静默删行；Astra 自建抽样层则应按唯一 ID 去重，并把排除规则、原始行号和所选变体写入 manifest。正式计分前还需用冻结 Harness 实测它如何处理这两行。

### 5.2 时间分布

| 月份 | 题数 | 月份 | 题数 |
|---|---:|---|---:|
| 2024-07 | 23 | 2024-12 | 45 |
| 2024-08 | 55 | 2025-01 | 62 |
| 2024-09 | 42 | 2025-02 | 57 |
| 2024-10 | 44 | 2025-03 | 68 |
| 2024-11 | 41 | 2025-04 | 63 |

它覆盖连续十个月，但不是严格按月均匀采样：最低月 23 题，最高月 68 题。做模型污染分析时应记录模型训练/知识截止日期，而不是只写“任务创建于 2024 年以后”。

### 5.3 仓库分布

前十个仓库贡献 222/500，即 44.4%；100 个仓库中有 40 个只出现一次。覆盖面比原 SWE-bench 的少数仓库更广，但任务并非对仓库均匀加权。

| 排名 | 仓库 | 题数 | 占比 |
|---:|---|---:|---:|
| 1 | `aws-cloudformation/cfn-lint` | 52 | 10.4% |
| 2 | `pylint-dev/pylint` | 29 | 5.8% |
| 3 | `conan-io/conan` | 29 | 5.8% |
| 4 | `matplotlib/matplotlib` | 26 | 5.2% |
| 5 | `deepset-ai/haystack` | 17 | 3.4% |
| 6 | `reflex-dev/reflex` | 15 | 3.0% |
| 7 | `streamlink/streamlink` | 14 | 2.8% |
| 8 | `pydata/xarray` | 14 | 2.8% |
| 9 | `keras-team/keras` | 13 | 2.6% |
| 10 | `instructlab/instructlab` | 13 | 2.6% |

因此直接对 500 行做 micro-average 会让高频仓库承担更大权重。Astra 的小样本 Pilot 更应“先按仓库分层，再在层内按难度抽样”，避免四题都来自相似代码库。

### 5.4 Gold patch 与测试规模

下表的 `files/hunks/lines` 来自官方 `difficulty`；“diff 行数”则直接数 patch 文本行，包含 diff 上下文，因此两者不能互换。

| 指标 | 均值 | P25 | 中位数 | P75 | P90 | P95 | 最大值 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Gold 修改文件数 | 3.02 | 1 | 2 | 3 | 5 | 8 | 88 |
| Gold hunks | 6.56 | 2 | 3 | 6 | 12 | 20 | 262 |
| Gold 修改行数 | 62.85 | 9 | 21 | 53 | 107 | 204 | 3,131 |
| Gold diff 文本行数 | 126.53 | 28 | 53 | 116 | 225 | 401 | 4,146 |
| Test diff 文本行数 | 91.77 | 29 | 49 | 94 | 173 | 272 | 1,686 |
| FAIL_TO_PASS 数 | 4.27 | 1 | 1 | 3 | 6 | 11 | 397 |
| PASS_TO_PASS 数 | 2,990.79 | 948 | 1,880 | 4,011 | 7,669 | 8,333 | 21,124 |

均值显著高于中位数，且最大值远离 P95，说明 patch 和测试规模都是重尾分布。只按平均“约 3 个文件、63 行”描述典型题会高估中间任务、低估极端任务。首期分层至少应区分：

- 中位附近：约 2 个文件、3 个 hunks、21 行；
- 较长任务：达到或超过 P90，即约 5 个文件或 107 行；
- 极端任务：超过 P95，单独做资源预检，不直接混入普通层。

## 6. 典型实例

下列实例按本地 `difficulty.lines` 的位置选择，用于展示结构跨度，不是官方语义类别，也不代表质量排序。

| 位置 | 实例 | 请求概述 | Gold 结构 | Oracle 规模 |
|---|---|---|---|---|
| 最小 | `bridgecrewio__checkov-6630` | Checkov 未识别挂载到 DMS serverless 的 security group | 1 文件、1 hunk、1 行 | F2P 1，P2P 4,635 |
| 行数中位附近 | `pytorch__torchtune-1806` | 四种 tokenizer 在 `add_eos=False` 时不应添加 EOS | 4 文件、8 hunks、21 行 | F2P 2，P2P 558 |
| P90 附近 | `pylint-dev__pylint-10328` | 只在 boolean context 建议简化 `z != []`，避免赋值语义改变 | 2 文件、7 hunks、107 行 | F2P 3，P2P 1,922 |
| 最大修改行数 | `aiogram__aiogram-1575` | 为 `InaccessibleMessage` 补齐与 `Message` 一致的方法 aliases | 21 文件、22 hunks、3,131 行 | F2P 39，P2P 1,465 |

这些例子也说明结构规模与测试负担不单调：最小一行 gold patch 仍需守住 4,635 个 PASS_TO_PASS；最大修改行数任务的 P2P 反而更少。用 patch 行数单独预测运行成本或 Agent 难度是不充分的。

## 7. 执行与复现要求

### 7.1 代码代际

官方仓库 `main` 已同时面向 MultiLang 和 Windows。其 README 明确建议：若评测本报告所分析的 Python/NIPS 数据，为公平比较应使用旧 `python-only` 分支的方法，尽管新 Harness 声称向后兼容 [3,5]。因此至少要分别冻结：

1. HF 数据 revision 与 Parquet SHA-256；
2. Python-only 或经验证兼容的评测代码 commit；
3. 每题 Docker image 的 immutable digest，而不是只存可变 tag；
4. Agent adapter、预算、超时和 patch 提取方式；
5. 本机 gold replay 后的有效实例清单。

### 7.2 Gold replay 与有效分母

官方评测说明称，任务构造时曾重复运行测试三次，但 Docker 不能保证完全隔离，测试仍会随机器和时间失效；因此建议在实验机器上对 gold patch 再运行三次，并用本机 gold 通过的实例作为实际分母 [4]。

这意味着“下载 500 行”不等于“本机有 500 个可评分任务”。建议资格门槛为：

```text
数据哈希正确
→ 唯一 ID/重复策略确定
→ 镜像 digest 冻结
→ gold patch 在目标机器 3/3 通过
→ 才进入 Agent clean/fault 运行
```

官方文档给出的单实例资源估计是 4 CPU、16 GB RAM，某些大型多语言仓库可高达 50 GB [4]。本 split 全部使用 `pytest` parser，但仍应按实际镜像测量峰值内存和运行时，不能从 parser 一致性推断成本一致。

## 8. 许可证、污染与安全边界

HF 数据卡与 Microsoft 代码仓库标为 MIT [2,3]，论文的仓库筛选也只保留带有效开源许可证的上游项目 [1]。但每条任务仍嵌入第三方 issue、讨论、patch 和测试内容；“数据卡标为 MIT”不应被扩大解释为所有上游内容都被统一重新授权。再分发或商用时仍应保留来源，并抽查所选任务的上游许可证。

SWE-bench-Live 的“live”机制能降低发布当时的陈旧性风险，但本报告分析的 `verified` 已被冻结且公开。到 2026-07，它更准确的定位是“相对较新的公开固定集”，而不是能证明零污染的实时隐藏集。模型在公开后训练、微调或通过轨迹接触这些任务的可能性不能排除；报告分数时应同时披露模型版本、训练/知识截止日期和运行日期。

容器也不是强安全边界。执行第三方仓库测试和 Agent 生成代码时，应在隔离宿主机或受控 runner 中运行，限制网络、凭据、挂载和资源。这个要求来自执行不可信代码的一般风险，不能由 Docker 镜像存在本身替代。

## 9. 对 Astra 的适用性

| 构念 | 覆盖 | 原因 |
|---|---|---|
| 真实仓库 issue 理解与修复 | 强 | 输入、代码基线、测试和 gold patch 均来自真实 PR |
| 多文件浏览、编辑和测试 | 强 | 结构跨度大，执行式 Oracle 可验证 |
| 回归控制 | 强 | 同时检查 FAIL_TO_PASS 与 PASS_TO_PASS |
| 长上下文/工具链 | 中 | 仓库任务天然需要多步操作，但没有统一交互轨迹 |
| Crash 后恢复、Checkpoint | 弱 | 原始 benchmark 不主动制造中断 |
| 状态所有权、审批和权限 | 弱 | 最终测试成功不验证基础设施治理 |
| 持续无污染 | 弱到中 | issue 较新，但 `verified` 已公开冻结 |

建议的 Astra 首期流程：

1. 原始 Parquet 保持只读，不改写为“清洗版官方数据”；
2. 候选池按唯一 `instance_id` 建索引，对重复项显式排除或只保留经 Harness 验证的一行；
3. 每个仓库最多抽一题，避免仓库权重集中；
4. 按 gold `files/hunks/lines` 与 P2P 数双轴分层，而不是只用修改行数；
5. 候选题先完成镜像 digest 冻结和 gold 3/3；
6. Clean 运行保留官方任务、工具语义和 Oracle；
7. 若加入进程中断、结果丢失或容器重启，标为 **MOI-derived fault case**，不得作为官方 SWE-bench-Live 分数；
8. 官方 task success 与 Astra 的恢复/审计指标并列报告，不互相替代。

不建议现在直接固定四个具体 Pilot 实例。上表中的典型题只是静态候选；在镜像可取性、运行时间、gold 3/3 和三个产品 Adapter 等价性验证前选题，会把环境可用性误当成任务难度。

## 10. 尚未关闭的阻塞项

- 未冻结 Python `python-only` Harness 的具体 commit；
- 未拉取实例 Docker 镜像，也未记录 image digest；
- 未对 499 个唯一 ID 或候选子集执行 gold patch 3/3；
- 重复 `conan-io__conan-18153` 在官方 Harness 中的实际处理尚未回放；
- 未完成所选任务的上游许可证逐题审查；
- 未建立 Astra、Hermes、Goose 的等价 patch 提取、超时和资源预算；
- 未验证 fault injection 不会改变原始 Oracle 的任务语义。

## 11. 结论

**RQ1：** 已冻结的数据工件是官方 HF 仓库的 Python `verified` split，revision 为 `a637bd4…`，Parquet 为 24,696,977 bytes，SHA-256 已与官方值一致。它不是原 SWE-bench Verified。

**RQ2：** 文件有 500 行、499 个唯一 ID、100 个仓库和 18 个真实字段。时间覆盖 2024-07 至 2025-04，仓库与结构难度都呈明显不均衡和重尾分布；前十仓库占 44.4%，gold 修改行数中位数为 21、P90 为 107、最大值为 3,131。

**RQ3：** 它适合测真实 Python 仓库的 issue 修复、代码操作和回归控制，但只下载 Parquet 不能得到可运行 benchmark。正式 Astra 实验必须继续冻结 Harness 和镜像、处理重复 ID、完成 gold 3/3，并把任何故障注入结果标为 MOI-derived。

本报告的核心判断是：**`verified` 在“固定、真实、可执行的软件修复结果层”上价值很高，但其自动过滤、公开冻结、重复 ID 和环境漂移意味着它不是开箱即用的无污染金标准。**

## References

[1] Linghao Zhang, Shilin He, Chaoyun Zhang, et al., “[SWE-bench Goes Live!](https://papers.nips.cc/paper_files/paper/2025/hash/d83c4a745789690f82e86d0ef752ae7c-Abstract-Datasets_and_Benchmarks_Track.html),” NeurIPS 2025 Datasets and Benchmarks Track, 2025.

[2] SWE-bench-Live Team, “[SWE-bench-Live Dataset Card](https://huggingface.co/datasets/SWE-bench-Live/SWE-bench-Live/blob/a637bd46829f3132e12938c8a0ca93173a977b8e/README.md),” Hugging Face dataset repository, revision `a637bd46829f3132e12938c8a0ca93173a977b8e`.

[3] Microsoft, “[SWE-bench-Live Official Repository](https://github.com/microsoft/SWE-bench-Live),” GitHub.

[4] Microsoft, “[SWE-bench-Live Evaluation Guide](https://github.com/microsoft/SWE-bench-Live/blob/main/evaluation/README.md),” GitHub.

[5] Microsoft, “[SWE-bench-Live Python-only Branch](https://github.com/microsoft/SWE-bench-Live/tree/python-only),” GitHub.
