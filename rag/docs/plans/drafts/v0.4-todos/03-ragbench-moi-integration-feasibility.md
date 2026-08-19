# RAGBench → MOI 接入链路可行性结论

> 日期：2026-07-30  
> 状态：`DIAGNOSTIC_ONLY / PARTIAL`  
> 关系：本文件是 [`../v0.4.md`](../v0.4.md) 的接入预研补充，不修改 v0.4 的 corpus、Gold、分母、指标或结论合同。

## 1. 执行结论

本次验证围绕以下链路展开：

```text
RAGBench Parquet
  → 可上传 PDF corpus
  → MOI 文件处理
  → MOI retrieval / Native Explore
  → 重新判分
```

当前结论是：**本地数据准备和诊断判分链路已验证；真实 MOI 端到端链路尚未完成，因此只能判为 `PARTIAL`，不能视为 MOI benchmark 已跑通。**

分段状态如下：

| 链路 | 当前状态 | 结论 |
|---|---|---|
| RAGBench Parquet → PDF | `VERIFIED_OFFLINE` | 已验证 |
| PDF → MOI Atomic Processing | `BLOCKED_AUTH` | 服务入口可达，但缺少有效 MOI 凭据，未上传 |
| Processing → BYOA retrieval dataset | `BLOCKED_PUBLIC_CONTRACT` | 公开契约没有给出 `file_id` 到 retrieval `dataset_id` 的确定映射 |
| MOI retrieval | `BLOCKED_AUTH_DATASET_ID` | 缺少 API key 和人工核对后的 dataset ID |
| PDF extraction → retrieval → score | `VERIFIED_ORACLE_MOCK` | 已验证诊断流程，不是 MOI 产品结果 |
| Native Explore answer/citation | `MANUAL_ONLY / UNCONFIRMED_API` | 尚未确认稳定的公开生成接口，需走 Native UI 并回填结果 |

因此，v0.4 的 D1-02 / G0 仍不能标记为通过。当前最多只能证明 benchmark 侧的输入准备、证据 lineage、状态记录和重新判分方案可工作，不能证明 MOI 的解析、嵌入、召回、回答或引用能力。

## 2. 已完成的本地原型

原型位于：

[`../../../prototypes/throwaway-ragbench-moi/`](../../../prototypes/throwaway-ragbench-moi/)

它被刻意隔离为 throwaway prototype，没有接入 v0.4 的正式 scored corpus、Gold 或运行分母。

本次离线 smoke 使用 RAGBench TechQA 的第一条有效样本：

- `question_id`：`techqa_DEV_Q243`
- RAGBench rows：1
- 生成 PDF：5
- 未复核 evidence candidates：3
- PDF 重新提取后的诊断命中：3/3
- 判分状态：`DIAGNOSTIC_ONLY`
- 后端标识：`oracle_mock`

原型产物包括：

| 产物 | 位置或说明 |
|---|---|
| 操作说明 | `rag/prototypes/throwaway-ragbench-moi/README.md` |
| 状态机 CLI | `rag/prototypes/throwaway-ragbench-moi/ragbench_moi.py` |
| PDF corpus | `runs/offline-smoke/output/pdf/`，由运行时生成且被 gitignore |
| corpus manifest | 输入 Parquet hash、生成器 hash、文档 hash、PDF 校验结果 |
| questions | 单条问题及本地文档别名 |
| Gold candidates | RAGBench evidence candidates，状态固定为 `UNREVIEWED_CANDIDATES` |
| retrieval result | 明确标记 `oracle_mock` 或 `moi_retrieval` |
| score | evidence substring recall，未复核时固定为 `DIAGNOSTIC_ONLY` |
| manual Explore template | 用于粘贴 Native UI response 和 citations |
| feasibility result | 每个链路环节的 verified / blocked 状态 |

## 3. 已验证内容

### 3.1 Parquet → PDF 可重复

原型会：

