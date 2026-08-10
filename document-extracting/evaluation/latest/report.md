# MOI vs LandingAI 信息提取多维评测报告

本报告只使用最终有效运行结果，不比较或引用此前的错误运行。主指标为三个数据集等权的标准化字段级 Micro F1。VRDU 中3个由 MOI 所配置模型供应商内容安全审查拦截的 case 已从双方共同评分集合中排除，因此 VRDU 使用同一组97个 case；`null`、空字符串和纯空白字符串统一视为空字段。

评分范围为 SROIE 100份、VRDU 97份、Kleister-NDA 100份，每个产品共297份文档。

## 1. 实验配置与复现信息

本节区分三类证据：仓库内 run 产物直接记录的值、与 case/Schema 可对应的历史运行时证据，以及仅由部署记录旁证的值。未持久化的配置不会按当前服务状态反推。六组实验均对同一数据集使用一套固定业务 Schema，但双方的 Schema 描述并非逐字相同，因此这是产品原生配置对比，不是同提示词、同模型对照。

### 1.1 六组实验、输入与执行区间

| 数据集 | 产品 | 提交输入 | 原始数 | 评分数 | 最终结果执行区间 | 配置证据 |
|---|---|---|---|---|---|---|
| SROIE | MOI | 由 JPG 等尺寸绘制生成的单页 PDF | 100 | 100 | 2026-07-27 15:59:49–17:24:26 +08:00 | [config](../../runs/matrixflow-sroie2019-workflow-2b084712/config.json) |
| SROIE | LandingAI | 原始 JPG | 100 | 100 | 2026-07-24 06:32:34–06:46:11 UTC | [config](../../runs/landingai-sroie-batch-20260724T063234Z/config.json) |
| VRDU Registration | MOI | PDF | 100 | 97 | 2026-07-28 11:35:08–12:04:21 +08:00 | [config](../../runs/matrixflow-vrdu-registration-schema-fixed/config.json) |
| VRDU Registration | LandingAI | PDF | 100 | 97 | 2026-07-24 05:58:42–06:15:00 UTC | [config](../../runs/landingai-vrdu-batch-20260724T055842Z/config.json) |
| Kleister-NDA | MOI | PDF | 100 | 100 | 2026-07-28 11:36:54–12:21:18 +08:00 | [config](../../runs/matrixflow-kleister-nda-schema-fixed/config.json) |
| Kleister-NDA | LandingAI | PDF | 100 | 100 | 2026-07-24 07:23:22–07:44:10 UTC | [config](../../runs/landingai-kleister-batch-20260724T072322Z/config.json) |

执行区间按各 case 最终状态文件中的时间汇总，不再把 `config.created_at` 当作整批运行时间。MOI SROIE 和 VRDU 的 `events.jsonl` 还保留了此前尝试或重复审计记录；评分脚本只读取每个 case 最终状态和最终输出。VRDU 的3个内容安全失败 case 从双方共同评分集合中排除，但仍保留在原始 run 中。

### 1.2 数据集快照与预处理

| 数据集 | 固定子集 | 选择规则 | 输入完整性 |
|---|---|---|---|
| SROIE2019 | train 中100个完整 case | 对排序后的完整 ID 使用 `random.Random(20260723).sample` | [manifest](../../datasets/SROIE2019/selection_manifest.json) 保存原始 JPG SHA256 |
| VRDU Registration | 官方 valid 100 | `FARA-lv2-mixed_template-train_10-test_300-valid_100-SD_0.json` 的 valid 列表 | [manifest](../../datasets/VRDU/selection_manifest.json) 保存 PDF SHA256 |
| Kleister-NDA | 83个 dev-0 + 17个 train | train 补充部分使用 `random.Random(20260723).sample` | [manifest](../../datasets/Kleister-NDA/selection_manifest.json) 保存 PDF SHA256 |

SROIE 为兼容 MOI 输入，由 [convert_sroie_images_to_pdf.py](../../scripts/convert_sroie_images_to_pdf.py) 把每张 JPG 绘制成单页 PDF：页面宽高直接使用原图像素值作为 PDF point，图片铺满页面、不裁剪、保持宽高比并启用页面压缩；LandingAI 仍提交原始 JPG。转换工具的历史 Python/Pillow/ReportLab 版本未写入 run，因此当前复现以转换脚本和已生成 PDF 为准。三个上游数据集的下载版本或上游 Git commit 也未持久化，仓库内 manifest 与逐文件 SHA256 是本次实验的数据快照事实来源。

