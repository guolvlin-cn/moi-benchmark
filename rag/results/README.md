# MOI RAG Benchmark 结果归档

`results/` 是可发布、可审计的结果层。它记录已经从本地运行产物中筛选、合并和汇总后的 canonical 结果，不是临时日志目录，也不是重新发起模型调用的运行目录。

当前归档包来自 `runs/final-results/moi/20260817-final/` 的整理结果；原始 `runs/` 和 `outputs/` 保持原位置，并继续作为本地运行留痕。

## 当前目录结构

```text
results/
├── README.md
├── metrics/
│   ├── README.md
│   ├── README-canonical.md
│   ├── canonical-manifest.json
│   ├── final-score-summary.json
│   └── <dataset>/
│       ├── README.md
│       ├── results.jsonl
│       ├── judge-input.jsonl
│       ├── judgements.jsonl
│       ├── judge-attempts.jsonl
│       ├── metrics.json
│       └── sources.json
└── reports/
    ├── MOI_rag_benchmark_v1.0.md
    ├── MOI_rag_reproduction_guide.md
    └── MOI RAG 0807.md
```

## `metrics/` 记录什么

`metrics/` 是逐题结果和可复算汇总的 canonical 归档。当前按数据集各保留一个目录，避免断点恢复或重跑后出现多个互相竞争的 `results` 文件：

| 数据集目录 | 当前记录 | 解释边界 |
|---|---|---|
| [`wikieval/`](metrics/wikieval/) | 50 道通用 RAG 题 | 已完成的 MOI run 与 RAGAS 诊断结果 |
| [`mmdocir/`](metrics/mmdocir/) | 1,658 道长文档多模态 QA 题 | page/layout 检索与 adapted QA；不是官方 MMDocIR QA leaderboard |
| [`docbench/`](metrics/docbench/) | 1,102 道 PDF QA 题 | current-corpus adapted recovery audit；失败题仍保留在全量分母 |
| [`enterpriserag-bench/`](metrics/enterpriserag-bench/) | 500 道企业知识题 | 当前 722 文档 slice，不代表官方完整语料 |
| [`lenovo-bench/`](metrics/lenovo-bench/) | 60 道统一 contract 题 | 以 formal FastGPT contract 为选定结果，项目自评口径另行保留 |

每个数据集目录的 README 说明具体 protocol、重试选择、有效分母、失败和不可比项；解释单个数字时应连同它一起阅读。

### 数据集目录内的文件

| 文件 | 含义 |
|---|---|
| `results.jsonl` | 每个 query 一条的最终 canonical 记录，保存选定答案/上下文、状态、attempt provenance 和必要的逐题字段；失败题不从分母中静默删除。 |
| `judge-input.jsonl` | 统一的 Judge 输入合同，通常包含 query、reference、answer 和 retrieved context；可直接交给 Judge。 |
| `judgements.jsonl` | 被选定并冻结的逐题判分结果；如果存在重复或错误调用，不用它们覆盖 canonical 判分。 |
| `judge-attempts.jsonl` | 所有 Judge 尝试，包括重试、重复、错误和失败，供审计和解释为什么选择某一结果。 |
| `metrics.json` | 数据集级汇总指标、有效/失败分母、协议、重算/沿用说明和结果状态；核对报告数值时优先以它为机器可读来源。 |
| `sources.json` | 该数据集结果所引用的运行文件、来源文件和 provenance 信息，帮助追溯结果从哪里整理而来。 |
| `README.md` | 该数据集的专属口径、canonical 选择规则、限制和不可比项。 |

### `metrics/` 根目录文件

- `canonical-manifest.json`：所有数据集及其归档文件的整体清单和 manifest 信息。
- `final-score-summary.json`：最终汇总与分母检查结果；它是对已有逐题结果和 Judge 产物的确定性再聚合，不代表新增 provider 调用。
- [`README.md`](metrics/README.md)：中文归档说明；[`README-canonical.md`](metrics/README-canonical.md)：canonical 结果包的补充说明。

## `reports/` 记录什么

`reports/` 是面向人阅读的叙述性报告：记录实验背景、配置、指标解释、结果表、比较边界、限制和后续计划。它们用于汇报和复现实验流程，不替代逐题 JSONL 或 `metrics.json`。

- [`MOI_rag_benchmark_v1.0.md`](reports/MOI_rag_benchmark_v1.0.md)：v1.0 汇报主文档。
- [`MOI_rag_reproduction_guide.md`](reports/MOI_rag_reproduction_guide.md)：复现所需的数据、服务、命令和验收说明。
- [`MOI RAG 0807.md`](reports/MOI%20RAG%200807.md)：较早的 0807 结果报告，用于历史对照，不应覆盖当前 canonical 数值。

报告中的数值核对顺序是：逐题 `results.jsonl`/`judgements.jsonl` → 数据集 `metrics.json` → `final-score-summary.json` → 报告表格。报告若使用 adapted、carry-forward 或不同分母，必须以数据集 README 的说明为准。

## 统一解释规则

- 同一数据集只认一个 canonical `results.jsonl`；断点恢复、重跑和 Judge 重试作为 `attempts` 或 `judge-attempts.jsonl` 保留，不覆盖审计轨迹。
- `N/A` 表示该协议下没有可用或可比较的测量，不等于 0，也不应在汇总时当作成功。
- 确定性检索/词法指标、LLM Judge 指标、历史 carry-forward 指标和 adapted protocol 指标必须分开解释，不能直接混成一个总分。
- `metrics/` 负责机器可读的事实，`reports/` 负责背景和结论，`docs/` 负责设计依据；三者职责不同。
- 重新聚合不会自动补齐缺失的 Judge 或 provider 调用；没有逐题证据的指标必须在数据集 README 中标明来源和限制。

## Git 与上传边界

物理文件仍保留在本地，原始运行产物继续放在被忽略的 `runs/`、`outputs/`。当前 `.gitignore` 对 `results/metrics/*/judge-input.jsonl` 和 `results/metrics/*/results.jsonl` 使用按文件名的规则，因此这两类文件在五个数据集目录中都会被 Git 忽略；`metrics.json`、`sources.json`、`judgements.jsonl`、`judge-attempts.jsonl`、manifest、README 和报告不匹配这两条规则，可正常上传。

如果目标是“只忽略超过 10 MB 的 JSON/JSONL，小文件仍上传”，需要把 `.gitignore` 改为当前六个大文件的显式路径；Git ignore 本身不会按文件大小判断。本文档按当前工作树的实际规则记录，不把物理存在误写成已纳入 Git。
