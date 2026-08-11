# Memoria LoCoMo Raw Turn 对标 Zep 实验结果

> 实验状态：**COMPLETE**  
> 数据范围：LoCoMo Category 1–4，10 个 sample，1,540 题  
> 记忆轨道：Controlled Track / Raw Turn，一条原始 turn 存为一条 memory  
> 主结果：Top-200，GPT-5.4 medium Reader + GPT-5.4 medium Zep Judge，**1,240/1,540 = 80.52%**  
> 实验完成时间：2026-08-10 20:58:04（北京时间）  
> 报告核对时间：2026-08-11（北京时间）

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
| End-to-End QA | **80.52%（1,240/1,540）** |

本次结果的可辩护表述是：

> Memoria 在 LoCoMo Category 1–4、Raw Turn 直存、Qwen `text-embedding-v4`/1,024 维、Top-200 条件下，Reader/Judge 均使用 `gpt-5.4` 和 `reasoning=medium`，采用适配 raw turn 时间语义的 Reader Prompt 和 Zep 官方仓库公开的 Judge Prompt，端到端问答准确率为 **80.52%**。

本实验对齐了 Zep 的 Reader/Judge 模型名、官网明确披露的 Reader reasoning effort 和官方仓库公开的 Judge Prompt；Judge `reasoning=medium` 是本实验的固定选择，Zep 官网只将 Judge 描述为 chain-of-thought grading。实验没有复现 Zep 的图构建、事件时间抽取、五路 multi-scope retrieval、Cross-encoder 或上下文结构。因此应称为：

> **Zep Model/Judge Aligned + Raw-Turn-Adapted Reader**

不能称为“严格复现 Zep 94.7%”。

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

每个 LoCoMo sample 对应一个隔离用户；QA 只访问所属 sample 的 memory。

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

本实验复用已验收的 Raw Turn 数据和同一份不可变 Top-200 检索快照，没有重新导入或重新检索。

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

`MRR@200 = 0.057744`。Top-200 Complete Recall 的分母是 1,536 道有 evidence 的题。

## 4. Zep 公开参考配置

