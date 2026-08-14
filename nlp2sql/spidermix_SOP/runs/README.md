# Spider Mix50运行结果说明

本目录同时保留正式结果和形成正式结果时的smoke、局部重跑、全局上下文试验，以便追溯。对外报告和自动验证只读取以下三组正式结果：

| 产品 | 正式目录 | 用途 |
|---|---|---|
| MOI | `moi/moi_spider_qwen37_20260813_round1/` | MatrixOne原生执行结果 |
| Wren AI | `wren/wren_spider_qwen37_20260814_round1/` | 同源MySQL评分 |
| Chat2DB | `chat2db/chat2db_spider_qwen37_20260814_fixed_database_round1/` | 三个固定数据库批次合并结果 |

其他目录不进入正式分数，不得与上述三组混合。正式目录、模型和指标由 `../provenance/freeze_manifest.json` 指定，并通过 `../verify_sop.py` 校验。
