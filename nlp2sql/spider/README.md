# Spider Mix50 NL2SQL评测

本目录集中保存基于 Spider dev 数据集构建的 mix50 公开基准，避免与 `enron_eval/` 私有数据集评测混放。

## 评测范围

- 题目数量：50；
- 数据库：`concert_singer`、`car_1`、`pets_1`；
- 难度分布：easy 30 题、medium 15 题、hard 5 题；
- 参评产品：MOI、Wren AI、Chat2DB；
- 执行引擎：SQLite；
- 主指标：Spider test-suite Execution Accuracy。

## 结果摘要

| 产品 | 通过率 |
|------|:------:|
| MOI | 66% |
| Wren AI | 82% |
| Chat2DB | 94% |

上述结果只代表本次 Spider mix50 固定样本和当时产品环境，不应与 `enron_eval/` 的 MySQL 8 私有数据集结果直接合并排名。

## 目录结构

```text
spider/
├── README.md
├── NL2SQL评测汇总报告.md        # 完整过程、结果和失败分析
├── datasets/
│   ├── questions_mix50.txt      # 50道自然语言问题
│   └── dev_gold_mix50.sql       # Golden SQL
├── results/
│   ├── moi/                     # MOI预测SQL和逐题记录
│   ├── wren/                    # Wren AI预测SQL和逐题记录
│   └── chat2db/                 # Chat2DB预测SQL和逐题记录
└── scripts/                     # Spider执行评测和报告脚本
```

## 使用方式

进入 `scripts/` 后运行：

```bash
python3 test_suite_eval.py \
  --gold ../datasets/dev_gold_mix50.sql \
  --pred ../results/moi/pred_mix50_moi.sql \
  --db /path/to/spider/database \
  --table /path/to/spider/tables.json \
  --etype exec
```

完整评测结论见：[NL2SQL评测汇总报告](NL2SQL评测汇总报告.md)。
