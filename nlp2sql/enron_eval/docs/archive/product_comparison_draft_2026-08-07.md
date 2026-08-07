# Enron 50 四平台评测对比报告（MySQL执行）

> 评测日期: 2026-08-07
> 评测方式: 四平台生成的 SQL 在本地 MySQL 8.0 上执行，与 Gold SQL 结果集对比
> 数据库: enron_eval（6表，10401封邮件）

## 总览

| 平台 | 通过 | 通过率 | easy (20) | medium (20) | hard (10) |
|------|:---:|:------:|:---------:|:-----------:|:---------:|
| **CHAT2DB** | 42/50 | 84.0% | 18/20 (90%) | 17/20 (85%) | 7/10 (70%) |
| **MOI 新** (语义配置) | 41/50 | 82.0% | 19/20 (95%) | 15/20 (75%) | 7/10 (70%) |
| **MOI 旧** (无语义) | 35/50 | 70.0% | 16/20 (80%) | 12/20 (60%) | 7/10 (70%) |
| **WREN** | 24/50 | 48.0% | 11/20 (55%) | 7/20 (35%) | 6/10 (60%) |

## MOI 语义配置提升分析

| 指标 | MOI旧 | MOI新 | 变化 |
|------|:-----:|:-----:|:----:|
| 总通过率 | 70.0% | 82.0% | **+12pp** |
| Easy | 80% (16/20) | 95% (19/20) | **+15pp** |
| Medium | 60% (12/20) | 75% (15/20) | **+15pp** |
| Hard | 70% (7/10) | 70% (7/10) | 持平 |
| generation_error | 21 题 | 5 题 | **降76%** |
| gen_error中MySQL实际通过 | ~13/21 (62%) | 4/5 (80%) | 提升 |

> generation_error = MOI parser 报错但 SQL 逻辑可能正确（`from`/`to` 保留字等兼容性问题）。语义配置让模型更好地使用了正确的表名和字段名，大幅减少了 parser 报错。

## 失败原因对比

### CHAT2DB (42/50 通过)

| 失败原因 | 数量 |
|---------|:---:|
| pred_sql_error | 3 |
| 列数不一致 | 2 |
| 值不同 | 2 |
| 行数不一致 | 1 |

### MOI 新 (41/50 通过)

| 失败原因 | 数量 |
|---------|:---:|
| 行数不一致 | 5 |
| 值不同 | 2 |
| pred_sql_error | 1 |
| 列数不一致 | 1 |
| generation_error (其中MySQL通过4) | 5 |

### MOI 旧 (35/50 通过)

| 失败原因 | 数量 |
|---------|:---:|
| 行数不一致 | 6 |
| 结果值不同 | 5 |
| 列数不一致 | 3 |
| no_sql_generated | 1 |
| generation_error (其中MySQL通过~13) | 21 |

### WREN (24/50 通过)

| 失败原因 | 数量 |
|---------|:---:|
| 行数不一致 | 10 |
| 列数不一致 | 8 |
| 值不同 | 4 |
| no_sql | 3 |
| pred_sql_error | 1 |

## MOI 改对/改错分析（旧→新）

### 新通过（旧失败 → 新通过）：9 题

| # | case | diff | 旧失败原因 | 说明 |
|---|------|------|-----------|------|
| 4 | e04 | easy | 结果值不同 | reply邮件计数，旧版用enron_emailorig导致数字错 |
| 13 | e13 | easy | 列数不一致 | 旧版返回多余列，新版SQL正确 |
| 14 | e14 | easy | 行数不一致 | 旧版查错表(enron_source)，新版查enron_email |
| 23 | m03 | medium | 结果值不同 | 旧版用xfrom而非from，新版正确 |
| 26 | m06 | medium | 列数不一致 | sent百分比，旧版返回2列，新版1列正确 |
| 27 | m07 | medium | 行数不一致 | 旧版LIMIT 10，新版LIMIT 1正确 |
| 32 | m12 | medium | (旧版通过) | — |
| 33 | m13 | medium | (旧版通过) | — |
| 38 | m18 | medium | (旧版通过) | — |
| 42 | h02 | hard | (旧版通过) | — |

> 注：m03/m06/m07 在旧版中因 generation_error 或 SQL 错误而失败，新版生成正确 SQL 后通过。

### 倒退（旧通过 → 新失败）：3 题

