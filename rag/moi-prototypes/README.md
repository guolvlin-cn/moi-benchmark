# MOI Prototypes：本地实现指南

本目录保存 MatrixFlow/MOI RAG 链路的可独立运行实现。它把解析、Embedding、
产品 RAG 和端到端编排拆成几个小模块，便于单独测试产品行为、替换 provider、
记录延迟和定位失败阶段。

这些模块不是完整 MatrixFlow Web 部署，也不把本地实验结果自动宣称为官方
`standard_rag` 端到端结果。每次运行都要记录实际使用的 parser route、模型、
索引表、数据集和 provider。

## 模块地图

| 模块 | 实现 | 主要用途 | 入口 |
|---|---|---|---|
| `local-matrixflow-parser/` | Go | MatrixFlow 文档解析、Office/OpenXML、MinerU、TaaS VLM | `go run ./cmd/local-matrixflow-parser ...` |
| `local-bge-m3-embedding/` | Python/FastAPI | 本机 BGE-M3 dense embedding OpenAI-compatible 服务 | `./start_local_bge_m3.command` |
| `local-matrixflow-rag/` | Go 产品模块 + Python CLI | MatrixOne 索引、MatrixFlow SearchRAGChunks、检索 Benchmark | `python3 local_matrixflow_rag.py ...` |
| `local-matrixflow-pipeline/` | Python | parser → documents.jsonl → ingest → QA/Benchmark 编排 | `python3 pipeline.py ...` |

## 依赖和目录布局

Go 模块通过 `replace` 使用相邻的 MatrixFlow checkout。推荐布局：

```text
gitrepos/
├── matrixflow/
└── moi-benchmark/
    └── rag/
        └── moi-prototypes/
```

先确认依赖和本地工具：

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag
test -d ../../matrixflow/moi-core
go version
python3 --version
docker compose version
uv --version
```

共享 API key 放在 `rag/.env`，不要提交真实值。Parser 的 `--env-file`、Pipeline
的 `--env-file` 和本地 RAG 的环境加载都应指向同一份本机凭据来源。

## 最短可运行链路：MatrixOne + 产品 RAG

### 1. 准备配置

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag
cp .env.example .env
chmod 600 .env

cd moi-prototypes/local-matrixflow-rag
cp config.example.json config.local.json
```

`config.example.json` 默认使用 MatrixOrigin TaaS 的 `BAAI/bge-m3`，向量维度
为 1024。离线接线测试可改用 `config.offline.example.json`；hash embedding
只验证写入、检索和结果结构，不代表产品质量。

### 2. 只启动 MatrixOne

```bash
docker compose up -d
docker compose ps
```

本地 MatrixOne 默认监听 `127.0.0.1:6001`。不要为了运行这个 prototype 启动
完整 MatrixFlow Web、Catalog 或 Worker。

### 3. 检查依赖并运行 smoke

```bash
set -a
source ../../.env
set +a

python3 local_matrixflow_rag.py check --config config.local.json
python3 local_matrixflow_rag.py pipeline \
  --config config.local.json \
  --source data/documents \
  --dataset data/questions.jsonl \
  --run runs/local-smoke \
  --max-hits 10 \
  --repeats 1 \
  --force
```

也可以分阶段运行：

```bash
python3 local_matrixflow_rag.py ingest \
  --config config.local.json \
  --source data/documents \
  --run runs/local-ingest \
  --force

python3 local_matrixflow_rag.py run \
  --config config.local.json \
  --dataset data/questions.jsonl \
  --run runs/local-query \
  --max-hits 10 \
  --repeats 1
```

更换 embedding provider 或维度后必须使用新的数据库/表，不能把 Qianfan 4096
维向量写入已有的 TaaS/BGE-M3 1024 维索引。

## 解析链路

### 解析路线

