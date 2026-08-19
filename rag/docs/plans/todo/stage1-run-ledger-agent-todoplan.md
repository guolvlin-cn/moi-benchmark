# Stage 1 Run Ledger 串行执行 TODO Plan（Agent 版）

> 目标：严格按 `MOI-RAG-实验记录表.xlsx` 的 `Run Ledger` 中 Stage 1 顺序执行 14 个计划实验；每完成一个实验，立即把运行元数据和逐指标结果回填到同一工作簿，并同步到同目录的 `MOI-RAG-实验记录表.md`。出现任何 API 相关错误时，立刻停机，不重试、不启动下一项，保留现场、同步停机记录并等待人工处理。

## 0. 唯一事实来源与工作边界

- 仓库根目录：`/Users/muuushroom/gitrepos/moi-benchmark/rag`
- 实验工作簿：`/Users/muuushroom/gitrepos/moi-benchmark/rag/outputs/experiment-record-20260804/MOI-RAG-实验记录表.xlsx`
- Markdown 实验记录：`/Users/muuushroom/gitrepos/moi-benchmark/rag/outputs/experiment-record-20260804/MOI-RAG-实验记录表.md`
- 计划范围：只执行 `Run Ledger!A5:Z18` 的 14 个 Stage 1 实验。不得自行加入只在其他计划文档中出现、但不在该范围内的实验。
- 结果回填：当前工作簿中的 Stage 1 区域为 `实验矩阵!R5:V83`，以 `实验ID + 指标` 为唯一定位键；不得按当前可见行号盲写。若工作簿后来插行，以键定位为准，不沿用旧行号。
- 运行元数据回填：`Run Ledger!I5:Z18`，以 `计划实验ID` 为唯一定位键。
- 论文基线只用于参照，绝不能复制到“实验结果”。
- Excel 是结构化结果的唯一事实来源；同目录 Markdown 是其可读镜像。每次结果、运行状态或 API 停机信息写入 Excel 后，必须在同一落表事务中同步 Markdown。两者未同步完成时，实验不算 `DONE`。
- 所有实验必须串行。前一项未完成并成功落表，不得启动下一项。
- 一个真实 run 使用一个不可变 `run_id`；不得覆盖不同内容的既有 run 目录。
- 每个涉及文档解析的实验，在发送任何解析 API 请求前必须先执行“本地解析结果复用 Gate”。如果本地已有该数据、该 parser/engine、该 pipeline 的完整解析文档，说明此前已经解析完成：禁止重复解析，直接复用本地结果进入转换、检索、评分和落表步骤。

### 本地解析结果复用 Gate（强制先于 API）

按以下顺序检查：

1. 在 `outputs/parsed-documents/<dataset>/<engine>/<pipeline>/<source_run_id>/`、当前计划输出目录及既有 run artifacts 中查找解析结果。MinerU、MOI 和其他 parser 只能在各自 engine/pipeline 目录内匹配，严禁跨 pipeline 复用或改名冒充。
2. “解析完成”必须同时满足：目标样本清单中的每个文档都有非空解析产物；manifest/status 标记完成；文档 ID 与输入一一对应；输入文件 SHA-256、dataset revision、parser/engine、pipeline 一致；文件可读且通过最低 schema/格式校验。只有零散 Markdown、缺 manifest、样本数量不足或 hash 不一致时，不能声称已完成。
3. 满足时：不运行 parse/upload-to-parser，也不发送任何解析 API 请求；在新 run 的 `system_manifest.json` 和 `control/status.json` 中记录：

   ```json
   {
     "parse_status": "REUSED_LOCAL_COMPLETE",
     "reused_from_run_id": "<source_run_id>",
     "reused_from_path": "<absolute_path>",
     "reused_manifest_sha256": "<sha256>",
     "new_parse_attempts": 0
   }
   ```

