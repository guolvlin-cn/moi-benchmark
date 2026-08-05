# 02 数据、Gold 与 source readiness

- [ ] **D-201** 依赖：M-101；登记 v0.4 不可变 corpus/question/gold 与新 freeze id 规则。DoD：缺陷只能全体重跑。
- [ ] **D-202** 依赖：D-203、D-240；建设并冻结 50 docs/250q 先行 pilot。DoD：pilot rights/egress 已通过，family 隔离，manifest 与页码/bbox/span/hash 完整；尚不声称 200/1000 已完成。
- [ ] **D-203** 依赖：D-201；在任何 Stage3 authoring 前冻结双审、adjudication 与抽验协议。DoD：目标为 gold validity≥95%、critical error=0、QWK≥0.60；实际执行由 D-213/D-214 验收，修订产生新 `gold_version`。
- [ ] **D-204** 依据规范引用 R-002/R-003/R-004；登记 EnterpriseRAG、FAB、MIRAGE、RAGPerf 及 parser/retrieval/reader 分层。DoD：EnterpriseRAG 非 PDF parser；FAB native 受 corpus+code+license gate；MIRAGE 仅 Base/Oracle/Mixed，扩展条件单列。R-* 是引用 ID，不是任务依赖。
- [ ] **D-205** 依赖：D-201；生成 Stage1 MVP shared Gold Context oracle（`20×1×2=40`），不得按平台复制。DoD：freeze hash 与 provenance 可验证；No-context/Noise 另立 denominator。

Gate G2：题目、claims/evidence、rubric、版本和 hash 全在运行前冻结。

## Source readiness 矩阵

