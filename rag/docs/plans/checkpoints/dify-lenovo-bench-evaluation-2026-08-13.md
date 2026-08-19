# Dify Lenovo-Bench 本地评估断点（2026-08-13）

## 当前状态

- 状态：`PARTIAL`（评测流程完成；1 条 QA 因 Qianfan `system_unsafe` 失败）
- 数据包已生成并通过 `EvalPackage.load` 校验；Dify 服务已确认运行，独立 dataset 已创建。
- 评估范围：Lenovo-Bench `moi-corpus-100q-v1` 的 formal split。

## 评估目标

- 系统：`dify_local`
- 数据包：`runs/dify-lenovo-bench-20260813/lenovo-bench-formal-v1/package`
- 语料：46 个原始 PDF、1104 页，全局单数据集入库。
- QA：60 条 formal QA，其中 answerable 53 条、unanswerable 7 条。
- run id：`dify-local-lenovo-bench-formal-v1`
- 输出根目录：`runs/dify-lenovo-bench-20260813`
- Dify dataset id：`2016e123-618e-4016-861d-dcda5d4db3d2`
- 条件：原始 PDF native ingestion；Dify 使用配置的 bge-m3 embedding 与默认 semantic retrieval。

## 解析与数据契约

- `package/manifest.json`、`package/corpus.jsonl`、`package/questions.jsonl` 已生成。
- `audit/prepared-pages.jsonl` 已生成 1104 条页面记录。
- 已复用 precision MinerU 输出核对扫描版 `Anti-Slavery_and_Human_Trafficking_Statement.pdf`；页面级审计记录 30 个无可提取文本页面，其中扫描版主体已保留 MinerU 文本。
- gold 字段保留 `source_documents`、`claims`、`evidence_sets`、`citation_requirements`、`answerability`，便于 QA 完成后计算 Lenovo-Bench 指标。

## 运行命令

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag
set -a; . .local-services/providers/qianfan.env; set +a
python3 local-rag-platforms/scripts/evaluation/competitor_eval_runner.py all \
  --system dify_local \
  --package runs/dify-lenovo-bench-20260813/lenovo-bench-formal-v1/package \
  --output-root runs/dify-lenovo-bench-20260813 \
  --run-id dify-local-lenovo-bench-formal-v1 \
  --repeats 1 --top-k 10 --poll-seconds 10 \
  --service-timeout 120 --provider-timeout 60 --upload-timeout 300 \
  --index-timeout 14400 --query-timeout 120 --qa-timeout 240 \
  --qa-concurrency 1 --dify-max-indexing-scopes 1
```

运行时重点查看：`dify-local-lenovo-bench-formal-v1/resource-map.json`、`terminal-ledger.jsonl`、`retrieval-metrics.json`、`qa-metrics.json` 和 runner 日志。generic runner 完成后，再由 Lenovo-Bench gold contract 计算 evidence-set、claim、answerability、citation 与延迟指标。

## 完成状态（2026-08-13 13:41 Asia/Shanghai）

- preflight：`READY`。
- ingest：46/46 文档 `completed`，Dify dataset id 为 `2016e123-618e-4016-861d-dcda5d4db3d2`。
- retrieval：60/60 `SUCCESS`。
- QA：60/60 终结，其中 59 `SUCCESS`、`moi100-q051` 失败；失败原因是 Qianfan 返回 `system_unsafe`，已保留原始 HTTP artifact。
- Lenovo judge：59/59 `success`。
- 指标：`dify-local-lenovo-bench-formal-v1/lenovo-metrics.json`；逐题结果：`lenovo-scored-rows.jsonl`；judge 断点：`lenovo-judge-ledger.jsonl`。
- 实时日志：`runs/dify-lenovo-bench-20260813/lenovo-bench-formal-v1/logs/runner-all-20260813-1230.log`；runner 结构化 progress 在实际输出目录的 `progress.jsonl`。

## 可复核的异常处理

- Weaviate 在入库期间自动重启并完成 schema/LSM 恢复；4 个在恢复窗口进入 error 的 PDF 已在同一 dataset 中删除后按原 PDF 重新上传并完成索引。
- 第一次因服务恢复失败的 120 条 BLOCKED terminal 行保留在 `terminal-ledger.first-attempt-blocked.jsonl`；最终账本只包含本次有效评测结果。
- 当前状态是 `PARTIAL` 而非 `SUCCESS`，因为 q051 的 QA 失败被保留在全量 60 题分母中。
