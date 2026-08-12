# Memoria 公开记忆基准最终综合评测报告

> 更新日期：2026-08-12  
> 评测范围：LongMemEval-S、LoCoMo；Mem0 协议对标、Zep 模型对标  
> 实验状态：四项实验均完成，所有 Reader/Judge 题目均有最终成功记录

## 1. 报告范围与核心结果

本报告只整理当前保留的四项最终实验，不纳入早期 Prompt 调试、失败版本、旧 Memoria 版本检索排查或中间消融结果。

| 数据集 | 对标对象 | Memoria 本地实验 | Reader / Judge | 检索 | 竞品公开结果 | 差值 |
| --- | --- | ---: | --- | --- | ---: | ---: |
| LongMemEval-S | Mem0 | **457/500（91.40%）** | GPT-5 / GPT-5 | Memoria Top-20 | Mem0 OSS GPT-5 Extraction 91.0% | +0.40pp |
| LongMemEval-S | Zep | **459/500（91.80%）** | GPT-5.4 medium / GPT-5.4 medium | Memoria Top-20 | Zep 451/500（90.20%） | +1.60pp |
| LoCoMo | Mem0 | **1,354/1,540（87.92%）** | GPT-5 / GPT-5 | Memoria Top-200 | Mem0 Platform v3 Top-200：README 92.5%；artifact 91.56% | -4.58pp / -3.64pp |
| LoCoMo | Zep | **1,393/1,540（90.45%）** | GPT-5.4 medium / GPT-5.4 medium | Memoria Top-200 | Zep 1,459/1,540（94.70%） | -4.25pp |

上表中的“对标”含义不完全相同：

- **Mem0 对标**：对齐 Mem0 公开的 Reader/Judge 模型、Prompt、答案清理和 Judge 规则；Memory 构建、Embedding 和检索后端仍是 Memoria。
- **Zep 对标**：对齐 Zep 官网公布的 GPT-5.4 Reader/Judge 模型配置；Zep 未公开当前实验的完整 Prompt，因此两项 Zep 模型对标实验均使用对应数据集的 Mem0 公开 Prompt 作为可审计代理。

因此，本地分数与竞品分数只是公开参照，不是只剩 memory backend 不同的严格排名。

## 2. 数据集说明

### 2.1 LongMemEval-S

LongMemEval-S 由 500 个长期会话记忆问答实例组成，每个实例包含目标会话、干扰会话、问题和参考答案。

| 官方题型 | 题数 |
| --- | ---: |
| Single-Session User | 70 |
| Single-Session Assistant | 56 |
| Single-Session Preference | 30 |
| Knowledge Update | 78 |
| Temporal Reasoning | 133 |
| Multi-Session | 133 |
| **合计** | **500** |

30 道 `_abs` 题是 Abstention 交叉子集，不是第七个互斥题型。六类成绩覆盖全部 500 题；Abstention 另外报告，不重复加入 Overall 分母。

| 项目 | 固定值 |
| --- | --- |
| 数据文件 | `longmemeval_oracle.json` |
| SHA-256 | `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c` |
| QA 数 | 500 |
| 检索证据指标分母 | 470 道非 Abstention 题 |
| 用户隔离 | 每个 `question_id` 对应一个独立 Memoria 用户 |

### 2.2 LoCoMo

LoCoMo 包含 10 组多会话样本、272 个 session、5,882 条 dialogue turn 和 1,986 道 QA。本轮依照 Mem0/Zep 公开口径只评估 Category 1–4，排除 446 道 Category 5 adversarial 题。

| Category | 类型 | 题数 |
| --- | --- | ---: |
| 1 | Multi-hop | 282 |
| 2 | Temporal | 321 |
| 3 | Open-domain | 96 |
| 4 | Single-hop | 841 |
| **合计** |  | **1,540** |

| 项目 | 固定值 |
| --- | --- |
| 数据文件 | `locomo10.json` |
| SHA-256 | `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4` |
| Sample / Session / Turn | 10 / 272 / 5,882 |
| 本次 QA | Category 1–4，1,540 |
| 有可用 evidence 标注 | 1,536 |
| 无 evidence 标注 | 4，均属于 Open-domain |
| 用户隔离 | 每个 sample 对应一个独立 Memoria 用户 |