### 1.3 LandingAI 配置

| 配置项 | 实际值或证据边界 |
|---|---|
| 接入方式 | 直接调用 ADE REST API，未使用 LandingAI SDK |
| API Base URL | `https://api.va.landing.ai/v1/ade` |
| Parse 模型 | `dpt-2-20260410`；300/300 case 响应 metadata 一致 |
| Extract 模型 | `extract-20260314`；300/300 case 响应 metadata 一致 |
| 模型回退 | 300/300 case 的 `fallback_model_version=null` |
| 并发数 | 5 |
| 轮询间隔 | 3.0 秒 |
| 单次 HTTP 超时 | 120 秒 |
| 提交重试 | 最多5次，指数退避上限30秒并加入随机抖动；本次所有 Parse/Extract 均首次提交成功 |
| 认证 | `Authorization: Bearer <API_KEY>`；密钥不写入 run 产物 |
| 平台版本边界 | ADE 未在响应中返回独立产品 build；以 `/v1/ade`、运行日期及两个 metadata model version 复现 |

LandingAI 调用链路：

| 阶段 | 方法与 API | 主要参数/产物 |
|---|---|---|
| 提交解析 | `POST /parse/jobs` | multipart `document`；仅显式传 `model=dpt-2-20260410`，其余 Parse 选项使用服务默认值 |
| 查询解析 | `GET /parse/jobs/{job_id}` | 轮询至完成，保存 Markdown、metadata 和 credits |
| 提交提取 | `POST /extract/jobs` | multipart `markdown`；`schema`、`model=extract-20260314`、`strict=true` |
| 查询提取 | `GET /extract/jobs/{job_id}` | 轮询至完成，保存 extraction、metadata、warnings 和 credits |
| 下载异步结果 | `GET {output_url}` | 仅在完成响应通过 `output_url` 返回结果时调用 |

三个 LandingAI runner 使用相同模型和运行参数，仅输入文件类型及 Schema 不同。没有额外自由文本 prompt；字段 `description` 与 `x-alternativeNames` 构成面向产品的抽取指令。精确 Schema 分别保存在 [SROIE](../../runs/landingai-sroie-batch-20260724T063234Z/schema.json)、[VRDU](../../runs/landingai-vrdu-batch-20260724T055842Z/schema.json) 和 [Kleister-NDA](../../runs/landingai-kleister-batch-20260724T072322Z/schema.json)。

### 1.4 MOI 配置

| 配置项 | 实际值或证据边界 |
|---|---|
| 部署形态 | `LOCAL_DEPLOY_PROFILE=dev` 本地源码部署；runner 通过 Frontend/反向代理 `127.0.0.1:18000` 访问 MOI API，直连 Backend 为 `18050`，Catalog 为 `18081`，OpenXML 为 `18817`，MatrixOne 为 `16001` |
| MOI 源码版本 | 部署记录显示 `dev@cbada900e9be4f7e47c60efacb42de1e14eca785`；该 commit 未写入 run config，属于部署旁证而非 run 自证 |
| Workspace ID | `abe9f340-ab88-0d9c-5773-837e70c25c48` |
| Workflow | `解析信息提取` / `2b084712-3ed2-4034-965b-8e2657693359` |
| Workflow version | `9d756d96-5c9f-4b98-965a-66f068d9cadf`；三个 MOI run 的最终 case 产物一致 |
| 工作流节点 | 文件读取 → `moi:parse` → `moi:llm.extract.structured.advanced` → Catalog 结果保存 |
| 文档解析 | `parse_tier=standard`，`page_selector=""`（全部页面），`vlm_ocr_model=qwen3-vl-plus` |
| 结构化提取模型 | `qwen3.7-max` |
| 执行方式 | runner 逐文件串行；单个 case 失败后继续；工作流执行模式 `one_shot` |
| 轮询/请求超时 | 5秒轮询；HTTP 60秒；上传/下载300秒；单任务3600秒 |
| Schema 传递 | SROIE 使用工作流默认值；VRDU、Kleister-NDA 通过 `values.extract_schema` 显式覆盖 |
| 认证 | Backend Bearer token + `X-Workspace-ID`；Catalog `X-API-Key`；认证值不入库 |

