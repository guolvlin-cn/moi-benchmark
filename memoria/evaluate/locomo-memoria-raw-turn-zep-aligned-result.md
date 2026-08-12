# Memoria LoCoMo Raw Turn 对标 Zep 模型实验结果

> 实验状态：**COMPLETE**
> 数据范围：LoCoMo Category 1–4，10 个 sample，1,540 题
> 记忆轨道：Controlled Track / Raw Turn，一条原始 turn 存为一条 memory
> 主结果：Top-200，GPT-5.4 medium Reader + GPT-5.4 medium Judge，Mem0 Prompt 协议，**1,393/1,540 = 90.45%**
> 实验完成时间：2026-08-12 10:25:16（北京时间）
> 报告核对时间：2026-08-12（北京时间）

## 1. 结论摘要

| 维度 | Memoria 本次结果 |
| --- | ---: |
| 导入验收 | 5,882/5,882 active memories，0 失败，0 缺失，0 多余 |
| 检索成功率 | 1,540/1,540（100%） |
| Hit@200 | 87.57%（1,345/1,536） |
| Mean Evidence Recall@200 | 81.62% |
| Complete Recall@200 | 75.00%（1,152/1,536） |
| Reader 成功 | 1,540/1,540 |
| Judge 成功 | 1,540/1,540 |
| End-to-End QA | **90.45%（1,393/1,540）** |

本次结果的准确表述是：

> Memoria 在 LoCoMo Category 1–4、Raw Turn 直存、Qwen `text-embedding-v4`/1,024 维、Top-200 条件下，对齐 Zep 官网公布的 GPT-5.4 Reader/Judge 模型配置，并采用完整公开且适合 Raw Turn 输入的 Mem0 Reader/Judge Prompt 协议，端到端问答准确率为 **90.45%**。

本实验正式名称为：

> **Memoria LoCoMo Raw Turn 对标 Zep 模型实验**
> **Zep Model-Aligned / Mem0 Prompt Protocol**

这里的“对标 Zep”指对齐 Zep 公布的模型配置，不表示严格复现 Zep 的 94.7% pipeline。Zep 官网没有公开 94.7% run 对应的完整 Reader Prompt、Judge Prompt、评分细则、commit、manifest 或逐题结果；本实验因此采用可审计、可复现且已在 Raw Turn 上验证有效的 Mem0 Prompt 协议。

核心对比：

| 实验 | 正确数 | Accuracy | 相对本次主结果 |
| --- | ---: | ---: | ---: |
| **GPT-5.4 medium + Mem0 Prompt 协议（本次）** | **1,393/1,540** | **90.45%** | — |
| GPT-5 + Mem0 Prompt 协议 | 1,354/1,540 | 87.92% | **+39 题 / +2.53 pp** |
| GPT-5.4 medium + Zep 仓库 Prompt 派生协议 | 1,240/1,540 | 80.52% | **+153 题 / +9.94 pp** |
| Zep 官网公开 Overall | 1,459/1,540 | 94.70% | **-66 题 / -4.25 pp** |

该结果支持两个结论：

1. 旧实验的 80.52% 不能解释为 GPT-5.4 能力弱于 GPT-5；在相同 Mem0 Prompt 协议下，GPT-5.4 比 GPT-5 高 2.53 个百分点。
2. GPT-5.4 从 80.52% 提升到 90.45%，说明旧 Zep-Prompt 派生实验的主要损失来自 Prompt、上下文组织和 Judge 评分协议与 Raw Turn 输入不匹配，而不是 GPT-5.4 本身。

## 2. 数据集与评测范围

### 2.1 数据冻结

| 项目 | 固定值 |
| --- | --- |
| 数据集 | LoCoMo / `locomo10.json` |
| SHA-256 | `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4` |
| Sample | 10 |
| Session | 272 |
| Dialogue turn / memory | 5,882 |
| 全部 QA | 1,986 |
| 本次 QA | Category 1–4，1,540 |
| 排除 | Category 5 adversarial，446 |
| 有可用 evidence 的题 | 1,536 |
| 无 evidence 的题 | 4，均属于 Category 3 |

问题分布：

