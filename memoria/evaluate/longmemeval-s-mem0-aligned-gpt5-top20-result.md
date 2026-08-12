# Memoria LongMemEval-S Mem0 对齐协议评测报告

> 实验完成日期：2026-08-11  
> 实验状态：完成，Reader 500/500，Judge 500/500，无系统失败  
> 核心结果：**457/500（91.40%）**

## 1. 实验目的

本实验在不改变 Memoria 检索结果的前提下，将 LongMemEval-S 的下游问答和评分协议尽可能与 Mem0 公开实验保持一致，观察同一份 Memoria Top-20 检索上下文在 Mem0 的 Reader 模型、Reader Prompt、Judge 模型和 Judge Prompt 下能够达到的端到端问答成绩。

本实验只包含一个主实验，不包含额外对照组，也没有对失败题或拒答题进行二次 Prompt 重跑和结果替换。

本实验回答的问题是：

> 固定 Memoria Top-20 检索结果，采用 Mem0 公开的 GPT-5 Reader/Judge 协议后，Memoria 在 LongMemEval-S 上的端到端准确率是多少？

## 2. 数据集基本信息

LongMemEval-S 共 500 道题，官方基础题型为六类。另有 30 道题的 `question_id` 以 `_abs` 结尾，构成 Abstention 交叉子集；Abstention 不是第七个互斥题型。

| 官方题型 | 题数 |
| --- | ---: |
| Single-Session User | 70 |
| Single-Session Assistant | 56 |
| Single-Session Preference | 30 |
| Knowledge Update | 78 |
| Temporal Reasoning | 133 |
| Multi-Session | 133 |
| **合计** | **500** |

30 道 Abstention 题分别归属于 Single-Session User 6 题、Knowledge Update 6 题、Temporal Reasoning 6 题和 Multi-Session 12 题。Overall 和六类题型结果均以完整 500 题为范围；Abstention 作为交叉诊断指标单独报告，不重复加入总分母。

| 数据项 | 值 |
| --- | --- |
| 数据集 | LongMemEval-S cleaned / oracle |
| 题目数 | 500 |
| Oracle dataset SHA256 | `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c` |
| 隔离方式 | 每个 `question_id` 使用独立用户空间，无跨题数据污染 |

## 3. 实验配置

### 3.1 Memoria 写入与检索

本实验没有重新导入数据或重新调用 Memoria 检索接口，而是直接使用此前已经完成并冻结的 500 题 Top-20 检索快照。

| 项目 | 配置 |
| --- | --- |
| Memory system | Memoria `0.4.0` |
| Memoria commit | `54c9114fd6888e11821edc2ee9acd570c17c5ee3` |
| Memory type | `semantic` |
| Embedding | `bge-m3`，1024 维 |
| 查询文本 | 原始问题文本 |
| 检索接口 | `/v1/memories/retrieve` |
| 检索路径 | Memoria 原生 `hybrid` |
| Reader 检索深度 | Top-20 |
| 检索快照题数 | 500 |
| 检索成功 | 500/500 |
| 跨题污染 | 0 |
| Retrieval snapshot SHA256 | `fe6f179d8cd21cf71a204ebfaf4c62fff7db5ae434a61b69a3c9fdff334a1434` |

Memoria 返回结果先按照检索排名截取 Top-20，再按照原始 `source_session_date` 从早到晚排序后交给 Reader。这一顺序与 Mem0 LongMemEval runner 的实际执行逻辑一致。实验使用原始会话日期，而不是 2026 年的 Memoria 导入时间，避免干扰相对时间计算。

### 3.2 Reader 与 Judge

| 项目 | 配置 |
| --- | --- |
| Reader model | `gpt-5` |
| Judge model | `gpt-5` |
| 实际返回模型 | `gpt-5-2025-08-07`（Reader/Judge 全部 500 次） |
| API | OpenAI-compatible Chat Completions，AIHubMix |
| Reader Prompt | Mem0 公开 LongMemEval Answer Generation Prompt |
| Judge Prompt | Mem0 公开 LongMemEval Unified Judge Prompt |
| Mem0 prompt commit | `4b61c5d31b9c668a12b4f5e78064248a02c82d2b` |
| User profile | 不注入 |
| System prompt | 不设置 |
| Temperature | 不传，使用 GPT-5 provider 默认值 |
| Max completion tokens | 4096 |
| Reader 输出处理 | 删除 `<mem_thinking>...</mem_thinking>`；存在 `ANSWER:` 时取最后一个 `ANSWER:` 后正文 |
| Judge 输出处理 | 删除 `<judge_thinking>...</judge_thinking>`，解析最终 `yes` / `no` |
| 运行方式 | 500 题单轮完整运行 |
| 失败策略 | Reader/Judge 缺失或失败保留在 500 题分母中并计错 |

