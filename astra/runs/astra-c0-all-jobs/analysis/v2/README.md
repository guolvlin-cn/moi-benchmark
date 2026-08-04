# Astra C0 benchmark statistics v2

该目录提供可重复运行的 Astra C0 统计流程。脚本只读取 benchmark 产物，不修改 Astra 源码或任务结果。

## 运行

直接使用当前默认数据源：

```bash
python3 work/astra-c0-all-jobs/analysis/v2/extract_astra_c0_trials.py
```

默认扫描：

- `work/astra-c0-all-jobs`
- `work/astra-c0-rerun-from-scratch-33/jobs`

显式指定一个或多个输入根目录：

```bash
python3 work/astra-c0-all-jobs/analysis/v2/extract_astra_c0_trials.py \
  --root work/astra-c0-all-jobs \
  --root work/astra-c0-rerun-from-scratch-33/jobs \
  --output-dir work/astra-c0-all-jobs/analysis/v2/output
```

`--root` 可重复；所有 root 扫描完成后才会全局去重。`--exclude-task TASK_ID` 也可重复，且默认始终排除 `tune-mjcf`。

后续只重跑部分 case 时，把新结果放入已有扫描根目录，或把新目录作为额外 `--root`，然后重新执行同一命令即可。

如需从仍在运行的 MatrixOne 服务端按保存的 `astra_session_id` 补全 token，先把数据库密码放入环境变量，再启用严格查询：

```bash
MATRIXONE_PASSWORD='…' \
python3 work/astra-c0-all-jobs/analysis/v2/extract_astra_c0_trials.py \
  --matrixone-token-source required
```

脚本会临时运行 `mysql:8.4` 客户端，并通过
`--network=container:all-in-one-matrixone-1` 连到 `127.0.0.1:6001`；容器加
`--rm`，只执行 `SELECT`，结束后自动删除。`auto` 模式查询失败或没有密码时
回退本地 artifact，`required` 则会失败退出，避免静默降级。密码不会进入命令行、
SQL、CSV、JSON 或报告。

## 选择规则

顺序固定为：

1. 递归发现所有具有 `task_name` 的 trial `result.json`；
2. 按 `task_id` 跨 root 选择最新 attempt；
3. 排除 `tune-mjcf` 和命令行指定的额外 task；
4. 只纳入 latest attempt 的 `verifier_result.rewards.reward` 为数字 `0` 或 `1` 的 case。

“最新”主键是离 trial 最近的 `YYYY-MM-DD__HH-MM-SS` 批次目录时间，依次以 `result.started_at`、`result.finished_at`、绝对路径打破平局。注意：如果 latest attempt 没有数字 verifier reward，任务会被排除，不会退回较旧的已评分 attempt。全部选择过程保存在 attempt audit CSV 中。

## 输出

默认写入 `analysis/v2/output/`：

- `astra-c0-latest-verified-trials.csv`：最终纳入的 task 级完整字段；
- `astra-c0-latest-verified-no-pass.csv`：上述数据的 verifier no-pass 子集；
- `astra-c0-latest-verified-summary.json`：机器可读的范围、完成情况、分组指标、定义与限制；
- `astra-c0-latest-verified-report.md`：人读报告；
- `astra-c0-attempt-selection.csv`：每次 attempt、排序与选取/排除原因；
- `astra-c0-data-quality.csv`：缺失 CTRF、token 不完整、timeout 配置不一致等质量问题。

所有 CSV 使用 UTF-8 with BOM，方便 Excel 直接打开。

## 数据口径

### Verify 与完成情况

- `verify_status` 只由数字 verifier reward 决定：`1=pass`，`0=no_pass`；CTRF 只提供独立的子测试明细。
- `normal_e2e_pass` 要求 verify pass、`product_terminal_status=completed`、return code 0、且无 Harbor exception。
- `clean_e2e_pass` 在 normal E2E 的基础上再要求无 timeout、无外层 retry。
- verify、timeout、产品生命周期、trajectory、formal eligibility 和 lifecycle gate 是互相独立的维度。一次运行可以 timeout 后仍通过 verifier。

### Timeout

脚本不会对所有日志做宽泛的 `timeout` 关键词搜索，因为配置字段本身就含有该词。当前分类为：

