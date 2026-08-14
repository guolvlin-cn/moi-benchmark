# 文档信息提取 Benchmark Track

状态：已完成 MOI 与 LandingAI 在 SROIE、VRDU Registration、Kleister-NDA
三个公开数据集上的正式对比评测。每个数据集冻结 100 个 case，共完成 6 组产品运行；
VRDU 中 3 个由 MOI 所配置模型供应商内容安全审查拦截的 case 从双方评分集合共同排除，
最终每个产品按 297 份文档计分。

本 Track 评估的是：**给定一套预定义业务 Schema，从文档中提取指定字段**。
它与 [文档解析 Track](../document-parsing/README.md) 分开：文档解析关注全文、版面、
表格和阅读顺序，本 Track 关注字段值是否正确、是否漏提或误提，以及输出是否符合 Schema。

正式结果请从 [多维评测报告](evaluation/latest/report.md) 开始阅读。报告包含实验配置、
总体与数据集级指标、字段级 F1、空值处理、正面对比、错误类型、耗时与成本、产品建议和
评测局限。评测方案的设计背景见 [v0.1 方案](plans/drafts/v0.1.md)。

## 当前正式结果

主指标是三个数据集各自标准化字段级 Micro F1 的等权平均：

| 产品 | 三数据集平均 F1 | 平均文档全对率 | 评分完成数 |
|---|---:|---:|---:|
| MOI | 64.57% | 20.81% | 297/297 |
| LandingAI | 69.77% | 27.10% | 297/297 |

总体分只用于快速定位结果，不能替代数据集和字段级分析：LandingAI 在 SROIE 收据上优势
明显；VRDU 的整体差距较小，MOI 的 Precision、空字段判断和文档全对率更好；Kleister-NDA
对双方都较难。具体选择建议和公平性边界见正式报告。

## 目录结构

```text
document-extracting/
├── README.md          # 本 Track 的入口和资产导航
├── plans/             # 评测方案与设计决策
├── datasets/          # 冻结的测试集、Golden 和选择清单
├── scripts/           # 数据准备、产品批跑、统一评分和报告生成脚本
├── runs/              # MOI/LandingAI 六组原始运行结果
└── evaluation/        # 从冻结数据与 runs 计算出的统一评测结果
```

### `plans/`：评测方案

- [`drafts/v0.1.md`](plans/drafts/v0.1.md)：MOI 与 LandingAI 的对比目标、公平性原则、
  数据集选择、指标体系、运行流程、预算、风险和完成标准。
- 该文件保留实验设计过程；实际运行配置和最终口径以
  [`evaluation/latest/report.md`](evaluation/latest/report.md) 及各 run 的 `config.json`
  为准。

### `datasets/`：测试数据与 Golden

三个数据集均已冻结为 100 个 case。各目录的 `selection_manifest.json` 记录选择规则、
case 列表和源文件 SHA-256，是确认测试集合与输入完整性的依据。

| 目录 | 文档类型与主要特征 | 预定义字段 | 主要内容 |
|---|---|---|---|
| `SROIE2019/` | 单页扫描收据；测试 OCR 噪声、商户与多行地址、日期和金额 | `company`、`date`、`address`、`total` | `train/img/` 原始 JPG，`train/pdf/` 为 MOI 生成的等尺寸单页 PDF，`train/entities/` 为 Golden |
| `VRDU/` | 多模板 Registration 表单；测试版式变化、字段缺失和相似字段定位 | `file_date`、`foreign_principle_name`、`registrant_name`、`registration_num`、`signer_name`、`signer_title` | `registration-form/main/pdfs/` 为 PDF，`dataset.jsonl` 为 OCR 与标注，`meta.json` 定义字段类型匹配规则，`few_shot-splits/` 保存官方划分 |
| `Kleister-NDA/` | 多页 NDA 合同；测试长文档、日期/期限归一化和重复主体数组 | `effective_date`、`jurisdiction`、`party`、`term` | `documents/` 为 PDF，`dev-0/` 与 `train/` 的 TSV 保存输入和 Golden；100 份由 83 个 dev-0 与 17 个 train case 组成 |

