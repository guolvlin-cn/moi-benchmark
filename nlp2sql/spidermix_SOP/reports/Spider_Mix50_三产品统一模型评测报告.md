# Spider Mix50 三产品统一模型评测报告

评测日期：2026-08-13 至 2026-08-14  
评测产品：MOI、Wren AI、Chat2DB  
统一模型：`qwen3.7-plus-2026-05-26`

## 1. 评测目标

本次评测使用 Spider 公开数据集中抽取的 Mix50，比较三个产品在统一模型下完成 NL2SQL 任务的能力，重点观察：

1. 能否生成并成功执行 SQL；
2. SQL 执行结果是否与 Golden SQL 一致；
3. 端到端生成延时；
4. Token 消耗情况。

本报告只使用每题一次、共 50 次请求的正式结果，不混入旧模型、重试实验或全局数据库上下文测试结果。

## 2. 数据集与运行口径

### 2.1 数据集覆盖

| 数据库 | 表数 | 数据行数 | 题数 |
|---|---:|---:|---:|
| `pets_1` | 3 | 40 | 17 |
| `concert_singer` | 4 | 31 | 17 |
| `car_1` | 6 | 889 | 16 |
| 合计 | 13 | 960 | 50 |

难度分布为 Easy 30 题、Medium 15 题、Hard 5 题。每道题只查询一个数据库，没有跨数据库 JOIN。

### 2.2 产品运行方式

| 产品 | 数据与执行引擎 | Schema 上下文 | 语义配置 | 会话方式 |
|---|---|---|---|---|
| MOI | 同源数据导入 MatrixOne；使用 MOI 原生执行结果 | 一个知识库包含三库 13 张表 | 无额外语义规则 | 每题独立会话 |
| Wren AI | 本地 MySQL | 一个多 Schema 项目包含 13 个模型 | 仅原始 Schema、主外键 | 每题独立请求 |
| Chat2DB | 本地 MySQL | 每题切换并固定到题目所属数据库 | 无额外问答样例或规则 | 每题新建对话 |

Chat2DB 的正式结果采用“每题固定正确数据库”的产品操作方式，因此其 Schema 候选范围比 MOI 和 Wren 更小。该差异可能降低 Chat2DB 的选表难度，解读排名时需要保留这一限制。

## 3. 指标定义

### Execution Accuracy

执行结果与 Golden SQL 一致的题数除以 50。比较采用严格结果等价：

- Golden SQL 包含 `ORDER BY` 时比较行顺序，否则忽略行顺序；
- 允许结果列排列顺序不同；
- 保留重复行语义；
- 多列、少列、多行、少行或结果值不同均判定错误。

MOI 使用 MatrixOne 中的原生执行结果与 MySQL Golden 结果比较；Wren 和 Chat2DB 的生成 SQL 与 Golden SQL 均在同一份 MySQL 快照执行后比较。

### SQL Success Rate

生成非空、只读且能在对应执行引擎成功执行的 SQL 题数除以 50。SQL 成功执行不代表结果正确。

### End-to-end Latency

从产品收到提问到完成本轮 SQL 生成流程的耗时。报告统一使用 50 条原始延时，采用线性插值计算 P50 和 P95。

### Token Usage

使用产品响应或本地日志可观测到的 Token 总数。不同产品的 Agent 调用次数、提示上下文和统计方式不同，因此 Token 适合观察资源量级，不应直接等同为模型单次调用效率。

## 4. 总体结果

| 产品 | Execution Accuracy | SQL Success Rate | 平均延时 | P50 | P95 | Token 总量 | 平均每题 Token |
|---|---:|---:|---:|---:|---:|---:|---:|
| MOI | **40/50（80%）** | **50/50（100%）** | 17.512s | 16.108s | 29.166s | 2,084,012 | 41,680 |
| Wren AI | **42/50（84%）** | **48/50（96%）** | 46.188s | 40.442s | 87.177s | 未获取 | 未获取 |
| Chat2DB | **40/50（80%）** | **50/50（100%）** | 12.496s | 11.230s | 19.838s | 757,422 | 15,148 |

主要结论：

- Wren AI 的严格执行正确率最高，为 84%，比另外两个产品高 4 个百分点；但有 2 题 SQL 未成功执行。
- MOI 与 Chat2DB 都实现了 100% SQL Success Rate，说明本轮 50 题均交付了可执行 SQL。
- Chat2DB 延时最低；MOI 居中；Wren AI 的 P50 和 P95 均明显更高。
- MOI 可观测 Token 总量约为 Chat2DB 的 2.75 倍，但两者 Agent 编排及 Token 统计范围不同，不能据此单独判断模型效率。
- Wren 本轮接口与日志没有提供可可靠归集的 Token，因此 Token 横向比较不完整。

## 5. 分难度结果