提示词哈希：

| Prompt | SHA256 |
| --- | --- |
| Answer Generation Prompt | `59f155c1c77e3000c6c75494232f669357f77a352d5ac5042decbacea230eebf` |
| Unified Judge Prompt | `c4dc2f6e34e92f9958b62222a0ed520b3ce80dede68bba164dc7961c27dae515` |

Mem0 提示词来源：[mem0ai/memory-benchmarks prompts.py](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/benchmarks/longmemeval/prompts.py)。实际切取、时间排序、Reader 输出清理和 Judge 调用逻辑来源：[mem0ai/memory-benchmarks run.py](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/benchmarks/longmemeval/run.py)。

## 4. 实验结果

### 4.1 Overall

本实验主结果为：

```text
非 Abstention：428/470
Abstention：29/30
Overall：(428 + 29) / (470 + 30) = 457/500 = 91.40%
```

因此，**91.40% 的分母是完整 500 题，不是 470 题**。

| 指标 | 正确数 | 题数 | 准确率 |
| --- | ---: | ---: | ---: |
| Overall | **457** | **500** | **91.40%** |
| 非 Abstention | 428 | 470 | 91.06% |
| Abstention | 29 | 30 | 96.67% |

### 4.2 官方六类结果

以下六类按照官方 `question_type` 统计，覆盖完整 500 题，其中已经包含归属于各类别的 Abstention 题。

| 官方题型 | 正确数 | 题数 | 准确率 |
| --- | ---: | ---: | ---: |
| Single-Session User | 69 | 70 | 98.57% |
| Single-Session Assistant | 56 | 56 | 100.00% |
| Single-Session Preference | 25 | 30 | 83.33% |
| Knowledge Update | 71 | 78 | 91.03% |
| Temporal Reasoning | 129 | 133 | 96.99% |
| Multi-Session | 107 | 133 | 80.45% |
| **Overall（微平均）** | **457** | **500** | **91.40%** |
| **六类宏平均** | — | — | **91.73%** |

需要注意，实验目录自动生成的 `metrics.json` 和 `report.md` 中，`by_question_type` 当前只统计了 470 道非 Abstention 题，并将 30 道 Abstention 单独列出。其 Overall `457/500` 正确，但其中的分类分母不是官方六类覆盖 500 题的口径。本报告已经将 Abstention 题放回各自官方类别，给出正确的六类完整统计。

## 5. 检索证据与问答结果

证据完整度只在 470 道非 Abstention 题上计算。Abstention 题没有正向答案证据，不应进入同一个 Complete Recall 分母。

| Top-20 证据状态 | 正确数 | 题数 | 问答准确率 |
| --- | ---: | ---: | ---: |
| 完整证据 | 419 | 442 | 94.80% |
| 证据不完整 | 9 | 28 | 32.14% |
| **全部非 Abstention** | **428** | **470** | **91.06%** |

Top-20 检索指标为：

| 检索指标 | 结果 |
| --- | ---: |
| Hit@20 | 99.57% |
| 平均 Evidence Recall@20 | 97.34% |
| Complete Recall@20 | 94.04%（442/470） |
| MRR | 76.07% |

本实验共有 43 道题判错：

- 19 道非 Abstention 题的 Top-20 证据不完整；
- 23 道非 Abstention 题的 Top-20 证据完整，但 Reader/Judge 最终仍判错；
- 1 道为 Abstention 题。

非 Abstention QA 为 91.06%，与 Complete Recall@20 94.04% 相差 2.98 个百分点。相比旧实验约 8.08 个百分点的差距，本次 Mem0 协议明显提高了 Reader 对完整和分散证据的利用率。与此同时，证据不完整题只有 9/28 正确，说明剩余错误中检索证据缺失仍是重要来源。

