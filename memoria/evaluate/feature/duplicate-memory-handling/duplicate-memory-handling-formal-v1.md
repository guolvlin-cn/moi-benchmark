# Memoria 重复与近重复记忆处理正式实验

## 1. 实验目标

本实验验证 Memoria 在直接写入记忆时对重复与近重复内容的实际处理边界，不将该能力表述为一般意义上的“事实更新”。核心检查三件事：

1. 完全相同的内容是否复用已有记忆；
2. 语义等价但文本不同的内容在什么距离范围内会替代旧记忆；
3. 独立事实和不同作用域的记忆是否能安全并存。

## 2. 源码对应逻辑

`store_memory` 会先生成 embedding，再在同一用户、分支、`memory_type` 和 `subject_id` 作用域内查找 L2 距离不大于 `0.3162` 的近重复记忆。该阈值对应归一化向量下约 `0.95` 的余弦相似度。

- 候选记忆进入阈值且 `trim()` 后文本相同：复用原记忆 ID；
- 候选记忆进入阈值但 `trim()` 后文本不同：插入新记忆并将旧记忆标记为被替代；
- 没有候选记忆进入阈值，或作用域不同：两条记忆并存。

因此，本实验的“等价改写更新”是产品能力边界测量，不是对任意语义等价文本都能更新的预设。

## 3. 数据集设计

数据集共 50 个 case、104 次记忆写入和 54 个关系判定。所有 case 使用普通自然语言，不在记忆文本中放置人工锚点。

| 类别 | case 数 | 构造方式 | 期望行为 |
|---|---:|---|---|
| 精确重复复用 | 10 | 6 个完全相同，4 个首尾空格变体 | 复用原 ID，仅保留 1 条活跃记忆 |
| 等价改写处理 | 24 | 8 个阈值内单次改写，8 个阈值外边界改写，4 个明显阈值外改写，4 个阈值内三版本链 | 语义上期望新表述替代旧表述，同时观察阈值的实际限制 |
| 并存与作用域隔离 | 16 | 8 个同作用域独立事实，以及 subject、memory type、branch、user 隔离各2个 | 两条记忆均保留，不误替代 |

等价改写样本在数据集生成时用同一 `text-embedding-v4` 配置测量并冻结 L2 距离；正式运行又直接从 MatrixOne 重新读取向量距离作为运行证据。

## 4. 实验配置

| 配置项 | 值 |
|---|---|
| Memoria 版本 | `0.4.0` |
| Memoria commit | `54c9114fd6888e11821edc2ee9acd570c17c5ee3` |
| 源码状态 | dirty；正式 manifest 保存了 source diff SHA-256 |
| Embedding | Qwen `text-embedding-v4` |
| Embedding 维度 | `1024` |
| 近重复阈值 | L2 `0.3162` |
| MatrixOne | manifest 中固定的 image digest |
| 数据库 | 全新隔离数据目录，运行前 `/admin/stats` 空库门禁通过 |
| 内部 LLM | 未启用 |
| 运行时间 | 2026-08-13 |

runner 逐请求保留 API 请求与响应，并同时核对 API 活跃状态、历史链、检索结果、MatrixOne 底层行、向量距离和金丝雀隔离性。

## 5. 正式结果

经过 runner 错误的缺失项补跑后，有效口径为 **36 PASS、14 FAIL、0 ERROR，严格 case 通过率 72.0%**。

| 类别 | PASS / 总数 | 准确率 |
|---|---:|---:|
| 精确重复复用 | 8 / 10 | 80.0% |
| 等价改写处理 | 12 / 24 | 50.0% |
| 并存与作用域隔离 | 16 / 16 | 100.0% |
| **总计** | **36 / 50** | **72.0%** |