| 难度 | 题数 | MOI | Wren AI | Chat2DB |
|---|---:|---:|---:|---:|
| Easy | 30 | 26/30（86.67%） | **27/30（90%）** | 26/30（86.67%） |
| Medium | 15 | 10/15（66.67%） | **12/15（80%）** | 10/15（66.67%） |
| Hard | 5 | **4/5（80%）** | 3/5（60%） | **4/5（80%）** |

Wren 的领先主要来自 Medium 题；Hard 只有 5 题，单题会引起 20 个百分点变化，因此不适合单独据此判断复杂 SQL 能力。

## 6. 分数据库结果

| 数据库 | 题数 | MOI | Wren AI | Chat2DB |
|---|---:|---:|---:|---:|
| `car_1` | 16 | 12/16（75%） | **14/16（87.5%）** | 13/16（81.25%） |
| `concert_singer` | 17 | 12/17（70.59%） | 12/17（70.59%） | **13/17（76.47%）** |
| `pets_1` | 17 | **16/17（94.12%）** | **16/17（94.12%）** | 14/17（82.35%） |

三个产品在 `concert_singer` 上都明显低于 `pets_1`。该库包含聚合、排序、最值与关联查询，也是三产品共同错误最集中的部分。

## 7. 失败分析

| 产品 | 未通过题数 | 主要自动判错原因 |
|---|---:|---|
| MOI | 10 | 7题列数不一致；3题结果值或顺序不一致 |
| Wren AI | 8 | 4题列数不一致；1题无 SQL；1题执行错误；1题行数不一致；1题结果值不一致 |
| Chat2DB | 10 | 8题列数不一致；1题行数不一致；1题结果值不一致 |

三产品共同未通过的题目为：

- `mix50_029`：`What is the maximum capacity and the average of all stadiums?`
- `mix50_033`：`Which year has most number of concerts?`
- `mix50_043`：`What is the name and capacity of the stadium with the most concerts after 2013?`

其中 `mix50_029` 的英文表达存在明显歧义，Golden SQL 读取表中的 `average` 字段，而模型也可能合理地理解为计算所有体育场容量的平均值。`mix50_033` 和 `mix50_043` 常见错误是额外返回用于排序的 `COUNT(*)`；查询主体可能找对，但严格结果评测仍会因为多出结果列而判错。

这说明本轮主要问题不只是“不会写 SQL”，还包括：

1. 返回列没有严格遵守问题要求；
2. 聚合字段与排序辅助字段被一起输出；
3. 少量 Spider 原问题本身表达不自然或有歧义。

建议保留本报告的严格自动分数作为主指标，再对未通过题目增加人工语义审核作为附加信息，不覆盖原始自动结果。

## 8. 产品表现概括

### MOI

优点是 50 题全部完成原生 SQL 生成和执行，SQL Success Rate 为 100%，并且在 `pets_1` 上表现很好。主要失分来自多返回字段及聚合结果差异。延时优于 Wren、慢于 Chat2DB；可观测 Token 最高，反映其完整 Agent 流程使用了更多上下文或模型步骤。

### Wren AI

严格执行正确率最高，尤其在 Medium 和 `car_1` 上领先。但本轮出现 1 题生成超时无 SQL、1 题 SQL 执行错误，SQL Success Rate 为 96%；同时端到端延时最高。Token 未能从当前本地接口稳定获取。

### Chat2DB

SQL Success Rate 为 100%，延时最低，严格正确率与 MOI 同为 80%。主要失分集中在额外输出辅助列。需要注意本轮按题目固定了正确数据库，减少了 Schema 检索范围；因此 80% 不能直接解释为其在三库全局上下文中的表现。

## 9. 结论与后续工作

在当前 Mix50 单轮、统一模型条件下：

- 严格执行正确率：Wren AI 最好，MOI 与 Chat2DB 并列；
- SQL 交付稳定性：MOI 与 Chat2DB 最好；
- 端到端延时：Chat2DB 最低，MOI 次之；
- Token：MOI 与 Chat2DB 已获取，Wren 暂缺，不能形成完整排名。

当前还不能计算 Repeat Correct Rate，因为三个产品都只有一轮 50 题结果。下一阶段如果需要评估稳定性，应在完全相同的数据库上下文下再运行两轮，形成每题三次结果后计算“三次均正确”的题目比例。

同时建议为自动判错题建立人工审核附录，重点区分：SQL 逻辑错误、仅多返回辅助列、数据库方言差异和题目歧义。

## 10. 结果文件

- MOI：[evaluation.json](../runs/moi/moi_spider_qwen37_20260813_round1/evaluation.json)
- Wren AI：[evaluation.json](../runs/wren/wren_spider_qwen37_20260814_round1/evaluation.json)
- Chat2DB：[evaluation.json](../runs/chat2db/chat2db_spider_qwen37_20260814_fixed_database_round1/evaluation.json)
- Chat2DB 合并后预测：[predictions.jsonl](../runs/chat2db/chat2db_spider_qwen37_20260814_fixed_database_round1/predictions.jsonl)
