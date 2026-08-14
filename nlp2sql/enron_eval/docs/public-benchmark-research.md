# Chat2DB、Wren与Spider公开评测调研

> 调研日期：2026-08-12
>
> 用途：记录公开资料、明确成绩口径，并为 Enron NL2SQL 后续扩展评测维度提供依据。

## 1. 本次调研结论

公开排行榜上的分数必须同时说明数据集、产品或 Agent、底层模型和指标，不能只比较一个百分比。

| 对象 | 可核验信息 | 结论 |
|---|---|---|
| Chat2DB-SQL-7B | Chat2DB 官方博客报告 Spider `Total 77.3` | 厂商自报；未进入 Spider 1.0 官方排行榜，且未公开 Total 的完整定义和复现材料 |
| Chat2DB-Agent | Spider 2.0-Snow 官方榜记录 `Chat2DB-Agent + Claude-4-Sonnet = 38.39` | 可作为官方榜单记录；约正确完成 210/547 个任务 |
| Wren AI | 旧版开源代码包含 Spider 1.0、BIRD 的准备、预测和评测框架 | 找到评测能力，但未找到 Wren 官方发布的固定模型、完整预测结果和最终公开得分 |
|  |

因此，公开资料不能直接回答“Chat2DB 和 Wren 谁更准确”。两者没有在同一公开数据集、同一模型和同一配置下给出可复现成绩。当前 Enron 项目统一数据、问题、模型和评分程序的实测结果，才是三产品横向比较的主要依据。

## 2. Chat2DB公开评测情况

### 2.1 Chat2DB-SQL-7B与Spider 1.0

Chat2DB 官方介绍中的 `Chat2DB-SQL-7B` 是基于 CodeLlama 微调的 7B Text-to-SQL 模型，支持约 16K 上下文。页面报告：

| 分项 | 得分 |
|---|---:|
| SELECT | 91.5 |
| WHERE | 83.7 |
| GROUP | 80.5 |
| ORDER | 98.2 |
| FUNCTION | 96.2 |
| TOTAL | 77.3 |

页面还给出了基础提示模板：

```text
### Database Schema

[CREATE TABLE语句]

### Task

Based on the provided database schema information,
<自然语言问题>
[SQL]
```

但该页面没有公开：

- 使用 Spider Dev 还是 Test；
- `Total 77.3` 的计算公式；
- 是否采用 Spider Exact Set Match、Execution Accuracy 或其他自定义指标；
- 完整预测结果、评测脚本和失败样例；
- 分项中的 `FUNCTION` 如何定义。

Spider 1.0 官方排行榜中没有以 Chat2DB 或 Chat2DB-SQL-7B 名义提交的记录。因此，报告中只能称其为“Chat2DB厂商基于Spider数据集报告的77.3分”，不能写成“Spider官方执行准确率77.3%”。

### 2.2 Chat2DB-Agent与Spider 2.0-Snow

Spider 2.0-Snow 官方排行榜记录：

```text
Chat2DB-Agent + Claude-4-Sonnet：38.39
```

Spider 2.0-Snow 共547题。官方评分程序执行产品输出，并将结果与标准结果表比较；失败、超时或无有效结果计为错误。`38.39` 对应约 `210/547`。

这里测的是“Chat2DB Agent流程 + Claude-4-Sonnet”，不是 Chat2DB-SQL-7B，也不是我们当前使用 Qwen3.7 Plus 的 Chat2DB 桌面版。Chat2DB没有公开这次提交的完整系统提示词、数据库探索步骤和纠错策略，因此该成绩只能作为产品公开能力参考，不能与我们的 Enron 分数直接换算。

## 3. Wren公开评测情况

Wren 旧版开源仓库提供了评测框架，支持：

- Spider 1.0；
- BIRD；
- `ask`、`generation`、`retrieval` 三种评测管线；
- SQL正确率，以及回答相关性、忠实度、上下文相关性、上下文召回率、上下文精确率等诊断指标；
- 可选的 LLM SQL语义等价判断。

这说明 Wren 做过较完整的评测工程建设，但“公开评测代码”和“公开最终得分”不是一回事。当前没有找到以下成套材料：

```text
固定Wren版本
+ 固定底层大模型
+ 固定Prompt和参数
+ 完整预测结果
+ 官方评分输出
+ Spider或BIRD排行榜提交记录
```