- `llm_request_timeout`：local session 中 `stream_transport` interruption 的 error detail，或 stderr，明确出现 `LLM fallback request failed (timeout Ns)`；
- `product_timeout`：产品终态或产品错误类型明确表示 timeout；
- `verifier_timeout`：Harbor verifier exception 明确表示 timeout；
- `adapter_timeout`：其他 Harbor exception 明确表示 timed out；
- `controller_deadline_suspected`：retry report 仍为 running/incomplete，且 agent execution 已达到配置 product deadline 的 95%。

最后一项是明确标注的推断，不是假装存在 literal timeout 日志。`timeout_observed`、`timeout_inferred` 和合并后的 `timeout` 均保留，避免混淆。

为兼容统一的 timeout/no-timeout 分组，trial 级 `timeout` 是 `timeout_or_deadline_suspected` 的别名。只接受 literal 证据时应使用 `timeout_observed`；报告会并列给出 observed、suspected 和二者并集，不能把推断的 3 项直接称为已确认 timeout。

### 时间与工具

- E2E、environment setup、agent setup、agent execution、verifier 都由 `started_at`/`finished_at` 相减。
- 外层 attempt duration 来自 `stream-transport-retry.json`。
- LLM 累计延迟来自 `context_trace_signal.metadata.timing.llm_total_ms`。
- 工具统计来自 local `step_events.jsonl`，按 event/call id 去重，分别统计 `ToolCallStarted/Completed/Failed/Skipped`。
- 工具失败率是 `failed / (completed + failed)`；skipped 不进入分母。
- `tool_telemetry_status=ledger_internally_complete` 只表示现有 step ledger 内部 started/terminal 闭合；如果整体 trajectory 为 partial，仍不能证明没有漏捕事件。
- LLM 和工具 duration 是调用延迟之和，可能因并行而重叠，不能解释为 agent 或批次 wall time。

### Token

Token 是供应商 usage 的落盘观测值，不使用本地 tokenizer：

```text
token_input = token_fresh_input + token_cache_read + token_cache_creation
token_total = token_input + token_output
```

cache 已经是 input 的组成部分，不能再计算 `input + cache + output`。

来源优先级与重试处理：

1. 服务端优先：若当前 MatrixOne 中还保留该 `astra_session_id`，汇总 `astra_runtime.agent_events` 的 `event_type=llm_response`。这是一行一个已返回模型响应的服务端记录，能覆盖 session 内 retry；命中的字段会写入 `token_server_*`，并成为 `token_*` 的 canonical 值。
2. 本地回退 session-wide input：汇总 `server-events.jsonl` 中去重后的 `context_trace_signal.metadata.budget.total_used`；
3. 本地 fresh/cache/output：最终成功的 `astra.stdout.json` 加最终成功 attempt 开始之前的 `pipeline_feedback`；
4. 没有成功 stdout：汇总所有已经返回并落盘的 `pipeline_feedback`；
5. `result.json` 的 Harbor token 只作终态交叉检查，不能替代跨 retry 的 session 总量。

服务端未命中通常意味着数据库保留期已过，绝不等同于 token 为 0；此时 `token_server_status=queried_not_found` 且脚本使用本地回退。只有 session input 与重建明细对账、且 output 存在时才提供“完整可观测 `token_total`”。这里的“完整”只针对已经返回并落盘的 usage 分量，不代表实际账单绝对完整。缺失 usage 保持空值，不按 0 处理；`token_known_minimum` 单列所有可观测部分。断流时，尚未返回 usage 的在途请求可能无法恢复，因此即使标为 reconciled，这仍不是供应商账单。

### 不可用资源

现有 artifact 没有可靠的 CPU、RAM、GPU、磁盘 I/O、网络字节或实际 provider billing。脚本在 summary 中标记为 `unavailable`，不会从执行时间或 token 推算。

## 测试

```bash
python3 -m unittest discover \
  -s work/astra-c0-all-jobs/analysis/v2/tests \
  -v
```

当前真实数据的数量只用于人工回归检查，不硬编码在单元测试中；因此未来添加新 attempt 不会导致合理的数据更新被测试误判为失败。