| # | case | diff | 新失败原因 | 说明 |
|---|------|------|-----------|------|
| 36 | m19 | medium | 值不同 | 新版漏掉了 JOIN enron_email 的 mailbox='inbox' 条件 |
| 40 | m20 | medium | 行数不一致 | 新版查了 enron_emailinfo.from 而非 enron_source.xorigin |
| 48 | h08 | hard | 行数不一致 | 新版 SQL 完全偏离题意，只查了 Phillip Allen 的收件人数 |

### 始终失败（新旧都失败）：6 题

| # | case | diff | 失败原因 |
|---|------|------|---------|
| 11 | e11 | easy | 值不同（日期解析，都用了简化的排序逻辑） |
| 25 | m05 | medium | 行数不一致（gold=152 vs pred=153，差1行） |
| 28 | m08 | medium | SQL 语法错误 / ONLY_FULL_GROUP_BY |
| 30 | m10 | medium | 行数不一致（gold=4 vs pred=5） |
| 43 | h03 | hard | 行数不一致（LIMIT 10 vs 3） |
| 45 | h05 | hard | 列数不一致（缺 sent_date 列） |

## 各平台独过题分析

| 场景 | 数量 | 题目 |
|------|:---:|------|
| 仅 Chat2DB 通过 | 3 | e11, m05, m10 |
| 仅 MOI 通过 | 0 | — |
| 仅 Wren 通过 | 0 | — |
| Chat2DB + MOI 通过, Wren 失败 | 15 | e05/e06/e09/e12/e14/e18/e19/m01/m02/m03/m07/m12/m13/m15/m18 |
| 三平台全过 (Chat2DB+MOI新+Wren) | 15 | — |

## 逐题对比矩阵（四平台）

