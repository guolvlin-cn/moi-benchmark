# scripts/

## test_suite_eval.py
Spider 官方 test-suite-sql-eval 评测工具。对比 gold SQL 和 pred SQL 的执行结果。

```bash
python3 test_suite_eval.py \
  --gold ../datasets/dev_gold_mix50.sql \
  --pred ../results/moi/pred_mix50_moi.sql \
  --db /path/to/spider/database \
  --table /path/to/spider/tables.json \
  --etype exec
```

## eval_report.py
生成逐题对比报告，每题显示 Gold SQL + 预测 SQL + 两端实际查询结果。

需要:
- Gold SQL 文件 (SQL\tdb_id 格式)
- 预测 SQL 文件 (一行一条SQL)
- Spider SQLite 数据库目录
- Spider dev.json (问题文本)

```bash
python3 eval_report.py \
  --gold ../datasets/dev_gold_mix50.sql \
  --pred ../results/chat2db/pred_mix50_chat2db.sql \
  --out ../results/chat2db/report.txt
```

## exec_eval.py
Spider 官方执行评测核心模块 (eval_exec_match, result_eq)，test_suite_eval.py 依赖此文件。