| Category | 类型 | 题数 |
| --- | --- | ---: |
| 1 | Multi-hop | 282 |
| 2 | Temporal | 321 |
| 3 | Open-domain | 96 |
| 4 | Single-hop | 841 |
| **合计** |  | **1,540** |

### 2.2 用户隔离与 sample 规模

每个 LoCoMo sample 对应一个隔离用户；每道题只检索所属 sample 的 memory。

| Sample | Session | Memory/turn | Category 1–4 QA |
| --- | ---: | ---: | ---: |
| `conv-26` | 19 | 419 | 152 |
| `conv-30` | 19 | 369 | 81 |
| `conv-41` | 32 | 663 | 152 |
| `conv-42` | 29 | 629 | 199 |
| `conv-43` | 29 | 680 | 178 |
| `conv-44` | 28 | 675 | 123 |
| `conv-47` | 31 | 689 | 150 |
| `conv-48` | 30 | 681 | 191 |
| `conv-49` | 25 | 509 | 156 |
| `conv-50` | 30 | 568 | 158 |
| **合计** | **272** | **5,882** | **1,540** |

## 3. Memoria 版本、导入与检索

本实验复用已经验收的 Raw Turn 数据和同一份冻结 Top-200 检索快照，没有重新导入或重新检索。这样 GPT-5、GPT-5.4 和 Prompt 消融实验面对完全相同的 retrieval 输入。

### 3.1 Memoria 版本

