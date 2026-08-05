# FAB-Bench 完整语料与多模态 MOI-ready 执行计划

日期：2026-08-05

## 目标

在不伪造或越过版权/访问权限的前提下，交付一份可复现的 FAB-Bench 数据包：

1. 200 个 QA 全量保留；
2. 127 个 QA 引用的唯一 `doc_id` 全部进入 source registry；
3. 对能合法取得的原始 PDF/图片执行 MatrixFlow/MOI 解析；
4. 生成文本、视觉资产、QA、Gold Context、provenance 和 MOI-ready manifests；
5. 对未公开或无权限的原始文档逐项标记 `missing`，不能用证据片段冒充完整源文档。

## 公开性判定

官方仓库公开的是 QA、论文 PDF 和一张系统架构图；README 描述的 150+ 论文、70+ 专利、SEMI 标准和约 347M tokens 的源语料没有随仓库发布。因此“完整 FAB-Bench”分为：

- `public-complete`：官方公开的 200 QA + 342 条 Gold Context evidence + 127 个唯一 doc_id；
- `source-complete`：上述内容加 127 个原始源文档及其图片资产；只有取得全部资源并通过 license/egress 审核后才能标记。

## 执行阶段

### F0：冻结 registry 与 provenance

- 从 QA 抽取 200 个问题、342 条 evidence、127 个唯一 `doc_id`。
- 保留 `has_image`；生成 `source-registry.jsonl` 和 `evidence-registry.jsonl`。
- 每个资源记录 URL、访问日期、license/access、sha256、mime、页数、状态。

### F1：获取原始资源

- 优先使用作者提供的 corpus 或正式公开下载链接。
- 对论文、专利和标准只使用合法公开来源；不能凭 doc_id 猜测或静默替换文档。
- 下载成功进入 `assets/originals/`；无法取得进入 `missing`，附具体原因。

### F2：文档/图片解析

- 文本层 PDF：本地 `local-matrixflow-parser --profile v3-native`。
- 扫描或需要页面图像的 PDF：MinerU precision/agent 或 MatrixFlow `document_visual.parse`。
- 独立图片：VLM OCR/caption 只作为视觉增强，并记录模型、版本、请求和结果 hash。
- 统一输出 text/table/image blocks，保留 page、bbox、OCR、caption、asset id。

### F3：MOI-ready 与索引输入

- 输出 `moi-documents.jsonl`、`manifest.jsonl`、`asset-manifest.jsonl`、题目和 Gold Context。
- 文本向量和图片向量分开建表；图片向量使用 `embedding_multimodal`，不把 hash embedding 当正式结果。
- 本地 RAG 增加 text-only、OCR/caption-fused、text+image hybrid 三种条件，使用独立表和独立 run。

### F4：验收

- QA coverage：200/200；evidence coverage：342/342；source registry：127/127。
- `has_image=true` 的 4 条 evidence 必须有明确 visual asset 状态。
- 每个成功资源可由 sha256 回放；每个缺失资源有原因；禁止把 `public_evidence_only` 标成 `source-complete`。
- 输出 public-complete 与 source-complete 两个明确状态，不以缺失资源阻塞可复现的 QA/evidence baseline。

## 预期产物

```text
datasets/downloads/prepared/fab-bench-complete-20260805/
  source-registry.jsonl
  evidence-registry.jsonl
  questions.jsonl
  gold-questions.jsonl
  source-completeness.json
  assets/originals/
  assets/images/
  evidence-prepared/fab-bench/
  parsing/evidence/parsed-documents.jsonl
  parsing/original/parsed-documents.jsonl
  moi-ready/moi-documents.jsonl
  moi-ready/image-index-input.jsonl
  moi-ready/asset-manifest.jsonl
  moi-ready/manifest.jsonl
  moi-ready/summary.json
```

## 不能宣称完成的条件

- 官方/作者未提供完整源语料；
- 仅有 Gold Context 片段而没有对应原文；
- 图片只有 `[IMAGE AVAILABLE]` 标志而没有实际资产；
- license、访问权限或 sha256 无法核验。

这些情况保留数据并标记状态，不删除 QA，也不伪造图片或原始 PDF。

## 本次执行结果（2026-08-05）

- F0：200/200 QA、342/342 evidence、127/127 唯一 `doc_id` 已冻结并写入 registry。
- F1：通过公开专利库/arXiv 获取 45 个原始 PDF；82 个源仍为
  `evidence_only`。其中 `patent_11` 通过 evidence 中明确出现的
  `US20140282291A1` 反查取得；不能仅凭别名猜测其余 `patent_*`。
- F2：127 个 evidence Markdown 全部经 `moi:parse/v3/native` 解析；45 个原始 PDF 中
  42 个成功、3 个因本地 PDFium 像素上限失败。成功解析结果包含 929 个 image blocks，
  已复制为带 SHA-256 的稳定 PNG assets。
- F3：已生成 `moi-ready/moi-documents.jsonl`、source/evidence/visual/asset manifests、
  `moi-ready/image-index-input.jsonl`、questions/gold-questions 和 completeness summary。
  其中 929 条图片索引输入记录包含稳定路径、SHA-256、页码、bbox 和
  `document_visual.index.image` 路由；本地 RAG CLI 尚未将其写入图片向量表，因此不冒充
  已完成的 hybrid vector index。
- F4：QA、evidence、doc_id、块 UUID、图片文件存在性与哈希全部校验通过。

当前交付状态是 `public-complete-evidence-only`，不是 `source-complete`：官方仓库没有发布
完整 220+ 源文档，4 条 `has_image=true` evidence 中 1 个（`patent_11`）已有可回放图片，
`MRS2015` 和 `Cost_of_Silicon_Viewed_from_VLSI_Design_Perspective` 的原始图片仍缺失。