当前最弱题型仍是 Multi-Session：107/133（80.45%）。其 26 道错误包括 14 道完整证据题、11 道证据不完整题和 1 道 Abstention 题。

## 6. 与此前 Memoria 实验对比

此前采用的 84.60% 结果为两阶段综合结果：第一阶段使用 `gpt-5.6-luna` Reader、`gpt-5.5` Judge 和 `legacy-opus` Prompt 跑完整 500 题；第二阶段只对首轮 51 道 IDK 题使用 `calibrated-opus` Prompt 重跑并替换同题标签。该实验 Judge 使用 LongMemEval 官方按题型 rubric。

本次实验是单次 500 题运行，Reader/Judge 均为 GPT-5，并使用 Mem0 公开的 Reader/Judge Prompt。因此两次实验不是单变量对照，分数差异同时包含 Reader 模型、Reader Prompt、Judge 模型和 Judge Prompt 的共同影响。

| 官方题型 | 此前 Memoria 实验 | 本次 Mem0 对齐实验 | 变化 |
| --- | ---: | ---: | ---: |
| Single-Session User | 68/70（97.14%） | 69/70（98.57%） | +1.43pp |
| Single-Session Assistant | 54/56（96.43%） | 56/56（100.00%） | +3.57pp |
| Single-Session Preference | 19/30（63.33%） | 25/30（83.33%） | +20.00pp |
| Knowledge Update | 62/78（79.49%） | 71/78（91.03%） | +11.54pp |
| Temporal Reasoning | 117/133（87.97%） | 129/133（96.99%） | +9.02pp |
| Multi-Session | 103/133（77.44%） | 107/133（80.45%） | +3.01pp |
| **Overall** | **423/500（84.60%）** | **457/500（91.40%）** | **+6.80pp** |
| **六类宏平均** | **83.63%** | **91.73%** | **+8.10pp** |
| Abstention | 19/30（63.33%） | 29/30（96.67%） | +33.34pp |
| 非 Abstention | 404/470（85.96%） | 428/470（91.06%） | +5.10pp |

逐题标签变化如下：

| 变化 | 题数 |
| --- | ---: |
| 两次都正确 | 413 |
| 旧实验错误、本次正确 | 44 |
| 旧实验正确、本次错误 | 10 |
| 两次都错误 | 33 |
| **净提升** | **34** |

提升最明显的是 Abstention、Single-Session Preference、Knowledge Update 和 Temporal Reasoning。由于 Mem0 Unified Judge Prompt 对语义等价、数值近似、偏好题和拒答匹配具有更明确且更宽松的接受规则，不能将全部提升单独归因于 GPT-5 Reader 或 Reader Prompt。

## 7. 与竞品公开结果对比

| 系统 | LongMemEval-S 结果 | 结果性质 |
| --- | ---: | --- |
| Mem0 Platform v3 Top-50 | 94.8%（474/500） | Mem0 官方仓库公开结果 |
| **Memoria Top-20，本次 Mem0 对齐协议** | **91.4%（457/500）** | 本地完整实测 |
| Mem0 OSS + GPT-5 Extraction | 91.0% | Mem0 官方 OSS 公开结果 |
| Zep | 90.2%（451/500） | Zep 官网公开结果 |
| Memoria 旧实验 | 84.6%（423/500） | 本地两阶段综合结果 |

本次 91.40% 与 Mem0 OSS 公开的 91.0% 接近，但不能解释为严格同条件下 Memoria 已超过 Mem0 或 Zep，原因包括：

- Mem0 OSS 使用信息抽取后的短记忆，本实验使用 Memoria 的长语义块；
- Mem0 公开实验可能采用不同 Top-K，本实验固定为 Top-20；
- Memory Extraction、Embedding、检索方式和记忆表示没有统一；
- Zep 使用不同的检索、Reader/Judge 和 Prompt 协议；
- 竞品没有公开可与本实验 Complete Recall@20 直接对齐的标准化证据召回结果。

因此，本次结果适合命名为：

> **Memoria LongMemEval-S Top-20 under Mem0-aligned GPT-5 Reader/Judge protocol：457/500（91.40%）**

它表示 Memoria 冻结 Top-20 检索上下文在 Mem0 下游问答与评分协议下的端到端成绩，而不是对 Mem0 完整端到端系统的严格复现。

