# Memoria 在 LongMemEval-S 上的阶段性评测总结

> 更新日期：2026-08-07
> 范围：截至当前的最佳 Memoria 结果、实验配置、竞品公开结果与后续工作
> 当前主结果：**423/500（84.60%）**

## 1. 结论摘要

Memoria 当前在 LongMemEval-S 上的最佳实测端到端问答准确率为 **84.60%（423/500）**。该结果使用 Memoria `0.4.0` 的冻结 Top-20 检索结果，Reader 为 `gpt-5.6-luna`，Judge 为 `gpt-5.5`。

这是一个明确的两阶段流程：首轮对全部 500 题运行；随后只对首轮 Reader 输出 IDK 的 51 题更换 Reader Prompt 并重跑 Reader/Judge，再以这 51 题的新标签替换首轮同题标签。计算为：

```text
首轮：414/500
首轮 51 道 IDK：23/51 正确
第二阶段 51 题：32/51 正确
综合：414 - 23 + 32 = 423/500（84.60%）
```

当前成绩低于竞品公开端到端结果：Zep 为 90.2%，Mem0 OSS 最高为 91.0%，Mem0 Platform v3 最高为 94.8%。不过这些结果在 Memory Extraction、Embedding、检索方式、Top-K、Reader、Judge 和 Prompt 上并未统一，因此只能作为公开结果横向参考，不能解释为严格同条件下 memory backend 的能力排名。

## 2. 数据集

LongMemEval-S 共 500 题，官方基础题型为六类。另有 30 道题的 `question_id` 以 `_abs` 结尾，构成 Abstention 交叉子集；Abstention 不是第七个互斥题型。

| 官方题型 | 题数 |
| --- | ---: |
| Single-Session User | 70 |
| Single-Session Assistant | 56 |
| Single-Session Preference | 30 |
| Knowledge Update | 78 |
| Temporal Reasoning | 133 |
| Multi-Session | 133 |
| **合计** | **500** |

30 道 Abstention 题分别归属于 Single-Session User 6 题、Knowledge Update 6 题、Temporal Reasoning 6 题和 Multi-Session 12 题。六类成绩覆盖全部 500 题；Abstention Accuracy 作为交叉诊断指标另外报告，不重复加入总分母或类别宏平均。

| 数据项 | 值 |
| --- | --- |
| 数据集 | LongMemEval-S cleaned / oracle，500 题 |
| Cleaned dataset SHA256 | `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` |
| Oracle dataset SHA256 | `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c` |
| 隔离方式 | 每个 `question_id` 使用独立用户空间，避免跨题污染 |
| 时间处理 | 使用 `observed_at` 相对时间平移，保留会话的相对时间关系 |

## 3. Memoria 实验配置

### 3.1 写入与检索

| 环节 | 配置 |
| --- | --- |
| Memory system | Memoria `0.4.0` |
| Commit | `54c9114fd6888e11821edc2ee9acd570c17c5ee3` |
| Memory type | `semantic` |
| Embedding | `bge-m3`，1024 维 |
| 长内容处理 | 确定性切分，单块不超过 30 KiB / 7000 tokens |
| 查询 | 原始问题文本 |
| 检索接口 | `/v1/memories/retrieve` |
| 检索路径 | Memoria 原生 `hybrid` |
| 检索深度 | Top-20 |
| Retrieval snapshot | 500 题冻结快照，SHA256 `fe6f179d8cd21cf71a204ebfaf4c62fff7db5ae434a61b69a3c9fdff334a1434` |
| 检索成功 | 500/500；跨题污染 0 |

检索证据指标仅在 470 道非 Abstention 题上计算。Abstention 题没有正向答案证据，不适合纳入同一证据召回分母。

| 检索指标 | Top-20 |
| --- | ---: |
| Hit@20 | 99.57% |
| 平均 evidence Recall@20 | 97.34% |
| Complete Recall@20 | 94.04%（442/470） |
| MRR | 76.07% |
| 检索延迟 p50 / p95 | 292.6 / 423.3 ms |

### 3.2 Reader 与 Judge

| 环节 | 配置 |
| --- | --- |
| Reader | `gpt-5.6-luna` |
| Judge | `gpt-5.5` |
| Temperature | `0.0` |
| Reader max output | 1024 tokens |
| Judge max output | 512 tokens |
| Reader context | 冻结检索快照的前 20 条结果 |
| Judge rubric | LongMemEval 官方按题型评分规则 |
| 失败策略 | 调用失败保留在 500 题分母并计错 |
| 第一阶段 Prompt | `legacy-opus`：证据不足时精确输出 `I don't know` |
| 第二阶段 Prompt | `calibrated-opus`：对首轮 51 道 IDK 题鼓励利用间接、分散证据推断，仅在确实无法推断时拒答 |

第一阶段 Reader 平均每题输入 51,754.7 tokens、输出 79.7 tokens、总计 51,834.4 tokens。第二阶段仅对预先由首轮 IDK 行为确定的 51 题执行，不使用 gold answer 或 Judge 标签选题。

## 4. Memoria 精度结果

以下六类按官方 `question_type` 统计，覆盖全部 500 题；其中已经包含各类下的 Abstention 题。

| 官方题型 | 正确数 | 准确率 |
| --- | ---: | ---: |
| Single-Session User | 68/70 | 97.14% |
| Single-Session Assistant | 54/56 | 96.43% |
| Single-Session Preference | 19/30 | 63.33% |
| Knowledge Update | 62/78 | 79.49% |
| Temporal Reasoning | 117/133 | 87.97% |
| Multi-Session | 103/133 | 77.44% |
| **Overall（微平均）** | **423/500** | **84.60%** |
| **六类宏平均** | — | **83.63%** |

