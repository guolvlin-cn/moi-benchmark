# Memoria Benchmark Track

状态：已完成 LongMemEval-S、LoCoMo 两个公开数据集的四项最终对标实验，
以及快照回滚、分支版本、低置信治理、重复记忆处理四项 Feature 正式实验。

本 Track 从两个层面评价 Memoria：公开数据集实验衡量长期记忆检索与问答效果，
Feature 实验直接验证记忆系统的状态管理、版本管理、质量治理和写入行为。
正式结论、数据集、脚本和原始证据分别保存在 `evaluate/`、`datasets/`、
`scripts/` 和 `runs/`。

## 公开记忆基准最终结果

公开基准采用 Memoria `0.4.0`、commit
`54c9114fd6888e11821edc2ee9acd570c17c5ee3`。数据直接写入 semantic memory，
不经过 `/v1/observe` 的原生 LLM 信息抽取；实验主要评价 Memoria 存储、检索与
固定 Reader/Judge 协议组合后的效果。

| 数据集 | 对标协议 | Memoria 本地结果 | Reader / Judge | 检索 |
| --- | --- | ---: | --- | --- |
| LongMemEval-S | Mem0 协议 | **457/500（91.40%）** | GPT-5 / GPT-5 | Hybrid Top-20 |
| LongMemEval-S | Zep 模型对标 | **459/500（91.80%）** | GPT-5.4 medium / GPT-5.4 medium | Hybrid Top-20 |
| LoCoMo | Mem0 协议 | **1,354/1,540（87.92%）** | GPT-5 / GPT-5 | Hybrid Top-200 |
| LoCoMo | Zep 模型对标 | **1,393/1,540（90.45%）** | GPT-5.4 medium / GPT-5.4 medium | Hybrid Top-200 |

- [最终综合报告](evaluate/memoria-longmemeval-locomo-final-summary.md)：数据集、版本、Memory 构建、Prompt、指标、逐类结果和竞品参照边界；
- [LongMemEval-S Mem0 协议结果](evaluate/longmemeval-s-mem0-aligned-gpt5-top20-result.md)；
- [LongMemEval-S Zep 模型对标结果](evaluate/longmemeval-s-zep-model-aligned-gpt54-top20-result.md)；
- [LoCoMo Mem0 协议结果](evaluate/locomo-memoria-raw-turn-mem0-compatible-result.md)；
- [LoCoMo Zep 模型对标结果](evaluate/locomo-memoria-raw-turn-zep-aligned-result.md)；
- [完整复现资产清单](scripts/REPRODUCIBILITY_INVENTORY.md)；
- [LongMemEval-S 建库与检索说明](scripts/longmemeval/RETRIEVAL_RUNBOOK.md)；
- [LoCoMo 建库、检索与 QA 说明](scripts/locomo/README.md)。

LongMemEval-S 使用 Memoria 当时默认/推荐的 `bge-m3`、1,024 维 Embedding；
LoCoMo 使用 DashScope `text-embedding-v4`、1,024 维。两者是独立建库实验，
不能把分数差异解释为单一 Embedding 差异。

最小证据链如下：

```text
公开数据集 + 固定 Memoria 版本与写入规则
  -> scripts/{longmemeval,locomo}/ 建库与检索
  -> runs/ 中冻结的检索快照
  -> 固定 Reader / Judge / Prompt
  -> evaluate/ 中的分项报告与最终综合报告
```

本地结果与 Mem0、Zep 的公开分数在 Memory 表示、Embedding、Top-K、Prompt
公开程度或服务版本上并不完全相同，因此属于协议或模型对标，不是严格的
同条件产品排名。

## Memoria Feature 正式结果

公开问答数据集不能完整覆盖 Memoria 自身的状态机制，因此 Feature 实验使用
自然语言记忆、确定性操作链和程序化断言，直接检查 API、数据库状态、历史关系、
检索可见性和用户隔离。每项正式实验均使用重新初始化的独立 MatrixOne 环境。