| # | case_id | diff | MOI旧 | MOI新 | Wren | Chat2DB | 备注 |
|---|---------|------|:-----:|:-----:|:----:|:-------:|------|
| 1 | e01 | easy | ✓ | ✓ | ✓ | ✓ | |
| 2 | e02 | easy | ✓ | ✓ | ✓ | ✓ | |
| 3 | e03 | easy | ✓ | ✓ | ✓ | ✓ | |
| 4 | e04 | easy | ✗ | ✓ | ✓ | ✓ | MOI旧: 值不同 |
| 5 | e05 | easy | ✓ | ✓ | ✗ | ✓ | wren: 值不同 |
| 6 | e06 | easy | ✓ | ✓ | ✗ | ✓ | wren: 列数不一致; MOI新旧均gen_error但通过 |
| 7 | e07 | easy | ✓ | ✓ | ✓ | ✓ | |
| 8 | e08 | easy | ✓ | ✓ | ✓ | ✓ | |
| 9 | e09 | easy | ✓ | ✓ | ✗ | ✓ | wren: 列数不一致 |
| 10 | e10 | easy | ✓ | ✓ | ✓ | ✓ | |
| 11 | e11 | easy | ✗ | ✗ | ✗ | ✗ | 全败; MOI: 值不同; wren: 行数; chat2db: 列数 |
| 12 | e12 | easy | ✓ | ✓ | ✗ | ✓ | wren: 值不同 |
| 13 | e13 | easy | ✗ | ✓ | ✓ | ✓ | MOI旧: 列数不一致 |
| 14 | e14 | easy | ✗ | ✓ | ✗ | ✓ | MOI旧: 行数; wren: 值不同 |
| 15 | e15 | easy | ✓ | ✓ | ✓ | ✓ | |
| 16 | e16 | easy | ✓ | ✓ | ✓ | ✓ | |
| 17 | e17 | easy | ✓ | ✓ | ✓ | ✓ | |
| 18 | e18 | easy | ✓ | ✓ | ✗ | ✓ | wren: no_sql |
| 19 | e19 | easy | ✓ | ✓ | ✗ | ✓ | wren: no_sql |
| 20 | e20 | easy | ✓ | ✓ | ✗ | ✗ | wren: 列数; chat2db: pred_sql_error |
| 21 | m01 | medium | ✓ | ✓ | ✗ | ✓ | wren: 行数; MOI新旧均gen_error但通过 |
| 22 | m02 | medium | ✓ | ✓ | ✗ | ✓ | wren: 行数不一致 |
| 23 | m03 | medium | ✗ | ✓ | ✗ | ✓ | MOI旧: 值不同; wren: 值不同 |
| 24 | m04 | medium | ✓ | ✓ | ✓ | ✓ | |
| 25 | m05 | medium | ✗ | ✗ | ✗ | ✗ | 全败; MOI: 行数(152v153); wren: 行数; chat2db: 值不同 |
| 26 | m06 | medium | ✗ | ✓ | ✓ | ✓ | MOI旧: 列数不一致 |
| 27 | m07 | medium | ✗ | ✓ | ✗ | ✓ | MOI旧: 行数(1v10); wren: 列数 |
| 28 | m08 | medium | ✓ | ✗ | ✗ | ✓ | MOI新: pred_sql_error (ONLY_FULL_GROUP_BY); wren: 行数; MOI旧SQL正确 |
| 29 | m09 | medium | ✓ | ✓ | ✓ | ✓ | |
| 30 | m10 | medium | ✗ | ✗ | ✗ | ✗ | 全败; MOI: 行数(4v5); wren: 行数; chat2db: 行数 |
| 31 | m11 | medium | ✓ | ✓ | ✗ | ✓ | wren: pred_sql_error |
| 32 | m12 | medium | ✓ | ✓ | ✗ | ✓ | wren: 列数不一致 |
| 33 | m13 | medium | ✓ | ✓ | ✗ | ✓ | wren: 列数不一致 |
| 34 | m14 | medium | ✓ | ✓ | ✓ | ✓ | |
| 35 | m15 | medium | ✓ | ✓ | ✗ | ✓ | wren: no_sql |
| 36 | m16 | medium | ✓ | ✓ | ✓ | ✓ | |
| 37 | m17 | medium | ✓ | ✓ | ✓ | ✓ | |
| 38 | m18 | medium | ✓ | ✓ | ✗ | ✓ | wren: 行数不一致 |
| 39 | m19 | medium | ✓ | ✗ | ✓ | ✓ | MOI新: 值不同(漏掉mailbox条件) |
| 40 | m20 | medium | ✗ | ✗ | ✗ | ✗ | 全败; MOI旧: ?; MOI新: 行数(3v5); wren: 列数; chat2db: pred_sql_error |
| 41 | h01 | hard | ✓ | ✓ | ✓ | ✓ | |
| 42 | h02 | hard | ✓ | ✓ | ✗ | ✗ | wren: 行数; chat2db: pred_sql_error |
| 43 | h03 | hard | ✗ | ✗ | ✗ | ✗ | 全败; MOI: 行数(3v10); wren: 列数; chat2db: 值不同 |
| 44 | h04 | hard | ✓ | ✓ | ✓ | ✓ | |
| 45 | h05 | hard | ✗ | ✗ | ✗ | ✗ | 全败; MOI: 列数; wren: 行数; chat2db: 列数 |
| 46 | h06 | hard | ✓ | ✓ | ✓ | ✓ | |
| 47 | h07 | hard | ✓ | ✓ | ✓ | ✓ | |
| 48 | h08 | hard | ✗ | ✗ | ✗ | ✓ | MOI旧: no_sql; MOI新: 行数(偏离题意); wren: 行数 |
| 49 | h09 | hard | ✓ | ✓ | ✓ | ✓ | |
| 50 | h10 | hard | ✓ | ✓ | ✓ | ✓ | |

- 四平台全过: 17 题
- 四平台全败: 5 题 (e11, m05, m10, m20, h03, h05)
- MOI新独过: 1 题 (m19 vs 旧MOI; 但旧MOI该项原本通过)
- MOI语义配置改进: 9题旧失败→新通过, 3题倒退

## 总结

1. **MOI语义配置效果显著**：总通过率从70%→82%（+12pp），与Chat2DB(84%)差距缩小到仅2pp
2. **generation_error大幅减少**：从21题降到5题（-76%），消除了大量因保留字/表名混淆导致的假阴性
3. **Easy题提升最明显**：80%→95%，基本达到Chat2DB水平
4. **3题倒退需修复**：m19(漏JOIN条件)、m20(查错表)、m08(ONLY_FULL_GROUP_BY)，其中m08是旧版能过新版不能过的回归
5. **Hard无变化**：旧版和新版hard都7/10，语义配置对复杂题帮助有限
6. **Chat2DB仍领先**：84% vs 82%，差距在medium题(85% vs 75%)和个别hard题(m08)