| ID | 来源/类型 | 数据形态 | 允许条件 | 阻塞条件 | Owner |
|---|---|---|---|---|---|
| D-206 | [EnterpriseRAG](../../../refs/papers/rag-benchmarks/2605.05253v1.pdf) | flattened JSON 企业文本 | schema 可解析、任务映射 | 当作 PDF parser | Data |
| D-207 | [FAB](../../../refs/papers/rag-benchmarks/2605.26476v1.pdf) | Gold Context/reader | gold context 可重放 | native 缺 corpus/code/license | Research |
| D-208 | [MIRAGE](https://arxiv.org/html/2504.17137) | Base/Oracle/Mixed | 条件标签与 split 固定 | 扩展条件冒充正式 | Research |
| D-209 | [RAGPerf](https://github.com/platformxlab/RAGPerf) | 性能结构 | 仅 workload 参考 | 质量排名 | Perf |
| D-210 | [blogs×4 来源核验](../../research/todo-benchmark-source-review-2026-08-05.md) | 工程文章 | 假设/指标灵感 | 排名证据 | Research |
| D-211 | parser/retrieval/reader | 分层公开 benchmark | 层内单独报告 | 与整机混算 | Research |

## 数据规模与 schema

| split | docs | questions | 用途 |
|---|---:|---:|---|
| Stage3 pilot | 50 | 250 | 发现缺陷、非正式排名 |
| dev | 40 | 200 | 调参/adapter smoke，不进 formal |
| pilot | 40 | 200 | 预运行，不淘汰资格 |
| formal | 120 | 600 | 固定 gold_version、三 repeats |
| total build | 200 | 1000 | family 隔离后汇总 |
| optional performance add-on | +800 | 0 | 仅把性能 corpus 扩到 1,000 docs；不进入质量/Gold |

`50/250` 是先行版本，不是最终 `200/1000` 之外的额外计数；只有在 lineage、family 与许可合同连续时才可并入后续版本，否则作为独立 pilot 冻结。最终发布总量仍为 200 docs/1,000 questions。

manifest 必填：`dataset_id,document_id,family_id,version,path,sha256,pages,language,layout,license,egress,split,owner`。question schema 必填：`question_id,family_id,cluster_id,type,answerability,citation_required,claims,critical_claims,evidence_set_ids,allowed_docs,gold_version`。evidence 必填页码、bbox（视觉题）、span、file/evidence hash。

## 质量、泄漏与修订

- **D-212** 依赖：D-242；family/近重复扫描。产物：leakage report；DoD：dev/pilot/formal family 不交叉。
- **D-213** 依赖：D-203、D-242；双审与 adjudication。产物：review matrix；DoD：formal 全双审、critical error=0、QWK≥0.60。
- **D-214** 依赖：D-213；gold validity 抽验。产物：validity report；DoD：≥95%，缺陷分布和修复理由完整。
- **D-215** 依赖：D-214；跨版本修订。产物：`gold_version` diff；DoD：旧版本只读，formal 新 run 全部采用同一版本。
- **D-216** 依赖：D-240、D-241、D-242；final license/egress reconciliation。产物：200-doc source approval；DoD：每份文档有授权、允许计划用途、egress 与 hash 证据。

触发条件：family 泄漏、critical error、license 失效或 schema 变化时立即停止运行，创建新 freeze id；不得局部补题。

## 稳定任务清单

- [ ] **D-217** Owner Data；依赖 D-240；产物 corpus registry；DoD 每文档 family/version/license/hash；估时按每 50-doc batch 4h+。
- [ ] **D-218** Owner Data；依赖 D-217；产物 layout tags；DoD text/table/mixed/scan 覆盖；估时 3h。
- [ ] **D-219** Owner Data；依赖 D-218；产物 page map；DoD 物理页/印刷页口径固定；估时 2h。
- [ ] **D-220** Owner Data；依赖 D-219；产物 bbox normalization；DoD 单位、坐标原点、精度固定；估时 4h。
- [ ] **D-221** Owner Data；依赖 D-220；产物 span hash；DoD 规范化文本与原文均可回放；估时 3h。
- [ ] **D-222** Owner Judge；依赖 D-221；产物 question blueprint；DoD 题型配额与 answerability 合计正确；估时 6h。
- [ ] **D-223** Owner Judge；依赖 D-222；产物 claim registry；DoD 每可答题非空 claims、critical 列表一致；估时 8h。
- [ ] **D-224** Owner Data；依赖 D-223；产物 evidence sets；DoD OR/AND 逻辑和替代证据明确；估时 8h。
- [ ] **D-225** Owner Reviewer；依赖 D-224；产物 first-pass review；DoD 每题 provenance 可定位；估时 8h。
- [ ] **D-226** Owner Reviewer；依赖 D-225；产物 second-pass review；DoD 双审独立完成再 adjudicate；估时 8h。
- [ ] **D-227** Owner Judge；依赖 D-226；产物 QWK report；DoD QWK≥0.60 或记录降级；估时 3h。
- [ ] **D-228** Owner Data；依赖 D-227；产物 validity sample；DoD gold validity≥95%；估时 4h。
- [ ] **D-229** Owner Program；依赖 D-214、D-216、D-228；产物 freeze approval；DoD rights/egress、gold validity、critical error=0、hash 均签署；估时 2h。
- [ ] **D-230** Owner Data；依赖 D-229；产物 revision protocol；DoD 旧版本只读、新版全局重跑；估时 2h。
- [ ] **D-231** Owner Research；依据 R-002；产物 PDF bibliography；DoD 本地两篇 PDF 的页码/用途/限制列明；估时 2h。
- [ ] **D-232** Owner Research；依据 R-002；产物 blog register；DoD 四 blog 仅假设/灵感；估时 2h。
- [ ] **D-233** Owner Research；依据 R-003/R-004；产物 layered catalog；DoD parser/retrieval/reader 分层独立；估时 4h。

D-217–D-230 的小时数只覆盖 schema/工具/单批次操作估算，不能相加后冒充 1,000 题全量人工成本。50/250 先行版本预算 8–15 人日；扩到 200/1,000 且完成 formal 双审、adjudication 与抽验，新增预算为 30–50 人日、6–8 周。

## 各 Gate 输出

G0 输出 source approval；G1 输出 ingest/readiness probe；G2 输出 manifest/question/gold/rubric/freeze hash；G3 输出 question-to-evidence coverage；G4 输出 validity/QWK/adjudication summary。任一输出缺失时标 `[!]`，不得以“待补”进入 formal。

## 证据字段审计

- [ ] **D-234** 每份 source 有 URL/本地路径、访问日期、license、egress、用途。
- [ ] **D-235** 每个 claim 有独立 claim_id、critical 标记、至少一 evidence_set。
- [ ] **D-236** 每个 evidence 有 document_id、page、span、file_sha256；视觉题另有 bbox。
- [ ] **D-237** 每个 unanswerable 题有 negative_type 与具体 negative_reason。
- [ ] **D-238** 每个 family 有泄漏扫描结果和 reviewer 签名。
- [ ] **D-239** 每次 gold 修订有 old/new version、diff、影响 run 与批准。

## Stage3 与性能扩容 Gate

- [ ] **D-240** Owner Rights/Program；依赖 D-201；产物 50-doc pilot source approval；DoD：候选文档逐份有 license、允许用途、egress、敏感性结论和 source hash，完成后才允许 D-202 authoring；估时按审批队列。
- [ ] **D-241** Owner Rights/Program；依赖 D-202；产物 full-corpus expansion approval；DoD：新增约 150 docs 在 authoring/ingest 前逐份通过与 D-240 相同的权利合同，且不会造成 split family 泄漏；估时按审批队列。
- [ ] **D-242** Owner Data；依赖 D-203、D-241；产物 200 docs/1,000q dataset；DoD：最终 split 固定为 dev40/200、pilot40/200、formal120/600，pilot lineage 连续或明确独立，manifest/Gold schema 完整；新增预算 30–50 人日。
- [ ] **D-243** Owner Rights/Perf；依赖 D-216；产物 optional 800-doc performance add-on manifest；DoD：额外文档全部有 license/egress/hash、与 200-doc 基础 corpus 合并后恰为 1,000 docs、五系统使用同一冻结集合，且不进入质量分数；未通过时性能只跑 50/200 档。

任何字段缺失都先标 schema defect；不通过删除题目或隐藏 N/A 修复。formal run 开始后发现 defect，保留原结果并全局新 freeze 重跑。