| Feature | Memoria 正式结果 | 主要验证对象 | 结论边界 |
| --- | ---: | --- | --- |
| 快照与回滚 | **50/50（100%）** | 空间级快照、跨级回滚、检索恢复、幂等性 | 未覆盖并发与超大空间 |
| 分支、Diff 与 Merge | **48/50（96%）** | 分支隔离、差异分类、无冲突合并、冲突暴露 | 2 个语义等价变更被误报为冲突；未测冲突解决 |
| 低置信记忆治理 | **50/50（100%）** | 置信阈值、年龄衰减、信任等级、重复治理 | 实际是淘汰/物理删除，不是可恢复隔离 |
| 重复与近重复处理 | **36/50（72%）** | 精确重复、等价改写、独立事实、作用域隔离 | 固定 Embedding 阈值对空格及阈值外改写敏感 |

重复与近重复处理是本轮唯一具备三方同构操作链的 Feature。44 个原生可比
case 中，Memoria 为 **30/44（68.2%）**、Mem0 Platform 为
**44/44（100%）**、Zep Cloud 为 **30/44（68.2%）**。另外 6 个 branch、
`subject_id`、`memory_type` 作用域 case 不适配竞品，不计入三方准确率。

- [Feature 测评总览](evaluate/feature/feature-evaluation-overview.md)：四项测评对象、统一配置、结果、限制和竞品能力对比；
- [Feature 数据集说明](datasets/feature/README.md)：正式 JSONL、Schema、分类和判定规则；
- [快照与回滚报告](evaluate/feature/snapshot-rollback/snapshot-rollback-formal-v1.md)；
- [分支、Diff 与 Merge 报告](evaluate/feature/branch-diff-merge/branch-diff-merge-formal-v1.md)；
- [低置信记忆治理报告](evaluate/feature/low-confidence-governance/low-confidence-governance-formal-v1.md)；
- [重复与近重复处理报告](evaluate/feature/duplicate-memory-handling/duplicate-memory-handling-formal-v1.md)；
- [重复记忆竞品对比报告](evaluate/feature/duplicate-memory-handling/duplicate-memory-handling-competitor-formal-v1.md)。

Feature 的最小证据链如下：

```text
datasets/feature/ 中的固定 case 与 JSON Schema
  -> scripts/features/ 中的数据构造器与 Runner
  -> 独立 Memoria / MatrixOne 环境，或 Mem0 / Zep 云 API
  -> runs/features/ 中的 manifest、逐 case 结果、断言和状态证据
  -> evaluate/feature/ 中的分项报告与总览
```

四项 Feature 的测评对象和断言数量不同，不能机械平均为一个“Feature 综合
准确率”。前三项在 Mem0、Zep 中存在部分相近概念，但没有与本轮操作链同构的
端到端接口，因此只对 Memoria 做正式验证；第四项才进行同数据集横向对比。

## 目录说明

| 目录 | 用途 |
| --- | --- |
| `datasets/` | Feature 可提交数据集；公开数据集本体位于 `datasets/downloads/`，由 Git 忽略 |
| `scripts/` | 当前正式实验的建库、检索、Reader/Judge、Feature Runner 和复现说明 |
| `runs/` | 当前正式实验的不可变原始证据；早期和已替代实验保存在 `runs/archive/` |
| `evaluate/` | 当前正式结果、分项分析和综合报告，是结论入口 |
| `plans/` | 评测方案、公开数据集实验设计和历史计划 |
| `research/` | 调研与历史背景材料，不作为最终结果依据 |
| `reports/` | 早期报告或补充研究；与 `evaluate/` 冲突时以后者为准 |

## 复现与使用边界

- 当前正式版本、模型、Prompt、数据哈希和运行参数以各报告及对应
  `manifest.json` 为准，README 只提供导航和摘要；
- `runs/` 是实验原始证据，不应为更新报告而覆写；重跑应创建新的运行目录；
- 本地公开数据集位于 `datasets/downloads/public-benchmarks/`，不提交数据本体；
- API Key、数据库凭据和其他运行时秘密不得提交；
- Smoke 只用于验证链路能否运行，不作为正式结果，也不进入报告分数。

评测方案入口：[plans/drafts/v0.1.md](plans/drafts/v0.1.md)。公开数据集实验计划与
阶段记录见 [plans/public-dataset-experiments.md](plans/public-dataset-experiments.md)。
