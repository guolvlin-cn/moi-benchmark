# NL2SQL Benchmark — Spider mix50

MOI 平台与竞品 (Wren AI, Chat2DB) 的 NL2SQL 能力对比评测。

## 数据集

50 道 Spider 题目，按难度混合：
- **easy (30题)**: 单表查询，无 JOIN/GROUP BY
- **medium (15题)**: JOIN / GROUP BY / HAVING
- **hard (5题)**: 子查询 / EXCEPT / INTERSECT

涉及3个数据库: `concert_singer`, `pets_1`, `car_1`

## 结果

| 平台 | easy | medium | hard | **总计** |
|------|------|--------|------|----------|
| MOI | 73.3% | 53.3% | 60.0% | **66.0%** |
| Wren AI | 86.7% | 66.7% | 100.0% | **82.0%** |
| Chat2DB | 96.7% | 93.3% | 100.0% | **94.0%** |

## 目录结构

```
nlp2sql/
├── README.md
├── datasets/
│   ├── dev_gold_mix50.sql        # Gold SQL 标准答案 (50题)
│   └── questions_mix50.txt       # 问题清单
├── results/
│   ├── moi/
│   │   ├── pred_mix50_moi.sql    # MOI 预测 SQL
│   │   └── report_mix50_records.txt  # 逐题对比报告
│   ├── wren/
│   │   ├── pred_mix50_wren.sql
│   │   └── report_mix50_wren_records.txt
│   └── chat2db/
│       ├── pred_mix50_chat2db.sql
│       └── report_mix50_chat2db_records.txt
└── scripts/                     # 评测脚本 (待添加)
```

## 评测方法

- 使用 Spider 官方 test-suite-sql-eval 工具
- Execution Accuracy (exec): Gold SQL 和预测 SQL 分别在 SQLite 上执行，对比结果集
- 评测参数: `--etype exec --keep_distinct`