1. 从指定 Parquet 读取 `question`、`documents` 和 evidence keys；
2. 只把 `documents` 写入 PDF；
3. 不把 RAGBench `response`、`adherence_score` 或其他产品输出写入 corpus；
4. 使用原始文档文本 SHA-256 生成稳定的本地 `doc_id`；
5. 记录输入 Parquet SHA-256 和生成器源码 SHA-256；
6. 用 pypdf 重新打开所有 PDF；
7. 对每个实际绘制的非空正文 segment 做逐段精确比对；
8. 另行记录空行数、分页重排和 whitespace-insensitive 内容 hash。

最后一次 smoke 中 5/5 PDF 均通过：

- 可重新打开；
- 正文可提取；
- rendered segment list 完全一致；
- rendered / extracted segment hash 一致；
- normalized source / extracted hash 一致。

这些 PDF 是从 RAGBench 文本字段生成的**合成测试载体**，不是原论文或原数据源的 PDF 复原件，不保留原始版面、页码、表格结构、图片或 bbox。

### 3.2 离线检索与判分不再绕过 PDF

离线 oracle 不直接把 Gold evidence 塞入 retrieval result。它先用 pypdf 从生成后的 PDF 中重新提取正文，再执行确定性的 evidence substring search，命中后才形成 retrieval chunks。

这验证了以下 benchmark 侧路径：

```text
Parquet documents
  → PDF rendering
  → PDF text extraction
  → deterministic retrieval
  → evidence recall
```

3/3 命中只说明这条工程路径没有丢失本样本的关键 evidence，不说明 MOI retrieval recall 为 1.0，也不能作为产品质量分数。

### 3.3 MOI API adapter 的安全边界

原型实现了以下公开接口形状：

- `POST /v1/genai/pipeline`
  - multipart `files`
  - JSON `payload`
  - `ParseNode → ChunkNode → EmbedNode`
- `GET /v1/genai/jobs/{job_id}`
  - 记录 `job_status`
  - 保存脱敏的 `file_id / file_name / file_status / error_message`
- `GET /byoa/api/v1/datasets`
  - 匿名时只做 transport reachability；
  - 已鉴权时可列出脱敏的 dataset `id / name`。
- `POST /byoa/api/v1/retrieval`
  - 显式传入一个或多个 `dataset_id`；
  - 只在操作者明确提供时传 `document_id`；
  - 本地 SHA 别名绝不冒充 MOI document ID。

所有携带 key 的请求均要求：

- 凭据只从环境变量读取；
- URL 必须使用 HTTPS；
- URL 不得带 userinfo；
- `--expected-host` 必须与 `MOI_API_URL` hostname 完全一致；
- 禁止自动跟随 redirect；
- 上传还必须显式提供 `--confirm-upload` 和 `--acknowledge-license-review`。

本次环境没有 `MOI_API_KEY`。匿名探针到达了 MOI 入口，但服务端以缺少 token 拒绝；上传命令在发起外部写入前被 `BLOCKED_AUTH` 阻断。**本次没有向 MOI 发送 TechQA PDF。**

## 4. 尚未验证内容

以下内容不能从离线 smoke 推断：

1. MOI 是否能成功解析这 5 个 PDF；
2. ParseNode、ChunkNode 和 EmbedNode 在目标租户中的真实配置与输出；
3. 处理完成的 `file_id` 如何确定地映射为 retrieval API 所需的 `dataset_id`；
4. MOI 对该问题的真实 chunks、rank、score 和 latency；
5. Native Explore 的最终答案、引用、引用可解析性和 claim-level 支持；
6. PDF 页面重新排版后，MOI citation locator 如何与 benchmark Gold 对齐；
7. MOI 对长文档、表格、视觉内容、OCR 和跨文档问题的表现；
8. 重复运行稳定性、错误恢复和操作成本；
9. 任何 v0.4 Pilot-TDAS、citation 或 reliability 指标。

特别需要注意：

- Atomic Processing API 返回 `job_id`，poll 返回 `file_id`；
- DeerFlow/BYOA retrieval 使用 `dataset_ids` 和可选 `document_ids`；
- 当前公开材料没有给出可由 benchmark 自动依赖的 `file_id → dataset_id` 映射；
- 不得猜测 ID，也不得把文件名 hash 当成平台 ID；
- Native Explore answer/citation 仍应优先通过产品 Native UI 验证。

