# MOI current-corpus RAG 评估 checkpoint（2026-08-11）

## 当前任务

- 协议：`CURRENT_CORPUS_ADAPTED`，仅评估已经存在于 MatrixOne 的语料，不补数据，不冒充论文官方完整语料。
- 顺序：DocBench → MMDocRAG → EnterpriseRAG-Bench → FAB-Bench。
- 已复用、不重跑：WikiEval MOI 50/50；MMDocIR MOI Page/Layout 各 1,658/1,658。
- 正式运行目录：`/Users/muuushroom/gitrepos/moi-benchmark/rag/runs/current-corpus-eval/20260811-021527.812`
- 终端日志：`/Users/muuushroom/gitrepos/moi-benchmark/rag/runs/current-corpus-eval-live.log`

## 冻结分母

| 数据集 | 当前 MatrixOne 文件 | 问题 |
|---|---:|---:|
| DocBench | 188 | 906 |
| MMDocRAG | 162 | 1,504 |
| EnterpriseRAG-Bench | 722 | 500 |
| FAB-Bench | 127 | 200 |

每个数据集的完整 `file_id` 集合、配置和问题快照均在 run 目录中保存并记录 SHA-256。Enterprise/FAB 对冻结的全部 current-corpus file IDs 做全库检索；DocBench/MMDocRAG 保持文档内检索。

## 启动与恢复

首次启动命令：

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag
python3 benchmarks/moi_current_corpus_eval.py
```

若进程因 API 错误、终端关闭或重启而停止，使用：

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag
python3 benchmarks/moi_current_corpus_eval.py \
  --resume /Users/muuushroom/gitrepos/moi-benchmark/rag/runs/current-corpus-eval/20260811-021527.812
```

恢复时复用已成功的 query/judge，不重复请求；初次失败仍保留在 first-pass 分母，恢复成功另存到 `recovered-results.jsonl`。

## 停机和结果规则

- embedding、generation、judge 均使用华为 MaaS；`bge-m3` + `qwen3-30b-a3b`。
- API retry 固定为 1，无 fallback。单题 API/HTTP/网络/超时或 judge 错误写入该数据集的 `skipped-errors.jsonl`，保留在首次请求分母中并跳过该题，随后继续评估；恢复时成功题和失败题都视为已完成，只运行尚无 terminal 结果的题。只有评估子进程崩溃、数据库/配置损坏等无法归属到单题的致命错误才停止整场。
- 每个数据集完成后生成 `qa-ledger.jsonl`，逐题保存原始 answer、ranked chunks、routes、provider/model、latency、原始 metrics、重新计算的逐题 metrics、judge 原始记录及 error；查询期间 Go `results.jsonl` 每题落盘，因此终端关闭或机器重启后仍可从同一 run 断点恢复。
- 2026-08-11 性能调整：实测 2 路全文检索会使当前 2 核 Colima 内的 MatrixOne 失去响应，因此正式运行保持本地查询 1 路、MaaS judge 2 路并发；查询 worker 仍独立写结果目录。`SHOW PROCESSLIST` 证明客户端 deadline 后全文 SQL 仍会留在 MatrixOne 服务端执行，因此任一 full-text deadline、`bad connection` 或 `unexpected EOF` 都立即触发熔断：停止当前 worker、只重启 `matrixone` 容器，`SELECT 1` 健康检查通过后自动从未完成题恢复。
- 原始逐题结果、judge 原始返回、日志、配置、问题、语料 manifest、metrics 和报告全部保存在正式 run 目录。
- DocBench/MMDocRAG 当前表没有 page image trace，因此本轮为 text-only adapted QA；图片 Recall、Image Quote P/R/F1 等指标留空。
- EnterpriseRAG-Bench 的论文官方 Correctness/Completeness judge 与 FAB-Bench 六维 G-Eval scorer 本地不可用时留空；仍计算可审计的检索、延迟、availability、lexical/客观题诊断指标。
- 正式运行完成后，以 run 内 `report.md` 和 `aggregated-metrics.json` 为准回填根目录 `TODO.md`。
- 已启动独立完成监听器；只有 `state.json.status=succeeded` 时才运行 `benchmarks/update_todo_from_current_corpus_eval.py`，把指标写入根目录 `TODO.md` 的实验 4/5/6/9/10/11/12 MOI 行。若评估失败则不填伪结果。