## 3. Memoria 版本与 Memory 构建

### 3.1 共同版本基线

| 项目 | 值 |
| --- | --- |
| 仓库 | `matrixorigin/Memoria` |
| 版本 | `0.4.0` |
| 基础 commit | [`54c9114fd6888e11821edc2ee9acd570c17c5ee3`](https://github.com/matrixorigin/Memoria/commit/54c9114fd6888e11821edc2ee9acd570c17c5ee3) |
| Commit 时间 | 2026-08-03 14:55:10 +08:00 |
| Commit 标题 | `feat: support extra metadata in batch write (#223)` |
| API | 本地 Memoria `http://127.0.0.1:8100` |
| 存储 | 独立 MatrixOne 运行时 |

两个数据集均采用 **Controlled Track**：评测数据直接写入 semantic memory，不经 `/v1/observe` 的 Memoria 原生 LLM 信息抽取。该设计用于固定写入内容，将本轮测试聚焦在 Memoria 存储/检索与下游 Reader/Judge 的组合效果；不代表 Memoria Native Extraction 轨道。

### 3.2 LongMemEval-S 写入与检索

| 环节 | 配置 |
| --- | --- |
| 写入接口 | `POST /v1/memories` |
| Memory type | `semantic` |
| 内容粒度 | 原始 session；超限时按 turn/段落/句子确定性切分 |
| 单块上限 | 30 KiB / 7,000 tokens |
| 时间 | 保留原始相对时间间隔，映射到 `observed_at` |
| Embedding | `bge-m3`，1,024 维 |
| Query | 原始问题，不改写 |
| Retrieval | `/v1/memories/retrieve`，`hybrid`，Top-20 |
| 检索完整性 | 500/500，跨题污染 0 |
| Snapshot SHA-256 | `fe6f179d8cd21cf71a204ebfaf4c62fff7db5ae434a61b69a3c9fdff334a1434` |

**Embedding 选型说明。** LongMemEval-S 建库沿用 Memoria commit `54c9114fd6888e11821edc2ee9acd570c17c5ee3` 官方 Compose 的默认配置 `BAAI/bge-m3` / 1,024 维；同版本 CLI 初始化向导将该组合标为 `recommended`。该选择代表采用 Memoria 当时的默认/推荐配置，不是为了对齐 Mem0 或 Zep。向量、维度和索引 schema 在建库后固定，两个 LongMemEval Reader/Judge 主实验均复用同一冻结检索快照；更换 Embedding 必须重新建库，并应作为独立检索实验而非直接并入当前结果。

Top-20 检索质量（非 Abstention 470 题）：

| Hit@20 | Mean Evidence Recall@20 | Complete Recall@20 | MRR |
| ---: | ---: | ---: | ---: |
| 99.57% | 97.34% | 94.04%（442/470） | 76.07% |

### 3.3 LoCoMo Raw Turn 写入与检索

| 环节 | 配置 |
| --- | --- |
| 写入接口 | `POST /v1/memories` |
| Memory type | `semantic` |
| 内容粒度 | 一条 dialogue turn 作为一条 memory |
| 实际 memory | 5,882/5,882，失败 0 |
| Native extraction | 关闭，`internal_llm=false` |
| 排除写入 | QA、observation、session summary、event summary |
| 时间 | `relative_shift_per_sample_v1`；Reader 通过 `dia_id` 回连原始 session 日期 |
| Embedding | DashScope `text-embedding-v4`，1,024 维 |
| Query | 原始问题，不改写 |
| Retrieval | `/v1/memories/retrieve`，`hybrid`，Top-200 |
| 检索完整性 | 1,540/1,540，每题 200 条，跨用户/重复 ID 为 0 |
| Snapshot SHA-256 | `b1d561df1a783d73d195a235b2f687cc88bb30ed477ac08f25c6c22994c2910c` |

LoCoMo 为支持公开 benchmark 运行使用了两项局部调整：

1. 对公开合成数据设置 `MEMORIA_SENSITIVITY_FILTER_ENABLED=false`，避免原始 turn 被改写；
2. API `retrieve/search` Top-K 上限从 100 调整为 200，没有改动混合评分公式。

Top-200 检索质量（有 evidence 的 1,536 题）：

| Hit@200 | Mean Evidence Recall@200 | Complete Recall@200 | MRR@200 |
| ---: | ---: | ---: | ---: |
| 87.57% | 81.62% | 75.00% | 0.057744 |

## 4. 四项实验配置

同一数据集的两项实验共用同一份冻结检索快照和同一套 Mem0 Prompt，不重新写入或检索。

| 编号 | 数据集 / 定位 | Reader | Judge | API / Reasoning | Context | Prompt |
| --- | --- | --- | --- | --- | --- | --- |
| LME-Mem0 | LongMemEval-S / Mem0 协议对标 | `gpt-5` | `gpt-5` | Chat Completions；不显式设 reasoning | Top-20 | Mem0 LongMemEval Reader + Unified Judge |
| LME-Zep | LongMemEval-S / Zep 模型对标 | `gpt-5.4` | `gpt-5.4` | Responses API；两者 `medium` | Top-20 | 同上，作为 Zep 未公开 Prompt 的代理 |
| LOC-Mem0 | LoCoMo / Mem0 协议对标 | `gpt-5` | `gpt-5` | Chat Completions；不显式设 reasoning | Top-200 | Mem0 LoCoMo Reader + Unified Judge |
| LOC-Zep | LoCoMo / Zep 模型对标 | `gpt-5.4` | `gpt-5.4` | Responses API；两者 `medium` | Top-200 | 同上，作为 Zep 未公开 Prompt 的代理 |

详细 API 配置：

| 项目 | GPT-5 两项实验 | GPT-5.4 两项实验 |
| --- | --- | --- |
| Provider | AIHubMix OpenAI-compatible | AIHubMix OpenAI-compatible |
| 请求模型 | `gpt-5` | `gpt-5.4` |
| 实际返回 | `gpt-5-2025-08-07` | 主要为 `gpt-54`；LongMemEval Reader 有10 次返回 `gpt-5.4` |
| API style | Chat Completions | Responses API |
| Reasoning effort | 不传参 | `medium` |
| Temperature | 不传参 | 不传参 |
| Max output/completion | 4,096 | 4,096 |
| 失败口径 | 缺失记录留在全量分母并计错；支持断点续跑 | 同左 |

四项实验最终均已补齐所有历史 API 失败；正式分数均使用每个 question ID 的最新成功 Reader/Judge 记录计算。

## 5. Prompt 来源与内容

### 5.1 来源与版本冻结

四项实验的 Prompt 都来自 Mem0 官方 `memory-benchmarks` 固定 commit：

- Commit：[`4b61c5d31b9c668a12b4f5e78064248a02c82d2b`](https://github.com/mem0ai/memory-benchmarks/commit/4b61c5d31b9c668a12b4f5e78064248a02c82d2b)
- LongMemEval Prompt：[`benchmarks/longmemeval/prompts.py`](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/benchmarks/longmemeval/prompts.py)
- LoCoMo Prompt：[`benchmarks/locomo/prompts.py`](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/benchmarks/locomo/prompts.py)

本地权威副本与哈希：

| 数据集 | Prompt | SHA-256 | 本地全文 |
| --- | --- | --- | --- |
| LongMemEval-S | Reader | `59f155c1c77e3000c6c75494232f669357f77a352d5ac5042decbacea230eebf` | [`mem0_prompts.py`](../scripts/longmemeval/mem0_prompts.py) |
| LongMemEval-S | Judge | `c4dc2f6e34e92f9958b62222a0ed520b3ce80dede68bba164dc7961c27dae515` | 同上 |
| LoCoMo | Reader | `79c9f09bcc8d5e9e8b7e9786af587b02a67d366ab79285fc148b73fd20f6297b` | [`mem0_prompts.py`](../scripts/locomo/mem0_prompts.py) |
| LoCoMo | Judge system | `36c007917faf1ab84516cdca577fb523711a9b993706fbae8ae37806e6f9adcc` | 同上 |
| LoCoMo | Judge user（without evidence） | `d248e056d993725e28fba8d16ca7081f0b59deae272ef294f3c6b00d48eac02b` | 同上 |

综合报告不再维护一份几百行的 Prompt 文本副本，以上固定 commit、哈希和本地源码是逐字复现依据。下文完整列出实际影响评分的 Prompt 内容和输出契约。

### 5.2 LongMemEval-S Reader Prompt 内容

Reader 被设定为可访问用户历史记忆的个人助理，核心行为如下：

1. 使用问题日期计算所有相对时间；
2. 优先遵循用户明确偏好和反偏好；
3. 数据已存在时必须进行年龄、价格、日期间隔和计数计算；
4. 核对问题中的精确实体、职位、商品变体和场景，不将相似但不同的实体混合；
5. 对计数题枚举全部项目并二次扫描，对跨主题问题分别寻找每个所需事实；
6. 冲突时优先更新的记忆，但区分不同人物、不同场景和历史事件；
7. 优先使用用户陈述的个人事实，不把 Assistant 的建议当成用户已发生的经历；
8. 只有主题真正未出现、特定事件不存在、实体错配或比较项不完整时，才输出 `The information provided is not enough`；
9. 在 `<mem_thinking>...</mem_thinking>` 中生成推理，用户答案取标签外且最后一个 `ANSWER:` 之后的内容。

Reader 的输入结构为：

```text
Memories (..., grouped by date):
{memories}

Today's Date: {question_date}
Question: {question}

<mem_thinking>...</mem_thinking>
ANSWER: {final_answer}
```

运行器先取检索排名 Top-20，再按原始 session 日期从早到晚稳定排序。为保持与固定 Mem0 源文本哈希一致，Prompt 模板中仍保留 `sorted newest-first` 的字样；实际传入顺序以运行器和逐题 `reader_prompts.jsonl` 为准。

### 5.3 LongMemEval-S Judge Prompt 内容

LongMemEval 使用一套统一 Mem0 Judge Prompt，最终只输出 `yes` 或 `no`。关键规则为：

- 按语义等价而非字面一致判分，并明确要求“不要过早判 no，疑似等价时倾向 yes”；
- 允许包含参考答案的超集答案和额外细节，除非额外内容已被证明错误；
- 列表项可以使用同义词、子概念或相关表述覆盖；
- 允许约数、范围、单位换算和日/周/月的小范围误差；
- 偏好题以是否表现对用户核心个人背景和主要偏好的理解为主，不将 rubric 当作逐项检查表；
- Abstention gold 下，任何表达“缺少信息/无法回答”的拒答都可判正确；
- 先在 `<judge_thinking>...</judge_thinking>` 中推理，然后在新行给出精确的 `yes` 或 `no`。

### 5.4 LoCoMo Reader Prompt 内容

LoCoMo Reader 将任务拆成严格的 7 个步骤：

1. **SCAN ALL MEMORIES**：从头到尾扫描所有 Top-200 memory，不因检索位置靠后而降权；
2. **ENTITY VERIFICATION**：确认事实归属的人物/实体，避免两个说话者混淆；
3. **COMBINE AND CROSS-REFERENCE**：合并分散在不同 memory 的事实，列表/计数题先枚举再计算；
4. **SELECT THE BEST ANSWER**：按对问题的直接性和具体程度选答案，不默认最高检索分就是最佳证据；
5. **TEMPORAL GROUNDING**：以 LoCoMo sample 的原始 reference date 做时间推理，不使用当前真实日期；
6. **INCLUSION CHECK**：列表和计数题再次检查遗漏、重复和过度排除；
7. **COMMIT AND ANSWER**：给出直接、具体的最佳答案，并在 `ANSWER:` 后输出最终文本。

Reader 输入先取检索排名 Top-200，再按原始 session 时间从旧到新排序，不向 Reader 显示排名或检索分数。最终契约为：

```text
The following memories are presented in chronological order (oldest to newest).

({memory_date}) {memory}
...

Question: {question}

Work through Steps 1-7, then give your final answer after "ANSWER:".
```

### 5.5 LoCoMo Judge Prompt 内容

Judge system prompt 原文：

```text
You are evaluating conversational AI memory recall. Return JSON only with the format requested.
```

Judge user prompt 的关键评分规则是：

- gold 列表中至少一项正确即给 partial credit；
- 接受语义等价改写、同类情感和额外细节；
- 日期误差在 ±14 天内接受，时长误差在 50% 内接受；
- 接受 semantic overlap 和 same referent；
- 只有完全没有命中 gold 中的任何正确项，或回答了完全不同的主题时，才判 `WRONG`；
- 输出一句 `reasoning` 和 `CORRECT/WRONG` label 的 JSON。

Judge evidence 关闭；Category 3 gold 按 Mem0 runner 规则只使用分号前的第一部分。这套 Judge 明显允许 partial credit 和较大时间容差，所以 LoCoMo 分数只应与相同 Judge 协议的结果比较。

## 6. LongMemEval-S 结果

### 6.1 Memoria 两项最终实验

| 官方题型 | LME-Mem0：GPT-5 | LME-Zep：GPT-5.4 medium | 变化 |
| --- | ---: | ---: | ---: |
| Single-Session User | 69/70（98.57%） | 69/70（98.57%） | 0.00pp |
| Single-Session Assistant | 56/56（100.00%） | 56/56（100.00%） | 0.00pp |
| Single-Session Preference | 25/30（83.33%） | 27/30（90.00%） | +6.67pp |
| Knowledge Update | 71/78（91.03%） | 72/78（92.31%） | +1.28pp |
| Temporal Reasoning | 129/133（96.99%） | 126/133（94.74%） | -2.25pp |
| Multi-Session | 107/133（80.45%） | 109/133（81.95%） | +1.50pp |
| **Overall** | **457/500（91.40%）** | **459/500（91.80%）** | **+0.40pp** |
| **六类宏平均** | **91.73%** | **92.93%** | **+1.20pp** |
| Abstention（交叉子集） | 29/30（96.67%） | 29/30（96.67%） | 0.00pp |

两项实验使用相同的数据、Top-20 检索快照、Reader Prompt 和 Judge Prompt。GPT-5.4 medium 组合仅净增 2 道正确题；22 道题发生标签翻转，其中 12 道由错变对、10 道由对变错。因此 +0.40pp 是小幅数值提升，不足以证明稳定的模型优势。

### 6.2 证据完整度与 QA

| Top-20 evidence 状态 | LME-Mem0 | LME-Zep |
| --- | ---: | ---: |
| Complete（442 题） | 419/442（94.80%） | 422/442（95.48%） |
| Incomplete（28 题） | 9/28（32.14%） | 8/28（28.57%） |
| 非 Abstention Overall | 428/470（91.06%） | 430/470（91.49%） |

GPT-5.4 medium 实验的 40 道非 Abstention 错题中，20 道在 Top-20 中已有完整证据，20 道证据不完整。`multi-session` 仍是最低分题型。

### 6.3 与 Mem0 公开结果对比

Mem0 在固定 commit 的 README 中公布：

| 系统 / 版本 | LongMemEval-S | 已知主要配置 |
| --- | ---: | --- |
| Mem0 Platform v3 Top-50 | 474/500（94.8%） | 托管 v3 pipeline；Top-50 |
| Mem0 Platform v3 Top-200 | 472/500（94.4%） | 托管 v3 pipeline；Top-200 |
| Mem0 OSS + GPT-5 Extraction | 91.0% | GPT-5 extraction/Reader/Judge；Qwen 600M Embedding；Qdrant |
| **Memoria LME-Mem0** | **457/500（91.40%）** | Memoria Top-20；GPT-5 Reader/Judge；Mem0 Prompt |

Memoria LME-Mem0 比 Mem0 OSS 公开的 91.0% 高 0.40pp，比 Platform v3 Top-50 低 3.40pp。该对比不严格：Mem0 OSS 使用信息抽取后的短记忆，Memoria 使用语义长块；Embedding、Top-K、Memory 表示和检索后端也不同。

### 6.4 与 Zep 公开结果对比

| 官方题型 | Memoria LME-Zep | Zep 官网 | 差值 |
| --- | ---: | ---: | ---: |
| Single-Session User | 98.57% | 94.3% | +4.27pp |
| Single-Session Assistant | 100.00% | 96.4% | +3.60pp |
| Single-Session Preference | 90.00% | 90.0% | 0.00pp |
| Knowledge Update | 92.31% | 93.6% | -1.29pp |
| Temporal Reasoning | 94.74% | 90.2% | +4.54pp |
| Multi-Session | 81.95% | 83.5% | -1.55pp |
| **Overall** | **459/500（91.80%）** | **451/500（90.20%）** | **+1.60pp** |

Zep 公布的 LongMemEval 配置是 GPT-5.4 Reader（`reasoning=medium`）、GPT-5.4 CoT Judge，以及 20 edges + 10 nodes + 10 episodes + 5 thread summaries + 5 observations 的五路 multi-scope retrieval 和 cross-encoder reranking；中位上下文 4,408 tokens。

Memoria LME-Zep 数值上高 1.60pp，但 Prompt、Memory 表示、检索、重排和上下文规模没有对齐，不能表述为严格超过 Zep。

## 7. LoCoMo 结果

### 7.1 Memoria 两项最终实验

| Category | LOC-Mem0：GPT-5 | LOC-Zep：GPT-5.4 medium | 变化 |
| --- | ---: | ---: | ---: |
| Multi-hop | 246/282（87.23%） | 253/282（89.72%） | +2.48pp |
| Temporal | 291/321（90.65%） | 298/321（92.83%） | +2.18pp |
| Open-domain | 69/96（71.88%） | 72/96（75.00%） | +3.13pp |
| Single-hop | 748/841（88.94%） | 770/841（91.56%） | +2.62pp |
| **Overall** | **1,354/1,540（87.92%）** | **1,393/1,540（90.45%）** | **+2.53pp** |

两项实验的 dataset、Raw Turn memory、Top-200 snapshot、Reader/Judge Prompt、memory 时间排序、reference date 和评分规则一致。GPT-5.4 medium 在四个类别上均提升，净增 39 道正确题。但 GPT-5 实验使用 Chat Completions 且未显式设置 reasoning，GPT-5.4 使用 Responses API + `medium`，不应将全部 2.53pp 强行归因于基础模型本身。

### 7.2 证据状态与 QA

| Top-200 evidence 状态 | LOC-Mem0 | LOC-Zep |
| --- | ---: | ---: |
| Complete（1,152 题） | 1,094/1,152（94.97%） | 1,112/1,152（96.53%） |
| Partial（193 题） | 164/193（84.97%） | 170/193（88.08%） |
| Missing（191 题） | 92/191（48.17%） | 107/191（56.02%） |
| No evidence annotation（4 题） | 4/4（100.00%） | 4/4（100.00%） |

LOC-Zep 的 147 道错题中，107 道发生在 evidence partial/missing 状态，占 72.79%。在 evidence complete 时仍有 40 道题判错，说明检索完整度是主要限制，Reader 推理和 Judge/标注边界也仍有误差。Missing 状态的高 QA 可能来自重复表述、非标注但等价的 turn、模型先验或宽松 Judge，不能用 QA 代替 evidence recall。

### 7.3 与 Mem0 公开结果对比

Mem0 固定 commit 中的 README 和逐题 artifact 存在内部不一致：

| 来源 | Mem0 Platform v3 Top-200 | Memoria LOC-Mem0 | 差值 |
| --- | ---: | ---: | ---: |
| [README 官方标称](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/README.md#locomo) | 1,425/1,540（92.50%） | 1,354/1,540（87.92%） | -4.58pp |
| [逐题 artifact](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/results/platform/locomo_results.json) 可复算值 | 1,410/1,540（91.56%） | 1,354/1,540（87.92%） | -3.64pp |

`locomo_results.json` 的 `metrics_by_cutoff` 和 1,540 条唯一 evaluation 逐题求和都是 1,410，README 则写 1,425。综合报告保留两个值：92.5% 是官方标称，91.56% 是当前公开逐题产物的可复算值。

### 7.4 与 Zep 公开结果对比

| 系统 | 正确 | Accuracy | 差值 |
| --- | ---: | ---: | ---: |
| **Memoria LOC-Zep** | **1,393/1,540** | **90.45%** | — |
| Zep 官网 | 1,459/1,540 | 94.70% | Memoria -4.25pp |

Zep 公布的 LoCoMo 配置是 GPT-5.4 Reader（`reasoning=medium`）、GPT-5.4 CoT Judge、五路 multi-scope retrieval 和 cross-encoder reranking，中位上下文 5,760 tokens。Memoria LOC-Zep 使用 Raw Turn Top-200，Reader 平均输入约 16.9K tokens。两者的 Memory 构建、时间处理、Embedding、检索、Prompt 和 Judge 都没有完全对齐。

Zep 官网的 LoCoMo 分类数字还存在内部不一致：页面分类正确数合计为 1,436，分类题数合计为 1,539，但 Overall 是 1,459/1,540。因此本报告只使用 Zep 官网 Overall，不生成 LoCoMo 分类差值。

## 8. 竞品版本、配置与数据来源

### 8.1 Mem0

| 项目 | 本报告口径 |
| --- | --- |
| 代码/产物 | `mem0ai/memory-benchmarks` + Mem0 Platform v3 / Mem0 OSS |
| 固定 commit | `4b61c5d31b9c668a12b4f5e78064248a02c82d2b` |
| LongMemEval Platform | Top-50 94.8%；Top-200 94.4% |
| LongMemEval OSS | GPT-5 Extraction 91.0% |
| LoCoMo Platform | Top-200 README 92.5%；逐题 artifact 91.56% |
| 检索公开描述 | semantic similarity + BM25 + entity boost |
| 完整性边界 | Platform v3 的 extraction、Embedding、托管检索细节和返回模型 snapshot 未形成完整公开 manifest |

来源：

- [Mem0 memory-benchmarks README（固定 commit）](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/README.md)
- [Mem0 LoCoMo 逐题 artifact](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/results/platform/locomo_results.json)
- [Mem0 LongMemEval Platform Top-50 artifact](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/results/platform/longmemeval_top50_results.json)
- [Mem0 OSS 结果目录](https://github.com/mem0ai/memory-benchmarks/tree/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/results/oss)

### 8.2 Zep

| 项目 | 官网当前公开口径 |
| --- | --- |
| 版本 | 官网未公布可对应的产品版本号或 commit |
| Reader | `gpt-5.4`，`reasoning=medium` |
| Judge | `gpt-5.4`，chain-of-thought grading |
| Retrieval | 20 edges + 10 nodes + 10 episodes + 5 thread summaries + 5 observations |
| Reranking | Cross-encoder，型号未公开 |
| LongMemEval | 451/500（90.2%）；p50/p95 104/162 ms；中位上下文 4,408 tokens |
| LoCoMo | 1,459/1,540（94.7%）；p50/p95 87/155 ms；中位上下文 5,760 tokens |
| 未公开 | 完整 Reader/Judge Prompt、评分容差、图构建/抽取模型、Embedding、Cross-encoder 型号、逐题产物 |

来源：[Zep Research](https://www.getzep.com/research/)，本报告于 2026-08-12 重新复核。

## 9. 结论与报告边界

1. **LongMemEval-S 最高本地结果是 91.80%。** 该结果使用 Memoria Top-20、GPT-5.4 medium Reader/Judge 和 Mem0 Prompt，数值高于 Zep 官网 90.2%，但不是严格同协议对比。
2. **LoCoMo 最高本地结果是 90.45%。** 该结果使用 Raw Turn Top-200、GPT-5.4 medium Reader/Judge 和 Mem0 Prompt，低于 Zep 官网 94.7% 和 Mem0 Platform v3 公开结果。
3. **GPT-5.4 medium 在 LoCoMo 上的增益更明显。** 在同 Prompt/同检索下，LongMemEval-S 仅提升 0.40pp，LoCoMo 提升 2.53pp。但 API style 和 reasoning 配置也一同改变，不应解释为纯基础模型效应。
4. **LoCoMo 的首要限制仍是 evidence completeness。** Top-200 Complete Recall 只有 75.00%；GPT-5.4 实验 147 道错题中 107 道位于 partial/missing 状态。
5. **LongMemEval-S 已经同时触及检索与下游上限。** Top-20 Complete Recall 为 94.04%；GPT-5.4 在完整证据题上为 95.48%，但仍有 20 道完整证据题被判错。
6. **分数高度依赖 Judge 协议。** 四项实验都使用 Mem0 的宽松语义判定规则；LoCoMo 还允许 partial credit、±14 天日期容差和 50% 时长容差。不能将本报告分数与使用更严格 Judge 的结果无条件混用。
7. **竞品结果是公开参照，不是统一受控实验。** Memory Extraction、Memory 表示、Embedding、Top-K、检索、reranker、Prompt、Provider 和 Judge 都可能不同，分差不能直接归因于 Memoria、Mem0 或 Zep 的 memory backend。

## 10. 详细报告与可复现产物

### 10.1 四份最终实验报告

- [LongMemEval-S 对标 Mem0](longmemeval-s-mem0-aligned-gpt5-top20-result.md)
- [LongMemEval-S 对标 Zep 模型](longmemeval-s-zep-model-aligned-gpt54-top20-result.md)
- [LoCoMo 对标 Mem0](locomo-memoria-raw-turn-mem0-compatible-result.md)
- [LoCoMo 对标 Zep 模型](locomo-memoria-raw-turn-zep-aligned-result.md)

### 10.2 结果目录

```text
memoria/runs/longmemeval-s-mem0-protocol-gpt5-top20-full500-v1/
memoria/runs/longmemeval-s-zep-aligned-gpt54-top20-full500-v1/
memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/evaluation/mem0-compatible-gpt5-reader-judge-top200-aihubmix-full1540-v1/
memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/evaluation/zep-model-aligned-gpt54-medium-mem0-prompt-top200-aihubmix-full1540-v1/
```

每个目录保留 `manifest.json`、Reader 答案、Judge 结果、指标、检查点和失败/恢复审计记录。检索快照另外以 SHA-256 冻结，后续重跑 Reader/Judge 时不需要重新导入或检索。

### 10.3 四项实验与当前复现脚本

| 实验 | 正式入口 | 核心评测器 | Prompt |
| --- | --- | --- | --- |
| LongMemEval-S 对标 Mem0 | [`run_mem0_protocol_top20.sh`](../scripts/longmemeval/run_mem0_protocol_top20.sh) | [`evaluate_mem0_protocol.py`](../scripts/longmemeval/evaluate_mem0_protocol.py) | [`mem0_prompts.py`](../scripts/longmemeval/mem0_prompts.py) |
| LongMemEval-S 对标 Zep 模型 | [`run_zep_aligned_top20.sh`](../scripts/longmemeval/run_zep_aligned_top20.sh) | [`evaluate_mem0_protocol.py`](../scripts/longmemeval/evaluate_mem0_protocol.py) | [`mem0_prompts.py`](../scripts/longmemeval/mem0_prompts.py) |
| LoCoMo 对标 Mem0 | [`run_top200_qa_judge.sh`](../scripts/locomo/run_top200_qa_judge.sh) | [`evaluate_top200.py`](../scripts/locomo/evaluate_top200.py) | [`mem0_prompts.py`](../scripts/locomo/mem0_prompts.py) |
| LoCoMo 对标 Zep 模型 | [`run_zep_model_top200_qa_judge.sh`](../scripts/locomo/run_zep_model_top200_qa_judge.sh) | [`evaluate_zep_model_top200.py`](../scripts/locomo/evaluate_zep_model_top200.py) | [`mem0_prompts.py`](../scripts/locomo/mem0_prompts.py) |

四个入口默认复用各自冻结的 retrieval snapshot。完整的数据导入、检索和
Memoria 补丁说明见 [`scripts/locomo/README.md`](../scripts/locomo/README.md)、
[`scripts/longmemeval/RETRIEVAL_RUNBOOK.md`](../scripts/longmemeval/RETRIEVAL_RUNBOOK.md)
以及 [`REPRODUCIBILITY_INVENTORY.md`](../scripts/REPRODUCIBILITY_INVENTORY.md)。

历史 Luna、Opus、Oracle、Memoria 版本排查和旧 Zep Prompt adapter 已移动到
`memoria/scripts/archive/`，不再作为最终结果的运行入口。冻结 run 目录中的
manifest 和原始 JSONL 未因本次目录整理而改写。