这一缺口是当前自动化全链路的主要 contract blocker。

## 5. 数据与发布边界

TechQA 在本原型中固定标记为：

```text
license_status = UNREVIEWED_THIRD_PARTY
redistribution_allowed = UNKNOWN
```

因此当前允许的用途仅应是：

- 本地内部工程可行性验证；
- 不对外分发的临时 PDF；
- 不包含在公开 release artifact 中的运行结果。

在完成独立权利审查前，不应：

- 将生成 PDF 上传到外部 SaaS 或第三方租户；
- 将 PDF、文档全文或可逆的大段文本提交到公开仓库；
- 将它们作为公司的公开 benchmark corpus 发布；
- 仅依据 RAGBench wrapper license 推断底层 TechQA 内容可商用或可再分发。

如果 v0.4 需要立即完成 Native proof，应优先使用一份**虚构或公司私有、明确允许外发**的 PDF，而不是先上传 TechQA 衍生文档。

## 6. 对 v0.4 的影响

### 6.1 不改变 v0.4 正式合同

本次原型不能替代 v0.4 已冻结的以下要求：

- 6 PDFs = 4 approved existing + 2 fresh fictional/private；
- 6 Smoke/dev；
- 20 sealed scored questions；
- 2 initial repeats；
- 固定 Gold evidence、claim rubric 和 citation contract；
- 40 initial attempts 的主分母。

RAGBench 衍生 PDF 目前不应自动进入 v0.4 的 6-file corpus，除非同时满足：

1. 内容权利已完成审查；
2. egress 已获批准；
3. synthetic layout 风险已记录；
4. Gold page/span locator 已按新 PDF 重新建立；
5. dev/scored family split 与 freeze 规则均满足。

### 6.2 当前 Gate 判断

| v0.4 Gate | 当前判断 | 原因 |
|---|---|---|
| G0 Identity/Safety/Scope | `[!] BLOCKED` | 无有效 MOI key；无 authenticated Native proof；TechQA egress 未批准 |
| G1 Native Journey/Smoke | `[ ] NOT STARTED` | 未完成真实 upload→ready→query→artifact proof |
| G2 Dataset/Rubric Freeze | `[-] OUT OF SCOPE` | 本原型只有未复核 evidence candidates |
| G3 Scored Run | `[-] OUT OF SCOPE` | 没有 MOI initial attempts |
| G4 Score/Audit/Report | `[-] OUT OF SCOPE` | 只有 oracle diagnostic score |

如果现在停止，本次结论只能写：

```text
DIAGNOSTIC_ONLY:
benchmark-side Parquet→PDF→extract→score path verified;
MOI Native journey remains blocked by auth, rights, and ID-contract gaps.
```

## 7. 解锁真实 MOI 验证的最短路径

### Step 1：先用安全 PDF 做 Native proof

- 选择 1 份虚构或私有且允许外发的 PDF；
- 记录 source、sha256、bytes、pages、egress、license；
- 不先使用 TechQA；
- 在新的 scratch dataset / workspace 中执行。

### Step 2：确认身份和目标

在本地环境设置：

```bash
export MOI_API_URL=https://approved-moi-host.example
export MOI_API_KEY='YOUR_LOCAL_SECRET'
```

要求：

- key 不写入 shell history、Markdown、日志或命令参数；
- 明确 tenant、workspace、dataset 和数据保留策略；
- `--expected-host` 与批准的 hostname 完全一致。

### Step 3：完成真实 processing proof

执行：

1. authenticated dataset probe；
2. gated upload；
3. poll 直到 `completed / failed`；
4. 保存 job ID、file ID、时间戳、状态和脱敏响应；
5. 核对 UI 中是否出现对应处理后文件。

通过条件：

- 上传文件 hash 与 manifest 一致；
- job terminal；
- 每个文件有明确状态；
- 处理后文件在 Native UI 可识别；
- 失败也必须作为有效 blocker evidence 保留。