此处的 `12/24` 使用 **case 口径**：8 个阈值内单次改写 case 和 4 个阈值内连续链 case 通过，其余 12 个阈值外 case 未通过。下文的“16 次正确替代”使用 **关系/操作口径**：8 个单次 case 各包含 1 次替代，4 个连续链 case 各包含 2 次替代，合计 `8 + 4×2 = 16` 次。

等价改写组的距离分层结果更能说明能力边界：

| 距离分层 | 关系数 | 正确替代 | 实际行为 |
|---|---:|---:|---|
| L2 阈值内 | 16 | 16 / 16 | 全部 supersede |
| 刚超出阈值 | 8 | 0 / 8 | 全部 coexist |
| 明显超出阈值 | 4 | 0 / 4 | 全部 coexist |

4 个三版本链 case 全部通过，共包含的 8 次阈值内连续替代均正确完成。

## 6. 结果分析

### 6.1 精确重复：文本比较之前仍受 embedding 门禁限制

6 个完全相同用例全部复用原 ID。仅有单侧前置空格或单侧后置空格的2个用例也复用成功。

但同时包含首尾各一个空格时，运行时 L2 距离为 `0.3379645`；首尾各三个空格时为 `0.4883051`，均超出 `0.3162` 阈值。尽管两组文本 `trim()` 后完全相同，但它们没有先通过向量候选门禁，因此最终以两条记忆并存。这说明当前实现并非先对输入做稳定的空白标准化再 embedding。

### 6.2 等价改写：行为严格由阈值决定

阈值内的 8 个单次改写和 4 个连续链 case 全部通过。阈值外 12 个 case 全部失败，旧表述和新表述均保留为活跃记忆。

这不是随机错误，而是与源码中的固定阈值完全一致。对用户来说，语义上等价并不保证能够替代；只有 embedding 距离进入高相似阈值才会触发。所以该功能更准确的定位是“近乎相同内容的去重与替代”，而非完整的记忆事实更新。

### 6.3 并存与隔离：本轮表现稳定

同作用域的 8 组独立事实均未被误替代。`subject_id`、`memory_type`、branch 和 user 四种作用域隔离各 2 个 case，共 8 个 case 全部通过。本轮没有观察到跨作用域误去重。

## 7. 等价改写 24 个 case 明细

本节中的 L2 距离来自数据集生成阶段冻结的 `text-embedding-v4` 测量。当前实现阈值为 `0.3162`。

### 7.1 阈值内单次改写

| Case | v1 | v2 | L2 | 结果 |
|---|---|---|---:|---|
| 011 | Iris drinks green tea every afternoon. | Iris drinks green tea each afternoon. | 0.1161 | PASS |
| 012 | Jack works remotely on Fridays. | Jack works remotely each Friday. | 0.2056 | PASS |
| 013 | Karen reviews her calendar every Monday morning. | Karen reviews her calendar each Monday morning. | 0.0573 | PASS |
| 014 | Leo keeps his passport in the home safe. | Leo keeps his passport inside the home safe. | 0.0927 | PASS |
| 015 | Mia takes the metro to work every weekday. | Mia takes the metro to work each weekday. | 0.0627 | PASS |
| 016 | Noah reads historical fiction before bed every night. | Noah reads historical fiction before bed each night. | 0.0528 | PASS |
| 017 | Olivia practices yoga before work every Tuesday. | Olivia practices yoga before work each Tuesday. | 0.0587 | PASS |
| 018 | Peter plans the weekly meals every Sunday. | Peter plans the weekly meals each Sunday. | 0.0995 | PASS |

### 7.2 刚超出阈值的单次改写