| route | 依赖 | 适用场景 | 结果边界 |
|---|---|---|---|
| `local` + `web-default` | 本地 parser | 复现产品路由边界、文本/Office 兼容路径 | 会明确记录未配置的外部 backend |
| `local` + `v3-native` | MatrixFlow Native | 本地文本、PDF、OpenXML 解析 | 不等于 Web `standard_rag` V2 |
| `precision` | 官方 MinerU API | 扫描 PDF、复杂版面 | 需要 `MINERU_API_TOKEN` |
| `agent` | 官方 MinerU Agent API | 轻量 Markdown 解析 | 有更严格的文件/页限制 |
| `vlm` | TaaS VLM | 图片或页面视觉补充 | 需要 `TAAS_API_KEY`，输出再走 Markdown normalization |

先做依赖规划：

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag/moi-prototypes/local-matrixflow-parser
go run ./cmd/local-matrixflow-parser plan \
  --input /absolute/path/document.pdf
```

执行本地 Native 解析：

```bash
go run ./cmd/local-matrixflow-parser parse \
  --input /absolute/path/document.pdf \
  --profile v3-native \
  --run runs/pdf-native
```

执行官方 MinerU precision 解析：

```bash
go run ./cmd/local-matrixflow-parser parse \
  --input /absolute/path/document.pdf \
  --pipeline precision \
  --env-file ../../.env \
  --run runs/mineru-precision
```

解析 run 会生成带时间戳的子目录，重点产物包括 `documents.jsonl`、manifest、
原始响应和阶段耗时。将解析产物交给 RAG 模块时使用 `--documents`，不要重新
猜测或手工改写文档结构。

## 本地 BGE-M3 Embedding

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag/moi-prototypes/local-bge-m3-embedding
cp .env.example .env
uv sync
./start_local_bge_m3.command
```

验证 API：

```bash
curl -fsS http://127.0.0.1:8081/healthz
curl -fsS http://127.0.0.1:8081/v1/models
curl -fsS http://127.0.0.1:8081/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-m3","input":["local smoke"]}'
```

默认是 lazy load；第一次 embedding 请求会加载或下载模型。macOS 优先使用
`BGE_DEVICE=auto`，如 MPS 不稳定则改为 `cpu`。服务只提供 BGE-M3 dense
1024 维向量，不实现 sparse 或 ColBERT 输出。

让 RAG 模块使用本地服务：

```bash
cd ../local-matrixflow-rag
cp config.local-bge-m3.example.json config.local-bge-m3.json
python3 local_matrixflow_rag.py check --config config.local-bge-m3.json
```

## 端到端编排

`local-matrixflow-pipeline` 将 parser 和 product RAG 组合起来，并为每次执行
创建独立的 run 目录：

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag/moi-prototypes/local-matrixflow-pipeline
python3 pipeline.py \
  --input /absolute/path/document.pdf \
  --config ../local-matrixflow-rag/config.local.json \
  --parser-pipeline precision \
  --env-file ../../.env \
  --question "这个文档说明了什么？" \
  --run runs/e2e
```

批量问题使用 `--dataset FILE.jsonl`。`--force` 只在确认要重建向量表时使用；
正常恢复或重新查询不要随意带 `--force`。

## 测试和验收

```bash
cd local-matrixflow-parser
go test ./...
go vet ./...

cd ../local-bge-m3-embedding
PYTHONPATH=. python3 -m unittest discover -s tests -v

cd ../local-matrixflow-pipeline
python3 -m unittest discover -s . -p 'test_*.py' -v
```

没有模型权重时，BGE-M3 的单元测试仍可使用 fake model 运行；需要真实模型、
MinerU、TaaS 或 MatrixOne 的检查必须单独标记为外部依赖测试。

## 结果解释和安全边界

- Parser miss、candidate miss、ranking miss、generation failure 要在 artifact 中
  分开记录，不能统称为“检索失败”。
- Page/Layout trace 不存在时报告 `N/A`，不能由 Markdown 文本反推官方布局指标。
- 可选的 controlled generation 只使用检索到的 product chunks，不等价于 Explore
  A2A Agent、浏览器渲染或完整 Web 应用。
- 所有 run 留在 `runs/` 下；不要把 API key、模型私有响应或大体量原始 payload
  复制到 README 或 Git。