4. 复用只跳过“解析”步骤，不自动跳过 scorer、指标计算、结果校验和 Excel/Markdown 双写。后续阶段仍必须使用本次冻结配置运行。
5. 本轮 Run Ledger 的 `Actual attempts` 只记录本轮真实新请求数；解析复用时解析新请求为 0。既有历史费用不得重复记入本轮 Cost；只有确认本轮没有产生该阶段费用时才可记 0，否则留空并附来源说明。
6. 如果找到的是完整的同一实验 run，且其 scores 和记录也已验证完整，则整个实验可进入 `REUSED_VERIFIED → WRITTEN_BACK → DONE`，无需重复解析或评分；仍须从原始 artifacts 重新核验并同步 Excel/Markdown，禁止直接抄旧表中的数字。
7. 如果本地结果只覆盖部分计划样本，默认 `BLOCKED_PARTIAL_PARSE_CACHE` 并报告缺失清单，不得自动补发 API 请求；只有用户明确允许补齐后，才对缺失文档发请求，已完成文档继续复用。

## 1. 强制停机规则：任何 API 错误第一次出现即停止

以下任一情况都属于 `API_ERROR`：HTTP 非 2xx、鉴权/权限错误、额度或限流、超时、连接重置、DNS/TLS/网络错误、服务不可用、模型/接口不存在、远端 job 失败、响应体为空或无法按协议解析、SDK 抛出的远端调用异常。

一旦发生：

1. 终止当前 worker/队列，禁止再发送新的 API 请求；不得自动 retry。若上游脚本内置 retry，正式运行前必须把 `max_attempts` 冻结为 1 或用 fail-fast adapter 包裹；做不到就不能开跑。
2. 不启动下一个实验，也不把该实验标记为完成。
3. 保留已生成的输入、响应、stderr/stdout、request/job ID 和时间戳；日志中不得写入 API key、token 或完整密钥。
4. 写入 `<current_run_dir>/control/API_ERROR_STOP.json`：

   ```json
   {
     "status": "STOPPED_API_ERROR",
     "experiment_id": "<实验ID>",
     "run_id": "<run_id>",
     "failed_step": "<步骤>",
     "occurred_at": "<ISO-8601>",
     "error_class": "<分类>",
     "http_status": "<可空>",
     "provider_request_id": "<可空>",
     "sanitized_message": "<脱敏信息>",
     "resume_from": "<实验ID/步骤>"
   }
   ```

5. 在 `Run Ledger` 对应行仅回填已经客观确定的元数据（例如 Run ID、开始/结束时间、Actual attempts）；不要填写 Cost 估算值。
6. 在 `实验矩阵` 对应实验的所有行中：结果、分子、分母继续留空；`Run ID` 可填本次 run；`N/A原因` 填 `STOPPED_API_ERROR:<error_class>`。这不是指标结果。
7. 保存工作簿并做公式错误检查后，将同一停机状态同步到 `MOI-RAG-实验记录表.md` 的 Stage 1 同步区；本地写文件不属于继续 API 实验，可以完成。
8. 向用户报告停止位置。只有收到明确的“恢复/重跑”指令才能继续。

API 错误之外：缺数据、缺 adapter、许可未批准、配置未冻结时也不得跳过并继续；分别以 `BLOCKED_DATA`、`BLOCKED_ADAPTER`、`BLOCKED_GOVERNANCE`、`BLOCKED_CONFIG` 停在当前实验并报告，但不要伪造 N/A 指标。

## 2. 一次性预检（S1-00）