| 项目 | 值 |
| --- | --- |
| Memoria 仓库 | `matrixorigin/Memoria` |
| 基础 commit | [`54c9114fd6888e11821edc2ee9acd570c17c5ee3`](https://github.com/matrixorigin/Memoria/commit/54c9114fd6888e11821edc2ee9acd570c17c5ee3) |
| Commit 日期 | 2026-08-03 14:55:10 +08:00 |
| Commit 标题 | `feat: support extra metadata in batch write (#223)` |
| 运行形态 | 基础 commit + benchmark 局部补丁 |

局部补丁：

1. `MEMORIA_SENSITIVITY_FILTER_ENABLED=false`：对公开合成 benchmark 做字节级直存。
2. `/v1/memories/retrieve` 的 Top-K 上限从 100 调整到 200；未改动混合检索公式。

### 3.2 导入配置

| 项目 | 配置 |
| --- | --- |
| 导入轨道 | Controlled Track，直接 `POST /v1/memories` |
| 粒度 | 一条 turn 导入为一条 semantic memory |
| Native extraction | 关闭，`internal_llm=false` |
| QA/summary 写入 | 禁止 |
| 图像 | `blip_caption` 追加到 content |
| 用户隔离 | `sample_id -> locomo-qwen-v4-{sample_id}` |
| 恢复键 | deterministic `ingest_key` |
| Embedding | DashScope `text-embedding-v4` |
| Embedding 维度 | 1,024 |
| Active-memory 验收 | 5,882/5,882 |

### 3.3 冻结检索配置

| 项目 | 值 |
| --- | --- |
| Endpoint | `POST /v1/memories/retrieve` |
| Query | 原始 LoCoMo question，不改写 |
| Top-K | 200 |
| Explain | `verbose` |
| 用户范围 | 仅问题所属 sample |
| Snapshot records | 1,540 |
| Valid retrievals | 1,540/1,540 |
| 每题返回数 | 恰好 200 |
| 跨用户/重复 ID | 0 |
| Retrieval snapshot SHA-256 | `b1d561df1a783d73d195a235b2f687cc88bb30ed477ac08f25c6c22994c2910c` |
| Retrieval manifest SHA-256 | `9c23de82592346e56f75b2d3177abab435c606296584e7dcffc06f754bb2c5f9` |

检索质量：

| 指标 | @10 | @20 | @50 | @200 |
| --- | ---: | ---: | ---: | ---: |
| Evidence Hit | 11.26% | 21.94% | 48.05% | **87.57%** |
| Mean Evidence Recall | 9.46% | 18.94% | 42.49% | **81.62%** |
| Complete Recall | 8.33% | 16.86% | 38.61% | **75.00%** |

`MRR@200 = 0.057744`。Top-200 Complete Recall 的分母是 1,536 道有 evidence 标注的题。

## 4. Zep 公开配置与披露边界

截至 2026-08-12，[Zep Research 页面](https://www.getzep.com/research/)公布的 LoCoMo 配置为：

| 环节 | Zep 官网配置 |
| --- | --- |
| Reader | `gpt-5.4` |
| Reader reasoning | `medium` |
| Judge | `gpt-5.4` |
| Judge 方式 | chain-of-thought grading |
| 检索 | 五路 multi-scope，客户端组合 |
| Facts/Edges | 20 |
| Entity Nodes | 10 |
| Episodes | 10 |
| Thread Summaries | 5 |
| Observations | 5 |
| 排序 | Cross-encoder reranking |
| 数据范围 | 1,540 道 LoCoMo Category 1–4 |
| 官网 Overall | 94.7%（1,459/1,540） |
| Retrieval latency | p50 87 ms / p95 155 ms |
| 中位上下文 | 5,760 tokens |

Zep 官网没有披露 94.7% run 的：

- 完整 Reader Prompt；
- 完整 Judge Prompt 和具体评分容差；
- Prompt 对应 commit 和运行 manifest；
- 图构建/信息抽取模型；
- Embedding 和 Cross-encoder 型号；
- 1,540 道题的逐题答案与 Judge 结果。

Zep 官方仓库 `getzep/zep` 的 `benchmarks/locomo/prompts.py` 虽然公开了一套 LoCoMo Prompt，但该文件本身没有出现 `gpt-5.4`，也没有声明这些 Prompt 是为 GPT-5.4 专门设计或与官网 94.7% run 配套。Zep Research 页面也没有把 94.7% run 绑定到该文件的具体 commit。

因此，本实验选择：

> 对齐 Zep 明确公布的 GPT-5.4 模型配置；Prompt 和评分规则采用完整公开、固定 commit、可哈希审计，并且已经验证适合 Raw Turn 输入的 Mem0 协议。

## 5. 本次 Reader/Judge 协议

### 5.1 模型与 API

| 项目 | Reader | Judge |
| --- | --- | --- |
| 请求模型 | `gpt-5.4` | `gpt-5.4` |
| API 返回模型 | `gpt-54`，1,540/1,540 | `gpt-54`，1,540/1,540 |
| Response status | `completed`，1,540/1,540 | `completed`，1,540/1,540 |
| Reasoning effort | `medium` | `medium` |
| Provider | AiHubMix OpenAI-compatible | 同左 |
| Base URL | `https://aihubmix.com/v1` | 同左 |
| API style | Responses API | Responses API |
| Max output tokens | 4,096 | 4,096 |
| Temperature | 不传参 | 不传参 |
| Timeout | 180 s | 180 s |
| Max retries | 5 | 5 |
| RPM | 每 client 200 | 每 client 200 |
| 并发 | 10 个 sample 并发，sample 内按题目顺序 | 同一题紧随 Reader |

Zep 官网只明确写 Reader `reasoning=medium`，Judge 仅描述为 GPT-5.4 chain-of-thought grading，没有单独公布 Judge reasoning effort。本实验为固定和对称起见，将 Judge 也设为 `medium`；这是本地实验选择，不是 Zep 官网已披露事实。

### 5.2 Prompt 来源与冻结

Reader/Judge Prompt 固定自 Mem0 官方 `memory-benchmarks` commit
[`4b61c5d31b9c668a12b4f5e78064248a02c82d2b`](https://github.com/mem0ai/memory-benchmarks/commit/4b61c5d31b9c668a12b4f5e78064248a02c82d2b)
的 [`benchmarks/locomo/prompts.py`](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/benchmarks/locomo/prompts.py)。本地完整文本保存在 `memoria/scripts/locomo/mem0_prompts.py`。

| Prompt | SHA-256 |
| --- | --- |
| Reader `ANSWER_GENERATION_PROMPT` | `79c9f09bcc8d5e9e8b7e9786af587b02a67d366ab79285fc148b73fd20f6297b` |
| Judge system prompt | `36c007917faf1ab84516cdca577fb523711a9b993706fbae8ae37806e6f9adcc` |
| Judge prompt（without evidence） | `d248e056d993725e28fba8d16ca7081f0b59deae272ef294f3c6b00d48eac02b` |
| 本地 Prompt module | `83486e0ac192e5809f0a2ebb614693bf20197b3d7fee5cf2d0df3f2c69a8e9e9` |

Reader 的主要规则包括：扫描全部 memory、人物归属校验、跨 memory 组合、列表/计数完整性检查、具体信息优先、基于 LoCoMo reference date 做时间推理，并从最后一个 `ANSWER:` 后提取最终答案。

Judge 的主要规则包括：

- gold 列表中至少一项正确即可给 partial credit；
- 允许语义等价表达和额外细节；
- 日期允许 ±14 天，时长允许 50% 误差；
- 接受 semantic overlap 和 same referent；
- 只有零正确项或完全不同主题才判 `WRONG`；
- 输出包含一句 reasoning 和 `CORRECT/WRONG` label 的 JSON。

该 Judge 相对宽松，但本次 GPT-5.4 和本地 GPT-5 对照实验使用的是同一套规则，因此两者可在该统一协议下比较。

### 5.3 Reader 输入组织

| 项目 | 值 |
| --- | --- |
| Memory 数 | 每题 Top-200 |
| 选择顺序 | 先取检索排名 Top-200 |
| Prompt 展示顺序 | 再按原始 session 时间从旧到新稳定排序 |
| 排名/分数 | 不向 Reader 展示 |
| Reference date | 该 sample 最后一个原始 session 日期 |
| User profile | 关闭 |
| Judge evidence | 关闭 |
| Category 3 gold | 与 Mem0 一致，只使用分号前第一部分 |
| Reader 答案抽取 | 取最后一个 `ANSWER:` 之后的文本 |

逐题核验显示，本次 GPT-5.4 实验与 GPT-5/Mem0 协议实验：

- 1,540/1,540 道题的 Reader Prompt hash 一致；
- 1,540/1,540 道题的 chronological memory ID 序列一致。

因此两次实验的输入 Prompt 和 memory 组织完全相同。剩余主要差异是模型、reasoning 设置和 API style：GPT-5.4 使用 Responses API + `medium`，GPT-5 原实验使用 Chat Completions 且未显式设置 reasoning effort。

## 6. 实验过程

### 6.1 旧 Zep-Prompt 派生实验

早期曾尝试将 Zep 官方仓库公开 Prompt 用于 Memoria Raw Turn：

1. 无效 v1 将 session/message time 当作 Zep Prompt 假设的 extracted `event_time`，导致 temporal 题稳定晚一天、晚一周或晚一个月；该实验停止并删除，不纳入正式结果。
2. v2 改为 `message_time`，新增 Raw-Turn Reader adapter，并保留 Zep 仓库 Judge Prompt，完成结果为 **1,240/1,540 = 80.52%**。

进一步审计发现，Zep 仓库 Prompt 并未与官网 GPT-5.4/94.7% run 明确绑定，而且 v2 同时改变了 Reader Prompt、memory 顺序、Judge 规则和 Category 3 gold 处理。80.52% 因此不能用于判断 GPT-5.4 相对 GPT-5 的能力。

该结果现在保留为：

> **Zep Repository-Prompt-Derived Raw-Turn Ablation**

它是 Prompt/协议消融，不再作为对标 Zep 模型的主结果。

### 6.2 新主实验

新实验采取以下控制策略：

1. 复用完全相同的 1,540 题和冻结 Top-200 snapshot；
2. Reader/Judge 均请求 Zep 官网公布的模型 `gpt-5.4`；
3. Reader 明确设置 `reasoning=medium`；Judge 也固定为 `medium`；
4. Reader/Judge 均使用 Mem0 固定 commit 的完整公开 Prompt；
5. Memory 时间排序、reference date、Category 3 gold 和 Judge 规则全部与 GPT-5/Mem0 协议实验一致；
6. 新建独立 run 目录，不覆盖旧 80.52% 消融结果；
7. 使用 append-only JSONL 保存每次调用，按每题最新成功记录断点恢复。

### 6.3 中断与恢复

本次 full run 没有单独保存 preflight 目录，直接在 full1540 目录中执行并断点续跑。

| 文件 | 总行数 | 唯一题 | 历史失败 | 最终成功 |
| --- | ---: | ---: | ---: | ---: |
| `answers.jsonl` | 1,583 | 1,540 | 43 | 1,540 |
| `judgments.jsonl` | 1,540 | 1,540 | 0 | 1,540 |
| `errors.jsonl` | 43 | — | 43 | — |

43 条 Reader 历史失败全部来自 AiHubMix 余额不足。补充余额并重跑后，43 道题均生成成功；所有失败 question ID 都能在最终 Reader success 集合中找到对应记录。

计分逻辑读取每题最新成功 answer/judgment，历史失败不进入最终分子或分母。manifest 创建于 2026-08-11 19:02:33（北京时间），最终 summary 写入于 2026-08-12 10:25:16（北京时间）；该窗口包含余额不足导致的长时间中断，不能当作纯模型执行时长。

## 7. 完整性与最终验收

| 项目 | 结果 |
| --- | ---: |
| Selected questions | 1,540 |
| Unique Reader question IDs | 1,540 |
| Latest successful Reader records | 1,540 |
| Reader returned `gpt-54` / `completed` | 1,540/1,540 |
| Unique Judge question IDs | 1,540 |
| Latest successful Judge records | 1,540 |
| Judge returned `gpt-54` / `completed` | 1,540/1,540 |
| Missing answers | 0 |
| Missing judgments | 0 |
| Historical error IDs recovered | 43/43 |
| Final complete | `true` |

最终分数已直接从 `judgments.jsonl` 每题最新成功记录独立复算，不只依赖 `summary.json`：

```text
CORRECT = 1,393
TOTAL   = 1,540
ACCURACY = 1,393 / 1,540 = 90.4545%
```

## 8. 最终结果

### 8.1 Overall 与分类

| Category | 正确 | 错误 | 总数 | Accuracy |
| --- | ---: | ---: | ---: | ---: |
| Multi-hop | 253 | 29 | 282 | **89.72%** |
| Temporal | 298 | 23 | 321 | **92.83%** |
| Open-domain | 72 | 24 | 96 | 75.00% |
| Single-hop | 770 | 71 | 841 | **91.56%** |
| **Overall** | **1,393** | **147** | **1,540** | **90.45%** |

### 8.2 按 Top-200 evidence 状态

| Evidence 状态 | 正确 | 错误 | 总数 | Accuracy |
| --- | ---: | ---: | ---: | ---: |
| Complete | 1,112 | 40 | 1,152 | **96.53%** |
| Partial | 170 | 23 | 193 | **88.08%** |
| Missing | 107 | 84 | 191 | 56.02% |
| No evidence annotation | 4 | 0 | 4 | 100.00% |

147 道错误中，107 道发生在 evidence partial/missing 状态，占 **72.79%**。当 Top-200 完整召回全部标注 evidence 时，GPT-5.4 + Mem0 Prompt 协议达到 **96.53%**。

该分层说明：

1. 检索 evidence completeness 仍是最主要的端到端限制；
2. GPT-5.4 能利用部分证据将 Partial 状态提升到 88.08%；
3. Missing 状态仍有 56.02% 正确，可能来自重复表述、非标注但等价的 turn、模型先验以及宽松 Judge；因此 QA accuracy 不能替代 evidence recall；
4. 即使 evidence complete，仍有 40 道题被判错，后续可针对 Reader 推理和标注/Judge 边界继续分析。

### 8.3 按 sample

| Sample | 正确 | 总数 | Accuracy |
| --- | ---: | ---: | ---: |
| `conv-26` | 146 | 152 | **96.05%** |
| `conv-30` | 78 | 81 | **96.30%** |
| `conv-41` | 134 | 152 | 88.16% |
| `conv-42` | 177 | 199 | 88.94% |
| `conv-43` | 157 | 178 | 88.20% |
| `conv-44` | 107 | 123 | 86.99% |
| `conv-47` | 137 | 150 | 91.33% |
| `conv-48` | 167 | 191 | 87.43% |
| `conv-49` | 140 | 156 | 89.74% |
| `conv-50` | 150 | 158 | **94.94%** |

### 8.4 Token 与延迟

| 指标 | Reader | Judge |
| --- | ---: | ---: |
| Calls | 1,540 | 1,540 |
| Input/prompt tokens | 26,008,417 | 1,155,114 |
| Output/completion tokens | 737,947 | 119,205 |
| Reasoning tokens | 677,755 | 56,553 |
| Total tokens | 26,746,364 | 1,274,319 |
| 平均 input/prompt tokens | 16,888.58 | 750.07 |
| 平均 output/completion tokens | 479.19 | 77.41 |
| 平均 reasoning tokens | 440.10 | 36.72 |
| 平均 total tokens | 17,367.77 | 827.48 |
| Latency p50 | 5,836.4 ms | 2,249.0 ms |
| Latency p95 | 20,203.2 ms | 4,519.5 ms |
| Latency max | 56,422.3 ms | 63,050.1 ms |

Reader 平均约 16.9K input tokens，显著大于 Zep 官网报告的 5,760-token 中位上下文。两边 context 结构和统计口径不同，不能据此直接比较系统效率。

## 9. 与 GPT-5 / Mem0 Prompt 同协议实验对比

两次实验的 dataset、Memoria 数据、Top-200 snapshot、Reader Prompt、memory 时间排序、reference date、Judge Prompt 和评分规则一致。

| Category | GPT-5.4 medium | GPT-5 | GPT-5.4 差值 |
| --- | ---: | ---: | ---: |
| Multi-hop | 89.72%（253/282） | 87.23%（246/282） | **+7 题 / +2.48 pp** |
| Temporal | 92.83%（298/321） | 90.65%（291/321） | **+7 题 / +2.18 pp** |
| Open-domain | 75.00%（72/96） | 71.88%（69/96） | **+3 题 / +3.13 pp** |
| Single-hop | 91.56%（770/841） | 88.94%（748/841） | **+22 题 / +2.62 pp** |
| **Overall** | **90.45%（1,393/1,540）** | **87.92%（1,354/1,540）** | **+39 题 / +2.53 pp** |

逐题交叉：

| GPT-5.4 | GPT-5 | 题数 |
| --- | --- | ---: |
| CORRECT | CORRECT | 1,339 |
| CORRECT | WRONG | 54 |
| WRONG | CORRECT | 15 |
| WRONG | WRONG | 132 |

净提升为 `54 - 15 = 39` 题。所有分类均提升，幅度在 2.18–3.13 个百分点之间，没有出现某一分类异常大幅退化。

这是一组较强的同协议对照，但仍不是严格单变量模型实验：GPT-5.4 使用 Responses API 并显式设置 `reasoning=medium`，GPT-5 原实验使用 Chat Completions，无法设置相同 reasoning effort。因此应表述为“GPT-5.4 medium 模型配置在相同 Mem0 Prompt 协议下提升 2.53 pp”，不把全部提升强行归因于基础模型本身。

## 10. 与旧 Zep-Prompt 派生消融对比

两次 GPT-5.4 实验使用相同的 Raw Turn 数据和 Top-200 snapshot，但下游 Prompt、memory 顺序、Judge 和 gold 处理不同。

| Category | 本次：Mem0 Prompt 协议 | 旧：Zep-Prompt 派生协议 | 差值 |
| --- | ---: | ---: | ---: |
| Multi-hop | 89.72%（253/282） | 64.18%（181/282） | **+72 题 / +25.53 pp** |
| Temporal | 92.83%（298/321） | 84.42%（271/321） | **+27 题 / +8.41 pp** |
| Open-domain | 75.00%（72/96） | 59.38%（57/96） | **+15 题 / +15.63 pp** |
| Single-hop | 91.56%（770/841） | 86.92%（731/841） | **+39 题 / +4.64 pp** |
| **Overall** | **90.45%（1,393/1,540）** | **80.52%（1,240/1,540）** | **+153 题 / +9.94 pp** |

逐题交叉：

| 本次 Mem0 Prompt 协议 | 旧 Zep-Prompt 派生协议 | 题数 |
| --- | --- | ---: |
| CORRECT | CORRECT | 1,232 |
| CORRECT | WRONG | 161 |
| WRONG | CORRECT | 8 |
| WRONG | WRONG | 139 |

Multi-hop 提升 25.53 个百分点，是总差距最大的来源。这与 Mem0 Reader Prompt 强调扫描全部 memory、跨 memory 组合、人物归属校验以及列表/计数完整性一致。

不过这仍是“完整下游协议”消融，不是 Reader Prompt 单变量实验。两组之间同时存在：

- Reader Prompt 差异；
- memory 展示顺序差异；
- Judge Prompt 和评分容差差异；
- Category 3 gold 预处理差异。

因此可得结论是：旧 Zep-Prompt 派生协议不适合本次 Raw Turn 输入，不能进一步断言 9.94 pp 全部来自 Reader Prompt 的某一句指令。

## 11. 与 Zep 官网结果对比

| 实验 | 正确 | Accuracy |
| --- | ---: | ---: |
| Memoria Raw Turn / Zep Model-Aligned / Mem0 Prompt Protocol | 1,393/1,540 | **90.45%** |
| Zep 官网公开 Overall | 1,459/1,540 | **94.70%** |
| 差值 | -66 | **-4.25 pp** |

该比较只能作为公开参考，不能解释为严格的 memory backend 排名。

| 维度 | Memoria 本次实验 | Zep 官网实验 |
| --- | --- | --- |
| Memory | 原始 turn，一 turn 一 memory | 图事实、实体、原始 episode、summary、observation |
| 时间 | Reader 从消息时间和文本解析事件时间 | 图构建阶段生成 fact event time |
| Embedding | Qwen `text-embedding-v4`/1,024 | 未披露 |
| 检索 | 单路 Memoria Top-200 hybrid | 五路 multi-scope，共 50 个 scope items |
| Reranker | Memoria 当前 hybrid score | 未披露型号的 Cross-encoder |
| Reader | GPT-5.4 medium，Mem0 Prompt | GPT-5.4 medium，Prompt 未公开 |
| Judge | GPT-5.4 medium，Mem0 Prompt | GPT-5.4，CoT grading，完整 Prompt 未公开 |
| 上下文规模 | Reader 平均约 16.9K input tokens | 中位 5,760 context tokens |
| 逐题产物 | 完整本地 JSONL | 官网未提供下载入口 |

Zep 官网分类数字仍无法与 Overall 相互核验：页面分类正确数合计 1,436、题数合计 1,539，但 Overall 写为 1,459/1,540。因此本报告只引用 Zep 官网的 Overall 94.7%，不使用其分类数字重新计算或做分类级差值。

## 12. 结果解释与限制

### 12.1 当前结论

- 本次主实验完整、可复算，正式结果为 **1,393/1,540 = 90.45%**。
- GPT-5.4 Reader/Judge 请求均成功返回 `gpt-54`，最终状态全部为 `completed`。
- 在相同 Mem0 Prompt 协议下，GPT-5.4 medium 比 GPT-5 高 **2.53 pp**；不存在 GPT-5.4 明显弱于 GPT-5 的证据。
- 旧 Zep-Prompt 派生实验的 80.52% 比本次低 **9.94 pp**，应作为 Prompt/协议消融结果，而不是主要 Zep 模型对标结果。
- Evidence complete 条件下达到 **96.53%**，当前主要瓶颈仍是 Top-200 evidence completeness。
- 与 Zep 官网 94.7% 相差 4.25 pp，但双方 memory 构造、检索、上下文、Prompt 和评分协议均未完全对齐，不能把差距全部归因于 Memoria backend。

### 12.2 不能由本实验推出的结论

- 不能称为严格复现 Zep 94.7%；
- 不能声称 Mem0 Prompt 就是 Zep 官网实际使用的 Prompt；
- 不能声称 Zep 仓库公开 Prompt 一定没有用于官网实验，只能说公开证据未建立绑定；
- 不能把 90.45% 与 94.7% 的差距解释成纯检索差距；
- 不能把 GPT-5.4 相对 GPT-5 的 2.53 pp 全部归因于基础模型，因为 API style 和 reasoning 配置也不同；
- 不能用 90.45% QA accuracy 替代 Hit@200、Mean Evidence Recall 或 Complete Recall。

### 12.3 后续轨道

若要进一步接近 Zep 官网的输入契约，应单独建立 Information Extraction / Structured Memory 轨道：

1. 从 raw turn 抽取事实、实体和实际事件时间；
2. 保留 raw episode provenance；
3. 固定抽取模型、Prompt、版本和失败重试；
4. 对抽取后的 memory 重新导入并重新检索；
5. 同时报告 evidence recall 和端到端 QA；
6. 与本次 Raw Turn 轨道使用独立命名和独立结果目录，不覆盖本次结果。

## 13. 复现产物与哈希

### 13.1 代码

| 文件 | SHA-256 |
| --- | --- |
| `evaluate_zep_model_top200.py` | `6b8018b1708de11db6506fae027d84a1c2a8fd7dd3c7e6daac6db3958a17552c` |
| `run_zep_model_top200_qa_judge.sh` | `55f7b4a3089765e9402d72f745ec7ccd33df37aa27d3993db32fce0e5c79180a` |
| `mem0_prompts.py` | `83486e0ac192e5809f0a2ebb614693bf20197b3d7fee5cf2d0df3f2c69a8e9e9` |

上述 SHA-256 是正式实验运行时记录的代码内容哈希。脚本目录本轮统一整理到
`memoria/scripts/`；正式 run 中的原始 manifest 和 JSONL 保持不变。

当前对应文件：

- [`evaluate_zep_model_top200.py`](../scripts/locomo/evaluate_zep_model_top200.py)
- [`run_zep_model_top200_qa_judge.sh`](../scripts/locomo/run_zep_model_top200_qa_judge.sh)
- [`evaluate_top200.py`](../scripts/locomo/evaluate_top200.py)：提供共享的数据、Prompt 构造与指标逻辑
- [`mem0_prompts.py`](../scripts/locomo/mem0_prompts.py)
- [`README.md`](../scripts/locomo/README.md)：从导入、Top-200 检索到 QA 的完整流程

运行入口：

```bash
cd /Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark
./memoria/scripts/locomo/run_zep_model_top200_qa_judge.sh full
```

脚本支持断点续跑：已经成功的 Reader 或 Judge 记录不会重复调用；失败记录追加到 JSONL 并保留审计历史。
在正式 Top-200 snapshot 已保留的情况下，该命令不会重新调用 Memoria 检索。

### 13.2 主实验结果

结果目录：

```text
memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/evaluation/
zep-model-aligned-gpt54-medium-mem0-prompt-top200-aihubmix-full1540-v1/
```

| 文件 | 作用 | SHA-256 |
| --- | --- | --- |
| `manifest.json` | 冻结输入、模型、Prompt、运行参数 | `e4d694360f02ea4a3fe0165176dc336a3f2e9aafccb637c4aa9598f83ebd7b3c` |
| `answers.jsonl` | Reader 原始输出、usage、latency、hash | `a176dc4ef1b1b0f810317d985141448e7b31ed1ccc763636ec384d801b89f43a` |
| `judgments.jsonl` | Judge 原始输出、reasoning、label | `10e0f1b3bfac42dc72e9fc306155d4738024536647997c197920018fd370a3b9` |
| `errors.jsonl` | 43 条历史余额错误，均已恢复 | `c528b698954fc8009b9586ff80bccdc36e1ec03384fef336ce0f102d0803a979` |
| `metrics.json` | 可复算汇总 | `be83eef9f7c1362b5b1ad1bc5e861a4a160b3fded5de12bf3d1751374cb4be53` |
| `summary.json` | 最终验收摘要 | `63825832b4e79a5b1c3d02d90a6c84b3008706eadebbf42fb3e5b417b013c906` |
| `report.md` | 运行目录自动摘要 | `3ff719a34d2d760c2cebe0f0fd332f315e3838a0e387ebbe009e9ee05cce7e9d` |

### 13.3 对照实验目录

GPT-5 + Mem0 Prompt 同协议：

```text
memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/evaluation/
mem0-compatible-gpt5-reader-judge-top200-aihubmix-full1540-v1/
```

旧 Zep-Prompt 派生消融：

```text
memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/evaluation/
memoria/runs/archive/locomo/zep-model-judge-aligned-gpt54-medium-rawturn-top200-aihubmix-full1540-v2/
```

正式验收以 `manifest.json` 的冻结配置、每题最新成功 JSONL 状态以及 `summary.json` 的 `complete: true` 联合判断，不以 JSONL 总行数替代唯一题状态。
