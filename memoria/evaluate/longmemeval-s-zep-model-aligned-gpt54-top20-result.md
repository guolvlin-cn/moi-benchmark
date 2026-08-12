# Memoria LongMemEval-S 对标 Zep 模型实验报告

> 实验完成日期：2026-08-12  
> 实验状态：完成，Reader 500/500，Judge 500/500，最终无缺失结果  
> 核心结果：**459/500（91.80%）**

## 1. 实验目的与定位

Zep 官网公布的 LongMemEval-S 实验使用 `gpt-5.4` Reader、`gpt-5.4` Judge 和 `reasoning=medium`，但没有公开完整的 Reader Prompt 和 Judge Prompt。因此，本实验在不改变 Memoria 检索结果的前提下：

- Reader 和 Judge 模型对齐 Zep 公布的 `gpt-5.4`；
- Reader 和 Judge 都使用 `reasoning=medium`；
- Zep 未公开的提示词由已在前一轮实验中验证有效的 Mem0 LongMemEval 公开提示词代理；
- 复用同一份 Memoria Top-20 冻结检索快照，不重新写入、不重新检索。

本实验命名为“对标 Zep 模型实验”，其准确含义是：

> **Memoria Top-20 检索 + Zep 公布的 GPT-5.4 Reader/Judge 模型配置 + Mem0 公开提示词代理。**

这不是 Zep 完整端到端协议的严格复现，也不是只比较 memory backend 的单变量实验。

## 2. 数据集

| 数据项 | 值 |
| --- | --- |
| 数据集 | LongMemEval-S cleaned / oracle |
| 题目数 | 500 |
| 官方基础题型 | 6 类 |
| Abstention | 30 题交叉子集，不是第七个互斥类别 |
| Oracle dataset SHA256 | `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c` |
| 隔离方式 | 每个 `question_id` 使用独立用户空间，无跨题数据污染 |

官方六类题型覆盖完整 500 题；Abstention 只作为交叉诊断指标单独统计，不再重复加入 Overall 分母。

## 3. 实验配置

### 3.1 Memoria 写入与检索

| 项目 | 配置 |
| --- | --- |
| Memory system | Memoria `0.4.0` |
| Memoria commit | `54c9114fd6888e11821edc2ee9acd570c17c5ee3` |
| 写入轨道 | Controlled Track，会话按确定性规则切分后直接写入 semantic memory |
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

**Embedding 选型说明。** 本轮建库沿用上述 Memoria commit 官方 `docker-compose.yml` 的默认配置 `BAAI/bge-m3` / 1024 维；同版本 CLI 初始化向导也将该组合标为 `recommended`。选择它是为了采用 Memoria 当时的默认/推荐配置，并非为了对齐 Zep。向量写入后，Embedding 模型、维度和索引 schema 已固定；本实验直接复用冻结的 Top-20 检索快照，以保证与其他 LongMemEval Reader/Judge 实验只比较下游模型和 Prompt。若更换 Embedding，需要重新建库并作为独立检索实验报告。

Reader 输入的上下文先按 Memoria 检索排名截取 Top-20，再依据原始 `source_session_date` 从早到晚排序。实验复用冻结快照，因此与先前 Mem0 对标实验使用完全相同的检索结果。

### 3.2 Reader 与 Judge

| 项目 | 配置 |
| --- | --- |
| Reader 请求模型 | `gpt-5.4` |
| Judge 请求模型 | `gpt-5.4` |
| 实验 protocol | `zep-model-aligned-mem0-prompts-v1` |
| API | OpenAI-compatible Responses API，AIHubMix |
| Reasoning effort | `medium`（Reader/Judge 一致） |
| Reader Prompt | Mem0 公开 LongMemEval Answer Generation Prompt |
| Judge Prompt | Mem0 公开 LongMemEval Unified Judge Prompt |
| Mem0 prompt commit | `4b61c5d31b9c668a12b4f5e78064248a02c82d2b` |
| User profile | 不注入 |
| System prompt | 不设置 |
| Max output tokens | 4096 |
| Reader 输出处理 | 删除 `<mem_thinking>...</mem_thinking>`；存在 `ANSWER:` 时取最后一个 `ANSWER:` 后的正文 |
| Judge 输出处理 | 删除 `<judge_thinking>...</judge_thinking>`，解析最终 `yes` / `no` |
| 失败策略 | 缺失 Reader/Judge 结果时保留在 500 题分母中并计错；可断点续跑 |