- [ ] `cd /Users/muuushroom/gitrepos/moi-benchmark/rag`。
- [ ] 确认工作簿存在且可读；复制一个只读备份到 `outputs/experiment-record-20260804/backups/<timestamp>-before-stage1.xlsx`。
- [ ] 确认同目录 `MOI-RAG-实验记录表.md` 存在且可读；同时备份为 `outputs/experiment-record-20260804/backups/<timestamp>-before-stage1.md`。
- [ ] 用 `@oai/artifact-tool` 导入工作簿，读取并校验 `Run Ledger!A4:Z18`、`实验矩阵!A4:W83`；禁止使用 `openpyxl`。当前第 84 行已进入 Stage 2，Stage 1 agent 不得修改。
- [ ] 验证 `Run Ledger` 正好有下述 14 个 Stage 1 ID，顺序完全一致；不一致则 `BLOCKED_CONFIG`。
- [ ] 记录当前 git commit、dirty-worktree 摘要、数据集 revision/hash、产品版本、region/tenant、parser、chunker、embedding、retriever/top-K、reranker、generator、prompt/judge version。未知字段不得猜测。
- [ ] 从 `.env` 或安全密钥存储只检查“变量是否存在”，不得打印值。
- [ ] 在任何 API 连通性测试或解析请求前，先执行本地解析结果复用 Gate，并生成 `runs/stage1/_control/parsed-cache-inventory.json`，记录发现的 engine、pipeline、source run、样本数、manifest hash 和完整性结论。不得为了“测试接口”重复解析一个已完成文档。
- [ ] 对每个会发 API 请求的 runner 做静态检查，确认首个 API 错误会非零退出且 attempts=1；尤其不要直接使用 DocBench 上游 `tenacity stop_after_attempt(6)`。
- [ ] 检查各数据集和字段级许可/远端处理许可。MultiHop-RAG MOI 与 RAGBench 未获批准时必须在到达对应任务时停机。
- [ ] 为本轮创建 `runs/stage1/_control/stage1-sequence.json`，初始 `next_experiment_id=S1-ODB-PREC-SMOKE`；每次成功落表后再原子更新。
- [ ] 检查或首次建立 Markdown 的 `## 10. Stage 1 执行同步记录（Agent 自动维护）`，使用下述固定 marker；不得整文件覆盖人工说明内容。

  ```markdown
  <!-- STAGE1_SYNC_START -->
  <!-- 该区间由 Stage 1 agent 从 Excel 和 run artifacts 机械生成，请勿手工修改。 -->
  <!-- STAGE1_SYNC_END -->
  ```

### 每个实验共用的执行状态机

新运行：`PENDING → CACHE_CHECKED → PREFLIGHT_OK → RUNNING → SCORING → VALIDATED → WRITTEN_BACK → DONE`

本地完整复用：`PENDING → CACHE_CHECKED → REUSED_LOCAL_COMPLETE → SCORING → VALIDATED → WRITTEN_BACK → DONE`

完整历史 run 复用：`PENDING → CACHE_CHECKED → REUSED_VERIFIED → WRITTEN_BACK → DONE`

只有 `DONE` 才能进入下一实验。任何 `API_ERROR` 进入 `STOPPED_API_ERROR`；本地确定性错误停留在当前实验，修复并重新验证后才能继续。

每个 run 至少保存：

```text
<run_dir>/
  config/frozen-config.json
  artifacts/input-manifest.jsonl
  raw/
  predictions/
  scores/metrics.json
  logs/run.log
  control/status.json
  system_manifest.json
```

解析完成的文档必须另存到 `outputs/parsed-documents/<dataset>/<engine>/<pipeline>/<run_id>/`；MinerU、MOI 和其他 parser 必须使用不同的 `engine` 目录，严禁改名冒充。

## 3. 串行实验清单

### S1-01 — `S1-ODB-PREC-SMOKE`（Run Ledger 第 5 行）

- [ ] 配置：OmniDocBench；MinerU Official；`S1-ODB-PRECISION`；`ADAPTED_PROTOCOL`；20-page smoke；seed=`20260803`。
- [ ] 先检查 `outputs/parsed-documents/omnidocbench/mineru/precision/` 和既有 `runs/stage1/omnidocbench/`。若同一 20 页 manifest 已完整解析，跳过下面的 parse 命令，复用预测进入 official scorer。
- [ ] 新建 `runs/stage1/omnidocbench/<run_id>/`，其中 `run_id` 建议为 `YYYYMMDD-HHMMSS-s1-odb-prec-smoke`。
- [ ] 执行：

  ```bash
  python3 benchmarks/omnidocbench/run_stage1.py prepare \
    --ground-truth datasets/downloads/document-rag/omnidocbench/data/OmniDocBench.json \
    --images datasets/downloads/document-rag/omnidocbench/data/images \
    --run-dir runs/stage1/omnidocbench/<run_id> \
    --sample-size 20 --seed 20260803

  python3 benchmarks/omnidocbench/run_stage1.py parse \
    --run-dir runs/stage1/omnidocbench/<run_id> \
    --parser-bin <absolute-local-matrixflow-parser> \
    --pipeline precision \
    --env-file /Users/muuushroom/gitrepos/moi-benchmark/rag/.env \
    --workers 4

  benchmarks/omnidocbench/score_official.sh \
    runs/stage1/omnidocbench/<run_id> \
    runs/stage1/omnidocbench/<run_id>/official/scorer-output

  python3 benchmarks/omnidocbench/export_parsed_documents.py \
    --run-dir runs/stage1/omnidocbench/<run_id> \
    --output-root outputs/parsed-documents/omnidocbench \
    --engine mineru --pipeline precision
  ```