模型与解析参数来自归档的历史 MOWL 运行对象：对象中的源文件名、Schema 和本次 case 能对应，因此强于根据当前工作流配置反推；但这些展开后的参数没有写入仓库内 `config.json`，仍应视为历史运行时证据。源码 commit 来自部署记录，证据等级更低。后续 runner 应在运行开始时把 commit、镜像 digest、workflow definition/default values 和展开后的每个 case 参数直接写入 run 目录。

### 1.5 Schema、提示词与推理参数

| 数据集 | 字段与类型 | 主要约束 |
|---|---|---|
| SROIE | `company/date/address/total: string` | MOI 默认 Schema 仅定义字段和类型；LandingAI 另有字段描述与别名 |
| VRDU | `file_date/foreign_principle_name/registrant_name/registration_num/signer_name/signer_title: string` | 保留 `foreign_principle_name` 的数据集拼写；registration number 按文本处理 |
| Kleister-NDA | `effective_date/jurisdiction/term: string`; `party: array<string>` | 日期归一到 YYYY-MM-DD；term 为 `number_unit`；party 可多值 |

MOI SROIE 的历史默认 Schema 为：

```json
{"type":"object","properties":{"company":{"type":"string"},"date":{"type":"string"},"address":{"type":"string"},"total":{"type":"string"}}}
```

MOI 的 VRDU/Kleister Schema 设置 `additionalProperties=false` 且所有字段必填，缺失标量返回空字符串、缺失 party 返回空数组；完整 Schema 位于各自 [VRDU config](../../runs/matrixflow-vrdu-registration-schema-fixed/config.json) 和 [Kleister config](../../runs/matrixflow-kleister-nda-schema-fixed/config.json)。LandingAI 使用 `strict=true`，并提供字段描述和别名。双方字段集合一致，但指令丰富度不同。

MOI 工作流没有绑定用户自定义 `instruction`，节点输入是解析文档、JSON Schema 和模型。实际 LLM 消息还包含 MOI 内置的 scalar/array/schema-grouping 模板；它们由上述 MOI commit 中的 `extract_prompt_templates.go` 和 `extract_group_extractor.go` 固定，而不是独立的实验 prompt 文件。当时结构化提取配置未被 worker YAML 覆盖，因此使用源码默认值：pipeline enabled、每批最多10个 block/12000 tokens、字段分组3–8、置信度阈值0.6、抽取并发4、thinking disabled、无显式 max tokens。`qwen3.7-max` 运行时覆盖 LLM/VL extraction model 并禁用二次 parser model；temperature、top_p 和 seed 未显式传入，使用供应商默认行为。

### 1.6 运行代码与评分配置

实验 runner、固定数据快照和首次评分结果归档于 benchmark commit `3e7ef53499897193213225719d487aa0bdcbb0ca`。历史 shell 命令没有原样持久化；复现入口为 `run_landingai_{sroie,vrdu,kleister}_batch.py`、`run_matrixflow_{sroie,vrdu,kleister}_extraction.py`，参数以各 run 的 `config.json` 和本节记录为准。所有 Python 命令使用 `/Users/wangyaqi/Documents/cursor_project/.venv`。

评分使用 [evaluate_extraction_benchmark.py](../../scripts/evaluate_extraction_benchmark.py) 的 `scoring_version=1.3`，再由本脚本生成报告。主指标为三个数据集各自 normalized Micro F1 的等权平均。评分规则包括：`null`/空字符串/纯空白统一为空；SROIE 日期和金额按类型归一；VRDU 复用字段类型匹配逻辑；Kleister 采用大写归一的 MultiLabel-F1；`party` 的字符串数组与严格单键 `[{"value": string}]` 表示等价；未知字段不替代目标字段；三个 VRDU 内容安全失败 case 从双方共同集合排除。

复现评分命令：

```bash
source /Users/wangyaqi/Documents/cursor_project/.venv/bin/activate
python document-extracting/scripts/evaluate_extraction_benchmark.py
python document-extracting/scripts/generate_extraction_report.py
```

## 2. 总体结论

| 产品 | 三数据集平均 F1 | 平均文档全对率 | 完成数 | 总体成功率 |
|---|---|---|---|---|
| MOI | 64.57% | 20.81% | 297/297 | 100.00% |
| LandingAI | 69.77% | 27.10% | 297/297 | 100.00% |

