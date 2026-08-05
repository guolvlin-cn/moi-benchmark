# 04 replay、鲁棒性与性能

- [ ] **DP-401** 依赖：A-316 及对应 Native ledger（pilot=M-125，formal=M-132）；Retrieved-context replay 使用已完成 Native run 的真实 context 与统一 generator/prompt/context budget。DoD：formal replay 不得早于 M-132，仅诊断上游，不进入整机榜。
- [ ] **DP-402** 依赖：D-205（Stage1）或 D-229/S-517（formal）；定义无平台维度的 shared replay。DoD：Stage1 只启用 Gold Context 40；formal Gold Context 由 DP-448 跑 1,800 units；No-context/Noise 仅在 DP-409 预注册独立分母后启用。Native 对 shared Gold 只报 descriptive reference delta；同 envelope 才报 retrieved-context-to-gold-context gap。
- [ ] **DP-403** 依赖：D-204；公共 benchmark 分层报告。DoD：blogs 仅工程假设/指标灵感，RAGPerf 仅性能结构参考。
- [ ] **DP-404** 依赖：S-519；性能仅在质量/功能 gate 后运行。DoD：固定硬件、配额、规模、预热、时长、并发、读写 mix、失败/censoring/autoscaling 规则。
- [ ] **DP-405** 依赖：DP-404；质量榜、性能榜分离并交付原始 latency/throughput/error。DoD：不得以性能补偿质量。

Gate G5：性能环境与预算可复现；任一未满足则只交质量结果。

## Replay 归因合同

- **DP-406** 依赖 A-302；captured-context replay。产物：每平台 context artifact；DoD：context 原文、截断、排序和 hash 可核验。
- **DP-407** 依赖 DP-406；统一 generator envelope。产物：model/prompt/context-budget manifest；DoD：除 context 外参数相同，才可比较 replay gap。
- **DP-408** 依赖 DP-407；gap report。DoD：Native→shared Gold 只作 descriptive reference delta；只有 retrieved-context replay→Gold-context replay 在同一 model/prompt/format/truncation/token budget 下才允许解释为上游 context gap。
- **DP-409** 依赖 D-205（Stage1）或 D-229/S-517（formal）；No-context/Noise preregistration。产物：condition registry 与 shared ledger；DoD：无 platform_id；No-context=`Q_nc×R_nc`，Noise=`Q_noise×C_noise×R_noise`，Q/C/R、扰动生成与 seed 全部先冻结。

## 公共研究诊断

| ID | 条件 | 交付 | 禁止 |
|---|---|---|---|
| DP-410 | EnterpriseRAG flattened JSON | retrieval/QA 方法摘要 | PDF parser 结论 |
| DP-411 | FAB Gold Context/reader | reader/oracle 诊断 | native 榜，除非 corpus+code+license gate |
| DP-412 | MIRAGE Base/Oracle/Mixed | 条件化结果 | Hard Negative/Contradictory 伪装正式 |
| DP-413 | RAGPerf | workload/perf 结构 | 质量排名证据 |
| DP-414 | blogs×4 | 工程假设登记 | 排名、因果或泛化宣称 |

## Performance manifest 与阶梯

性能环境必填：`hardware,quota,dataset_id,corpus_hash,dataset_size,warmup,duration,concurrency,read_write_mix,timeout,censoring,autoscaling,build/query_separation,seed`。

- **DP-415** 依赖 S-519；建库阶梯：50/200 docs 必测；1,000 docs 只在 D-243 通过时启用，记录 ingest/index/build time 与 corpus hash。
- **DP-416** 依赖 DP-415；查询阶梯：低/中/高并发，固定 question mix、payload size、context budget。
- **DP-417** 依赖 DP-416；warm-up/duration/endurance。DoD：预热不计稳态，运行时长、失败、censoring 规则预注册。
- **DP-418** 依赖 DP-417；autoscaling。DoD：扩缩容事件、配额耗尽与重试单列，不将 censoring 删除。
- **DP-419** 依赖 DP-418；独立性能报告。DoD：P50/P95 latency、throughput、error、cost proxy 与质量榜分离。

性能停止触发：质量/功能 gate 未通过、硬件漂移、quota 改变、autoscaling 规则未锁定；此时只交质量与诊断结果。

性能 manifest 另含 `deployment_topology,replicas,pods,resource_limits,orchestrator,network_rtt,network_topology,storage,vector_db,cache_policy_warm_cold`；固定 workload 与质量抽检，失败/censoring 保持在分母。

## Replay/研究任务清单