- [ ] 验证 20/20 页面均有 prediction、attempt、latency 和 scorer 输出；失败样本不得从分母删除。
- [ ] 回填：Normalized Edit Distance、CDM、TEDS、Accepted-page rate、P50/P95 latency。

### S1-02 — `S1-ODB-AGENT-SMOKE`（第 6 行）

- [ ] 与 S1-01 使用同一 20 页抽样规则，pipeline 改为 `agent`，输出目录和 run_id 独立。
- [ ] 先检查 `outputs/parsed-documents/omnidocbench/mineru/agent/`；只有 agent pipeline 的完整结果可以复用，precision 结果不能代替 agent。
- [ ] 依次运行 prepare、parse、official score、export；export 使用 `--engine mineru --pipeline agent`。
- [ ] 回填：Normalized Edit Distance、CDM、TEDS、Accepted-page rate、P50/P95 latency。

### S1-03 — `S1-ODB-PREC-200`（第 7 行）

- [ ] 配置：MinerU Official；precision；200-page stratified；seed=`20260803`。
- [ ] 先检查 MinerU/precision 的既有 200 页 manifest；完整命中时跳过 parse，只运行尚未完成的 scorer/指标和双写步骤。
- [ ] 复用 S1-01 命令模板，把 `--sample-size` 改为 `200`，使用新 run_id。
- [ ] 完成 official score 和 MinerU/precision 隔离导出。
- [ ] 回填：Normalized Edit Distance、CDM、TEDS、Accepted-page rate、Gold Evidence Preservation、P50/P95 latency。

### S1-04 — `S1-ODB-FULL`（第 8 行）

- [ ] 配置：OmniDocBench 1,651-page local snapshot；系统必须是 `MOI / frozen main parser`；pipeline=`MOI-QS-NATIVE`；条件=`Native + official scorer adapter`。
- [ ] 先确认所调用的是“真实 MOI Native parser”，并将 exact product/parser version 写入 `system_manifest.json`。若实际仍是 MinerU 服务，`BLOCKED_CONFIG`，不得以 MOI 名义运行或落表。
- [ ] 先检查 `outputs/parsed-documents/omnidocbench/moi/native/`。若存在覆盖本次 1,651 页 manifest 的完整 MOI Native 解析结果，禁止再次解析，直接适配官方 Markdown 并评分；MinerU precision/full 结果不能当作 MOI Native 缓存。
- [ ] 使用经验证的 MOI Native adapter 准备 1,651 页、解析、转换为官方 Markdown 命名并运行 `score_official.sh`。
- [ ] 解析文档导出必须使用 `--engine moi --pipeline native`。
- [ ] 回填：Normalized Edit Distance、CDM、TEDS、Accepted-page rate、Gold Evidence Preservation、Run completeness。
- [ ] 不要直接运行 `benchmarks/omnidocbench/run_full_evaluation.sh`：它还包含 Run Ledger 未列出的 agent-200/agent-full 条件，且不能替代 MOI Native 身份核验。

### S1-05 — `S1-READOC-SMOKE`（第 9 行）

- [ ] 配置：READoc；MOI；`MOI-QS-NATIVE`；arXiv 50 + GitHub 50 PDFs。
- [ ] 先检查 `outputs/parsed-documents/readoc/moi/native/`；100 个目标 PDF 均完整命中时跳过 MOI 解析，只运行 READoc 格式适配和评分。
- [ ] 先新增/冻结仓库级 adapter，将 MOI Markdown 转成 READoc 官方 scorer 输入；当前上游入口位于 `datasets/downloads/document-rag/readoc/code/READoc/`，不能把上游 baseline 脚本当作 MOI runner。
- [ ] 固定 100 个文件清单及 hash；MOI 解析结果保存到 `outputs/parsed-documents/readoc/moi/native/<run_id>/`。
- [ ] 使用 READoc 官方 scoring 实现计算并回填：EDS、TEDS、KTDS、Accepted-file rate、Gold Evidence Preservation、P50/P95 latency。

### S1-06 — `S1-MMDOCIR-PAGE`（第 10 行）

