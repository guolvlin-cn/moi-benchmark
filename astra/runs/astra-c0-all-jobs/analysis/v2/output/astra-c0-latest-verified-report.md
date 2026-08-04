# Astra C0 latest verified benchmark statistics

本报告由 `extract_astra_c0_trials.py` 自动生成。新增或替换部分 case 的运行结果后，重新执行脚本即可；不要手工修改产物。

## 范围与最新运行选择

| 项目 | 数量/内容 |
| --- | ---: |
| 扫描到的有效 attempt | 121 |
| 排除前唯一 task | 89 |
| 存在重复运行的 task | 32 |
| 重复产生的额外 attempt | 32 |
| 排除 task | tune-mjcf |
| 最终纳入的 latest + verified task | 86 |

选择顺序是：先跨所有输入目录按 task 选最后一次运行，再排除 `tune-mjcf`，最后只纳入 latest reward 为数字 `0/1` 的 case。latest 没有 verifier reward 时不会回退到旧的已评分运行。

最新运行无数字 verifier reward：torch-tensor-parallelism, train-fasttext。

## 完成情况

| 指标 | 数量 |
| --- | ---: |
| Verify pass | 44 |
| Verify no-pass | 42 |
| Verify pass rate | 51.16% |
| Observed timeout（明确证据） | 34 |
| Controller deadline suspected（推断） | 3 |
| Timeout or deadline suspected（并集） | 37 |
| Neither timeout nor deadline suspected | 49 |
| Combined rate | 43.02% |
| Normal E2E pass | 36 |
| Clean E2E pass | 35 |
| Harbor exception | 0 |

`normal_e2e_pass` 要求 verifier pass、product completed、return code 0 且无 Harbor exception；`clean_e2e_pass` 进一步要求没有 timeout 且没有外层 retry。轨迹完整性、formal eligibility 和 lifecycle gate 分开报告，不用来改写 verifier 分数。

| Verify × Timeout-or-deadline-suspected | Yes | No |
| --- | ---: | ---: |
| Pass | 3 | 41 |
| No-pass | 34 | 8 |

Timeout 类型：controller_deadline_suspected=3, llm_request_timeout=34。其中 `controller_deadline_suspected` 是由“retry report 仍为 running/incomplete + agent 时长达到配置 deadline”推断的单列指标；其余是显式日志/状态/异常证据。

## 时间与资源

| 指标 | 覆盖 | 累计 | 中位数 | P90 |
| --- | ---: | ---: | ---: | ---: |
| 端到端 task 时间 | 86/86 | 2444.60 min | 16.81 min | 60.27 min |
| Environment setup | 86/86 | 105.32 min | 0.10 min | 0.34 min |
| Agent setup | 86/86 | 31.06 min | 0.07 min | 1.25 min |
| Agent execution | 86/86 | 1937.51 min | 15.05 min | 49.52 min |
| Verifier | 86/86 | 337.04 min | 0.47 min | 2.41 min |
| 外层 product attempt 累计 | 27/86 | 516.45 min | 18.85 min | 36.35 min |
| LLM 调用累计延迟 | 84/86 | 943.68 min | 8.46 min | 27.12 min |

这些累计值是 task-seconds 或调用延迟之和，不是整批并行 benchmark 的墙钟时间。LLM 与工具调用可能重叠，不能与 agent wall time 相加做资源分解。CPU、RAM、GPU、磁盘、网络字节和实际供应商账单在现有 artifact 中不可用，脚本不做估算。

## Token 数据口径

- 数据来自 Astra 落盘的供应商 usage，不使用本地 tokenizer。若本次查询命中 MatrixOne，则优先采用 `astra_runtime.agent_events` 中该 session 的 `llm_response` 聚合；未命中才回退到本地落盘记录。
- `input = fresh + cache_read + cache_creation`；`total = input + output`。cache 已包含在 input 内，绝不再次相加。
- 本地回退的 session input 汇总 `server-events.jsonl` 中去重后的 `context_trace_signal.metadata.budget.total_used`，可覆盖同 session 的外层 resume/retry。
- fresh/cache/output 由最终成功的 `astra.stdout.json` 加上最终 attempt 开始前的 `pipeline_feedback` 重建；没有成功 stdout 时使用全部已经返回的 feedback usage。
- `result.json` 的 Harbor token 只作终态交叉检查；它通常只覆盖最后一次 CLI invocation，不能替代 session-wide retry 总量。
- 缺失不是 0。只有 canonical input 和重建 output 都完整时才给“完整可观测 `token_total`”；否则只给明确命名的 `token_known_minimum`。断流中未返回 usage 的在途请求仍可能漏记，因此这不是账单口径。
- MatrixOne 查询：mode=required，status=queried，请求 session=86，命中 session=9。数据库保留期外的旧 session 会显示为未命中，而不是 token=0。