### Step 4：人工确认 ID 映射

- 使用 authenticated dataset list 和 Native UI 对照文件名、workspace 和时间；
- 人工确认 retrieval `dataset_id`；
- 如有重复名称或多候选，停止，不猜测；
- 将确认过程写入 decision log；
- 在官方或平台团队确认前，不把 `file_id` 直接当作 `dataset_id`。

### Step 5：完成真实 retrieval 和 Native Explore proof

对同一问题分别执行：

1. retrieval API，保存 chunks、rank、latency 和资源 IDs；
2. Native Explore UI，保存最终 response、citations、截图或可回放 artifact；
3. 将 response/citations 回填 `manual_explore_run.jsonl`；
4. 只使用人工复核并冻结后的 Gold 重新判分；
5. 将 backend 标记为 `moi_retrieval` 或 `moi_native_explore`，不得沿用 `oracle_mock`。

### Step 6：再决定是否自动化

只有在以下条件同时满足后，才值得把 prototype 升级为 v0.4 helper：

- authenticated upload/poll 已稳定；
- `file_id → dataset_id` 映射得到官方确认或可重复验证；
- Native answer/citation capture 契约稳定；
- 权利、egress 和 retention 审批完成；
- 失败状态、retry 和 artifact lineage 可保存；
- 不需要改变 v0.4 Gold、分母和冻结规则。

否则继续走 Native UI + 最小人工 ledger，比建立一个会错误映射 ID 的自动 harness 更可靠。

## 8. 建议的下一步决策

优先级建议如下：

| 优先级 | 行动 | 预期结果 |
|---:|---|---|
| P0 | 获取批准的 MOI tenant/API key，并确认 retention/egress | 解锁 G0 身份与安全检查 |
| P0 | 用 1 份 fictional/private PDF 完成 Native upload→ready→query→artifact | 获得真实 Native proof |
| P0 | 向 MOI 平台方确认 `file_id / dataset_id / document_id` 契约 | 决定自动化是否可靠 |
| P1 | 建立 1 题人工 Gold，完成 retrieval + Explore 双路径回放 | 验证重新判分与 citation capture |
| P1 | 再扩展到 v0.4 的 6 Smoke | 判断能否进入 G1 |
| P2 | 完成 TechQA/其他公开数据集的逐源权利审查 | 决定是否允许内部上传或后续发布 |
| P2 | 映射稳定后把 prototype 收敛为最小 helper | 减少手工操作，不扩大 v0.4 scope |

## 9. 决策摘要

1. **本地链路可行**：RAGBench Parquet 可以转换为可提取、可校验的 PDF，并支持从 PDF 正文重新检索和判分。
2. **MOI 真实链路未跑通**：没有凭据、没有确认 dataset ID、没有 Native answer/citation artifact。
3. **3/3 不是 MOI 分数**：它只属于 `oracle_mock / DIAGNOSTIC_ONLY`。
4. **自动化的关键 blocker 不是 PDF，而是平台 ID 契约和 Native answer capture。**
5. **TechQA 不能默认外发或发布**：必须先完成底层内容的权利审查。
6. **v0.4 继续以 Native UI 和 approved corpus 为准**：本原型只作为 D1-02 的接入预研和 blocker evidence。

## 10. 参考

- [MOI 原子能力 API](https://docs.matrixorigin.cn/zh/m1intelligence/MatrixOne-Intelligence/workflow%20api/automic_api/)
- [MOI × DeerFlow RAG 集成说明](https://docs.matrixorigin.cn/zh/m1intelligence/MatrixOne-Intelligence/develop/deerflow/)
- [DeerFlow MOI provider source](https://github.com/bytedance/deer-flow/blob/main-1.x/src/rag/moi.py)
- [`v0.4.md`](../v0.4.md)
- [`01-five-day-execution-plan.md`](01-five-day-execution-plan.md)
- [`02-acceptance-and-result-template.md`](02-acceptance-and-result-template.md)
- [`RAGBench → MOI prototype`](../../../prototypes/throwaway-ragbench-moi/)