- [ ] 配置：MMDocIR Evaluation full evaluation set；MOI Native page retrieval；top-K 列表必须在 frozen config 中明确。
- [ ] 先新增/冻结 adapter：导入 corpus/page，执行 MOI page retrieval，保存每个 query 的完整 ranked list、score、latency 和 qrels 映射；上游 scorer 位于 `datasets/downloads/document-rag/mmdocir/code/MMDocIR/`。
- [ ] 回填：Recall@K、nDCG@K、Complete evidence-set recall@K、Context Precision@K、P50/P95 latency。每个 K 分项必须可从 `scores/metrics.json` 追溯，不能只写一个未注明 K 的数。

### S1-07 — `S1-MMDOCIR-LAYOUT`（第 11 行）

- [ ] 使用与 S1-06 相同的数据 revision，但 retrieval unit 改为 layout block；使用独立 run_id 和输出目录。
- [ ] 保存 block→page→document 的稳定映射和完整 ranked list。
- [ ] 回填：Recall@K、Complete evidence-set recall@K、Context Precision@K、Run completeness。

### S1-08 — `S1-VIDORE-V2`（第 12 行）

- [ ] 配置：ViDoRe V2 当前 4 个 subset；MOI Native visual page retrieval；冻结 subset 名称、revision、retriever 和 K。
- [ ] 新增/冻结 file-based MOI adapter，向 `datasets/downloads/document-rag/vidore-v2/code/vidore-benchmark/` 的官方 evaluator 提交 ranked page results；不得用上游预置 retriever 冒充 MOI。
- [ ] 分 subset 和 macro 两层保存分数；回填：nDCG@K、Recall@K、P50/P95 latency、Run completeness。

### S1-09 — `S1-DOCBENCH-SMOKE`（第 13 行）

- [ ] 配置：DocBench；20 PDFs / 50 QA；MOI Quick-start Native；样本清单固定并可复算。
- [ ] 新增/冻结 MOI upload→parse→retrieve→answer adapter；每个 QA 保存 answer、citations、retrieval trace、初次 attempt、latency。
- [ ] 官方 judge 的 prompt/model/version 必须固定。上游 `run.py` 有 6 次 API retry，禁止原样用于本实验。
- [ ] 回填：Official Correctness / Accuracy、Correctness、Reference-claim Recall、Gold-evidence Support、Citation entailment precision、TDAS、P50/P95 latency。

### S1-10 — `S1-DOCBENCH-FULL`（第 14 行）

- [ ] 仅在 S1-09 全链路通过后运行；配置为 229 PDFs / 1,102 QA，复用同一冻结 pipeline，使用新 run_id。
- [ ] 回填：Official Correctness / Accuracy、Correctness、Reference-claim Recall、Gold-evidence Support、Citation locator validity、Citation entailment precision、TDAS、Initial availability。

### S1-11 — `S1-MMDOCRAG-200`（第 15 行）

- [ ] 配置：MMDocRAG；200 stratified QA；MOI Native multimodal RAG；冻结抽样 seed、模态/问题类型分层、K 和 judge。
- [ ] 新增/冻结 MOI adapter，并使用 `datasets/downloads/document-rag/mmdocrag/code/MMDocRAG/` 的 scorer；图像证据和文本证据必须保留不同 locator 类型。
- [ ] 回填：Recall@K、Correctness、Reference-claim Recall、Gold-evidence Support、Citation entailment precision、TDAS、P50/P95 latency。

### S1-12 — `S1-MULTIHOP-OFFICIAL`（第 16 行）

- [ ] 配置：2,255 个 non-null retrieval questions；分别运行 `MH-VOYAGE-RR` 与 `MH-BGE-RR`，但保留在同一计划实验 ID 下的不同 batch/run 记录；若单行 Ledger 无法无损记录两个 run，先复制该计划行生成第二条 batch 行，不得把两条 pipeline 的分数平均。
- [ ] 论文复现配置：256-token chunks；retrieve top-20；`bge-reranker-large` rerank top-10；排除 301 个 null retrieval question，分母必须为 2,255。
- [ ] 仓库现有 `prototypes/local-matrixflow-rag/multihop_benchmark.py` 只可作为数据冻结参考，正式全量 runner/scorer 需先固化到 `benchmarks/`。
- [ ] 回填每个 pipeline 独立的 MRR@10、MAP@10、Hits@K (any-hit)、Official Correctness / Accuracy、P50/P95 latency；不得混成单值。