| Token 指标 | 覆盖 | 合计 | 中位数 | P90 |
| --- | ---: | ---: | ---: | ---: |
| Input（含 cache） | 86/86 | 31,119,204 | 213,510.50 | 928,243 |
| Fresh input | 85/86 | 4,555,848 | 37,410 | 117,777.80 |
| Cache read | 85/86 | 26,067,392 | 169,856 | 841,100.80 |
| Cache creation | 85/86 | 0 | 0 | 0 |
| Output | 85/86 | 3,515,722 | 25,396 | 99,112.40 |
| 完整可观测 total | 85/86 | 34,138,962 | 238,214 | 1,030,025.80 |
| 可观测 minimum | 86/86 | 34,634,926 | 241,113 | 1,016,953.50 |

| Token accounting status | Tasks |
| --- | ---: |
| complete_no_trace_crosscheck | 1 |
| complete_terminal_no_trace | 1 |
| server_reconciled | 9 |
| session_input_only | 1 |
| session_reconciled | 74 |

## 工具调用

工具以 local `step_events.jsonl` 为账本，按 event/call id 去重。`ledger_internally_complete` 只表示现有账本内部 started/terminal 闭合，不保证 partial trajectory 没有漏捕。started、completed、failed、skipped 分开；失败率是 `failed / (completed + failed)`。工具 elapsed 之和是累计调用延迟，并行时会重复覆盖墙钟时间。

| 指标 | 数量 |
| --- | ---: |
| Agentic StepStarted | 1,674 |
| ToolCallStarted | 2,253 |
| ToolCallCompleted | 2,096 |
| ToolCallFailed | 155 |
| ToolCallSkipped | 2 |
| 终态覆盖率 | 100.00% |
| 加权失败率 | 6.89% |

工具分布：`{"bash":1546,"display_sixel":2,"git":18,"glob":4,"grep":74,"introspect":40,"list_dir":35,"read_file":258,"reflect":28,"session":4,"str_replace":23,"task_board":104,"tool_search":7,"web_fetch":5,"web_search":7,"write_file":98}`。

失败工具分布：`{"bash":125,"git":11,"grep":1,"read_file":5,"str_replace":1,"web_fetch":5,"write_file":7}`。

## 数据质量与 no-pass 明细

CTRF 覆盖 85/86；数据质量 issue 共 21 条。逐项记录见 `astra-c0-data-quality.csv`，全部 attempt 的选择过程见 `astra-c0-attempt-selection.csv`。

Issue 类型：controller_deadline_inferred=3, fallback_timeout_config_mismatch=11, matrixone_local_trace_delta=2, missing_ctrf=1, retry_report_incomplete=3, token_input_only=1。