## 3. 数据集级结果

| 数据集 | 产品 | 评分数 | P | R | Micro F1 | Macro F1 | 文档全对率 | Strict F1 | 成功率 | Schema 合规 |
|---|---|---|---|---|---|---|---|---|---|---|
| sroie | moi | 100 | 80.15% | 78.75% | 79.45% | 79.46% | 43.00% | 53.47% | 100.00% | 100.00% |
| sroie | landingai | 100 | 90.23% | 90.00% | 90.11% | 90.12% | 69.00% | 69.34% | 100.00% | 100.00% |
| vrdu | moi | 97 | 70.26% | 66.89% | 68.54% | 68.40% | 14.43% | 64.09% | 100.00% | 100.00% |
| vrdu | landingai | 97 | 66.01% | 76.26% | 70.76% | 68.32% | 10.31% | 63.35% | 100.00% | 100.00% |
| kleister | moi | 100 | 41.93% | 50.25% | 45.71% | 52.48% | 5.00% | 24.23% | 100.00% | 100.00% |
| kleister | landingai | 100 | 45.30% | 52.01% | 48.42% | 54.19% | 2.00% | 25.73% | 100.00% | 100.00% |

## 4. 字段级 F1

| 数据集 | 字段 | MOI F1 | LandingAI F1 | 差值（MOI-LandingAI） |
|---|---|---|---|---|
| sroie | address | 64.32% | 86.00% | -21.68pp |
| sroie | company | 77.78% | 83.00% | -5.22pp |
| sroie | date | 88.89% | 97.00% | -8.11pp |
| sroie | total | 86.87% | 94.47% | -7.60pp |
| vrdu | file_date | 75.74% | 40.84% | +34.90pp |
| vrdu | foreign_principle_name | 49.61% | 49.62% | -0.01pp |
| vrdu | registrant_name | 61.78% | 92.15% | -30.37pp |
| vrdu | registration_num | 80.46% | 98.43% | -17.97pp |
| vrdu | signer_name | 70.07% | 72.50% | -2.43pp |
| vrdu | signer_title | 72.73% | 56.41% | +16.32pp |
| kleister | effective_date | 79.39% | 89.04% | -9.65pp |
| kleister | jurisdiction | 28.42% | 20.21% | +8.21pp |
| kleister | party | 39.38% | 43.88% | -4.50pp |
| kleister | term | 62.75% | 63.64% | -0.89pp |

## 5. 空字段与非空字段

空字段误提率衡量 Gold 为空时产品仍返回值的比例；非空漏提率衡量 Gold 有值但产品返回空的比例。

| 数据集 | 产品 | Gold 空字段数 | 空字段正确率 | 空字段误提率 | Gold 非空字段数 | 非空正确率 | 非空漏提率 | 非空错值率 |
|---|---|---|---|---|---|---|---|---|
| sroie | moi | 0 | - | - | 400 | 78.75% | 1.75% | 19.50% |
| sroie | landingai | 0 | - | - | 400 | 90.00% | 0.25% | 9.75% |
| vrdu | moi | 144 | 79.17% | 20.83% | 438 | 66.89% | 11.64% | 21.46% |
| vrdu | landingai | 144 | 50.69% | 49.31% | 438 | 76.26% | 0.68% | 23.06% |
| kleister | moi | 95 | 67.37% | 32.63% | 305 | 41.64% | 5.90% | 52.46% |
| kleister | landingai | 95 | 80.00% | 20.00% | 305 | 42.95% | 2.30% | 54.75% |

## 6. 文档级正面对比

| 数据集 | 评分数 | 双方全对 | 仅 MOI 全对 | 仅 LandingAI 全对 | 双方均未全对 |
|---|---|---|---|---|---|
| sroie | 100 | 40 | 3 | 29 | 28 |
| vrdu | 97 | 5 | 9 | 5 | 78 |
| kleister | 100 | 2 | 3 | 0 | 95 |

## 7. 错误类型

| 数据集 | 产品 | 正确 | 错值 | 漏字段 | 空字段误提 | 数组混合错误 | 系统失败字段 |
|---|---|---|---|---|---|---|---|
| sroie | moi | 315 | 78 | 7 | 0 | 0 | 0 |
| sroie | landingai | 360 | 39 | 1 | 0 | 0 | 0 |
| vrdu | moi | 407 | 94 | 51 | 30 | 0 | 0 |
| vrdu | landingai | 407 | 101 | 3 | 71 | 0 | 0 |
| kleister | moi | 191 | 76 | 18 | 31 | 84 | 0 |
| kleister | landingai | 207 | 86 | 7 | 19 | 81 | 0 |

