# DocBench 全量评估断点（2026-08-07）

## 状态

- 状态：已由用户主动暂停
- 数据集：DocBench
- 全量 query：1102
- 已完成并保留：38
- 未完成：1064
- 重复次数：1
- 评估类型：MOI native retrieve-then-generate
- embedding：TaaS `bge-m3`（1024 维，与现有向量库一致）
- 生成/Judge 回退：千帆，配置自动读取自 `.local-services/providers/qianfan.env`

## 运行目录

- Run：`runs/stage1/moi-rag-native/20260807-160758.787`
- 状态文件：`runs/stage1/moi-rag-native/20260807-160758.787/state.json`
- Manifest：`runs/stage1/moi-rag-native/20260807-160758.787/manifest.json`
- 已完成结果：`runs/stage1/moi-rag-native/20260807-160758.787/datasets/docbench/query-run/20260807-160801.486/results.jsonl`
- 已完成结果行数：38
- 查询日志：`runs/stage1/moi-rag-native/20260807-160758.787/logs/query-docbench.log`

## 暂停记录

`manifest.json` 与 `state.json` 均已写入 `status=interrupted`，没有评估进程残留。结果文件、问题集、配置和日志均保留。

恢复时应复用该运行目录中的配置、问题集和已完成结果；当前启动器默认会创建新 run，不能自动跳过这 38 个已完成 query。