| Task | Timeout 类型 | Product 状态 | Token 状态 | Tool started/failed | 路径 |
| --- | --- | --- | --- | ---: | --- |
| adaptive-rejection-sampler | llm_request_timeout | failed | session_reconciled | 44/3 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-07-31__16-47-36/adaptive-rejection-sampler__zWvbxZ5` |
| build-pmars | no | completed | session_reconciled | 85/5 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/build-pmars__FWjWrmH` |
| build-pov-ray | no | completed | session_reconciled | 76/3 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-07-31__16-04-29/build-pov-ray__92VcxjZ` |
| cancel-async-tasks | no | completed | session_reconciled | 4/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-08-03__00-05-42/cancel-async-tasks__4fjo42J` |
| chess-best-move | llm_request_timeout | failed | session_reconciled | 8/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/chess-best-move__FRDxL33` |
| circuit-fibsqrt | llm_request_timeout | failed | server_reconciled | 43/2 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-08-03__11-07-37/circuit-fibsqrt__bCZJk4C` |
| code-from-image | llm_request_timeout | failed | session_reconciled | 34/1 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/code-from-image__gvGTG56` |
| crack-7z-hash | llm_request_timeout | failed | session_reconciled | 42/4 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/crack-7z-hash__cPniiwq` |
| distribution-search | llm_request_timeout | failed | session_reconciled | 1/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/distribution-search__8DZUgkw` |
| dna-assembly | llm_request_timeout | completed | session_reconciled | 35/4 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-08-03__01-30-00/dna-assembly__eBo7G6H` |
| dna-insert | no | completed | server_reconciled | 18/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-08-03__13-01-37/dna-insert__CxCpvgu` |
| extract-elf | llm_request_timeout | failed | session_reconciled | 11/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/extract-elf__GD6CnuF` |
| extract-moves-from-video | no | adapter_infra_error | complete_no_trace_crosscheck | 58/5 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/extract-moves-from-video__Kn9TUHU` |
| filter-js-from-html | llm_request_timeout | failed | session_reconciled | 1/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/filter-js-from-html__nxqNena` |
| gcode-to-text | llm_request_timeout | failed | session_reconciled | 29/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/gcode-to-text__zfxZT3h` |
| gpt2-codegolf | llm_request_timeout | failed | server_reconciled | 36/4 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-08-03__16-27-47/gpt2-codegolf__drvhmQJ` |
| hf-model-inference | no | completed | session_reconciled | 23/2 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-08-03__01-15-16/hf-model-inference__WnwC9qD` |
| install-windows-3.11 | llm_request_timeout | adapter_infra_error | session_reconciled | 61/6 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/install-windows-3.11__uZvMHsz` |
| kv-store-grpc | no | adapter_infra_error | session_reconciled | 15/1 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-07-31__17-23-32/kv-store-grpc__DmHsvDp` |
| llm-inference-batching-scheduler | llm_request_timeout | failed | session_reconciled | 4/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/llm-inference-batching-scheduler__rd2oFtp` |
| mailman | llm_request_timeout | failed | session_reconciled | 38/7 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/mailman__k3KGXd5` |
| make-doom-for-mips | controller_deadline_suspected | adapter_infra_error | server_reconciled | 58/1 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-08-03__12-26-04/make-doom-for-mips__LTHmSGk` |
| make-mips-interpreter | llm_request_timeout | completed | server_reconciled | 72/5 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-08-03__10-22-52/make-mips-interpreter__3pmWNgQ` |
| mcmc-sampling-stan | no | completed | session_reconciled | 47/1 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/mcmc-sampling-stan__MUwmpU6` |
| model-extraction-relu-logits | llm_request_timeout | completed | session_reconciled | 22/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-08-03__00-47-16/model-extraction-relu-logits__S8Ng7R3` |
| overfull-hbox | llm_request_timeout | failed | session_reconciled | 7/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/overfull-hbox__dd6SowD` |
| path-tracing | llm_request_timeout | failed | session_reconciled | 15/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/path-tracing__MeFg9Qn` |
| path-tracing-reverse | llm_request_timeout | failed | session_reconciled | 29/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/path-tracing-reverse__4bBbg5Q` |
| polyglot-rust-c | llm_request_timeout | failed | session_reconciled | 26/1 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-08-02__23-38-33/polyglot-rust-c__MxGEeoh` |
| portfolio-optimization | llm_request_timeout | failed | session_reconciled | 6/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/portfolio-optimization__wVkTn6y` |
| protein-assembly | llm_request_timeout | failed | session_reconciled | 39/1 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/protein-assembly__KBjU6Hg` |
| qemu-startup | controller_deadline_suspected | adapter_infra_error | server_reconciled | 33/7 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-08-03__15-19-11/qemu-startup__qvWN54g` |
| raman-fitting | llm_request_timeout | failed | session_reconciled | 12/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/raman-fitting__p6RLcDx` |
| regex-chess | llm_request_timeout | failed | session_reconciled | 2/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/regex-chess__mjmpJiQ` |
| regex-log | llm_request_timeout | failed | session_reconciled | 27/1 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-07-31__15-21-07/regex-log__jhTUvrD` |
| reshard-c4-data | llm_request_timeout | failed | session_reconciled | 4/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/reshard-c4-data__LivLs9j` |
| rstan-to-pystan | llm_request_timeout | failed | session_reconciled | 16/1 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/rstan-to-pystan__XccEPFL` |
| schemelike-metacircular-eval | llm_request_timeout | failed | session_reconciled | 4/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/schemelike-metacircular-eval__YB25YaT` |
| torch-pipeline-parallelism | llm_request_timeout | failed | session_reconciled | 2/0 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/torch-pipeline-parallelism__iioR7V9` |
| video-processing | llm_request_timeout | failed | server_reconciled | 46/1 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-08-03__11-35-33/video-processing__dmjKwBT` |
| winning-avg-corewars | llm_request_timeout | failed | session_reconciled | 8/1 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-all-jobs/2026-07-29__19-36-33/winning-avg-corewars__x5s4avf` |
| write-compressor | llm_request_timeout | failed | session_reconciled | 21/1 | `/Users/chenyuwei/Documents/MOI benchmark/work/astra-c0-rerun-from-scratch-33/jobs/2026-08-03__00-09-45/write-compressor__hXHvyBd` |
