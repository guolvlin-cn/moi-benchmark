# Memoria LoCoMo Raw Turn 对标 Mem0 实验结果

> 实验状态：**COMPLETE**  
> 数据范围：LoCoMo Category 1–4，10 个 sample，1,540 题  
> 记忆轨道：Controlled Track / Raw Turn，一条原始 turn 存为一条 memory  
> 主结果：Top-200，GPT-5 Reader + GPT-5 Judge，**1,354/1,540 = 87.92%**  
> 实验时间：导入 2026-08-08（北京时间）；检索与问答 2026-08-10（北京时间）  
> 对齐基线：Mem0 `memory-benchmarks` commit `4b61c5d31b9c668a12b4f5e78064248a02c82d2b`

## 1. 结论摘要

| 维度 | Memoria 本次结果 |
| --- | ---: |
| 导入验收 | 5,882/5,882 active memories，0 失败，0 缺失，0 多余 |
| 检索成功率 | 1,540/1,540（100%） |
| Hit@200 | 87.57%（1,345/1,536） |
| Mean Evidence Recall@200 | 81.62% |
| Complete Recall@200 | 75.00%（1,152/1,536） |
| End-to-End QA | **87.92%（1,354/1,540）** |
| Reader/Judge 最终完整性 | 1,540/1,540 + 1,540/1,540 |

本次结果的可辩护表述是：

> Memoria 在 LoCoMo Category 1–4、Raw Turn 直存、Qwen `text-embedding-v4`/1,024 维、Top-200，并使用与 Mem0 固定 commit 一致的 GPT-5 Reader/Judge Prompt 时，端到端问答准确率为 **87.92%**。

与 Mem0 的主要对齐项是问题范围、Top-K、Reader/Judge 模型名、Prompt 和评分规则；两个系统的 memory 构造、Embedding、检索后端和 LLM provider 不完全一致，因此分差不能全部归因于 memory backend。

## 2. 数据集与评测范围

### 2.1 数据冻结

| 项目 | 固定值 |
| --- | --- |
| 数据集 | LoCoMo / `locomo10.json` |
| SHA-256 | `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4` |
| Sample | 10 |
| Session | 272 |
| Dialogue turn | 5,882 |
| 全部 QA | 1,986 |
| 本次 QA | Category 1–4，1,540 |
| 排除 | Category 5 adversarial，446 |
| 有可用 evidence 的题 | 1,536 |
| 无 evidence 的题 | 4，均属于 Category 3 |
| Evidence normalization 有记录的题 | 13 |

问题类型分布：

| Category | 类型 | 题数 |
| --- | --- | ---: |
| 1 | Multi-hop | 282 |
| 2 | Temporal | 321 |
| 3 | Open-domain | 96 |
| 4 | Single-hop | 841 |
| **合计** |  | **1,540** |

### 2.2 Sample 规模

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

每个 sample 对应一个隔离用户；每用户平均 588.2 条 memory，最少 369，最多 689。

## 3. Memoria 版本与运行配置

### 3.1 代码版本

