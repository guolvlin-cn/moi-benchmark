# 重复与近重复记忆处理竞品正式实验

## 1. 实验目的

本实验使用同一份 50-case 数据集，对比 Memoria、Mem0 Platform 和 Zep Cloud 在以下三类场景中的最终行为：

1. 重复输入是否会新增冗余记忆；
2. 语义等价改写是否会被吸收或替换；
3. 独立事实与不同作用域是否能安全并存。

该实验测的是“重复与近重复记忆处理”，不是一般意义上的事实值更新。

## 2. 数据集

数据集为 `duplicate-memory-handling-formal-v1.jsonl`，共 50 个 case、104 次写入：

| 类别 | Case 数 | 内容 |
|---|---:|---|
| 精确重复复用 | 10 | 6 个完全相同文本、4 个首尾空格变体 |
| 语义等价处理 | 24 | 8 个阈值内改写、8 个阈值附近改写、4 个明显改写、4 个三版本链 |
| 并存与作用域隔离 | 16 | 8 个同作用域独立事实，subject、memory type、branch、user 隔离各 2 个 |

数据集 SHA-256 为 `b30ae3ac6bbe02a792bafa497afa23bb31d310601e23db5795fb68c66fc39657`。

## 3. 产品接入与协议差异

| 产品 | 实验版本 | 写入接口 | 处理方式 | 作用域处理 |
|---|---|---|---|---|
| Memoria | `0.4.0`；commit `54c9114fd6888e11821edc2ee9acd570c17c5ee3`；源码为 dirty 状态，manifest 保留 source diff SHA-256 | 本地 `store_memory` | 直接保存输入文本，使用 `text-embedding-v4` 与固定 L2 阈值判断复用或替换 | 原生 user、branch、subject、memory type |
| Mem0 Platform | API `v3` ADD-only；正式响应未返回服务端产品版本号 | `v3/memories/add`，`infer=true` | 云端先抽取并规范化事实，再决定 ADD 或不产生事件 | user 原生；subject、memory type、branch 到 `agent_id`、`app_id`、`run_id` 的映射仅为非同构适配 |
| Zep Cloud | API `v2`；正式响应未返回服务端产品版本号 | `v2/graph.add` text episode | 云端异步抽取图谱 edge；一个输入可能拆成多条互补事实 | user 原生；subject、memory type、branch 没有同构字段，实验通过独立 user graph 适配 |

因此，这不是三个完全相同内部机制的严格复现。比较对象是写入相同自然语言后形成的可观察语义状态。

Mem0 Platform 与 Zep Cloud 的正式 API 响应均未返回可固定的服务端产品版本号，因此这里只记录实际调用的 API 代际，不能将其误写成产品发布版本。manifest 另行保留数据集与 runner 哈希、运行时间和逐请求原始响应，本次云端结果也不能直接外推到未来版本。

## 4. 统一判定口径

### 4.1 主指标

采用 `incremental-semantic-state-v1` 口径：

- 重复/等价 case：后续写入不能引入新的语义冗余；允许 Zep 将一次输入拆成多个互补 edge；
- 独立事实 case：两个事实都必须在最终状态保持活跃；
- 作用域 case：相同文本在两个逻辑作用域中必须分别保留。

Zep 不能直接按 edge 数计分，因为一个 episode 在第一次写入时就可能拆出多个 edge。判定会比较每次写入前后的活跃 edge、失效 edge、事实文本及 episode 来源。14 个 Zep FAIL 均在 `scored-results.jsonl` 中保留人工判定理由与机器提取证据。

### 4.2 辅助指标：最新表述采用

“没有新增重复”不代表“采用了最新措辞”，所以单独报告：

- Memoria：最终是否由新版本替代旧版本；
- Mem0：最新写入是否产生事件并改变最终状态；
- Zep：最终是否存在仅来自最新 episode 的活跃 edge，且不存在仅来自旧 episode 的活跃 edge。

该辅助指标反映的是可观察状态变化，不等价于三个产品内部完全相同的 update 语义。

## 5. 实验运行

| 项目 | Mem0 Platform | Zep Cloud |
|---|---|---|
| 正式运行 | `mem0-platform-v3-formal50-v1` | `zep-cloud-formal50-v3` |
| Case 完成 | 50 / 50 | 50 / 50 |
| API ERROR | 0 | 0 |
| Case 内顺序 | 串行，等待 event `SUCCEEDED` | 串行，等待 episode `processed=true` |
| Case 间并发 | 1 | 8 |
| 正式数据清理 | 未清理，保留云端状态 | 未清理，保留云端状态 |

Zep 正式 v3 运行前有两次未计分运行：

1. `zep-cloud-formal50-v1` 的固定 `created_at` 落在未来，首批 episode 一直为 `processed=false`；在任何 case 完成前停止，并标记为 `aborted_invalid_protocol`；
2. `zep-cloud-formal50-v2` 在受限网络沙箱内启动，50 个请求均在连接本地代理时失败、未触达 Zep，并标记为 `invalid_environment`。

两次目录均保留原始证据，但不进入正式分母。修正后的 v3 使用固定历史时间戳，50 个 case 全部正常完成。

## 6. 正式结果

### 6.1 三方原生可比结果

三方原生可直接比较的核心集合为 44 case：10 个精确重复、24 个语义等价、8 个同作用域独立事实和 2 个 user 隔离 case。

