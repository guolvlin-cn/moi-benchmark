# `plans/TODO.md` benchmark 来源核验

日期：2026-08-05
范围：EnterpriseRAG-Bench、FAB-Bench、MIRAGE、RAGPerf，以及 TODO 引用的四篇平台博客。
证据规则：论文、官方仓库与官方数据发布为主证据；博客仅用于还原实验设置和形成待验证假设，不作为平台能力或排名的事实依据。

## 结论先行

| TODO 中的来源归因 | 忠实度 | 应如何改写/使用 |
|---|---|---|
| EnterpriseRAG-Bench 提供企业语料、十类问题、Gold Documents、Gold Answer、Atomic Facts 和评测逻辑 | **基本忠实，但适用范围需收窄** | 可作为合成企业文本的检索与 grounded QA 主基准。发布物是扁平 JSON 文本，不是原始 PDF/Office 文件，不能证明解析、OCR、表格或版面能力。评测是带版本的固定 gold set；gold correction 是后续审校/版本更新机制，不是在一次被测运行中动态改 Gold。 |
| FAB-Bench 提供 `native_rag` / `gold_context` 双模式，并可诊断 retrieval gap | **方法归因忠实，可复现性被高估** | 论文原名是 `with_kb` / `without_kb`，定义与 TODO 的两个本地别名一致；但官方仓库当前只有 200 条 QA JSON 与 gold-context 摘录，没有源 corpus、生成/评测/adapter 代码，也没有 LICENSE。现状只能直接复现 gold-context fixture，不能开箱复现完整 native-RAG 比较。 |
| MIRAGE 提供 Base、Oracle、Mixed、Hard Negative、Contradictory 五种模式 | **部分不忠实** | MIRAGE 原论文只有 Base、Oracle、Mixed 三种设置。Hard Negative 与 Contradictory 可以保留，但必须标记为本项目扩展，不可归因给 MIRAGE。 |
| RAGPerf 支持 TODO 的全部性能指标和固定压力档位 | **架构思想忠实，具体指标/档位部分过度归因** | RAGPerf 确实覆盖模块化阶段、并发读写更新、延迟/吞吐、CPU/内存/I/O、GPU、索引和 vLLM 的 TTFT/TPOT。TODO 中 p50/p95/p99、超时/错误率、token 成本、每千次成本、命名为“update-to-searchable”的指标，以及 100/1k/10k、1/5/10/20/50 等档位，应标为项目自定义。 |

建议在 TODO 的每个模式和指标旁增加 `source-native`、`adapted`、`project-extension` 三类 provenance 标签，避免把本地设计写成论文原生协议。

## 1. EnterpriseRAG-Bench 来源卡

主证据：