| Case | v1 | v2 | L2 | 结果 |
|---|---|---|---:|---|
| 019 | Thomas walks along the river after dinner. | Thomas takes a walk along the river after dinner. | 0.4334 | FAIL |
| 020 | Uma checks the project board every morning. | Every morning, Uma checks the project board. | 0.3405 | FAIL |
| 021 | Xavier stores backups on an external drive. | Xavier keeps backup copies on an external drive. | 0.3188 | FAIL |
| 022 | Zach prefers a window seat on long flights. | For lengthy flights, Zach likes sitting next to the window. | 0.3796 | FAIL |
| 023 | Caleb attends a pottery class on Saturdays. | Saturday is the day Caleb takes lessons in making pottery. | 0.4415 | FAIL |
| 024 | Diana walks her dog in the park every evening. | Each evening, Diana takes her dog out for a walk in the park. | 0.3233 | FAIL |
| 025 | Gavin works remotely on Fridays. | Gavin works from home on Fridays. | 0.3348 | FAIL |
| 026 | Hazel enjoys historical fiction before bed. | Hazel likes reading historical novels at bedtime. | 0.3193 | FAIL |

### 7.3 明显超出阈值的单次改写

| Case | v1 | v2 | L2 | 结果 |
|---|---|---|---:|---|
| 027 | Yvonne reads for thirty minutes before sleeping. | Before going to sleep, Yvonne spends half an hour reading. | 0.5147 | FAIL |
| 028 | Aaron exercises at the gym after work. | Once his workday ends, Aaron goes to the gym to exercise. | 0.6666 | FAIL |
| 029 | Bella reviews her task list before lunch. | Prior to her midday meal, Bella goes through the tasks on her list. | 0.5380 | FAIL |
| 030 | Fiona drinks coffee without sugar. | Fiona takes her coffee unsweetened. | 0.4707 | FAIL |

### 7.4 阈值内连续版本链

| Case | v1 | v2 | v3 | 关系距离 | 结果 |
|---|---|---|---|---|---|
| 031 | Grace drinks green tea every morning. | Grace drinks green tea each morning. | Grace drinks green tea every morning of the week. | v1→v2: 0.0844; v2→v3: 0.2488 | PASS |
| 032 | Henry reviews his calendar every Monday. | Henry reviews his calendar each Monday. | Henry reviews his calendar every Monday morning. | v1→v2: 0.0737; v2→v3: 0.1542 | PASS |
| 033 | Julia walks by the river every evening. | Julia walks by the river each evening. | Julia takes a walk by the river each evening. | v1→v2: 0.1181; v2→v3: 0.2512 | PASS |
| 034 | Nina works remotely every Friday. | Nina works remotely each Friday. | Nina works remotely on every Friday. | v1→v2: 0.0832; v2→v3: 0.1227 | PASS |

## 8. runner recovery 说明

原始 50-case run 记录为 34 PASS、14 FAIL、2 ERROR。两个 ERROR 都来自 runner 将 `create_branch.user_ref` 当成必填字段，而数据集协议中该操作默认使用 primary 用户。这两个 case 在产品操作开始前即中止，不能计为 Memoria 失败。

处理方式是保留原始不可变产物，修正 runner 后只补跑 `dmh-formal-047` 和 `dmh-formal-048`，两者均 PASS。正式报告使用合并后的 36/50 口径，原始 metrics、errors 和 recovery 目录全部保留。

## 9. 产物与可复现性

- 数据集：`memoria/datasets/feature/duplicate-memory-handling/duplicate-memory-handling-formal-v1.jsonl`
- 数据集说明：`memoria/datasets/feature/duplicate-memory-handling/duplicate-memory-handling-formal-v1.md`
- runner：`memoria/scripts/features/run_duplicate_memory_handling_formal.py`
- 原始运行：`memoria/runs/features/duplicate-memory-handling/memoria-v040-54c911-dirty-qwen-v4-formal50-v1/`
- 错误补跑：原始运行目录下 `recoveries/runner-user-ref-fix-v1/`
- 合并指标：原始运行目录下 `resolved-metrics.json`

原始目录保留 dataset/schema/runner 哈希、source diff 哈希、逐请求响应、case 结果、断言、状态、历史、检索、关系、MatrixOne 证据、空库门禁和金丝雀证据。
