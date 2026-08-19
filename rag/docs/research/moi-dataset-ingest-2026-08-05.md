# EnterpriseRAG-Bench / FAB-Bench：MOI 本地流程接入记录

日期：2026-08-05

本记录对应 `tools/prepare_moi_ragbench.py` 以及本地
`local-matrixflow-parser` / `local-matrixflow-rag` 的实际运行结果。

## 入口与边界

- 文本适配：将 EnterpriseRAG-Bench Parquet 行和 FAB-Bench 公开
  `gold_context_sources` 证据片段包装为 Markdown，并保留原始 `doc_id`。
- 解析：MatrixFlow Parse V3 Native，`route=moi:parse/v3/native`，
  `backend=native-text`。
- 检索：解析后的标准 `documents.jsonl` 进入 MatrixFlow
  `SplitDocumentsLength`、`MultiLevelIndex`、embedding 和本地 MatrixOne
  `SearchRAGChunks`。
- 这不是线上 `standard_rag` V2 的黑盒运行；所有产物均记录
  `web_equivalent=false`。
- Enterprise 完整 Parquet 有 511,962 行；本地全量适配的是 500 道公开题目
  关联的 722 个文档，而不是把 1.4GB Parquet 无限制地灌入本地数据库。
- FAB 公开仓库没有完整 source corpus；本地只导入 200 道题的 127 个公开证据
  文档，不能标记为完整 FAB corpus ingestion。

## 完成情况

| 数据集 | 解析输入 | parser documents | 本地 RAG smoke | 备注 |
|---|---:|---:|---:|---|
| EnterpriseRAG-Bench representative | 32 files | 1,225 | 32/32 成功 | deterministic hash embedding，诊断用途 |
| EnterpriseRAG-Bench full question-linked slice | 722 files | 23,464 | 未完成 | 33,290 个条目完成 embedding 准备，但 MatrixOne 表写入/提交前任务因内存压力中止 |
| FAB-Bench public evidence | 127 files | 936 | 200/200 成功 | 仅公开 Gold Context，非完整 corpus |

随后生成了扩展版完整公开包：

- `datasets/downloads/prepared/fab-bench-complete-20260805/`
- 200 QA、342 evidence、127 doc_id 全覆盖。
- 45 个公开可核验原始 PDF，82 个 source 仍为 `evidence_only`。
- 45 个原始 PDF 中 42 个通过本地 PDFium Native，输出 929 个 image blocks/PNG assets；3 个扫描 PDF 触发像素上限，待 MinerU retry。
- 当前 summary 状态为 `public-complete-evidence-only`，`source_complete=false`；不能将官方未发布的 220+ 源语料标为完整 source corpus。

已将两套完整解析结果另外导出为仓库约定的 `moi-ready-v1` 边界：

- `outputs/parsed-documents/moi-ready-v1/datasets/enterpriserag-bench/`：722 个源文件、23,464 个标准块。
- `outputs/parsed-documents/moi-ready-v1/datasets/fab-bench/`：127 个源文件、936 个标准块。

两个目录均包含 `moi-documents.jsonl`、`manifest.jsonl`、题目/金标准 JSONL、
`summary.json` 和 README；summary 中 `status=ready`、`failed_documents=0`，
并明确记录 `route=moi:parse/v3/native` 与 `web_equivalent=false`。

已完成的本地 RAG 结果（Hash embedding，仅做流程 smoke）：

- Enterprise 32 题：mean source recall `0.7188`，P95 retrieval `81.96 ms`。
- FAB 200 题：mean source recall `0.7750`，mean evidence recall `0.2071`，P95 retrieval `176.00 ms`。

这些数值不能作为最终模型质量结论；正式 v1.0 运行应替换为冻结的线上 embedding/model，并按数据集 gold 语义重新校准 evidence/answer 指标。

## 产物

原始适配/解析产物位于被 Git 忽略的 `datasets/downloads/` 下；稳定的
MOI-ready 导出位于被 Git 忽略的 `outputs/parsed-documents/` 下：

- 代表性双数据集准备、解析和 RAG 结果：
  `datasets/downloads/prepared/moi-ragbench-20260805/`
- Enterprise 全量 question-linked 解析结果（RAG 检索中止但解析产物完整）：
  `datasets/downloads/prepared/moi-ragbench-20260805-full-enterprise/`
- 可复现适配器：`tools/prepare_moi_ragbench.py`

可再次运行的核心命令（需已下载数据和已构建 parser binary）：

```sh
python3 tools/prepare_moi_ragbench.py \
  --enterprise-parquet datasets/downloads/public/enterpriserag-bench/data/huggingface/documents-test.parquet \
  --enterprise-questions datasets/downloads/public/enterpriserag-bench/data/questions.jsonl \
  --fab-root datasets/downloads/public/fab-bench/code \
  --out datasets/downloads/prepared/moi-ragbench-20260805 \
  --enterprise-question-limit 32 \
  --parser-bin /tmp/local-matrixflow-parser \
  --moi-ready-root outputs/parsed-documents/moi-ready-v1/datasets
```

之后把任一数据集的 `parsed-documents.jsonl` 传给
`prototypes/local-matrixflow-rag` 的 `pipeline --documents` 即可复现本地
分块、索引、embedding 和检索。