因此，不能给 Wren 引用一个经过官方验证的 Spider/BIRD 分数。

网上出现的 `Wren Spider 89.2%` 来自第三方韩文演示页面，同时还声称 WikiSQL 94.5%、SParC 87.8%、CoSQL 85.4%。该页面没有说明模型、数据划分、指标和复现代码，不属于 Wren 官方资料，正式报告不采用。

## 4. 底层模型和提示词是否统一

公开基准一般统一数据、任务输入和评分程序，不要求参评产品使用相同大模型或相同系统提示词。

| 评测 | 底层模型 | 提示词情况 |
|---|---|---|
| Chat2DB-SQL-7B Spider自测 | 基于CodeLlama微调的Chat2DB-SQL-7B | 仅公开基础Schema+Question模板 |
| Chat2DB-Agent Spider 2.0-Snow | Claude-4-Sonnet | 完整Agent提示词和流程未公开 |
| Wren Spider/BIRD框架 | 由运行者在配置文件中指定 | 产品内部多阶段Prompt存在于源码，但没有对应公开分数的冻结配置 |
| 本项目Enron评测 | 三产品统一为Qwen3.7 Plus | 用户问题统一；产品内部Prompt、检索和纠错机制保留 |

本项目不应强制三个产品使用同一套内部提示词。Schema检索、语义层、SQL校验、反思和修正本身就是产品能力。若完全替换为同一个Prompt，测到的将主要是大模型直接生成SQL的能力，而不是MOI、Wren和Chat2DB的完整产品能力。

## 5. Spider评测包含哪些维度

Spider 1.0并非简单比较两个SQL字符串。其历史和官方评测主要包括：

### 5.1 Component Matching

将SQL解析后按组件诊断，例如：

- `SELECT`及聚合；
- `WHERE`及运算符；
- `GROUP BY`与`HAVING`；
- `ORDER BY`；
- `AND/OR`；
- `UNION/INTERSECT/EXCEPT`；
- SQL关键字。

这些分项适合回答“模型错在表、字段、过滤、聚合还是排序”，但不能单独证明完整SQL能够得到正确答案。

### 5.2 Exact Set Match

不是逐字符比较，而是将预测SQL与Golden SQL解析成结构后进行集合匹配。全部要求的结构组件均匹配，整题才记为正确。Spider 1.0排行榜长期报告该指标作为重要参考。

### 5.3 Execution Accuracy

分别执行预测SQL和Golden SQL，再比较查询结果。不同写法只要得到相同结果，就可能判为正确；但在单一数据库实例上，错误SQL也可能碰巧得到相同结果。

### 5.4 Test Suite Accuracy

在多组经过构造的测试数据库上执行SQL，以减少“错误SQL在当前数据上碰巧结果相同”的假阳性。Spider从2020年起将其作为官方主要指标。

这些指标关注点不同，不应混成一个没有定义的综合分：

```text
Component Matching：哪里错了
Exact Set Match：SQL结构是否整体匹配
Execution Accuracy：当前数据上答案是否一致
Test Suite Accuracy：换一组能区分语义的数据后是否仍然正确
```

## 6. 当前Enron评测已经覆盖什么

当前阶段以最终产品是否解决用户问题为核心，已经记录或计划记录：

1. **Execution Accuracy**：候选SQL与Golden SQL的执行结果是否一致；
2. **SQL Success Rate**：是否生成非空、安全且可成功执行的SQL；
3. **End-to-end Latency**：请求从提交到SQL完整返回的P50、P95；
4. **Repeat Correct Rate**：同一问题重复运行时是否持续正确；
5. **人工复核**：修正列数、排序规则、大小写、问题歧义等自动评分边界情况。

当前主指标选择 Execution Accuracy 是合理的，因为它最接近用户最终能否获得正确数据。但它的不足也很明确：

- 只告诉我们对错，不能自动说明错误发生在哪个SQL组件；
- 单一数据快照存在偶然等价；
- 对多列、展示列和排序要求需要额外规则；
- 不能独立衡量Schema检索、语义理解和SQL生成各阶段；
- 不能判断正确SQL是否低效；
- Token消耗在部分产品接口中不可获得，暂时无法公平比较。

## 7. 后续建议增加的评测维度

后续不必一次引入大量指标。建议继续把 Execution Accuracy 作为主指标，再增加三组能够直接计算或清晰标注的诊断维度。