| 项目 | 值 |
| --- | --- |
| Memoria 仓库 | `matrixorigin/Memoria` |
| 基础 commit | [`54c9114fd6888e11821edc2ee9acd570c17c5ee3`](https://github.com/matrixorigin/Memoria/commit/54c9114fd6888e11821edc2ee9acd570c17c5ee3) |
| Commit 日期 | 2026-08-03 14:55:10 +08:00 |
| Commit 标题 | `feat: support extra metadata in batch write (#223)` |
| 导入补丁 SHA-256 | `a668ae33c3c5e4fd83f642c75003e1d299f81c039ca300bb4c89996bf7aca128` |
| Top-K 路由文件 SHA-256 | `51eeb10a76158b93e9cfb463ac5b5bf07c7a56e6d59ff84e36c697c3bbeaeaa9` |

运行时不是纯 commit checkout，而是“基础 commit + 两项 benchmark 补丁”：

1. `MEMORIA_SENSITIVITY_FILTER_ENABLED=false`：对公开合成 benchmark 做字节级直存，避免敏感词过滤改写原始 turn；生产默认仍为启用。
2. API 的 `retrieve/search` Top-K 上限从 100 调到 200；其他检索公式未因本次实验改动。

### 3.2 环境

| 项目 | 值 |
| --- | --- |
| OS | macOS 14.5 arm64 |
| Python | 3.11.13 |
| OpenAI Python SDK | 1.109.1 |
| Memoria API | `http://127.0.0.1:8100` |
| 数据存储 | Memoria 本地 MatrixOne 运行时 |

## 4. Memory 导入方案与验收

### 4.1 映射

```text
sample_id     -> X-Impersonate-User: locomo-qwen-v4-{sample_id}
session_n     -> Memoria session_id
dialogue turn -> one semantic memory
dia_id        -> subject_id + extra_metadata.dia_id
```

| 项目 | 配置 |
| --- | --- |
| 导入轨道 | Controlled Track，直接 `POST /v1/memories` |
| 粒度 | 一条 turn 导入为一条 memory |
| Memory type | `semantic` |
| Native extraction | 关闭，`internal_llm=false` |
| QA 写入 | 禁止 |
| 排除字段 | `qa` / `observation` / `session_summary` / `event_summary` |
| 图像 | `blip_caption` 追加到 content，`img_url` 保留在 metadata |
| 时间 | `relative_shift_per_sample_v1` |
| 时间公式 | `observed_at = run_anchor - (sample_max_date - session_date)` |
| 去重分区 | `subject_id=dia_id` |
| 恢复键 | deterministic `ingest_key` |
| 客户端限制 | 7,000 tokens / 30,720 bytes |
| Embedding | DashScope `text-embedding-v4` |
| Embedding 维度 | 1,024 |
| 导入并发 | 1 worker |
| 导入耗时 | 1,084.827 s |

Reader 展示日期时没有直接使用平移后的 `observed_at`，而是通过 `dia_id` 回连 LoCoMo 原始 `session_n_date_time`，以与 Mem0 的原始会话日期排序语义一致。

### 4.2 导入验收

| 验收项 | 结果 |
| --- | ---: |
| Selected samples | 10/10 |
| Completed samples | 10/10 |
| Sessions | 272 |
| Expected memories | 5,882 |
| Accepted active memories | 5,882 |
| Failed memories | 0 |
| Missing `ingest_key` | 0 |
| Extra `ingest_key` | 0 |

验收以最终 active memory 与预期 `ingest_key` 对账为准，不以客户端 checkpoint 数量代替最终状态。

## 5. 检索实验

### 5.1 检索配置

| 项目 | 值 |
| --- | --- |
| Endpoint | `POST /v1/memories/retrieve` |
| Query | 原始 LoCoMo `question`，不改写 |
| Top-K | 200 |
| 离线 cutoff | 10 / 20 / 50 / 200，都来自同一份 Top-200 snapshot |
| Explain | `verbose` |
| Workers | 10 |
| Timeout | 120 s |
| Client retries | 3 |
| 用户范围 | 仅问题所属 sample 的隔离用户 |
| 返回验证 | 必须恰好 200 条，且无跨用户、重复 ID、缺失 provenance |

本次 1,540 题的 `explain.path` 均为 `hybrid`；图检索尝试 1,540 次但未返回图候选，后续混合检索全部成功，没有进入最终纯 full-text fallback。

当前 commit 中的混合排序为：

```text
final_score = 0.3 * vector_score
            + 0.2 * keyword_score
            + 0.2 * temporal_score
            + 0.3 * confidence_score
```

其中候选预取 `fetch_k=max(3*top_k, 20)=600`，temporal decay 常数为 168 小时，有效 confidence 小于 0.05 的 memory 被过滤；本实验没有提交用户反馈。

### 5.2 检索完整性与性能

| 项目 | 结果 |
| --- | ---: |
| Snapshot records | 1,540 |
| Valid retrievals | 1,540/1,540 |
| Failed/invalid | 0 |
| First-pass success | 1,517/1,540（98.51%） |
| 返回数 | 每题 200 |
| 跨用户或重复 | 0 |
| Client latency P50 / P95 | 799.1 / 2,032.4 ms |
| Client latency max | 12,564.3 ms |
| Server total P50 / P95 | 748.7 / 1,981.1 ms |
| Query embedding P50 / P95 | 177.8 / 251.4 ms |
| Hybrid vector phase P50 / P95 | 548.0 / 1,591.2 ms |
| 全量检索 wall time | 174.306 s |

### 5.3 检索质量

严格检索指标分母是 1,536 道有规范化 evidence 的题；4 道无 evidence 题不进入该分母。

| 指标 | @10 | @20 | @50 | @200 |
| --- | ---: | ---: | ---: | ---: |
| Evidence Hit | 11.26% | 21.94% | 48.05% | **87.57%** |
| Mean Evidence Recall | 9.46% | 18.94% | 42.49% | **81.62%** |
| Complete Recall | 8.33% | 16.86% | 38.61% | **75.00%** |

`MRR@200 = 0.057744`。

Top-200 分类结果：

| Category | Evidence N | Hit@200 | Mean Recall@200 | Complete Recall@200 |
| --- | ---: | ---: | ---: | ---: |
| Multi-hop | 282 | 86.17% | 62.28% | 35.11% |
| Temporal | 321 | 91.90% | 89.80% | 87.23% |
| Open-domain | 92 | 73.91% | 60.12% | 47.83% |
| Single-hop | 841 | 87.87% | 87.34% | 86.68% |

Multi-hop 的 Hit@200 为 86.17%，但 Complete Recall@200 只有 35.11%，是当前检索最明显的薄弱项：系统往往能找到一部分线索，但难以召回多跳题标注的全部 supporting turns。

## 6. Reader/Judge 协议

### 6.1 模型与 API 参数

| 项目 | Reader | Judge |
| --- | --- | --- |
| 请求模型 | `gpt-5` | `gpt-5` |
| API 返回模型 | `gpt-5-2025-08-07`，1,540/1,540 | `gpt-5-2025-08-07`，1,540/1,540 |
| Provider/API | AiHubMix OpenAI-compatible / `https://aihubmix.com/v1` | 同左 |
| API style | Chat Completions | Chat Completions + `json_object` |
| Max completion tokens | 4,096 | 4,096 |
| Temperature | GPT-5 不传参，使用 provider default | 同左 |
| Timeout | 120 s | 120 s |
| Max retries | 5 | 5 |
| RPM | 每 client 200 | 每 client 200 |
| 并发 | 10 个 sample 并发，sample 内按题目顺序 | 同一题紧随 Reader |

### 6.2 Prompt 冻结

Prompt 逐字固定自 Mem0 commit
[`4b61c5d31b9c668a12b4f5e78064248a02c82d2b`](https://github.com/mem0ai/memory-benchmarks/commit/4b61c5d31b9c668a12b4f5e78064248a02c82d2b)
的 [`benchmarks/locomo/prompts.py`](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/benchmarks/locomo/prompts.py)。本地完整文本保存在 [`mem0_prompts.py`](../benchmark/locomo/mem0_prompts.py)，不在本报告再维护第二份副本，以避免文本漂移。

| Prompt | SHA-256 |
| --- | --- |
| Reader `ANSWER_GENERATION_PROMPT` | `79c9f09bcc8d5e9e8b7e9786af587b02a67d366ab79285fc148b73fd20f6297b` |
| Judge system prompt | `36c007917faf1ab84516cdca577fb523711a9b993706fbae8ae37806e6f9adcc` |
| Judge prompt（without evidence） | `d248e056d993725e28fba8d16ca7081f0b59deae272ef294f3c6b00d48eac02b` |
| 本地 Prompt module | `83486e0ac192e5809f0a2ebb614693bf20197b3d7fee5cf2d0df3f2c69a8e9e9` |

Judge system prompt 原文：

```text
You are evaluating conversational AI memory recall. Return JSON only with the format requested.
```

Reader 的主要规则是扫描所有 memory、实体校验、跨 memory 组合、优先具体信息、以 LoCoMo 原始日期做时间推理、列表/计数完整性检查，并在 `ANSWER:` 后输出最终答案。

Judge 的主要规则是：

- gold 列表中至少一项正确即可给 partial credit；
- 允许语义等价的改写和额外细节；
- 日期允许 ±14 天，时长允许 50% 误差；
- 接受 semantic overlap 和 same referent；
- 只有零正确项或完全不同主题才判 `WRONG`；
- 输出一句 `reasoning` 和 `CORRECT/WRONG` label。

该 Judge 规则相对宽松，但它就是 Mem0 基线的同一规则；本实验没有额外放宽。

### 6.3 Reader 输入组织

| 项目 | 值 |
| --- | --- |
| Memory 数 | 每题 Top-200 |
| 选择顺序 | 先取检索排名 Top-200 |
| Prompt 展示顺序 | 再按原始 session 时间从旧到新稳定排序 |
| 排名/分数 | 不向 Reader 展示 |
| Reference date | 该 sample 最后一个原始 session 日期 |
| User profile | 关闭 |
| Judge evidence | 关闭 |
| Category 3 gold | 与 Mem0 一致，只使用分号前的第一部分 |
| Reader 答案抽取 | 取最后一个 `ANSWER:` 之后的文本 |

## 7. 端到端问答结果

### 7.1 Overall 与分类

| Category | 正确 | 错误 | 总数 | Accuracy |
| --- | ---: | ---: | ---: | ---: |
| Multi-hop | 246 | 36 | 282 | 87.23% |
| Temporal | 291 | 30 | 321 | **90.65%** |
| Open-domain | 69 | 27 | 96 | 71.88% |
| Single-hop | 748 | 93 | 841 | 88.94% |
| **Overall** | **1,354** | **186** | **1,540** | **87.92%** |

验收状态：

```text
successful_answers:   1540 / 1540
successful_judgments: 1540 / 1540
complete:             true
```

### 7.2 按 Top-200 evidence 状态拆分

| Evidence 状态 | 正确 | 错误 | 总数 | QA Accuracy |
| --- | ---: | ---: | ---: | ---: |
| Complete：全部标注 evidence 召回 | 1,094 | 58 | 1,152 | 94.97% |
| Partial：只召回部分 | 164 | 29 | 193 | 84.97% |
| Missing：标注 evidence 全部未命中 | 92 | 99 | 191 | 48.17% |
| No evidence：数据无可用标注 | 4 | 0 | 4 | 100.00% |

1,354 道正确题由 `1094 + 164 + 92 + 4` 构成。因此 QA 87.92% 不等于检索完整率；Complete Recall@200 要求一题的全部标注 evidence 都命中，而 Judge 只要答案达到 Mem0 的正确性规则即可判对。

Category × evidence 状态（格式为 `correct/total`）：

| Category | Complete | Partial | Missing | No evidence |
| --- | ---: | ---: | ---: | ---: |
| Multi-hop | 92/99 | 130/144 | 24/39 | — |
| Temporal | 266/280 | 10/15 | 15/26 | — |
| Open-domain | 40/44 | 15/24 | 10/24 | 4/4 |
| Single-hop | 696/729 | 9/10 | 43/102 | — |

### 7.3 LLM 运行量与成功响应性能

| 指标 | Reader | Judge |
| --- | ---: | ---: |
| 最终成功 calls | 1,540 | 1,540 |
| Prompt tokens | 26,008,417 | 1,146,786 |
| Completion tokens | 1,794,077 | 323,014 |
| Total tokens | 27,802,494 | 1,469,800 |
| 平均 prompt tokens/call | 16,888.58 | 744.67 |
| 平均 completion tokens/call | 1,164.99 | 209.75 |
| 平均 total tokens/call | 18,053.57 | 954.42 |
| Latency P50 | 16,077.8 ms | 4,107.6 ms |
| Latency P95 | 35,997.6 ms | 7,700.0 ms |
| Latency max | 141,167.7 ms | 125,076.5 ms |

Reader + Judge 最终成功响应中记录的 usage 合计 **29,272,294 tokens**。该数字不包含失败、空输出或重试请求中未被 runner 保存的 usage，因此不等于 provider 计费总 token。成功记录和一次最终失败记录可确认的请求尝试数为 Reader 1,574、Judge 1,542。本报告不根据 OpenAI 公开价格估算费用，因为实际计费来自 AiHubMix，没有在 run manifest 中冻结当时价格。表中 latency 同样是最终成功 API 响应的延迟，不包含前置失败尝试、backoff 和人工补跑间隔。

Reader 最终成功记录的尝试次数分布：1 次 1,520 题，2 次 16 题，3 次 1 题，4 次 1 题，5 次 2 题。Judge 中 1,538 题一次成功，2 题两次成功。

全量首轮中 `conv4_q4` 的 Reader 因 `finish_reason=length` 连续 5 次空输出而失败；使用原参数断点补跑后一次成功，Judge 判为 `CORRECT`。`answers.jsonl` 因 append-only 恢复机制共 1,541 行；按 `question_id` 取最新记录后为 1,540 个唯一成功结果。

## 8. 与 Mem0 Platform v3 对比

### 8.1 协议对齐与差异

| 项目 | Memoria 本实验 | Mem0 Platform v3 公开产物 | 对齐状态 |
| --- | --- | --- | --- |
| 数据 | LoCoMo Category 1–4，1,540 | 同左 | 一致 |
| Top-K | 200 | 200 | 一致 |
| Reader | `gpt-5` | `gpt-5` | 模型名一致 |
| Judge | `gpt-5` | `gpt-5` | 模型名一致 |
| Reader/Judge Prompt | 固定 commit 的同一文本与 hash | 同一仓库 commit | 一致 |
| Judge evidence | 关闭 | artifact `with_evidence=false` | 一致 |
| User profile | 关闭 | runner 默认关闭 | 一致 |
| GPT-5 输出上限 | 4,096 | runner 默认 4,096 | 一致 |
| Temperature | GPT-5 不传参 | runner 对 GPT-5 不传参 | 一致 |
| RPM / timeout / retries | 200 / 120 s / 5 | 200 / 120 s / 5 | 一致 |
| LLM provider | AiHubMix，实际 snapshot `gpt-5-2025-08-07` | Azure，未记录返回 snapshot | 不同/信息不全 |
| Memory construction | Raw Turn 直存 | Platform v3 内部 pipeline | 不同 |
| Embedding | Qwen `text-embedding-v4`/1,024 | 未披露 | 无法对齐 |
| Retrieval | Memoria hybrid | Platform v3 内部检索 | 不同 |

因此本次是 **Mem0-compatible evaluation protocol**，不是 Mem0 Platform v3 内部 pipeline 的完全复制。可以说我们没有使用比 Mem0 更宽松的 Prompt；不能说除 memory backend 外所有条件都相同。

### 8.2 Mem0 公开数字不一致

在同一个 Mem0 commit 中，README 和逐题 JSON 存在内部不一致：

| 来源 | Mem0 Top-200 | Memoria | Memoria 相对差值 |
| --- | ---: | ---: | ---: |
| [README 标称值](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/README.md#locomo) | **1,425/1,540 = 92.5%** | 1,354/1,540 = 87.92% | **-71 题 / -4.58 pp** |
| [仓库逐题 artifact](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/results/platform/locomo_results.json) 可复算值 | **1,410/1,540 = 91.56%** | 1,354/1,540 = 87.92% | **-56 题 / -3.64 pp** |

`locomo_results.json` 本身的 `metrics_by_cutoff` 写明 1,410，对其 1,540 条唯一 evaluation 逐题求和也是 1,410；README 则写 1,425。两者相差 15 题，且在同一 commit 中同时提交，当前公开信息不足以判断哪个是最终正确值。

对外摘要可保留 Mem0 README 的 **92.5% 官方标称值**，但必须附注公开逐题 artifact 只能复算出 **91.56%**，不应把 92.5% 写成已被逐题产物验证的数字。

### 8.3 与 Mem0 逐题 artifact 的分类对比

| Category | Memoria | Mem0 artifact | 差值 |
| --- | ---: | ---: | ---: |
| Multi-hop | 87.23%（246/282） | 93.26%（263/282） | -6.03 pp |
| Temporal | 90.65%（291/321） | 92.83%（298/321） | -2.18 pp |
| Open-domain | 71.88%（69/96） | 76.04%（73/96） | -4.17 pp |
| Single-hop | 88.94%（748/841） | 92.27%（776/841） | -3.33 pp |
| **Overall** | **87.92%（1,354/1,540）** | **91.56%（1,410/1,540）** | **-3.64 pp** |

逐题 label 交叉：

| Memoria | Mem0 artifact | 题数 |
| --- | --- | ---: |
| CORRECT | CORRECT | 1,293 |
| CORRECT | WRONG | 61 |
| WRONG | CORRECT | 117 |
| WRONG | WRONG | 69 |

两者逐题 label 一致率为 88.44%。这个交叉仅用于定位差异题，不能单独证明差异来自检索、记忆构造、Reader 随机性或 Judge 稳定性中的哪一层。

## 9. 结果解读与限制

1. **QA 87.92% 不是检索召回率。** Complete Recall@200 为 75.00%，Hit@200 为 87.57%；QA 受 Reader 推理、重复信息、模型先验和 Judge 规则共同影响。
2. **本实验与 Mem0 使用同一宽松度的 Judge Prompt。** Partial credit 和 semantic overlap 不是 Memoria 额外引入的优待，Mem0 结果也使用同样规则。
3. **检索指标是 exact `dia_id` evidence 匹配。** 未命中指定 turn 但命中另一条重复表述时，检索指标仍可计 missing，Reader 却可能答对。
4. **Raw Turn 是 Controlled Track，不是 Memoria Native Track。** 它绕过 `/v1/observe` 的原生信息抽取，用于隔离测试检索与时间排序能力。
5. **Provider 不一致。** Memoria 经 AiHubMix 获得的实际 snapshot 是 `gpt-5-2025-08-07`；Mem0 artifact 记录 Azure + `gpt-5`，但没有保存 Azure 实际返回 snapshot。
6. **Mem0 自身的 92.5% 标称值与逐题 JSON 不一致。** 领导摘要可引用官方标称值，技术报告必须并列 91.56% 可复算值。
7. **当前仅有 Top-200 QA。** Top-10/20/50 只计算了检索指标，没有另外发起 Reader/Judge 调用，不应报告这三个 cutoff 的 QA 分数。

## 10. 可复现产物

主运行目录：

```text
memoria/runs/locomo-qwen-text-embedding-v4-1024-turn-v1/
├── manifest.json
├── summary.json
└── evaluation/
    ├── mem0-compatible-retrieval-top200-full1540-v1/
    │   ├── manifest.json
    │   ├── retrieval.jsonl
    │   ├── evidence_normalization.json
    │   ├── metrics.json
    │   ├── report.md
    │   └── summary.json
    └── mem0-compatible-gpt5-reader-judge-top200-aihubmix-full1540-v1/
        ├── manifest.json
        ├── answers.jsonl
        ├── judgments.jsonl
        ├── errors.jsonl
        ├── metrics.json
        ├── report.md
        └── summary.json
```

关键产物校验：

| 产物 | SHA-256 |
| --- | --- |
| Import `manifest.json` | `9c71cfa58ebb17f98faeb102c0729e2923cb847a8a7b67774002cdb2befbc1d4` |
| Import `summary.json` | `74ce1aa88dc1799ba37540e72ce00b70ea55ff3de8c20a8a7461b09c259b9209` |
| Retrieval `manifest.json` | `9c23de82592346e56f75b2d3177abab435c606296584e7dcffc06f754bb2c5f9` |
| Retrieval `retrieval.jsonl` | `b1d561df1a783d73d195a235b2f687cc88bb30ed477ac08f25c6c22994c2910c` |
| Retrieval `metrics.json` | `e915bb6074e2accc778928a759a976caf227111b1a3e8ae36ee9e531bad3ca83` |
| Evidence normalization | `fd4eb4926240a192343bd271095a4880e2aff406b8df7473cb4f2f29063a243a` |
| E2E `manifest.json` | `61a4ec493aea68968715361529c1d12f848b7cf481bb85c738cdd02b454d0fa0` |
| E2E `answers.jsonl` | `6b7814383d24a3d6fa238086f516ba9413bf1ca7a350475db39ef3616c093b10` |
| E2E `judgments.jsonl` | `c4d72d98b22c3fb5c1a1d30584811a0e5361e15f4d612aeda8d36c3e8a4d1718` |
| E2E `metrics.json` | `2f653f8fd96fdd6c98146a02e1b029e200a54017cc46822aecc37f9ecd822522` |
| E2E `summary.json` | `1ede8f044282175d61731c22a1863fa4fd1ca4de1574b9ad447b3d64a884fd08` |

运行器与 Prompt 源码：

- [`ingest.py`](../benchmark/locomo/ingest.py)
- [`retrieve.py`](../benchmark/locomo/retrieve.py)
- [`evaluate_top200.py`](../benchmark/locomo/evaluate_top200.py)，实验时 SHA-256 `2b0cec88945ca3a038df1342c2f8c5122d72af60a0c6ef376f775a78582b60dd`
- [`mem0_prompts.py`](../benchmark/locomo/mem0_prompts.py)
- [`test_evaluate_top200.py`](../benchmark/locomo/test_evaluate_top200.py)

## 11. 最终验收

| 验收项 | 状态 |
| --- | --- |
| 数据 SHA 和规模校验 | PASS |
| 5,882 条 active memory 对账 | PASS |
| 1,540 题 Top-200 snapshot | PASS |
| 每题 200 条、无跨用户、无重复 | PASS |
| 1,536 题进入 evidence retrieval 指标 | PASS |
| 1,540 题 Reader 最终成功 | PASS |
| 1,540 题 Judge 最终成功 | PASS |
| GPT-5 实际返回 snapshot 单一 | PASS |
| Prompt hash 与固定 Mem0 commit 一致 | PASS |
| 失败题保留且原参数补跑 | PASS |
| 最终分母 1,540，无遗漏题 | PASS |

**最终冻结结果：Memoria Raw Turn / LoCoMo Category 1–4 / Top-200 / GPT-5 = 87.92%（1,354/1,540）。**