数据本体来自公开数据集，但本仓库中的冻结子集是本次实验的事实输入。重新下载数据后，
应先对照 manifest 校验 case 列表和 SHA-256，不能只按目录中文件数判断是否一致。

### `scripts/`：数据准备、运行与评分

数据准备：

- [`select_cases.py`](scripts/select_cases.py)：按固定规则将三个数据集筛选为 100 个 case，
  并写出 `selection_manifest.json`。该脚本会删除未选中的数据，具有破坏性；正式子集已经冻结，
  日常复现评分不需要再次执行。
- [`convert_sroie_images_to_pdf.py`](scripts/convert_sroie_images_to_pdf.py)：把 SROIE JPG
  转成 MOI 可接收的单页 PDF，不改变 LandingAI 使用的原始 JPG。

LandingAI 批跑：

- [`run_landingai_sroie_batch.py`](scripts/run_landingai_sroie_batch.py)
- [`run_landingai_vrdu_batch.py`](scripts/run_landingai_vrdu_batch.py)
- [`run_landingai_kleister_batch.py`](scripts/run_landingai_kleister_batch.py)

三个脚本执行 LandingAI ADE 的 Parse → Extract 异步任务，保存配置、Schema、逐 case
状态和原始响应。通过环境变量 `LANDINGAI_API_KEY` 认证；支持 `--dry-run`、
`--case-limit` 和 `--run-dir` 断点续跑。正式运行会消耗 LandingAI credits。

MOI 批跑：

- [`run_matrixflow_sroie_extraction.py`](scripts/run_matrixflow_sroie_extraction.py)：通用
  Matrixflow/MOI runner，也是另外两个数据集 runner 的底层实现。
- [`run_matrixflow_vrdu_extraction.py`](scripts/run_matrixflow_vrdu_extraction.py)
- [`run_matrixflow_kleister_nda_extraction.py`](scripts/run_matrixflow_kleister_nda_extraction.py)

MOI runner 负责上传文档、触发指定 Workflow、轮询结果并下载产物；支持 token/API key
环境变量、`--dry-run`、`--limit`、`--force` 和失败后继续。Workspace、Workflow、模型及
端口均可能随部署变化，复跑前应以目标环境和正式报告中的证据边界重新确认，不能直接把
脚本默认值视为当前生产配置。

统一评分与报告：

- [`evaluate_extraction_benchmark.py`](scripts/evaluate_extraction_benchmark.py)：读取三个
  Golden 和六个 run，执行评分器 v1.3，生成基础指标和逐字段明细。
- [`generate_extraction_report.py`](scripts/generate_extraction_report.py)：基于基础评分产物
  生成空字段、正面对比、错误类型等派生表和 Markdown 报告。

### `runs/`：产品原始运行结果

`runs/` 保存每次产品调用的原始证据，不是评分结果目录。正式评分默认读取以下六组：

| 产品 | SROIE | VRDU | Kleister-NDA |
|---|---|---|---|
| MOI | `matrixflow-sroie2019-workflow-2b084712/` | `matrixflow-vrdu-registration-schema-fixed/` | `matrixflow-kleister-nda-schema-fixed/` |
| LandingAI | `landingai-sroie-batch-20260724T063234Z/` | `landingai-vrdu-batch-20260724T055842Z/` | `landingai-kleister-batch-20260724T072322Z/` |

每个 run 顶层通常包含：

- `config.json`：输入目录、模型/API、并发、超时、Workflow 或 Schema 等运行配置；
- `summary.json`：整批完成、失败、credits 等摘要；
- `events.jsonl`：提交、轮询、重试和完成事件；
- `schema.json`：LandingAI 使用的完整 Schema；MOI 的显式 Schema 记录在对应 config 中；
- `cases/`：逐 case 状态、原始响应和下载产物，是评分脚本实际读取的结果来源。

