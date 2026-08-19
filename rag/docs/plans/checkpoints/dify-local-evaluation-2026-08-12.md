# Dify 本地评估断点（2026-08-12）

## 状态

- **状态**：`USER_PAUSED`
- **暂停时间**：2026-08-12 09:39（Asia/Shanghai）
- **暂停范围**：仅暂停 Dify 本地评估 runner；Dify 本地 Docker 服务、数据卷和已有评估 artifact 保持运行/保留。
- **服务状态**：本地 Dify 容器仍在运行，API、Web、worker、PostgreSQL、Redis、Weaviate 等服务未执行 `down`。
- **模型出网**：沿用当前评估配置，Qianfan/MaaS provider 通过外部 endpoint 提供模型和 Embedding；本次断点未修改 provider 配置。

## 当前实验

- **平台**：`dify_local`
- **数据集/条件**：`MMDocIR / page`
- **阶段**：入库、解析和索引 readiness；QA 尚未开始。
- **运行目录**：

  `runs/competitor-eval-campaign/local-frozen-v14-20260811/004-mmdocir-page-dify_local`

- **当前 run id**：

  `local-frozen-v14-20260811-004-mmdocir-page-dify_local-attempt-3`

- **当前 run 目录**：

  `runs/competitor-eval-campaign/local-frozen-v14-20260811/004-mmdocir-page-dify_local/local-frozen-v14-20260811-004-mmdocir-page-dify_local-attempt-3`

- **原 runner PID**：`24584`
- **停止方式**：先发送 `SIGINT`，确认退出后未执行强制 kill；当前没有该 run 的 Dify evaluator 进程。

## 暂停时快照

`resource-map.partial.json` 中共记录 313 个资源 scope：

| 状态 | 数量 |
|---|---:|
| `ready` | 127 |
| `failed` | 69 |
| `indexing` | 1 |
| `not_started` | 116 |

- `progress.jsonl`：1118 行。
- `terminal-ledger.jsonl`：0 行；尚未产生 QA terminal record。
- QA 已完成问题数：0；因此本次 run 不能作为 QA 结果使用。
- 已保存 HTTP raw artifact：约 17,632 个 JSON 文件。
- 已保存的 run-relative secret 文件：128 个；仅保留路径引用，不在本文件或报告中展开内容。
- 最后记录的阶段：`ingest / polling`。
- 最后记录的 resource：`mmdocir:doc:mmdocir_doc_ed46f1d6c90ebcd2cde9f0ff`。
- 最后记录的状态：该 scope 仍处于 `indexing`，`active_indexing=true`。

已观察到的失败类型包括：

- 创建同名/同 key 数据集时返回 HTTP 409，表示本地 Dify 中已有对应资源；
- `DIFY_INDEX_TIMEOUT`，scope 仍为 `indexing`；
- `DIFY_INDEX_FAILED`，scope 返回 `error`。

上述失败记录和原始请求/响应保留在 run 目录中；没有根据答案文本推断检索或 citation 结果。

## Artifact 位置

以下文件和目录不要删除或覆盖：

- [resource-map.partial.json](/Users/muuushroom/gitrepos/moi-benchmark/rag/runs/competitor-eval-campaign/local-frozen-v14-20260811/004-mmdocir-page-dify_local/local-frozen-v14-20260811-004-mmdocir-page-dify_local-attempt-3/resource-map.partial.json)
- [resource-map.json](/Users/muuushroom/gitrepos/moi-benchmark/rag/runs/competitor-eval-campaign/local-frozen-v14-20260811/004-mmdocir-page-dify_local/local-frozen-v14-20260811-004-mmdocir-page-dify_local-attempt-3/resource-map.json)
- [progress.jsonl](/Users/muuushroom/gitrepos/moi-benchmark/rag/runs/competitor-eval-campaign/local-frozen-v14-20260811/004-mmdocir-page-dify_local/local-frozen-v14-20260811-004-mmdocir-page-dify_local-attempt-3/progress.jsonl)
- [terminal-ledger.jsonl](/Users/muuushroom/gitrepos/moi-benchmark/rag/runs/competitor-eval-campaign/local-frozen-v14-20260811/004-mmdocir-page-dify_local/local-frozen-v14-20260811-004-mmdocir-page-dify_local-attempt-3/terminal-ledger.jsonl)
- `runs/competitor-eval-campaign/local-frozen-v14-20260811/004-mmdocir-page-dify_local/local-frozen-v14-20260811-004-mmdocir-page-dify_local-attempt-3/http/`
- `runs/competitor-eval-campaign/local-frozen-v14-20260811/004-mmdocir-page-dify_local/local-frozen-v14-20260811-004-mmdocir-page-dify_local-attempt-3/providers/`
- `runs/competitor-eval-campaign/local-frozen-v14-20260811/004-mmdocir-page-dify_local/local-frozen-v14-20260811-004-mmdocir-page-dify_local-attempt-3/secrets/`

## 恢复方式

恢复前先确认 Dify 服务、provider endpoint 和当前 indexing scope 状态；不要删除 Dify 数据卷，也不要为同一断点重新生成新的 artifact 根目录。沿用本地未提交的 provider/Dify 环境变量后，可使用同一 `run_id` 恢复：

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag

python3 local-rag-platforms/scripts/evaluation/competitor_eval_runner.py qa \
  --system dify_local \
  --package .local-services/competitor-eval-ready/v1/mmdocir/page \
  --output-root runs/competitor-eval-campaign/local-frozen-v14-20260811/004-mmdocir-page-dify_local \
  --run-id local-frozen-v14-20260811-004-mmdocir-page-dify_local-attempt-3 \
  --repeats 1 \
  --top-k 10 \
  --poll-seconds 10 \
  --service-timeout 600 \
  --provider-timeout 60 \
  --upload-timeout 300 \
  --index-timeout 1800 \
  --query-timeout 120 \
  --qa-timeout 240 \
  --qa-concurrency 4 \
  --dify-max-indexing-scopes 1
```

恢复后先重新检查 `resource-map.partial.json` 和 Dify 中遗留的 dataset/document 状态，再决定是否对 409 资源做显式复用、清理或新建诊断 run。新的诊断尝试必须使用新的 `run_id`，不能覆盖本断点的原始记录。

## 断点结论

本次 Dify 评估已安全暂停，但尚未进入 QA，因此没有可汇报的 Dify QA 指标。该断点可从已有 127 个 ready scope 继续；剩余 116 个未开始 scope、69 个失败 scope 和 1 个 indexing scope 需要在恢复时继续处理或单独归因。Dify 本地服务仍可直接用于后续恢复和 API 调试。