提示词哈希：

| Prompt | SHA256 |
| --- | --- |
| Answer Generation Prompt | `59f155c1c77e3000c6c75494232f669357f77a352d5ac5042decbacea230eebf` |
| Unified Judge Prompt | `c4dc2f6e34e92f9958b62222a0ed520b3ce80dede68bba164dc7961c27dae515` |

提示词来源：[Mem0 memory-benchmarks `prompts.py`](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/benchmarks/longmemeval/prompts.py)。

### 3.3 实际返回模型与运行完整性

500 次 Reader 和 500 次 Judge 的请求模型均为 `gpt-5.4`。AIHubMix 响应元数据中的模型名称如下：

| 环节 | `gpt-54` | `gpt-5.4` | 最终成功 |
| --- | ---: | ---: | ---: |
| Reader | 490 | 10 | 500/500 |
| Judge | 500 | 0 | 500/500 |

`errors.jsonl` 保留了 488 条账户余额不足和 1 条连接异常的历史失败尝试。这些题目后续均已断点补齐；最终按每题最新成功记录汇总，不存在未完成题目。

## 4. 实验结果

### 4.1 Overall

```text
非 Abstention：430/470 = 91.49%
Abstention：29/30 = 96.67%
Overall：(430 + 29) / 500 = 459/500 = 91.80%
```

| 指标 | 正确数 | 题数 | 准确率 |
| --- | ---: | ---: | ---: |
| **Overall** | **459** | **500** | **91.80%** |
| 非 Abstention | 430 | 470 | 91.49% |
| Abstention | 29 | 30 | 96.67% |

### 4.2 官方六类结果

以下六类按数据集原始 `question_type` 统计，已将 30 道 Abstention 题放回它们所属的官方题型，因此分母合计为 500。

| 官方题型 | 正确数 | 题数 | 准确率 |
| --- | ---: | ---: | ---: |
| Single-Session User | 69 | 70 | 98.57% |
| Single-Session Assistant | 56 | 56 | 100.00% |
| Single-Session Preference | 27 | 30 | 90.00% |
| Knowledge Update | 72 | 78 | 92.31% |
| Temporal Reasoning | 126 | 133 | 94.74% |
| Multi-Session | 109 | 133 | 81.95% |
| **Overall（微平均）** | **459** | **500** | **91.80%** |
| **六类宏平均** | — | — | **92.93%** |

`multi-session` 仍然是最弱题型，共错 24/133，占全部 41 道错题的 58.54%。其他题型中，Temporal Reasoning 错 7 题、Knowledge Update 错 6 题、Single-Session Preference 错 3 题、Single-Session User 错 1 题，Single-Session Assistant 全部正确。

### 4.3 检索证据完整度与问答

证据指标只在 470 道非 Abstention 题上计算。

| Top-20 证据状态 | 正确数 | 题数 | QA 准确率 |
| --- | ---: | ---: | ---: |
| 完整证据 | 422 | 442 | 95.48% |
| 证据不完整 | 8 | 28 | 28.57% |
| **全部非 Abstention** | **430** | **470** | **91.49%** |

| 检索指标 | Top-20 |
| --- | ---: |
| Hit@20 | 99.57% |
| 平均 Evidence Recall@20 | 97.34% |
| Complete Recall@20 | 94.04%（442/470） |
| MRR | 76.07% |

40 道非 Abstention 错题中，20 道在 Top-20 中已有完整证据，20 道证据不完整。这说明剩余误差同时来自检索证据缺失和 Reader/Judge 对已有证据的利用与判定。

### 4.4 Token 与延迟

Responses API 返回的 reasoning tokens 是 output tokens 的子集，不应重复加到 total tokens。

