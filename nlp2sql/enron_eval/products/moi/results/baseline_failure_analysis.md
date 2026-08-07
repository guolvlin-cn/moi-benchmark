# MOI Enron 50：Golden SQL 与 MOI SQL 失败对比

## 结论

- 宽松比较（忽略 `m01` 并列行的顺序差异）：35/50，70%，失败15题。
- 严格比较（遵循 `docs/evaluation-design.md`：Golden含 `ORDER BY` 时比较结果顺序）：34/50，68%，失败16题。
- MOI实际终态：49题 `completed`，1题 `failed`（`h08`）。旧结果文件中的21个 `generation_error` 是采集脚本把中途重试错误误判为最终错误，不能用于统计MOI最终完成率。
- 本报告比较的是最终捕获SQL与Golden SQL的执行结果，不按MOI自然语言答案判分。

验证环境：本机 MySQL 8.0.46、`enron_eval` 同一数据快照、只读账号。数值做等值规范化，结果顺序按Golden SQL要求比较。

## 15道主要失败题

| 题号 | Golden SQL关键逻辑 | MOI最终捕获SQL关键逻辑 | 失败说明 |
|---|---|---|---|
| `e04` | `enron_emailinfo` 中 `LOWER(TRIM(subject)) LIKE 're:%'`，结果1910 | 统计 `enron_emailorig` 中不属于Re主题的ID，结果321 | 最终捕获SQL逻辑反向且换了表。MOI自然语言答案提到了正确的1910，但该SQL不支持最终结论。 |
| `e11` | 用 `STR_TO_DATE(REGEXP_SUBSTR(...))` 解析完整时间，按时间和ID降序 | 手写 `SUBSTRING_INDEX` 拆日期，并增加年份 `< 2010` | 错误排除了数据中两封2020年邮件；Golden前两行是2020年，MOI从2002年开始。 |
| `e13` | 直接返回两个非空计数：`nonempty_xfrom_rows`、`nonempty_xto_rows` | 返回总行数及4个NULL/空字符串计数 | 虽可人工推算非空数，但SQL没有返回题目要求的两个字段；列数5对2。 |
| `e14` | 从 `enron_email.people` 返回3个不重复员工目录 | 从 `enron_source` 返回 `xfilename,xorigin` 共8行 | 概念映射到来源文件信息，而不是归档员工目录 `people`。 |
| `m03` | 按规范化 `enron_emailinfo.from` 邮箱地址统计 | 按 `xfrom` 显示名统计 | 字段含义选错；例如Golden返回邮箱地址，MOI返回“Phillip K Allen”等显示名，数量也有差异。 |
| `m05` | 先按每封邮件统计不同规范化收件地址；`LEFT JOIN`，无收件人按0；再求平均 | 对已有 `emailto` 行直接计数；`INNER JOIN`；未去重和规范化；额外返回邮件数 | 不只是JOIN问题。MOI遗漏0收件人邮件，也可能重复计算地址；153行对152行，部分平均值不同。 |
| `m06` | SQL直接计算并返回百分比 `8.77` | SQL只返回 `sent_count=912,total_count=10401` | 自然语言答案算出了8.77%，但最终捕获SQL没有直接回答百分比；列数2对1。 |
| `m07` | 规范化地址、排除空值、按不同邮件计数，`LIMIT 1` | 未规范化/过滤，`LIMIT 10` | 第一行碰巧正确，但题目只要求一个邮箱，结果行数10对1。 |
| `m10` | 回复邮件关联 `enron_emailorig nth=1`，统计历史邮件头 `from` | 关联 `enron_emailto`，统计当前邮件收件人 `to` | “回复了谁”按统一口径指被引用上一封邮件的历史发件人；MOI统计成当前收件人，语义不同。 |
| `m12` | 只筛选精确地址 `enron.announcements@enron.com`，按不同邮件计数 | 将13个包含announcement含义的地址加入 `IN`，并用 `COUNT(*)` | 自行扩大“公告邮箱”的定义；第一名结果由106变108。 |
| `m19` | 筛选发件人并精确限制 `mailbox='inbox'`，返回一个计数0 | 漏掉inbox条件，按 `people,mailbox` 分组返回32行 | 核心过滤条件遗漏。自然语言答案后来说明0，但最终捕获SQL不是该结论对应的SQL。 |
| `m20` | 从 `enron_source.xorigin` 按不同ID统计来源员工 | 从 `enron_email.people` 按行数统计归档员工 | `xorigin` 是来源员工标识，`people` 是归档目录。Campbell结果为6489对6490，字段值大小写也不同。 |
| `h03` | 在当前邮件 `emailinfo.subject` 上筛回复邮件，连续移除一个或多个Re前缀，返回前3 | 在历史头 `emailorig.subject` 上直接分组，不做主题标准化，返回前10 | 表、标准化逻辑和Top N均不符合题意；结果完全不同。 |
| `h05` | 先动态解析日期并找最忙日，再返回 `sent_date,sender,count` 前5 | 直接硬编码 `Tue, 12 Dec 2000`，只返回发件人和数量 | 硬编码日期不可泛化，缺少题目要求的日期列；并列时也缺少邮箱升序排序。 |
| `h08` | 计算Larry与Phillip共同收件地址及双方不同邮件数 | 无SQL | `deepseek-v4-flash` 上游返回504 Gateway Timeout，是唯一最终状态为failed的题。 |

## 严格规则下额外失败：m01

Golden SQL和MOI SQL返回的80行内容相同，但排序规则不同：

```sql
-- Golden
ORDER BY email_count DESC, people ASC, mailbox ASC

-- MOI
ORDER BY cnt DESC
```

当邮件数并列时，MOI没有指定 `people,mailbox` 次级排序，所以行顺序与Golden不同。项目正式口径规定Golden含 `ORDER BY` 时比较有序结果，因此严格评分应将 `m01` 判错；若只比较无序结果集合，则可判对，得到35/50。

## 对原失败分析的修正

1. “35/50、15题失败”适用于忽略 `m01` 并列顺序的宽松评分；正式严格评分是34/50。
2. `m05` 根因不只是 `INNER JOIN`，还包括未按每封邮件去重规范化收件地址、未纳入0收件人邮件、返回列不一致。
3. `m12` 更准确的分类是“筛选范围过度扩张”，不属于字段选错。
4. `e04`、`m06`、`m19` 的自然语言答案包含正确结论，但最终捕获SQL不直接产生该结论。NL2SQL评测按SQL判错是合理的，同时说明MOI一次回答可能执行多条SQL，采集器需要明确选择主答案对应SQL。
5. “21题generation_error”不是MOI最终失败数。20题在中途遇到SQL错误后被MOI自动改写并最终完成，只有 `h08` 最终失败。
6. `from/to` 是保留字；初始SQL未正确引用时解析失败属于SQL生成/改写兼容问题，不能笼统称为MatrixOne Parser Bug。最终SQL已在MySQL上执行的事实也不能证明初始失败全部是数据库解析器缺陷。

## 原始文件

- Golden SQL：`benchmark/golden/questions_enron_50_golden.sql`
- MOI SQL：`runs/moi/2026-08-06_moi_baseline_no_semantic_01/predictions.jsonl`
- 原始MOI事件：`runs/moi/2026-08-06_moi_baseline_no_semantic_01/raw/`
- 评测口径：`benchmark/questions/spec/evaluation_conventions.md`