竞品来源：

- [Mem0 memory-benchmarks 官方仓库](https://github.com/mem0ai/memory-benchmarks)
- [Mem0 Platform LongMemEval Top-50 结果](https://github.com/mem0ai/memory-benchmarks/blob/main/results/platform/longmemeval_top50_results.json)
- [Mem0 OSS 结果目录](https://github.com/mem0ai/memory-benchmarks/tree/main/results/oss)
- [Zep Research](https://www.getzep.com/research/)

竞品数据沿用截至 2026-08-06 的公开资料核对结果；如用于后续对外报告，应再次确认官网和官方仓库是否更新。

## 8. Token 与运行效率

| 环节 | 调用数 | Prompt tokens | Completion tokens | Total tokens | 平均 Prompt/题 | 平均 Completion/题 | P50 | P95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Reader | 500 | 26,731,212 | 437,783 | 27,168,995 | 53,462 | 876 | 14.76s | 31.06s |
| Judge | 500 | 777,527 | 164,473 | 942,000 | 1,555 | 329 | 4.69s | 10.05s |
| **合计** | **1,000** | **27,508,739** | **602,256** | **28,110,995** | — | — | — | — |

Mem0 Prompt 要求 Reader 和 Judge 在指定标签中生成较完整的推理过程，因此 completion tokens 和调用延迟显著高于此前的简短答案/简短 Judge 输出协议。

## 9. 结论

1. 固定 Memoria Top-20 检索结果，使用 Mem0 公开的 GPT-5 Reader/Judge 模型与 Prompt 后，LongMemEval-S 端到端准确率达到 **457/500（91.40%）**。
2. 91.40% 的分母是完整 500 题，其中非 Abstention 为 428/470，Abstention 为 29/30。
3. 相比此前采用的 423/500（84.60%）结果，本次净增加 34 道正确题，提高 6.80 个百分点；但该提升是 Reader、Reader Prompt、Judge 和 Judge Prompt 共同变化的结果。
4. 在 Top-20 证据完整的 442 道非 Abstention 题上，本次达到 419/442（94.80%），说明 Mem0 协议显著提高了证据利用率。
5. 当前剩余主要短板为 Multi-Session，以及 28 道 Top-20 证据不完整题。完整证据仍判错的 23 道题还存在 Reader 推理或 Judge 判断的排查空间。
6. 本次结果应作为独立的“Mem0 对齐协议”结果记录，不应在不说明协议差异的情况下直接覆盖或替代此前 84.60% 的官方 rubric 口径结果。

## 10. 实验产物

实验目录：

```text
memoria/runs/longmemeval-s-mem0-protocol-gpt5-top20-full500-v1/
```

主要文件：

| 文件 | 内容 |
| --- | --- |
| `manifest.json` | 冻结实验配置、模型、提示词版本及哈希 |
| `reader_prompts.jsonl` | 500 道题的完整 Reader Prompt |
| `answers.jsonl` | 500 条 Reader 原始输出及清理后的答案 |
| `judgments.jsonl` | 500 条 Judge 输出和最终标签 |
| `metrics.json` | 自动汇总指标 |
| `report.md` | 自动生成的运行报告 |
| `checkpoint.json` | Reader/Judge 完成进度 |
| `errors.jsonl` | 失败记录，本次为空 |

运行脚本与固定提示词：

| 文件 | 作用 |
| --- | --- |
| [`run_mem0_protocol_top20.sh`](../scripts/longmemeval/run_mem0_protocol_top20.sh) | 本实验正式入口，固定 GPT-5 Reader/Judge、Top-20 和正式 run 目录 |
| [`evaluate_mem0_protocol.py`](../scripts/longmemeval/evaluate_mem0_protocol.py) | Reader、Judge、断点续跑和指标汇总 |
| [`mem0_prompts.py`](../scripts/longmemeval/mem0_prompts.py) | 固定 Mem0 LongMemEval Reader/Judge Prompt |
| [`snapshot_common.py`](../scripts/longmemeval/snapshot_common.py) | 冻结 retrieval 与数据集对齐校验 |

正式复现命令：

```bash
./memoria/scripts/longmemeval/run_mem0_protocol_top20.sh full all
```

该入口读取既有 Top-20 snapshot，不会重新调用 Memoria 检索。