- 本地论文：[2605.05253v1.pdf](/Users/muuushroom/gitrepos/moi-benchmark/rag/refs/papers/rag-benchmarks/2605.05253v1.pdf)
- 官方仓库：[onyx-dot-app/EnterpriseRAG-Bench](https://github.com/onyx-dot-app/EnterpriseRAG-Bench)
- 官方数据页：[Hugging Face dataset](https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench)
- 固定发布版：[v1.0.0 release](https://github.com/onyx-dot-app/EnterpriseRAG-Bench/releases/tag/v1.0.0)

### 规模与语料形态

- 论文摘要和 §2（pp. 1–3）称约 50 万份合成企业文档、9 个来源：Slack、Gmail、Linear、Google Drive、HubSpot、Fireflies、GitHub、Jira、Confluence；官方数据页当前九个分片合计 **511,962** 条。
- 共有 **500** 个问题、10 类。论文 Table 2（p. 2）给出的数量为：Basic 175、Semantic 125、Intra-Doc 40、Project 40、Constrained 30、Conflicting 20、Completeness 20、Miscellaneous 20、High Level 10、Info Not Found 20。
- 数据生成分为 scaffolding、high-fidelity 和 high-volume 三阶段，并加入噪声；每个 QA 可带 gold answer、atomic answer facts，以及“适用时”的 gold document IDs（§4，pp. 5–7）。High Level、Info Not Found 等类型并不都天然有 gold documents，因此统一 schema 必须允许空集合。
- **不支持把它当 PDF/解析 benchmark。** 发布物是源系统记录归一化后的 JSON 文本。论文 Limitations（§7，pp. 11–12）明确指出文档被压平成 JSON，缺少嵌套结构、富文本、表格和媒体；仓库 release 也发布 JSON/ZIP 分片，而非原始 PDF、Office、图片或邮件容器。它能评测检索与回答，不能单独覆盖上传、parser、OCR、layout/table extraction。

### 运行模式与指标

- 论文没有 FAB 式双模式；其标准提交流程是对每个 `question_id` 返回 `answer` 与 `document_ids`（Appendix A，p. 14）。
- §5（pp. 8–9）定义四项核心评估：
  1. correctness：LLM judge 的二值正确性；
  2. completeness：命中的 atomic answer facts 比例；
  3. document recall：通常按 Recall@10；
  4. invalid extra documents：额外无效文档的绝对数量。
- 总分是：回答被判正确时取 completeness，否则为 0。基线实验的回答模型和评估模型均使用 GPT-5.4 Medium（§6，pp. 9–10），因此成本、模型漂移及同模型 judge 偏差需要单独记录。
- Gold Set Correction（§5，pp. 8–9）用于把多个 judge 一致确认的漏标有效文档送入人工审校，并在之后的固定数据/leaderboard 版本中修正。**它不是对某次提交边评边动态重写 gold set**；复现实验必须锁定 release/commit 和 gold 版本，不能用同次被测输出改变分母。

### 许可、可获取性与 schema 映射

- 官方仓库和 Hugging Face 数据页均声明 **MIT**；v1.0.0 提供全量包和按源切片。数据页显示约 1.41 GB，GitHub `all_documents.zip` 约 1.26 GB，完整接入前要预留下载、解压、索引和版本固定步骤。
- 问题 JSON 的原生字段为 `question_id`、`question_type`、`source_types`、`question`、`expected_doc_ids`、`gold_answer`、`answer_facts`。TODO 中 `valid_document_ids`、`contradictory_document_ids`、`answerable` 和详细 tracing/result 字段是合理的本地扩展，但不是 EnterpriseRAG-Bench 原生 schema。
- 官方评测 harness 和比较脚本可作为适配基线；接入平台时仍需固定 top-k、回答 prompt、生成模型、judge 模型与失败处理，否则跨平台比较会混入生成配置差异。

### 可迁移性与限制

可迁移价值较高：九类企业应用的统一文本记录、明确 gold IDs 与 atomic facts，适合测试权限之外的企业检索/回答主链路，也适合建立 source-wise 和 question-type-wise 诊断。

边界同样明确（§7，pp. 11–12）：语料是单一虚构科技公司 Redwood Inference 的合成数据；高容量阶段的连贯性较弱；路径/schema 会漂移；对话偏“围绕任务”；没有多模态、原生复杂格式或真正系统化的 multi-hop 压测；gold set 仍可能漏标并随版本修订。因此不要把结果外推为真实企业数据、解析质量或权限安全性的完整证明。

## 2. FAB-Bench 来源卡

主证据：

- 本地论文：[2605.26476v1.pdf](/Users/muuushroom/gitrepos/moi-benchmark/rag/refs/papers/rag-benchmarks/2605.26476v1.pdf)
- 官方仓库：[FuturefabAI/FAB-Bench](https://github.com/FuturefabAI/FAB-Bench)

### 规模与语料/问题形态

- §3.1（pp. 3–4）描述的候选知识源包括 150+ 篇 IEDM/ISSCC/VLSI 论文、70+ 项专利和 SEMI 标准，约 3.47 亿 token、188 个主题；术语表有 431 个术语、7 类。
- 论文摘要称从 **1,300+** 个生成候选中筛选 200 条，Figure 1（p. 4）写 1,500，仓库 README 又写“original 1,400 questions”。这三个版本不一致，报告中应只把 **最终公开 200 条** 视为已核验规模。
- 最终题集：ROB/needle 59、MULTI 90、GEN 51，共 200 条；论文设置为 512-token chunk、128-token overlap（§3.2，pp. 4–5）。
- 对仓库 200 个 JSON 的结构审计显示，它们包含问题、ground-truth answer 和 `gold_context_sources` 摘录，但不含可重建论文所述知识库的源文档。尤其 MULTI 90 条中，按 `doc_id` 计有 **59 条只涉及一个 distinct document**；因此发布标签可支持“多片段/多事实”诊断，但不能把全部 MULTI 题都等同为已验证的跨文档 multi-hop。

### 模式与指标

- Appendix F.3（p. 25）明确给出双模式：
  - Mode A `with_kb`：走框架原生 retrieval pipeline；
  - Mode B `without_kb`：绕过检索并注入 gold context；
  - 差值 Δ = B − A；差值大提示 retrieval bottleneck，两者都低提示 generation bottleneck。
- 因此 TODO 将它们命名为 `native_rag` 与 `gold_context`，并定义 `Retrieval Gap = GoldContext - NativeRAG`，在概念上是忠实映射；建议保留论文原名作 alias，防止来源漂移。
- §3.4（p. 7）定义六项 0–10 G-Eval 指标：Completeness、Technical Depth、Factuality、Relevance、Context Utilization、Support Quality。实验用 DeepEval 与 GPT-4.1-mini judge；该 judge 尚无完整 human-correlation 验证（Limitations，p. 15）。
- 论文比较 4 个模型、4 个框架、4K–32K context 配置；AnythingLLM 主实验固定预处理 JSON，但跨框架实验中 retrieval、模型可配置性和 source attribution 并不等价（§3.5、§4，pp. 7–13；Appendix F，p. 25）。因此论文结果适合做诊断示例，不适合作为严格受控的平台排行榜。

### 许可与实际可获取性

截至 2026-08-05，对官方 GitHub 默认分支的核验结果是：

- 仅 2 次提交；仓库主体为论文 PDF、图片、README 和 `QAs/` 下 200 个 JSON；
- **没有源 corpus**（论文、专利、SEMI standards 的可索引文件未发布）；
- **没有生成器、evaluator、DeepEval 配置或四平台 adapter/runner 代码**；
- **没有 `LICENSE` 文件，GitHub license 元数据为空**。

因此，论文“dataset released”只能稳妥解释为 200 条 QA/gold-context fixtures 已公开。没有明确许可时，不应默认这些 JSON 可重新分发；包含论文、专利和标准的源 corpus 还涉及获取权与版权边界。TODO 当前承诺“200 条全量跑 `native_rag`”并非开箱可复现：要么取得作者提供的 corpus/代码/license，要么在明确许可下另建等价语料并将结果标为复现变体。`gold_context` 模式则可以从现有摘录进行技术验证，但正式纳入发布基准前仍需完成许可审查。

### 可迁移性与限制

可迁移价值主要在双模式诊断、六维 rubric 和受控的 model-swap 设计。论文也声称 adapters 所需工作较少（§3.5，p. 7），但 Appendix F（p. 25）同时披露 MaxKB 无法通过 API 返回 source context、RAGFlow attribution 需推断、Metaso 模型不可配置；这些限制会直接影响统一 trace schema。

主要风险（Limitations，p. 15）：题量仅 200、无全面人类 judge 相关性、未做独立 retriever ablation、跨领域需要重校阈值、模型会漂移。再加上当前仓库缺 corpus/代码/license，FAB 应先作为**方法与 fixture 来源**，而不是即插即用的完整公开 benchmark。

## 3. MIRAGE 归因核验

主证据：[论文 HTML](https://arxiv.org/html/2504.17137)；[官方仓库](https://github.com/nlpai-lab/MIRAGE)（Apache-2.0）。

- 数据包含 7,560 条整理后的 QA，候选池共 37,800 个 chunk，来源为英文 Wikipedia 衍生的 PopQA、Natural Questions、TriviaQA、IfQA、DROP。
- §4 只定义三种 setting：**Base**（无 context）、**Oracle**（一个正确 chunk）、**Mixed**（5 个 chunk，其中一个 oracle 加噪声/无关 chunk）。
- 四个主指标为 Noise Vulnerability、Context Acceptability、Context Insensitivity、Context Misinterpretation；论文还报告 retrieval F1/precision/recall/NDCG 与回答 exact match。
- 论文和官方数据中没有独立的 **Hard Negative** 或 **Contradictory** track。TODO 可把“语义接近但不支持答案的困难负例”和“直接冲突证据”作为本项目稳健性扩展，但命名应为 `mirage-inspired/hard-negative`、`project/contradictory`，不能写成“复现 MIRAGE 五模式”。
- MIRAGE 自身的限制包括公共数据污染风险、核心设计仍是单 oracle 的 single-hop、来源分布不均和部分 false labels；Oracle 模式超过 90% 时也可能过易。它适合做 context sensitivity/噪声敏感性基线，不足以替代企业 multi-hop 或矛盾证据专项集。

## 4. RAGPerf 归因核验

主证据：[论文 HTML](https://arxiv.org/html/2603.10765)；[官方仓库](https://github.com/platformxlab/RAGPerf)（Apache-2.0）。

- RAGPerf 把系统拆成 embedding、indexing、retrieval、reranking、generation；可配置 Query/Insert/Update/Removal 比例、并发和 Uniform/Zipfian 访问分布，并在更新时维护动态 ground truth。
- 官方 workload 包括 Wikipedia（约 19.3 GB/6.41M）、Arxiv PDF（48 GB/30k）、GitHub code（32 GB/11M）和 People's Speech（35.5 GB/0.3M），并覆盖 LanceDB、Milvus、Qdrant、Chroma、Elasticsearch 及多类索引算法；还包含 OCR、ColPali、Whisper 等多模态路径。
- 论文明确报告/采集：端到端 latency 和 throughput，CPU/内存/I/O，NVML GPU 指标，ingestion throughput、GPU memory、index storage/memory、insertion/index/query latency，以及 **vLLM endpoint** 的 TTFT、TPOT、KV 指标；质量侧用 Ragas 计算 context recall、factual consistency 和 query accuracy。
- TODO 的模块化 profiling、混合查询/插入/更新/删除和 freshness 压测可以说“受 RAGPerf 启发”。但主证据没有把下列项目规定为其标准 protocol：固定 p50/p95/p99 清单、timeout/error rate、token cost、cost per 1,000 queries、名为 update-to-searchable delay 的指标，或 100/1k/10k 文档与 1/5/10/20/50 并发档位。它们都可以保留，但应标记为 `project-defined`。
- 官方实现依赖 Linux procfs/cgroups v2、NVML、自定义 C++20 monitor、Python 和可观测的模块化 pipeline；TTFT/TPOT 依赖 vLLM telemetry。对 AnythingLLM、RAGFlow 等黑盒 API，若拿不到内部 trace，通常只能可靠获得客户端端到端延迟、吞吐、错误率和外部资源采样，不能声称完整复现 RAGPerf 的阶段级指标。

## 5. 四篇博客的实验设置与可信边界

四篇都不能替代 primary benchmark。以下数值只是“博客声称”，未把它们当作已复现事实。

### 5.1 91AIHub：四大开源知识库平台实测

来源：[文章页](https://91aihub.com/articles/%E5%9B%9B%E5%A4%A7%E5%BC%80%E6%BA%90%E7%9F%A5%E8%AF%86%E5%BA%93%E5%B9%B3%E5%8F%B0-rag-%E5%AE%9E%E6%B5%8B-maxkb-ragflow-fastgpt-dify)

- **对象**：MaxKB、RAGFlow、FastGPT、Dify；文章仅明确 RAGFlow v0.26。称使用 TechQA 646 文档/40 问、CUAD 50/50、CMRC 211/40、DocVQA 50/50。
- **控制变量**：同一台 Xeon 72-core/62 GB/RTX 3090 24 GB 机器，同一组 corpus/questions，Ollama `qwen2.5:14b` 同时作 generator/judge，`qwen3-embedding:4b` 作 embedding。
- **未控制项**：FastGPT 用 top-1，其他平台 top-5；其余版本、chunking、parser/OCR、prompt、重复次数和索引参数没有完整披露。同模型自评也可能放大偏差。
- **可复现性**：文章没有公开脚本、平台配置快照、逐题 JSONL、日志或原始输出。其“文本 recall 80–100%”“扫描件仅 RAGFlow OCR 约 76%”等只能视为作者一次环境中的观察。
- **可信边界**：这是迁移/转载链条较长的社区二手材料，适合提取待验证假设——尤其 OCR 是潜在分化点——不能用其百分比作本项目验收阈值或排名先验。

### 5.2 PromptQuorum：AnythingLLM vs PrivateGPT vs Open WebUI

来源：[文章页](https://www.promptquorum.com/zh/power-local-llm/anythingllm-vs-privategpt-vs-openwebui-rag)

- **对象**：作者称以同一 5,047-page corpus、50 个问题/5 类问题比较 AnythingLLM、PrivateGPT、Open WebUI，并看 latency、hallucination、citation 和 hidden cost。
- **控制变量**：页面只声称 corpus 与问题相同；平台版本、LLM/embedding、硬件、chunk/top-k、judge、重复次数均未给出。
- **可复现性**：中文页面目录列出“方法”，正文却缺少相应方法内容；也没有 corpus、50 问、逐题答案、脚本或 raw results。文章声称的 6% hallucination、240/720 ms p50/p95 及 8k–12k 页退化无法独立核验。
- **可信边界**：独立媒体自测可提示应记录引用率、幻觉和规模拐点，但证据密度不足，不宜引用任何数字作基线。

### 5.3 StudioBrain：AnythingLLM RAG Benchmark

来源：[文章页](https://studiobrain.ca/docs/RAG_Benchmark)

- **对象**：AnythingLLM + OpenRouter，约 103 页 mGear 文档，公开 6 个问题；比较 20 个 model slug（含一次失败），覆盖 7B–35B、MoE 与闭源模型。
- **控制变量**：同一 workspace/index、system prompt、chat/retrieval path、问题和 rubric，仅更换生成模型。这一设计可迁移为本项目的 model-swap 回归。
- **未披露项**：AnythingLLM 版本、实际 retrieval 参数值、硬件、重复次数、judge prompt；评委是 Codex/ChatGPT 5.5，未做人类校准。
- **可复现性**：页面说保存 raw/normalized JSON，但只给建议路径和空模板，没有可下载 artifacts 或 runner。6 问样本也不足以稳定排名。
- **可信边界**：适合借鉴固定索引后换模型的实验结构；不支持外推为 AnythingLLM 平台能力结论，也不能把模型排名并入正式 benchmark。

### 5.4 Dify v3.9.5 Benchmark Report

来源：[Dify 官方报告页](https://ee.dify.ai/reports/v3.9.5/benchmark-report/)

- **对象**：Dify v3.9.5，Kubernetes 下每个 pod 1 CPU/2 GB，比较 5 种 API/worker topology；负载一类是空 `Start → End` workflow，另一类是 `Start → mocked OpenAI LLM → End` 的 SSE event 流。
- **控制变量**：版本、容器资源和 topology 有披露，因此可参考其部署扩缩容结构；但 request 数、持续时间、mock cadence、节点硬件、网络/存储与 raw samples 未公开。
- **可复现性**：页面给出 `langgenius/dify-benchmark:28e83d2d`，但该仓库/commit 当前不能从公开 GitHub 获取。页面声称空 workflow 约 40 QPS、events/s 从 81.9 增至 238.59、p50 TTFE 约 130 ms，缺少 raw artifact 无法复算。
- **可信边界**：这是厂商对自家产品的 first-party synthetic workload，不是独立 RAG benchmark；mock LLM/空流程既不测 retrieval quality，也不代表真实模型 TTFT。它只能启发 Dify 部署拓扑和 SSE instrumentation，不能与 EnterpriseRAG/FAB 的答案质量或真实端到端延迟直接比较。

## 6. 对 TODO 的落地建议

### 必须修正

1. **EnterpriseRAG 分层命名**：把它放在“归一化文本的 retrieval + grounded generation”层；PDF ingestion、OCR、table/layout parsing 继续使用单独数据集和 gold，不以 EnterpriseRAG 分数代替。
2. **固定 gold 版本**：每次运行记录 Enterprise release/commit、question file hash、评测代码/模型版本；同次 run 不允许动态接受新 `valid_document_ids`。新发现进入离线 adjudication，下一 benchmark version 才生效。
3. **FAB 可运行范围**：当前只承诺 `gold_context` 技术试跑；将 `native_rag` 标为 blocked-by-corpus/license/code。取得作者材料或重建语料后，必须把后者标作 exact reproduction 或 derived variant。
4. **MIRAGE 更名**：标准轨只保留 Base/Oracle/Mixed；Hard Negative、Contradictory 放进“project robustness extensions”。
5. **RAGPerf provenance**：把它明确支持的阶段/资源/更新负载与本项目额外的 percentile、错误率、成本、freshness SLA、规模/并发档位分开列。

### 建议保留

- EnterpriseRAG 的 500 题、question-type/source-wise 切片、gold document recall、correctness 与 atomic-fact completeness；先跑小切片做 adapter validation，再锁版本跑全量。
- FAB 的双模式思想和六维 rubric；正式比较时把 judge 模型、prompt、temperature、重试及 parse failure 一并留档，并增加少量人工复核。
- MIRAGE 的三种 canonical context settings，用于回答模型对 context/noise 的敏感性基线。
- RAGPerf 的模块化 workload vocabulary 和混合读写更新场景；黑盒平台只报告实际可观测字段，缺失阶段指标写 `unavailable`，不做推算。
- 四篇博客中的配置项清单、OCR/规模拐点/model-swap/部署拓扑等作为 hypothesis backlog；任何百分比和平台优劣都必须由本项目 raw artifacts 重跑后才能进入结论。

### 发布门槛

每一条正式结果至少应保存：benchmark/release/commit、问题和 corpus hash、平台/模型/embedding/parser 版本、完整配置、请求级输入输出与 retrieved IDs、失败/重试、计时边界、judge 输入输出、资源采样和可复算汇总。没有这些 artifacts 的博客数字只进入“待验证”，不进入 leaderboard 或验收标准。
