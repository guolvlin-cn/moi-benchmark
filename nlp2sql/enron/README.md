# Enron 邮件 NL2SQL 评测集

基于 Enron 邮件数据集的 NL2SQL 评测，50 道中文题目，覆盖三档难度。

## 数据

Enron 邮件数据，6 表，来自 `~/my_data/` CSV 文件：

| 表 | 行数 | 说明 |
|---|:---:|---|
| enron_emailinfo | 10,401 | 邮件核心信息（发件人/主题/正文/日期） |
| enron_email | 10,401 | 人员→文件夹→邮件数量映射 |
| enron_emailto | 71,670 | 收件人（展开，一对多） |
| enron_emailxto | 72,349 | 收件人原始名 |
| enron_source | 10,401 | 源文件/文件夹/员工 |
| enron_emailorig | 1,161 | 原始邮件链 |

## 评测集

50 题，中文问题，附 Gold SQL，已通过 SQLite 验证。

| 难度 | 题数 | SQL 特征 |
|------|:----:|---------|
| Easy | 20 | 单表过滤、聚合、排序、去重、关键词搜索 |
| Medium | 20 | 2-3 表 JOIN、GROUP BY+HAVING、子查询、NULL 处理 |
| Hard | 10 | INTERSECT/EXCEPT、嵌套子查询、窗口函数、多表 JOIN |

## 目录

```
enron/
├── README.md
├── data/
│   └── enron.sqlite           # SQLite 数据库（34MB，.gitignore）
├── cases/
│   └── cases_enron_50.yaml    # 50 题 + Gold SQL
├── predictions/
│   ├── moi/                   # MOI 预测 SQL
│   ├── wren/                  # Wren AI 预测 SQL
│   └── chat2db/               # Chat2DB 预测 SQL
├── results/                   # 评测报告
└── scripts/
    ├── build_sqlite.py        # CSV → SQLite 建库
    └── verify_gold.py         # 验证 Gold SQL
```

## 快速开始

```bash
# 1. 建库（需要 ~/my_data/ 中的 CSV 文件）
python scripts/build_sqlite.py

# 2. 验证 Gold SQL
python scripts/verify_gold.py

# 3. 评测（待完成）
# 参考 Spider 评测流程：各平台生成 pred SQL → agent-eval-tools 评分
```

## 评测方法

使用 agent-eval-tools 的 ExecutionAccuracyScorer：
- Gold SQL 和 Pred SQL 在 SQLite 上执行
- ResultSetComparator 做 multiset 对比（不要求列名/行序一致）
- 列数必须相等（多返列会判错，需人工标记）

## MOI 优势维度

- 中文 NL2SQL — 所有题目为中文，测试 MOI 的中文理解能力
- 正文语义搜索 — body 字段关键词搜索（meeting/California/energy）
- 多表关系推理 — 发件人↔收件人双向关系
- 自然语言推理 — "最活跃的人""同时收到过"需 Agent 推理