这些目录应视为不可变实验记录。重跑时应创建新的 run 目录；不要直接修改正式 run 中的
case 结果，也不要用当前服务状态反推历史运行配置。

### `evaluation/`：统一评分结果

[`evaluation/latest/`](evaluation/latest/) 是当前正式评分输出：

| 文件 | 内容 |
|---|---|
| `report.md` | 面向阅读的完整多维报告，也是本 Track 的主要结果入口 |
| `summary.json` | 评分器版本、排除项、各数据集/产品指标和总体指标 |
| `comparison.csv` | 每个数据集 × 产品一行的核心指标 |
| `field_metrics.csv` | 每个字段的 Precision、Recall、F1 等明细 |
| `details.jsonl` | 每个 case × 字段的 Golden、预测值、归一化结果和错误分类 |
| `empty_value_metrics.csv` | 空字段正确、误提以及非空字段漏提/错值统计 |
| `head_to_head.csv` | 文档级双方全对、仅一方全对和双方均未全对统计 |
| `error_summary.csv` | 错值、漏字段、空字段误提、数组错误和系统失败汇总 |

`latest/` 是派生结果，可由冻结数据、正式 runs 和评分脚本重建；需要审计单个指标时，优先
沿 `report.md → summary/comparison → details.jsonl → runs/cases` 追溯，而不是只看总分。

## 评测口径摘要

- 主指标：三个数据集各自标准化字段级 Micro F1 的等权平均，不按 case 数或字段数混合加权。
- 空值兼容：JSON `null`、空字符串和纯空白字符串统一视为缺失值。
- 数据集归一化：SROIE 对日期和金额做类型归一；VRDU 使用字段类型匹配；Kleister
  使用大写归一的 MultiLabel-F1。
- 数组兼容：Kleister `party` 的字符串数组与单键 `[{"value": "..."}]` 对象数组
  视为等价表示，Schema 合规统计也不因此判错。
- 失败处理：通常把系统失败作为缺失预测计入分母；本次 VRDU 的 3 个供应商内容安全拦截
  属于评测范围外因素，因此从双方评分集合共同排除。
- 未知字段不会替代或修复目标字段；评分不会通过猜测字段映射来提高产品分数。

详细规则、实验配置和结果解释以 [正式报告](evaluation/latest/report.md) 为准。

## 最小复现链路

只复算评分时，不需要重新调用 MOI 或 LandingAI：

```text
datasets 中冻结的 Golden + runs 中六组正式结果
  -> evaluate_extraction_benchmark.py
  -> evaluation/latest/{summary.json, comparison.csv, field_metrics.csv, details.jsonl}
  -> generate_extraction_report.py
  -> evaluation/latest/{派生 CSV, report.md}
```

按照本项目约定，Python 命令使用统一虚拟环境：

```bash
source /Users/wangyaqi/Documents/cursor_project/.venv/bin/activate
python document-extracting/scripts/evaluate_extraction_benchmark.py
python document-extracting/scripts/generate_extraction_report.py
```

如果只想核验现有结论，建议先备份或指定新的 `--output-dir`，避免覆盖
`evaluation/latest/` 中已归档的正式产物。重新调用产品前，先使用 runner 的
`--dry-run` 或小规模 `--case-limit`/`--limit` 做 Smoke，并单独创建新的 run 目录。

## 当前结论边界

本次是双方产品原生链路在三个公开英文数据集上的一次运行对比，不是同模型、同提示词、
同硬件实验。它没有覆盖中文私有文档、重复运行稳定性、私有部署、工作流编排、模型替换、
权限治理或完整 TCO，因此不能把这些未测试能力写成已验证优势。产品选择和数据集级结论请
直接引用正式报告，并同时保留其中的实验配置和局限说明。
