# Memoria 低置信记忆治理正式数据集 v1

## 一、用途

该数据集用于正式验证 Memoria 能否根据记忆的信任等级、初始置信度和年龄，准确淘汰有效置信度低于阈值的活动记忆，同时保留不应淘汰的记忆，并保证治理计数、API 状态、检索可见性、幂等性和用户隔离一致。

该实验验证的是确定性治理规则，不评价大模型能否为自然语言记忆生成合理的初始置信度。所有记忆均通过 `POST /v1/memories` 直接写入，并显式声明 `trust_tier`、`initial_confidence` 和 `age_days`。

## 二、文件

- 用例：`low-confidence-governance-formal-v1.jsonl`
- Schema：`low-confidence-governance-formal-v1.schema.json`
- 生成器：`memoria/scripts/features/build_low_confidence_governance_formal_dataset.py`
- 正式执行器：`memoria/scripts/features/run_low_confidence_governance_formal.py`
- 用例数量：50
- 记忆数量：110
- 操作数量：497
- 预声明必需断言：597
- 数据集 SHA-256：`4adc22ffd5d44e2d950dfa0cc148b578992e88958c1b05f6f28231db98f945c1`
- Schema SHA-256：`14de9adb0536c5b40bdd114d79caf62e228f536eeaff1a922bba71242cafc66a`
- 生成器 SHA-256：`a06bdc9354e76455a5b5fd40ce87372a7406748ad1e10f47a4c3ecb3bc50c4b0`

## 三、治理规则

正式预期按照当前固定版本的规则计算：

```text
有效置信度 = initial_confidence × exp(-age_days / half_life_days)
```

| 信任等级 | 半衰期 |
|---|---:|
| T1 | 365 天 |
| T2 | 180 天 |
| T3 | 60 天 |
| T4 | 30 天 |

判断规则：

- 有效置信度 `< 0.2`：预期物理淘汰；
- 有效置信度 `>= 0.2`：预期保留。

数据集同时冻结每条记忆的 `expected_effective_confidence` 和 `expected_action`，生成器会重新计算并验证二者，避免人工标注漂移。

## 四、分类

| 分类 | 数量 | 主要目的 |
|---|---:|---|
| `clear_delete` | 10 | 验证明显低于阈值的单条记忆被淘汰，其中 2 条覆盖低于检索下限的深度过期记忆 |
| `clear_retain` | 10 | 验证明显高于阈值的单条记忆不被误删 |
| `tier_comparison` | 10 | 在年龄和初始置信度相同时，对比不同信任等级产生的不同结果 |
| `mixed_batch` | 10 | 每个用户包含 5 条记忆，验证两条淘汰、三条保留和计数准确性 |
| `safety_boundary` | 10 | 验证阈值邻近样本、重复治理、状态幂等和金丝雀用户隔离 |
| **合计** | **50** | |

110 条记忆的预期结果为：

- 50 条淘汰；
- 60 条保留；
- T1 记忆 25 条；
- T2 记忆 23 条；
- T3 记忆 23 条；
- T4 记忆 39 条。

## 五、检索下限的处理

Memoria 检索层会过滤有效置信度低于 `0.05` 的记忆，而治理淘汰阈值为 `0.2`。因此数据集明确区分两类待淘汰记忆：

1. `0.05 <= 有效置信度 < 0.2`：治理前必须能够检索，治理后必须消失；
2. `有效置信度 < 0.05`：治理前只要求活动状态存在，不要求检索可见；治理后仍要求状态和单条读取结果证明其已被淘汰。

字段 `require_pre_retrieval` 用于声明是否执行治理前检索断言。本数据集共有 107 条记忆要求治理前可检索，3 条深度过期记忆不设置该要求。

## 六、时间锚点

数据集保存相对年龄 `age_days`，不保存固定的绝对 `observed_at`。正式执行器应在运行开始时冻结一个 UTC 时间锚点，并按以下方式生成写入时间：

```text
observed_at = run_anchor_utc - age_days
```

同一正式运行的全部记忆必须使用同一个锚点。运行清单需要记录锚点及换算结果，确保预期有效置信度可以复核。

## 七、操作流程

普通用例执行：

```text
直接写入初始记忆
→ 捕获治理前活动状态
→ 对 require_pre_retrieval=true 的记忆执行治理前检索
→ POST /v1/governance，force=true
→ 捕获治理后活动状态
→ 对每条记忆执行单条读取和治理后检索
→ 检查金丝雀用户状态
```

`safety_boundary` 类用例会再次执行治理，并验证：

- 第二次返回 `quarantined=0`；
- 第二次治理前后活动状态哈希相等；
- 金丝雀用户状态保持不变。

## 八、判定规则

正式执行器必须检查：

- 治理前活动记忆别名集合与数据集完全一致；
- 所有要求治理前可检索的记忆确实可见；
- 第一次治理返回的 `quarantined` 与预期淘汰数量完全一致；
- 本数据集不构造失效历史，因此 `cleaned_stale` 必须为 0；
- 治理后活动记忆集合只包含预期保留项；
- 被淘汰记忆的单条读取为 HTTP 200 且响应体为 `null`；
- 被淘汰记忆在治理后检索中不可见；
- 保留记忆的内容、类型、信任等级、置信度、时间和元数据保持一致；
- 浮点置信度使用容差比较，不比较序列化字符串；
- 保留记忆在治理后仍可检索；
- 重复治理保持幂等；
- 每个用例结束后金丝雀用户状态哈希保持不变。

`orphan_graph_cleaned` 只记录为诊断信息，不要求固定为 0。直接写入后，异步实体任务可能生成图节点；记忆被淘汰时，治理操作可能同步清理相应孤立图数据。

## 九、能力边界

该数据集不验证：

- 对话抽取模型生成初始置信度的质量；
- 语义矛盾检测与 `conflicts_with` 标记；
- 信任等级自动提升或降低；
- 来源完整性治理；
- 失效版本历史清理；
- 可恢复的隔离状态。

当前 `quarantine_low_confidence` 实际执行物理删除，因此正式报告应使用“低置信记忆治理”或“低置信记忆淘汰”，不能表述为可恢复隔离。

## 十、结果入口

正式实验已执行完成，原始运行产物保存在：

`memoria/runs/features/low-confidence-governance/memoria-v040-54c911-qwen-v4-formal50-v1/`

正式结果报告已保存到：

`memoria/evaluate/feature/low-confidence-governance/low-confidence-governance-formal-v1.md`