### S1-13 — `S1-MULTIHOP-MOI`（第 17 行）

- [ ] 首先验证字段级许可和远端处理许可；未获批即 `BLOCKED_GOVERNANCE`，不得运行。
- [ ] 配置：2,556 QA / 609 docs；MOI Quick-start Native；保留 null_query，并冻结 top-K、answer/judge 配置。
- [ ] 全量 adapter 必须输出 document/evidence ranked list、answer、citations、answerable prediction 和首次 attempt 状态。
- [ ] 回填：Recall@K、All-evidence success@K、Complete evidence-set recall@K、Correctness、Strict unanswerable success、TDAS、Initial availability。

### S1-14 — `S1-RAGBENCH-REG`（第 18 行）

- [ ] 首先取得 config approval，只允许批准的 TechQA/EManual 配置；不得自动扩大到 msmarco 或其他配置。未批准即 `BLOCKED_GOVERNANCE`。
- [ ] 将 `prototypes/throwaway-ragbench-moi/ragbench_moi.py` 中验证过的逻辑固化为正式 benchmark adapter；prototype 结果不得直接当正式结果。
- [ ] 冻结 MOI pipeline、TRACe/evaluator version、processed-context reader 和分母。
- [ ] 回填：Official Correctness / Accuracy、Correctness、Gold-evidence Support、Run completeness。

## 4. 每个实验完成后的 Excel + Markdown 双写事务

每个实验必须按以下顺序执行一次“双写事务”，成功后才能把 sequence 的 `next_experiment_id` 前移：

- [ ] 校验 `scores/metrics.json` 中的实验 ID、run_id、dataset hash、pipeline ID 与 frozen config 一致。
- [ ] 若使用本地解析结果，在 Run Ledger、Markdown Run Ledger 和 checkpoint 中同步记录 `parse_status=REUSED_LOCAL_COMPLETE`、`reused_from_run_id/path`、manifest hash 和本轮新解析 attempts=0；不得让读者误以为本轮重新调用了解析 API。
- [ ] 所有率值同时保存 `value`、`numerator`、`denominator`；percentile/距离类指标若不存在自然分子分母，则只填“实验结果”，分子/分母留空，并按指标口径处理 N/A。
- [ ] 用 `@oai/artifact-tool` 导入原工作簿；先按 `计划实验ID` 定位 Run Ledger 行，填写 I:Z 的客观字段。
- [ ] 再按 `实验ID + 指标` 定位实验矩阵行，填写：R=实验结果、S=分子、T=分母、U=N/A原因、V=Run ID。
- [ ] 多 K 或多 subset/pipeline 的结果不能塞进一个歧义单元格：在不改变原行的前提下复制对应指标行，明确在“指标”或“备注”中写 `@K`、subset、pipeline/batch；每个结果仍能唯一映射到 run_id。
- [ ] `0` 是有效结果，不能当空值；无可计算结果时使用指标规范中的 N/A code，不能填 0。
- [ ] 导出到临时 xlsx，检查 `#REF!|#DIV/0!|#VALUE!|#NAME?|#N/A`，并 inspect 本实验对应 Ledger 行和矩阵行；验证后原子替换主工作簿。
- [ ] 以刚验证通过的 Excel 和 `<run_dir>` 工件为输入，重新生成 Markdown 的 `STAGE1_SYNC_START/END` 区间。不要从终端显示文本、人工记忆或论文基线抄数。
- [ ] Markdown 同步区至少包含以下两张表：

  1. `Stage 1 Run Ledger`：计划实验 ID、状态、系统、Pipeline、样本、Run ID、Batch ID、dataset hash、code commit、product version、开始/结束时间、planned/actual attempts、cost、输出位置。
  2. `Stage 1 逐指标结果`：实验 ID、指标、实验结果、分子、分母、N/A 原因、Run ID、指标来源文件。