截至 2026-08-11，[Zep Research 页面](https://www.getzep.com/research/)公布的 LoCoMo 配置为：

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

Zep 官网没有披露当前实验的图构建/信息抽取模型、Embedding 型号和 Cross-encoder 型号。

官网分类数与 Overall 仍无法相互核验：分类正确数合计 1,436、题数合计 1,539，但 Overall 写为 1,459/1,540。本文只把 94.7% 作为 Zep 官网公开参考，不用分类数字重算其总分。

## 5. 本次 Reader/Judge 协议

### 5.1 模型与 API

| 项目 | Reader | Judge |
| --- | --- | --- |
| 请求模型 | `gpt-5.4` | `gpt-5.4` |
| API 返回模型 | `gpt-54`，1,540/1,540 | `gpt-54`，1,540/1,540 |
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

环境：

| 项目 | 值 |
| --- | --- |
| OS | macOS 14.5 arm64 |
| Python | 3.11.13 |
| OpenAI Python SDK | 1.109.1 |

### 5.2 Prompt 来源与冻结

Zep 官方 Prompt 来源固定为 `getzep/zep` commit
[`ba4fc3cc5b00cda7dde63833007467ffd6cba3a8`](https://github.com/getzep/zep/commit/ba4fc3cc5b00cda7dde63833007467ffd6cba3a8)
下的
[`benchmarks/locomo/prompts.py`](https://github.com/getzep/zep/blob/ba4fc3cc5b00cda7dde63833007467ffd6cba3a8/benchmarks/locomo/prompts.py)。

该文件是 Zep 官方仓库公开的 LoCoMo Prompt 实现，但 Zep Research 页面没有提供与 94.7% run 一一对应的 manifest、commit 或逐题产物。因此本文把它称为“Zep 官方仓库公开 Prompt”，不声称已经证明它与官网 94.7% run 的实际 Prompt 字节级一致。

| Prompt | 使用方式 | SHA-256 |
| --- | --- | --- |
| Zep context template | 仅作为官方来源冻结；v2 Reader 不直接使用 | `f257da19d7bfa582a44cad7c833388523adf5d4985e0d53009e6e817e3379c07` |
| Zep Reader system | **逐字使用** | `406d340c8d410efdafc7748a4e469e3916fbcf71b4bfab546c3188d0b914af25` |
| Zep Reader user | 保留官方版本供审计；v2 使用 raw-turn adapter | `d2a51881a50b8a9828c9c1cac4106c6732dbe75e054d7e8533bf110c5f69da58` |
| Zep Judge system | **逐字使用** | `5ad9b31f3ac100dcb5d025460d524a166cf51d68ab03ff67544bd7897691304f` |
| Zep Judge user | **逐字使用** | `f662eda63c31a0f5663003bbf171b5ec9903f2a7a3f7eee1b83a2c0d8cb4cb5f` |
| Raw-turn context template | 本实验新增 | `601a3d98f2c5c09248fe2a9d7c41153bff1ad73e4f1e474370fe835725f38352` |
| Raw-turn Reader user adapter | 本实验新增 | `e2273012012c559466bf7a1353acaf511763310c869930bbfa77ac1f9fadcaff` |

本地 Prompt module SHA-256：
`a5974187b6106868089e673ab683b83208ce8d4884fd0e6fd55978f0f01ce07f`。

### 5.3 为什么 Reader 必须适配 raw turn

Zep 官方 Reader Prompt 的输入契约是：`fact.valid_at` 已经由图构建阶段解析为事件真正发生的时间。因此官方 Prompt 明确要求模型相信 fact timestamp，而不是重新解释 turn 中的 `yesterday`、`last week`。

Memoria 本次轨道直接存原始 turn，只有消息/session 时间，没有事件时间抽取。若把 session 时间伪装成 `event_time`，会系统性导致日期晚一天、晚一周或晚一个月。

v2 的适配方式：

| 项目 | v2 规则 |
| --- | --- |
| 上下文标签 | `<MEMORIES>` |
| 每条时间字段 | `message_time` |
| 时间语义 | 消息发送时间，不是事件发生时间 |
| `yesterday` | 相对该 memory 的 `message_time` 减一天 |
| `last week` | 相对 message time 解析为前一周 |
| `last month` | 相对 message time 解析为前一自然月 |
| 扫描 | 要求从头到尾扫描 Top-200，不在首个相关项停止 |
| 多跳 | 要求跨 memory 组合并核对人物归属 |
| 展示顺序 | 保留 Top-200 检索排名顺序 |

该适配只改变 Reader user prompt 和 raw-turn context template；Zep Judge system/user Prompt 未改动。

### 5.4 Judge 评分边界

Zep Judge 要求先给一句解释，最后只输出 `CORRECT` 或 `WRONG`。它明确允许语义相同、答案更长、日期格式不同但实际日期/时期相同。

相较本地 Mem0 对标实验使用的 Judge，Zep Judge 在以下方面更严格：

- 没有“列表中任意一项命中即正确”的强制 partial-credit 规则；
- 没有日期 ±14 天容差；
- 没有时长 ±50% 容差；
- 更容易因列表不完整、日期偏差或最终结论冲突判 `WRONG`。

因此 Zep-aligned 与 Mem0-aligned 分数同时包含 Reader Prompt、Reader 模型和 Judge 规则差异，不能把分差解释为 memory backend 差异。

## 6. 无效 v1 预实验与纠正

正式 v2 前曾运行一个 v1 小样本。v1 将原始 turn 的 session 时间写入 Zep `event_time` 字段，同时逐字使用 Zep Reader Prompt。前 73 个有效 Judge 中仅 42 个正确，且 temporal 题稳定出现：

```text
gold 2023-05-07 -> answer 2023-05-08
gold 2023-01-19 -> answer 2023-01-20
gold 2022-12-21 -> answer 2022-12-22
```

根因是输入契约错误，而不是 GPT-5.4 调用失败：Zep Prompt 假设 timestamp 已是事件时间，raw turn 的 timestamp 实际是消息时间。v1 随即停止，preflight/full 目录均已删除，不纳入任何正式结果。

v2 改为 `message_time` 并显式解析相对时间。已知 temporal 回归题恢复正确，包括 5 月 7 日、1 月 19 日、12 月 21 日以及 `last week`、`last month` 问题。最终 temporal 为 271/321，84.42%。

## 7. 完整性与断点验收

### 7.1 最终状态

| 项目 | 结果 |
| --- | ---: |
| Selected questions | 1,540 |
| Unique latest Reader records | 1,540 |
| Latest Reader success/completed | 1,540/1,540 |
| Unique latest Judge records | 1,540 |
| Latest Judge success/completed | 1,540/1,540 |
| Missing answers | 0 |
| Missing judgments | 0 |
| Final complete | `true` |

### 7.2 历史失败与恢复

JSONL 是 append-only checkpoint，因此文件行数大于问题数：

| 文件 | 总行数 | 唯一题 | 历史失败 | 最终成功 |
| --- | ---: | ---: | ---: | ---: |
| `answers.jsonl` | 1,554 | 1,540 | 14 | 1,540 |
| `judgments.jsonl` | 1,555 | 1,540 | 15 | 1,540 |
| `errors.jsonl` | 29 | — | 29 | — |

14 个 Reader 历史失败来自 AiHubMix 余额不足；15 个 Judge 历史失败来自响应同时包含 `CORRECT` 和 `WRONG`，被严格解析器拒绝。断点续跑后全部补成功。正式计分使用每题最后一条记录，历史失败不进入最终分母或分子。

实验窗口从 manifest 创建到 summary 完成为约 43 分 35 秒；其中包含余额不足后的中断和续跑，不应解释为纯模型运行耗时。

## 8. 最终问答结果

### 8.1 Overall 与分类

| Category | 正确 | 错误 | 总数 | Accuracy |
| --- | ---: | ---: | ---: | ---: |
| Multi-hop | 181 | 101 | 282 | 64.18% |
| Temporal | 271 | 50 | 321 | **84.42%** |
| Open-domain | 57 | 39 | 96 | 59.38% |
| Single-hop | 731 | 110 | 841 | **86.92%** |
| **Overall** | **1,240** | **300** | **1,540** | **80.52%** |

### 8.2 按 Top-200 evidence 状态

| Evidence 状态 | 正确 | 错误 | 总数 | Accuracy |
| --- | ---: | ---: | ---: | ---: |
| Complete | 1,060 | 92 | 1,152 | **92.01%** |
| Partial | 110 | 83 | 193 | 56.99% |
| Missing | 66 | 125 | 191 | 34.55% |
| No evidence annotation | 4 | 0 | 4 | 100.00% |

300 道错误中，208 道发生在 evidence partial/missing 状态，占 69.33%。在完整召回全部标注 evidence 时，Reader + Judge 达到 92.01%。

该分组说明：

1. Top-200 evidence completeness 是端到端表现的首要分层变量；
2. Multi-hop Complete Recall@200 只有 35.11%，与其最低问答准确率一致；
3. 仍有 92 道题在 evidence 完整时判错，包含 Reader 去重、跨 turn 组合、图片 caption 推断、时间标注歧义以及 Judge 严格度问题。

### 8.3 按 sample

| Sample | 正确 | 总数 | Accuracy |
| --- | ---: | ---: | ---: |
| `conv-26` | 130 | 152 | 85.53% |
| `conv-30` | 72 | 81 | **88.89%** |
| `conv-41` | 121 | 152 | 79.61% |
| `conv-42` | 156 | 199 | 78.39% |
| `conv-43` | 131 | 178 | 73.60% |
| `conv-44` | 102 | 123 | 82.93% |
| `conv-47` | 114 | 150 | 76.00% |
| `conv-48` | 156 | 191 | 81.68% |
| `conv-49` | 128 | 156 | 82.05% |
| `conv-50` | 130 | 158 | 82.28% |

### 8.4 Token 与延迟

| 指标 | Reader | Judge |
| --- | ---: | ---: |
| Calls | 1,540 | 1,540 |
| Input tokens | 26,904,702 | 669,057 |
| Output tokens | 486,231 | 126,744 |
| Reasoning tokens | 415,772 | 75,616 |
| Total tokens | 27,390,933 | 795,801 |
| Latency p50 | 5,012.3 ms | 2,473.9 ms |
| Latency p95 | 13,612.3 ms | 4,821.9 ms |
| Latency max | 37,319.7 ms | 10,730.2 ms |

Reader 每题平均约 17,471 input tokens。其上下文显著大于 Zep 官网报告的 5,760-token 中位上下文；二者输入构造不同，不能据此直接比较服务效率。

## 9. 与本地 Mem0-aligned 实验对比

两次本地实验使用完全相同的 Memoria 导入数据和 Top-200 检索 snapshot，只改变 Reader/Judge 下游协议。

| Category | Zep Model/Judge Aligned | Mem0 Prompt/Judge Aligned | 差值 |
| --- | ---: | ---: | ---: |
| Multi-hop | 64.18%（181/282） | 87.23%（246/282） | -23.05 pp |
| Temporal | 84.42%（271/321） | 90.65%（291/321） | -6.23 pp |
| Open-domain | 59.38%（57/96） | 71.88%（69/96） | -12.50 pp |
| Single-hop | 86.92%（731/841） | 88.94%（748/841） | -2.02 pp |
| **Overall** | **80.52%（1,240/1,540）** | **87.92%（1,354/1,540）** | **-7.40 pp** |

逐题交叉：

| Zep-aligned | Mem0-aligned | 题数 |
| --- | --- | ---: |
| CORRECT | CORRECT | 1,213 |
| WRONG | WRONG | 159 |
| WRONG | CORRECT | 141 |
| CORRECT | WRONG | 27 |

差值最大的是 Multi-hop。主要协议差异：

| 项目 | Zep-aligned v2 | Mem0-aligned |
| --- | --- | --- |
| Reader | GPT-5.4，medium | GPT-5 |
| API | Responses | Chat Completions |
| Reader Prompt | Zep-derived raw-turn adapter | Mem0 强扫描/组合 Prompt |
| Memory 展示顺序 | 检索排名顺序 | Top-200 先选取，再按 session 时间排序 |
| Judge | Zep 官方 Judge | Mem0 宽松 Judge |
| 列表 partial credit | 未明确允许 | 命中任一 gold item 即正确 |
| 日期容差 | 同日期/同时间段 | ±14 天 |
| Category 3 gold | 原始完整 gold | 分号前第一部分 |

所以 7.40 个百分点是完整下游协议差异，不是 GPT-5.4 与 GPT-5 的单变量能力差异。

## 10. 与 Zep 官网结果对比

| 实验 | 正确 | Accuracy |
| --- | ---: | ---: |
| Memoria Raw Turn / Zep Model-Judge Aligned v2 | 1,240/1,540 | **80.52%** |
| Zep 官网公开 Overall | 1,459/1,540 | **94.7%** |
| 差值 | -219 | **-14.22 pp** |

该比较只能作为公开参考，不能解释为严格的 memory backend 排名。

| 维度 | Memoria 本次实验 | Zep 官网实验 |
| --- | --- | --- |
| Memory | 原始 turn，一 turn 一 memory | 图事实、实体、原始 episode、summary、observation |
| 时间 | Reader 从 message time 解析相对时间 | 图构建阶段生成 fact event time |
| Embedding | Qwen `text-embedding-v4`/1,024 | 未披露 |
| 检索 | 单路 Memoria Top-200 hybrid | 五路 multi-scope，共 50 个 scope items |
| Reranker | Memoria 当前 hybrid score | 未披露型号的 Cross-encoder |
| Reader | GPT-5.4 medium，raw-turn adapter | GPT-5.4 medium |
| Judge | Zep 官方 Prompt，GPT-5.4 medium | GPT-5.4，CoT grading；官网未单独写 Judge reasoning effort |
| 上下文规模 | Reader 平均约 17.5K input tokens | 中位 5,760 context tokens |
| 逐题产物 | 完整本地 JSONL | 官网未提供下载入口 |

## 11. 结果解释与后续实验

### 11.1 当前结论

- v2 完整、可复算，80.52% 是本次正式结果。
- GPT-5.4 medium 调用正常；所有最终响应均为 `completed`。
- v1 的系统性时间错误已消除；temporal 达到 84.42%。
- 完整 evidence 条件下准确率为 92.01%，说明 Reader/Judge 在证据充分时整体可靠。
- 端到端主要短板仍是 Multi-hop evidence completeness，其次是 Zep Judge 对列表完整性和日期的严格判定。

### 11.2 下一条公平实验轨道

若要进一步接近 Zep 官网输入契约，应单独建立 Information Extraction / Structured Memory 轨道：

1. 从 raw turn 抽取事实、实体和实际事件时间；
2. 保留 raw episode provenance；
3. 将抽取后的 event time 交给逐字 Zep Reader Prompt；
4. 固定抽取模型、Prompt、版本、失败重试和导入验收；
5. 重新检索并同时报告 evidence recall 与端到端 QA；
6. 与当前 Raw Turn 轨道分开命名、分开结果目录，不覆盖本次结果。

## 12. 复现产物与哈希

### 12.1 代码

| 文件 | SHA-256 |
| --- | --- |
| `evaluate_zep_top200.py` | `fc53b77df98cce175559e382aabb1bde0bf3e1c09fc7e9bbe2cfc85440058a79` |
| `zep_prompts.py` | `a5974187b6106868089e673ab683b83208ce8d4884fd0e6fd55978f0f01ce07f` |
| `run_zep_top200_qa_judge.sh` | `ef02393a4a36e98283c980ad1f1097e943e08ec564c28190a9e6268a028d8b5a` |

### 12.2 结果

结果目录：

```text
memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/evaluation/
zep-model-judge-aligned-gpt54-medium-rawturn-top200-aihubmix-full1540-v2/
```

| 文件 | 作用 | SHA-256 |
| --- | --- | --- |
| `manifest.json` | 冻结输入、模型、Prompt、运行参数 | `72066e4bf0d101a57d9e2e53cf6a8d5e9b9622f1c194768baa437a891facfea8` |
| `answers.jsonl` | Reader 原始输出、usage、latency、hash | `682db5c1737fec312168308844bc33d9e5bc0d0b0b2941d3510543ae141082fb` |
| `judgments.jsonl` | Judge 原始输出、reasoning、label | `91ad06184e1989e891b19dd97edf9b1704dcb2588ea487444e2c68629404fe43` |
| `errors.jsonl` | 历史失败，均已恢复 | `990be6f715cd7ff14111c72f18fdd0ab319c17542ea4fb51a282c5a550b88784` |
| `metrics.json` | 可复算汇总 | `a6b0112a087911910a5f305965cb02bece9a17bb0324da19d373c1d779dd6a30` |
| `summary.json` | 最终验收摘要 | `9ef88783633e5a62e87808187750e4672eb5d7fa9dc0c3f049d79da2a83739e8` |

正式验收以 `manifest.json` 的冻结配置、每题最新 JSONL 状态以及 `summary.json` 的 `complete: true` 联合判断，不以 JSONL 总行数代替唯一题状态。