- [ ] **DP-420** Owner Diagnostic；依赖 A-316、A-330 及对应 Native run（formal=M-132）；产物 context capture QA；DoD 只使用已经产生的真实 context，原文/顺序/截断/token/hash 一致；估时 6h+。
- [ ] **DP-421** Owner Diagnostic；依赖 DP-420；产物 generator manifest；DoD model/prompt/temperature/context budget 固定；估时 4h。
- [ ] **DP-422** Owner Diagnostic；依赖 DP-421；产物 replay runs；DoD `600×N_trace×R_replay`，默认建议 R=3 且必须在 G2 冻结，失败留分母；估时按 N_trace/R。
- [ ] **DP-423** Owner Judge；依赖 DP-422、DP-448；产物 replay scorecard；DoD descriptive Native delta 与可归因 retrieved-context-to-gold-context gap 分列；估时 8h+。
- [ ] **DP-424** Owner Research；依赖 D-206；产物 EnterpriseRAG memo；DoD JSON retrieval/QA 边界明确；估时 6h。
- [ ] **DP-425** Owner Research；依赖 D-207；产物 FAB memo；DoD Gold Context/reader 仅限当前条件；估时 6h。
- [ ] **DP-426** Owner Research；依赖 D-208；产物 MIRAGE memo；DoD Base/Oracle/Mixed 正式，扩展标签化；估时 6h。
- [ ] **DP-427** Owner Research；依赖 D-209；产物 RAGPerf note；DoD 只引用性能结构；估时 3h。
- [ ] **DP-428** Owner Research；依赖 D-210；产物 blog assumptions；DoD 每条假设有可证伪后续；估时 3h。
- [ ] **DP-429** Owner Research；依赖 D-211；产物 layered report；DoD parser/retrieval/reader 分目录；估时 8h。

## Performance 任务清单

- [ ] **DP-430** Owner Perf；依赖 S-519；产物 hardware manifest；DoD CPU/GPU/RAM/storage/network 与版本 hash；估时 4h。
- [ ] **DP-431** Owner Perf；依赖 DP-430；产物 quota manifest；DoD vendor quota、rate limit、预算冻结；估时 2h。
- [ ] **DP-432** Owner Perf；依赖 DP-431；产物 corpus ladder；DoD 50/200 docs 使用质量 corpus；1,000 docs 仅在 D-243 通过时使用同一 200+800 manifest，并分别记录 hash；估时 8h+。
- [ ] **DP-433** Owner Perf；依赖 DP-432；产物 query ladder；DoD 低/中/高并发与 read/write mix；估时 8h。
- [ ] **DP-434** Owner Perf；依赖 DP-433；产物 endurance log；DoD warmup、steady-state、duration、censoring；估时 12h。
- [ ] **DP-435** Owner Perf；依赖 DP-434；产物 autoscaling log；DoD 扩缩容、queue、quota failure 单列；估时 6h。
- [ ] **DP-436** Owner Judge；依赖 DP-435；产物 performance report；DoD latency/throughput/error 与质量榜分离；估时 8h。

## Replay 安全边界

- [ ] **DP-437** context 只来自目标平台真实输出，禁止以 Gold 代替平台 context。
- [ ] **DP-438** 统一 generator 的 prompt/context budget 固定并 hash 化。
- [ ] **DP-439** oracle/no-context/noise 不携带 platform_id，避免伪造平台重复。
- [ ] **DP-440** 只有同 envelope 才报告 gap 的可归因解释，否则写 descriptive only。
- [ ] **DP-441** replay 失败与 native 失败分别留分母，不互相替换。

## 性能报告审计

- [ ] **DP-442** warm-up 与 steady-state 分段，warm-up 不计入稳态 P50/P95。
- [ ] **DP-443** timeout、quota、censoring、autoscaling event 单独统计。
- [ ] **DP-444** workload 的 docs、questions、read/write mix、并发固定且可重放。
- [ ] **DP-445** 性能报告不引用质量分数做综合排名。
- [ ] **DP-446** 每个 steady-state workload 前后运行同一冻结质量 probe；质量漂移、cache policy 或 deployment topology 变化时停止该性能批次并保留 censoring。
- [ ] **DP-447** 1,000-doc 档未通过 D-243 时必须标 `NOT_RUN/PERF_CORPUS_UNAVAILABLE`，不得复制或无许可扩充 200-doc 质量 corpus。
- [ ] **DP-448** Owner Diagnostic；依赖 DP-421、D-229、S-517；产物 formal shared Gold Context ledger；DoD `600×3=1,800`、无 `platform_id`，使用与 retrieved-context replay 完全相同的 model/prompt/format/truncation/token budget；估时按 1,800 requests。