- [ ] Markdown 中的空值保持空白；`0` 必须显示为 `0`；包含 `|`、换行或反引号的字段按 Markdown 表格规则转义。数值精度和单位必须与 Excel 一致。
- [ ] 对本次实验做双向抽查：Markdown 的 Run ID、每个指标值、分子、分母、N/A 原因必须与 Excel 完全一致；同时确认未改动 Stage 2/3 数据和 Markdown marker 外的人工正文。
- [ ] 先分别写入临时 `.xlsx`、`.md`，两者都通过验证后再替换正式文件；写入 `outputs/experiment-record-20260804/checkpoints/<实验ID>-<run_id>-record-sync.json`，记录两个正式文件的 SHA-256、同步时间和 source `metrics.json` hash。
- [ ] 另存 `outputs/experiment-record-20260804/checkpoints/<实验ID>-<run_id>.xlsx`。
- [ ] 另存 `outputs/experiment-record-20260804/checkpoints/<实验ID>-<run_id>.md`。
- [ ] 更新 `<run_dir>/control/status.json` 为 `DONE`，再更新 `stage1-sequence.json`。

如果 Excel 更新成功但 Markdown 同步失败：将当前实验置为 `RECORD_SYNC_FAILED`，不得开始下一实验；从刚保存的 Excel 重新生成 Markdown，不得重新运行实验或重新请求 API。

### Markdown 同步内容示例

```markdown
<!-- STAGE1_SYNC_START -->
_同步时间：2026-08-04T12:00:00+08:00；Excel SHA-256：`...`_

### Stage 1 Run Ledger

| 计划实验 ID | 状态 | Pipeline | Run ID | 开始时间 | 结束时间 | Actual attempts | 输出位置 |
|---|---|---|---|---|---|---:|---|
| S1-ODB-PREC-SMOKE | DONE | S1-ODB-PRECISION | `<run_id>` | `<ISO-8601>` | `<ISO-8601>` | 20 | `runs/...` |

### Stage 1 逐指标结果

| 实验 ID | 指标 | 实验结果 | 分子 | 分母 | N/A 原因 | Run ID | 来源 |
|---|---|---:|---:|---:|---|---|---|
| S1-ODB-PREC-SMOKE | Accepted-page rate | `<value>` | `<n>` | `20` |  | `<run_id>` | `scores/metrics.json` |
<!-- STAGE1_SYNC_END -->
```

## 5. 指标计算约束

- 所有指标以工作簿 `指标口径` 和冻结的官方 scorer 为准；不得由 agent 自创简化公式。
- Recall@K=`命中的 gold evidence 数 / gold evidence 总数`；Complete evidence-set recall@K 只有 gold evidence 全部进入 top-K 才计 1；Hits@K(any-hit) 只要命中任一证据即计 1，三者不得混用。
- nDCG@K 使用冻结 relevance/qrels 和 log-discount；MRR@10 取首个相关项倒数排名；MAP@10 按官方 MultiHop-RAG 口径。
- Accuracy/Correctness 的分母保留 initial timeout/error/空响应；retry 不得改善 initial 指标。
- P50/P95 使用逐 attempt wall-clock latency 的固定聚合；不得只对成功样本计算，除非工作簿指标口径明确如此。
- Run completeness=`拥有全部必需工件且通过 schema 校验的样本数 / 计划样本数`。
- Citation、claim、evidence、TDAS 指标以 `plans/golden-and-metrics-spec-v0.4.md` 的冻结定义为准。

## 6. 完成条件

- [ ] 14 个 Stage 1 项全部处于 `DONE`，或者在首个 blocker/API error 处按协议停止；不得越过停止点。
- [ ] 每个 DONE 实验都存在不可变 run 目录、配置/版本/数据 hash、raw outputs、逐样本明细、聚合指标和 checkpoint workbook。
- [ ] 每个涉及解析的实验都有 cache-check 结论；检测到完整本地解析文档时没有重复解析请求，并能从 `reused_from` 追溯到原始解析 manifest。
- [ ] 每个 DONE 实验在同目录 Markdown 同步区中都有对应 Run Ledger 行和全部逐指标行；Markdown 与 Excel 的值、分子、分母、N/A 原因、Run ID 一致。
- [ ] 每次双写都有 `.xlsx`、`.md` checkpoint 和 `record-sync.json` 哈希清单；任一缺失都不能标记为 DONE。
- [ ] MinerU、MOI 和其他 pipeline 的解析文档已按 engine/pipeline 分目录保存。
- [ ] 工作簿中的每个已完成结果都能从 `Run ID` 追溯到 `metrics.json` 和逐样本分子/分母。
- [ ] 未完成实验的结果单元格仍为空，论文基线没有进入实验结果列。