| 核心可比范围 | Memoria | Mem0 Platform | Zep Cloud |
|---|---:|---:|---:|
| 精确重复复用 | 8 / 10（80.0%） | 10 / 10（100.0%） | 7 / 10（70.0%） |
| 语义等价处理 | 12 / 24（50.0%） | 24 / 24（100.0%） | 15 / 24（62.5%） |
| 同作用域独立事实与 user 隔离 | 10 / 10（100.0%） | 10 / 10（100.0%） | 8 / 10（80.0%） |
| **原生可比合计** | **30 / 44（68.2%）** | **44 / 44（100%）** | **30 / 44（68.2%）** |

剩余 6 个 case 测试 Memoria 原生的 subject、memory type 和 branch 去重隔离，Memoria 为 `6/6`。Mem0 将三者分别映射为 `agent_id`、`app_id`、`run_id` 后得到 `0/6`，但这些字段语义并不相同，因此只作为非同构适配观察，不计入 Mem0 主分数。Zep 通过为每个逻辑作用域创建独立 user graph 得到 `6/6`，同样属于适配结果，不代表 Zep 原生支持三种同构字段。

### 6.2 语义等价分层

| 子类 | Memoria | Mem0 Platform | Zep Cloud |
|---|---:|---:|---:|
| 阈值内单次改写 | 8 / 8 | 8 / 8 | 6 / 8 |
| 阈值附近但阈值外 | 0 / 8 | 8 / 8 | 4 / 8 |
| 明显阈值外改写 | 0 / 4 | 4 / 4 | 3 / 4 |
| 三版本链 | 4 / 4 | 4 / 4 | 2 / 4 |

这里的阈值分层来自 Memoria 使用的 `text-embedding-v4` 距离，只用于保持原数据集结构；Mem0 和 Zep 并不使用该阈值。

### 6.3 最新表述采用

| 产品 | 结果 | 说明 |
|---|---:|---|
| Memoria | 12 / 24 | 阈值内 case 由新文本替代旧文本，阈值外保留两条 |
| Mem0 Platform | 1 / 24 | 23 个 case 的后续写入没有产生事件，通常保留第一次抽取的规范化表述；仅 case 032 改变状态 |
| Zep Cloud | 9 / 24 | 按严格 episode 来源口径，最终采用新 episode 且不保留仅来自旧 episode 的 edge |

Mem0 的 24/24 语义等价主指标表示“没有形成两条活跃记忆”，不能表述为 24/24 完成了新版本替换。

## 7. 结果分析

### 7.1 Mem0：去重覆盖广，但通常不采用最新表述

Mem0 对 10 个精确重复和 24 个语义等价 case 均避免了重复活跃记忆，包括 Memoria 阈值外的明显改写。说明其 `infer=true` 抽取与云端决策对自然语言改写的吸收范围明显宽于 Memoria 的固定向量阈值。

但它通常保留第一次抽取后的表述，后续写入返回空事件。该行为更接近“识别为已有事实并忽略”，不是“把旧记忆更新为用户最新措辞”。

8 个同作用域独立事实和 2 个原生 user 隔离 case 全部通过。subject、memory type、branch 的 6 个 case 分别映射到 `agent_id`、`app_id`、`run_id` 后，第二次写入仍被视为已有事实；该结果只能说明这套非同构适配没有复现 Memoria 的隔离行为，不能据此判定 Mem0 的原生作用域能力失败。

### 7.2 Zep：图谱合并有效，但结果有抽取波动

Zep 在部分重复和等价 case 中会让同一活跃 edge 同时关联两个 episode，或者使旧 edge 失效并生成新 edge，这是明确的合并/替换证据。

失败主要有三种：

1. 第二次输入新增与旧事实相同或高度重叠的活跃 edge；
2. 三版本链中旧表述继续活跃，同时新增重复的新表述；
3. 写入第二个独立事实后，第一个事实的 edge 被错误淘汰。该问题出现在 case 040 和 042。

Zep 第一次写入本身偶尔就会生成重复 edge，因此本实验主指标判断的是后续重复写入是否进一步引入冗余，而不是把首次图谱抽取质量混入重复处理分数。

### 7.3 Memoria：边界清晰，但固定阈值造成漏检

Memoria 对作用域隔离和独立事实并存最稳定，16/16 全部通过；阈值内的 16 次相邻等价关系也全部正确替代。失败集中在首尾空格导致 embedding 越过门禁，以及人类语义等价但 L2 超出 `0.3162` 的改写。

因此三者呈现不同取舍：Memoria 的直接存储与作用域规则最可解释；Mem0 的语义去重覆盖最广，但通常不保留最新措辞；Zep 能通过图谱 provenance 表达合并与替换，但 edge 抽取和失效行为存在波动。三方没有同构的非 user 作用域，相关适配结果必须单列。

## 8. 产物

- 数据集：`memoria/datasets/feature/duplicate-memory-handling/duplicate-memory-handling-formal-v1.jsonl`
- Mem0 runner：`memoria/scripts/features/run_mem0_duplicate_memory_formal.py`
- Zep runner：`memoria/scripts/features/run_zep_duplicate_memory_formal.py`
- 统一 scorer：`memoria/scripts/features/score_competitor_duplicate_memory_formal.py`
- Mem0 正式结果：`memoria/runs/features/duplicate-memory-handling/mem0-platform-v3-formal50-v1/`
- Zep 正式结果：`memoria/runs/features/duplicate-memory-handling/zep-cloud-formal50-v3/`
- 每个正式目录均包含 manifest、冻结 case、逐请求响应、case 结果、逐 case 评分与汇总指标。