## 8. 耗时与成本

| 数据集 | 产品 | 平均耗时 | P95 | 总 Credits | 平均 Credits/Case |
|---|---|---|---|---|---|
| sroie | moi | 16.14s | 26.00s | - | - |
| sroie | landingai | 21.94s | 28.25s | 359.8 | 3.60 |
| vrdu | moi | 17.18s | 30.00s | - | - |
| vrdu | landingai | 30.97s | 70.44s | 759.0 | 7.82 |
| kleister | moi | 26.64s | 46.00s | - | - |
| kleister | landingai | 31.97s | 47.59s | 2147.7 | 21.48 |

耗时口径并非完全一致：MOI 使用每个任务从开始到完成的墙钟时间；LandingAI 使用 Parse 与 Extract 响应中报告的服务耗时之和。因此耗时只用于观察当前运行表现，不作为严格同硬件性能结论。MOI 当前没有可比的 credits 数据。

## 9. 综合评测分析

- LandingAI 的三数据集平均 F1 为69.77%，比 MOI 的64.57%高5.20个百分点；平均文档全对率高6.29个百分点，整体开箱准确率领先。
- SROIE 是差距最大的场景，LandingAI F1 高10.66个百分点，并在 company、date、address、total 四个字段上全部领先；MOI 的主要短板是多行地址。
- VRDU 的总体差距只有2.22个百分点。MOI 的 Precision 高4.25个百分点、文档全对率高4.12个百分点、空字段误提率低28.48个百分点；LandingAI 的 Recall 高9.37个百分点，表现为 MOI 更保守、LandingAI 更积极填值。
- VRDU 字段表现存在明显互补：MOI 在 file_date 和 signer_title 上领先，LandingAI 在registrant_name 和 registration_num 上明显领先。
- Kleister 对双方都很难，F1 均低于50%，主要瓶颈是 party 多实体数组和 jurisdiction。MOI 文档全对率为5%，LandingAI为2%，但 LandingAI 字段级 F1 仍高2.71个百分点。
- VRDU 的3个供应商内容安全失败作为范围排除项记录，不进入双方准确率和成功率统计。
- MOI Kleister 的 `party` 序列化为单字段对象数组。评测将其视为字符串数组的等价表示，语义评分和 Schema 合规统计均不因此判错。
- Strict 与标准化分数差距较大，说明日期格式、标点、空白、地址换行和数组表示会产生明显落库清洗成本。

## 10. 产品选择建议

- 标准收据和快速 API 接入场景：当前更推荐 LandingAI，其 SROIE 准确率和文档全对率有明确优势。按本次兼容口径，双方三个数据集的 Schema 合规率均为100%。
- 监管表单或错误填值代价较高的场景：MOI 在 VRDU 上具有竞争力。其 Precision、空字段判断和文档全对率更好，适合宁可返回空值、也不希望写入错误值的策略。
- 强调召回、允许后续人工审核的表单场景：LandingAI 更有优势，其 VRDU 非空字段漏提率仅0.68%，MOI为11.64%。
- NDA/合同场景：双方都不应直接用于无人审核入库，应采用自动提取后人工复核。LandingAI 在 effective_date 和 party 上稍好，MOI 在 jurisdiction 和文档全对率上稍好。
- 本次评测没有测试私有部署、工作流编排、模型替换、提示词调优、权限治理或系统集成，这些能力不能作为本报告验证出的产品优势。

## 11. 评测局限

- 每个产品只运行一次，没有通过重复运行评估随机波动和结果稳定性。
- 数据来自三个公开英文数据集，不能直接代表中文文档或公司真实业务文档。
- 没有对争议标注和近似匹配结果进行人工复核，结论依赖冻结的自动评分规则。
- 双方使用各自产品链路，但模型、运行环境和计费方式不同，本次不是同模型或同硬件对照实验。
- 耗时统计口径不同，不能据此得出严格的性能领先结论。
- LandingAI 有 credits 数据，MOI 缺少统一的算力和模型调用成本，因此不能得出完整 TCO 结论。
