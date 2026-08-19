# Local RAG platform scripts

这里集中放置竞品目录的可执行脚本；平台实现和部署资源仍保留在各自的
`*_local/` 目录，统一 API 保留在 `api/`，共享测试保留在 `tests/`。

```text
scripts/
├── deployment/          # 本地服务 prepare / record / preflight
├── evaluation/          # 竞品评测 runner、数据包、judge 和 MMDocIR/WikiEval
├── benchmarks/
│   ├── lenovo/          # Lenovo-Bench 运行、评分和 watcher
│   ├── enterprise/     # EnterpriseRAG-Bench 专用处理
│   └── providers/      # MaaS/Qianfan 外部 embedding 基线
└── reports/             # benchmark 合并和 pilot 汇总
```

脚本默认从仓库根目录执行，运行产物仍写入根目录的 `runs/` 或被忽略的
`.local-services/`，不会因为脚本移动而改变产物位置。

例如：

```bash
python3 local-rag-platforms/scripts/deployment/prepare_local_services.py preflight
python3 local-rag-platforms/scripts/evaluation/competitor_eval_runner.py preflight --system fastgpt_local
python3 local-rag-platforms/scripts/benchmarks/lenovo/lenovo_latency_benchmark.py --help
```