| 环节 | 调用数 | Input tokens | Output tokens | 其中 Reasoning | Total tokens | 平均 Total/题 | P50 | P95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Reader | 500 | 26,731,212 | 256,615 | 157,307 | 26,987,827 | 53,976 | 7.83s | 19.76s |
| Judge | 500 | 771,663 | 83,257 | 60,536 | 854,920 | 1,710 | 4.83s | 9.47s |
| **合计** | **1,000** | **27,502,875** | **339,872** | **217,843** | **27,842,747** | — | — | — |

## 5. 与 Zep 官网公开结果对比

### 5.1 精度对比

Zep 官网当前报告 LongMemEval-S **451/500（90.2%）**。分类正确数是根据官网百分比和数据集标准题数舍入反推，合计与官网 Overall 一致。

| 官方题型 | Memoria 本次实测 | Zep 官网 | 差值 |
| --- | ---: | ---: | ---: |
| Single-Session User | 98.57%（69/70） | 94.3%（约 66/70） | +4.27pp |
| Single-Session Assistant | 100.00%（56/56） | 96.4%（约 54/56） | +3.60pp |
| Single-Session Preference | 90.00%（27/30） | 90.0%（27/30） | 0.00pp |
| Knowledge Update | 92.31%（72/78） | 93.6%（约 73/78） | -1.29pp |
| Temporal Reasoning | 94.74%（126/133） | 90.2%（约 120/133） | +4.54pp |
| Multi-Session | 81.95%（109/133） | 83.5%（约 111/133） | -1.55pp |
| **Overall** | **91.80%（459/500）** | **90.20%（451/500）** | **+1.60pp** |

数值上，Memoria 本次实测比 Zep 官网公布结果多答对 8 题。但这个差值不能解释为 Memoria memory backend 在同条件下超过 Zep。

### 5.2 配置对比与协议差异

| 环节 | Memoria 本次实验 | Zep 官网实验 | 对齐状态 |
| --- | --- | --- | --- |
| 数据集 | LongMemEval-S，500 题 | LongMemEval-S，500 题 | 对齐 |
| Reader | `gpt-5.4`，`reasoning=medium` | `gpt-5.4`，`reasoning=medium` | 对齐公布配置 |
| Judge | `gpt-5.4`，`reasoning=medium` | `gpt-5.4`，CoT grading | 模型对齐；完整评分协议未对齐 |
| Reader Prompt | Mem0 公开 Prompt | 未公开 | 无法严格对齐 |
| Judge Prompt | Mem0 Unified Judge Prompt | 未公开 | 无法严格对齐 |
| Memory 表示 | Memoria semantic 长块 | Zep 图中 facts/entities/episodes/observations/summaries | 未对齐 |
| 检索 | Memoria `hybrid` Top-20 | 五路 multi-scope：20 edges + 10 nodes + 10 episodes + 5 summaries + 5 observations | 未对齐 |
| Reranking | Memoria 当前原生混合排序 | Cross-encoder reranking | 未对齐 |
| 上下文规模 | Reader 平均输入约 53,462 tokens/题，含提示词 | 中位返回上下文 4,408 tokens/题 | 统计定义不同，仅作规模参考 |
| 最终失败 | 0 | 0 | 对齐 |

Zep 的 multi-scope 检索将多种图对象并行检索后在客户端组合，并使用 cross-encoder 重排。Memoria 本次使用的是冻结的原生 hybrid Top-20 语义块。两者的信息抽取、记忆表示、检索候选空间、排序方式和 Reader 上下文规模都不同。