Abstention 交叉子集为 **19/30（63.33%）**。当前主要短板是 Single-Session Preference、Multi-Session、Knowledge Update 和 Abstention。与此同时，Top-20 Complete Recall 已达到 94.04%，说明后续仍有一部分空间位于 Reader 的证据利用、拒答策略和 Judge 稳定性，而不仅是检索覆盖率。

## 5. 竞品公开结果对比

### 5.1 Overall

| 系统 | LongMemEval-S 最佳公开/实测结果 | 结果性质 |
| --- | ---: | --- |
| Mem0 Platform v3 Top-50 | **94.8%（474/500）** | 官方仓库公开结果 |
| Mem0 OSS + GPT-5 Extraction | **91.0%** | 官方 OSS 对照实验 |
| Zep | **90.2%（451/500）** | 官网公开结果 |
| **Memoria** | **84.6%（423/500）** | 本地完整实测，两阶段 Prompt |

Memoria 相对 Zep 低 5.6 个百分点，相对 Mem0 OSS 低 6.4 个百分点，相对 Mem0 Platform v3 Top-50 低 10.2 个百分点。

### 5.2 分类精度

| 官方题型 | Memoria | Zep | Mem0 OSS GPT-5 | Mem0 Platform v3 Top-50 |
| --- | ---: | ---: | ---: | ---: |
| Single-Session User | 97.1% | 94.3% | 95.7% | 98.6% |
| Single-Session Assistant | 96.4% | 96.4% | 92.9% | 98.2% |
| Single-Session Preference | 63.3% | 90.0% | 93.3% | 93.3% |
| Knowledge Update | 79.5% | 93.6% | 91.0% | 93.6% |
| Temporal Reasoning | 88.0% | 90.2% | 94.7% | 94.0% |
| Multi-Session | 77.4% | 83.5% | 83.5% | 93.2% |
| **Overall** | **84.6%** | **90.2%** | **91.0%** | **94.8%** |

### 5.3 竞品配置与披露边界

| 系统 | 已知主要配置 | 关键未披露项 |
| --- | --- | --- |
| Zep | `gpt-5.4` Reader/Judge；reasoning=`medium`；五路 multi-scope retrieval；cross-encoder reranking；中位上下文 4,408 tokens | 图构建/记忆提取模型、Embedding、reranker 型号、完整 Prompt |
| Mem0 OSS | GPT-5 Memory Extraction/Reader/Judge；Qwen 600M Embedding；Qdrant | 汇总表未明确该组具体 Top-K |
| Mem0 Platform v3 Top-50 | 托管 v3 pipeline；semantic similarity + BM25 + entity boost；Top-50 | Extraction、Embedding、Reader、Judge 和完整 Prompt 未被结果 manifest 明确钉死 |

Zep 与 Mem0 当前主要公布端到端问答结果，没有公开可与 Memoria Complete Recall@20 直接对齐的标准化 Recall@K、MRR、nDCG 或 evidence completeness。因此不能把端到端分差直接归因于检索能力。

## 6. 后续工作

1. **Judge 复核**：固定现有 Reader 回答，使用 LongMemEval 官方 Judge 配置与当前 `gpt-5.5` 进行交叉复核，重点检查错题、Abstention 和语义等价拒答的评分稳定性。
2. **Reader Prompt 与模型实验**：当前 Top-20 在 470 道非 Abstention 题上的 Complete Recall@20 已达到 **94.04%（442/470）**，明显高于当前非 Abstention QA 准确率 **85.96%（404/470）**，说明在不改变检索结果的情况下，Reader Prompt 如何利用完整或分散证据以及 Reader 模型本身仍有优化空间。后续应继续平衡“利用间接证据作答”与“信息确实不足时拒答”，重点观察 Preference、Knowledge Update、Multi-Session 和 Abstention；新 Prompt 或模型必须完整跑 500 题并单独报告。
3. **信息抽取实验**：增加信息抽取阶段，将会话或检索上下文抽取为结构化、任务相关信息后再交给 Reader；保持检索快照、Reader、Judge 和评分规则不变，比较 QA、Token、延迟和错误来源。
4. **严格对照**：如竞品后续披露完整配置或可复现产物，再统一 Extraction、Embedding、Top-K、Reader、Judge 和 Prompt 进行受控对照。

## 7. 结果与来源

### Memoria 本地实验产物

- 第一阶段：`memoria/runs/longmemeval-s-e2e-reader-luna-judge-gpt55-top20-opus-prompt-full500-v1/`
- 第二阶段：`memoria/runs/longmemeval-s-e2e-reader-luna-judge-gpt55-top20-calibrated-prompt-idk51-v1/`
- 冻结检索：`memoria/runs/longmemeval-s-bge-m3-relative-shift-v1/retrieval/top20-full500-v1/`
- 完整实验记录：`memoria/runs/longmemeval-s-repro-legacy-claude-opus-4-6-gpt54-top10-full500-v1/ARTIFACT_RECORD.md`

### 官方与竞品来源

- [LongMemEval 官方仓库](https://github.com/xiaowu0162/LongMemEval)
- [Zep Research](https://www.getzep.com/research/)
- [Mem0 memory-benchmarks 官方仓库](https://github.com/mem0ai/memory-benchmarks)
- [Mem0 Platform LongMemEval Top-50 逐题结果](https://github.com/mem0ai/memory-benchmarks/blob/main/results/platform/longmemeval_top50_results.json)
- [Mem0 OSS 逐题结果目录](https://github.com/mem0ai/memory-benchmarks/tree/main/results/oss)

竞品公开数据核对日期为 2026-08-06；如官网或官方仓库更新，应重新核验后再用于对外比较。