### 7.1 SQL组件错误标签

对自动判错题和人工复核题增加以下布尔字段：

```text
table_correct
column_correct
join_correct
filter_correct
aggregation_correct
grouping_correct
ordering_correct
limit_correct
normalization_correct
```

每项统计：

```text
组件正确率 = 该组件判断正确的适用题数 / 使用该组件的题数
```

这样可以直接回答“产品主要败在语义选表，还是SQL排序”。第一阶段可以由人工标注失败题；后续再用SQL解析器辅助，不让LLM裁判单独决定分数。

### 7.2 按题型切片的执行正确率

利用已有50题标签，分别计算：

- Easy、Medium、Hard；
- 口语化、详细表达；
- 单表、跨表JOIN、聚合、日期、文本匹配、集合、窗口函数；
- 明确语义题、存在合理歧义题。

计算方式仍然是：

```text
切片Execution Accuracy = 切片内正确题数 / 切片题目总数
```

它不增加新的主观判分，只让同一个正确率更有解释力。

### 7.3 效率与稳定性

继续使用可直接采集的数据：

- End-to-end Latency：P50、P95、Max、超时数；
- SQL Success Rate：成功执行数/总请求数；
- Repeat Correct Rate：三次均正确题数/50；
- SQL执行耗时：候选SQL在统一MySQL快照执行的P50、P95；
- Token：只有三个产品都能取得同口径的输入、输出Token时才进入主表，否则单独标注 `N/A`。

### 7.4 增强版语义正确性测试

未来若要接近 Spider Test Suite Accuracy，可针对关键题构造少量“对抗数据快照”。例如：

- 增加大小写不同但语义相同的邮箱；
- 增加日期字符串按字典序和时间顺序不同的记录；
- 增加并列第一，检验二级排序；
- 增加无收件人的邮件，检验LEFT JOIN；
- 增加重复收件人，检验`COUNT(*)`与`COUNT(DISTINCT ...)`；
- 增加同一员工的多个邮箱，检验人员与邮箱语义。

候选SQL必须在原始快照和对抗快照上都与Golden SQL结果一致，才算增强语义正确。这样能发现“当前数据上碰巧正确”的SQL。

## 8. 下一阶段推荐顺序

1. 完成MOI、Wren、Chat2DB在同一Enron条件下的150次采集；
2. 保留现有自动Execution Accuracy，不覆盖原始统计；
3. 完成失败题人工复核并形成附加修正分；
4. 给50题补齐题型标签，自动生成分难度、表达方式和SQL能力切片；
5. 给失败题补充SQL组件错误标签；
6. 选择10道最容易“碰巧正确”的题，制作小规模对抗快照；
7. 最后再决定是否引入Token成本或LLM裁判类指标。

## 9. 报告引用建议

正式报告可使用以下表述：

> 本项目当前以Execution Accuracy为主指标，并报告SQL生成成功率、端到端时延和重复正确率。Spider公开评测还包含SQL组件匹配、结构精确匹配和Test Suite Accuracy等维度。后续版本将增加按SQL组件和题型切片的错误诊断，并探索针对Enron数据构造对抗快照，以减少单一数据实例导致的偶然等价。

## 10. 参考资料

- [Spider 1.0官方网站与历史排行榜](https://yale-lily.github.io/spider)
- [Spider官方Test Suite评测程序](https://github.com/taoyds/test-suite-sql-eval)
- [Spider 2.0官方网站与排行榜](https://spider2-sql.github.io/)
- [Spider 2.0-Snow官方评测程序](https://github.com/xlang-ai/Spider2/tree/main/spider2-snow/evaluation_suite)
- [Chat2DB-SQL-7B官方介绍](https://chat2db.ai/resources/blog/Chat2DB-SQL-7B)
- [Chat2DB-SQL-7B模型页](https://huggingface.co/Chat2DB/Chat2DB-SQL-7B)
- [Wren AI旧版评测框架](https://github.com/Canner/WrenAI/tree/legacy/v1/wren-ai-service/eval)
- [Wren AI当前Evaluation功能](https://docs.getwren.ai/cp/guide/evaluation/overview)
- [声称Wren Spider 89.2%的第三方页面，不作为正式依据](https://aidenhong.com/presentations/wren-ai/wren-ai.html)