Zep 官网来源：[Zep Research](https://www.getzep.com/research/)，本报告于 2026-08-12 复核。

## 6. 与相同提示词的 GPT-5 实验对比

该对比的检索快照、Top-K、Reader Prompt、Judge Prompt、输出清理和评分解析均相同，但 Reader 和 Judge 都从 GPT-5 变为 GPT-5.4，因此仍不是只更换 Reader 的单变量实验。

| 官方题型 | GPT-5 + Mem0 Prompt | GPT-5.4 + Mem0 Prompt | 变化 |
| --- | ---: | ---: | ---: |
| Single-Session User | 69/70（98.57%） | 69/70（98.57%） | 0.00pp |
| Single-Session Assistant | 56/56（100.00%） | 56/56（100.00%） | 0.00pp |
| Single-Session Preference | 25/30（83.33%） | 27/30（90.00%） | +6.67pp |
| Knowledge Update | 71/78（91.03%） | 72/78（92.31%） | +1.28pp |
| Temporal Reasoning | 129/133（96.99%） | 126/133（94.74%） | -2.25pp |
| Multi-Session | 107/133（80.45%） | 109/133（81.95%） | +1.50pp |
| **Overall** | **457/500（91.40%）** | **459/500（91.80%）** | **+0.40pp** |
| **六类宏平均** | **91.73%** | **92.93%** | **+1.20pp** |

两次实验有 22 道题的最终标签发生变化：12 道由错变对，10 道由对变错，净增 2 道正确题。因此，在当前 500 题规模下，该结果只表明 GPT-5.4 Reader/Judge 组合取得了小幅数值提升，不足以证明存在稳定的模型优势。

## 7. 结论

1. 固定 Memoria Top-20 检索快照，使用 `gpt-5.4` Reader/Judge、`reasoning=medium` 和 Mem0 公开 Reader/Judge Prompt 后，LongMemEval-S 端到端准确率为 **459/500（91.80%）**。
2. 本次 500 道 Reader 和 Judge 均完整成功，没有因系统失败计错的题目；运行期间的历史失败已经全部通过断点续跑补齐。
3. 本次成绩在数值上高于 Zep 官网的 90.2%，但只能作为公开结果参照；提示词、记忆表示、检索、重排和上下文规模没有对齐，不能宣称严格超过 Zep。
4. 相比使用相同 Mem0 Prompt 的 GPT-5 实验，本次仅提高 0.40 个百分点，并出现 22 道标签翻转，暂不能认定 GPT-5.4 带来了显著的稳定增益。
5. `multi-session` 仍是最主要的错误来源；同时，完整证据题中仍有 20 题被判错，后续如需进一步确认结果稳定性，应优先复核错题的 Reader 答案和 Judge 标签。

## 8. 实验产物

实验目录：

```text
memoria/runs/longmemeval-s-zep-aligned-gpt54-top20-full500-v1/
```

| 文件 | 内容 |
| --- | --- |
| `manifest.json` | 冻结配置、模型、提示词版本和哈希 |
| `reader_prompts.jsonl` | 500 道题的完整 Reader Prompt |
| `answers.jsonl` | Reader 原始输出、清理后答案及历史尝试 |
| `judgments.jsonl` | Judge 原始输出、标签及历史尝试 |
| `metrics.json` | 自动汇总指标 |
| `report.md` | 自动生成的简要运行报告 |
| `checkpoint.json` | Reader/Judge 最终完成进度 |
| `errors.jsonl` | 运行过程中的历史失败记录 |

运行脚本与固定提示词：

| 文件 | 作用 |
| --- | --- |
| [`run_zep_aligned_top20.sh`](../scripts/longmemeval/run_zep_aligned_top20.sh) | 本实验正式入口，固定 GPT-5.4 medium Reader/Judge、Top-20 和正式 run 目录 |
| [`evaluate_mem0_protocol.py`](../scripts/longmemeval/evaluate_mem0_protocol.py) | Reader、Judge、断点续跑和指标汇总 |
| [`mem0_prompts.py`](../scripts/longmemeval/mem0_prompts.py) | Zep 未公开 Prompt 时采用的固定 Mem0 Prompt proxy |
| [`snapshot_common.py`](../scripts/longmemeval/snapshot_common.py) | 冻结 retrieval 与数据集对齐校验 |

正式复现命令：

```bash
./memoria/scripts/longmemeval/run_zep_aligned_top20.sh full all
```

该入口读取既有 Top-20 snapshot，不会重新调用 Memoria 检索。
