# MOI OmniDocBench 全量评测分析

更新时间：2026-08-05

## 1. 结论

MOI IDC 4.1.14 在 OmniDocBench v1.6 全量 1651 页上的正式 Overall 为
**90.23**。这是本报告唯一采用的测试结果。

| 指标 | 结果 | 趋势 | 是否进入 Overall |
|---|---:|---|---|
| Overall | **90.23** | 越高越好 | — |
| Text Edit Distance | 0.1002 | 越低越好 | 是，以 `1 - Edit` 计入 |
| Formula CDM | 94.04 | 越高越好 | 是 |
| Table TEDS | 86.66 | 越高越好 | 是 |
| Table TEDS-S | 89.78 | 越高越好 | 否，辅助观察表格结构 |
| Reading Order Edit Distance | 0.3135 | 越低越好 | 否，单独报告 |

从 Overall 的失分构成看，当前最大扣分项是表格，其次是文本，公式相对最好：

| 主指标 | 距离满分 | 对 Overall 的扣分 | 占 Overall 总失分 |
|---|---:|---:|---:|
| Table TEDS | 13.34 | **4.45** | 45.5% |
| Text | 10.02 | **3.34** | 34.2% |
| Formula CDM | 5.96 | **1.99** | 20.3% |

因此，MOI 当前最值得关注的不是公式，而是表格区域检测、表格结构恢复及复杂
页面中的正文保留和阅读顺序。

## 2. 测试对象与实际配置

### 2.1 解析链路

本次评测对象为 **MOI IDC 4.1.14**，实际链路为：

1. 本地 Paddle `PP-DocLayout_plus-L` 检测表格区域；
2. 将表格区域从 MinerU 输入中涂白或替换为占位符，避免重复识别；
3. MinerU 2.7.4 使用 `vlm-vllm-async-engine` 解析处理后的 PDF；
4. 当前运行口径下，MinerU VLM 对应 `MinerU2.5-2509-1.2B`；
5. MOI V2 Pipeline 合并 MinerU 文本块与 Paddle 表格块；
6. 使用 `qwen3.5-27b` 执行标题、页眉页脚、表格 HTML、多表判断等 VLM
   后处理。

Paddle 在这里承担的是表格区域检测，不是完整的 PaddleOCR-VL 文档解析模型。
`use_remote_paddle_layout=false`，说明表格版面检测使用本地 Paddle，而不是远程
Paddle 服务。

| MOI 内部组件 | 实际版本/模型 | 在 MOI 中的作用 | 与公开榜单模型的关系 |
|---|---|---|---|
| MinerU | 软件/镜像版本 `2.7.4`；backend `vlm-vllm-async-engine`；VLM 权重口径为 `MinerU2.5-2509-1.2B`（1.2B） | 解析表格区域被遮盖或占位后的 PDF，主要提供正文、标题和公式块 | 使用了 MinerU-2.5 权重，但输入已被 MOI 预处理，之后还会经过 MOI 合并和后处理，因此不等同于榜单中的独立 MinerU-2.5 完整流程 |
| Paddle | `PP-DocLayout_plus-L`，本地运行 | 检测表格等版面区域，为 MOI 表格抽取和占位提供区域 | 只是版面检测模型，不是 PaddleOCR-VL、PaddleOCR-VL-1.5 或 1.6 的完整端到端解析流程 |
| MOI 后处理 VLM | `qwen3.5-27b` | 标题、页眉页脚、多表判断、表格 HTML 等后处理 | MOI 自有组合链路的一部分，不对应 OmniDocBench 榜单中的独立解析器 |

因此，MOI 的 90.23 不能理解为 MinerU-2.5 分数与 PaddleOCR-VL 分数的组合或
加权。MOI 实际上是“MinerU-2.5 VLM + Paddle 版面检测 + MOI/Qwen 后处理”的
完整系统分数。

### 2.2 关键配置解释

1651 个最终 ZIP 均包含配置快照。审计结果为：**1651/1651 配置一致**。

| 配置维度 | 实际值 | 含义 |
|---|---|---|
| Parser Pipeline | `enable_parser_pipeline=true` | 启用 MOI V2 后处理链路 |
| MinerU backend | `vlm-vllm-async-engine` | 使用 MinerU VLM 后端 |
| 后处理 VLM | `qwen3.5-27b` | 标题、页眉页脚、表格等后处理模型 |
| Paddle Layout | `use_remote_paddle_layout=false` | 本地 `PP-DocLayout_plus-L` |
| 并发 | `max_workers=16` | 解析内部最大 worker 数 |
| 页眉页脚输入 | `enable_header_footer_as_text=true` | MinerU 的 header/footer 先按正文进入后续链路 |
| 页眉页脚检测 | `enable_vlm_header_footer_detection=true` | MOI 仍会重新判断页眉页脚 |
| 标题检测 | `enable_vlm_title_detection=true` | 启用 VLM 标题检测 |
| PPT 标题模式 | `ppt_title_detection_mode=block` | 按块进行 PPT 标题检测 |
| 表格 HTML 重建 | `enable_table_html_regeneration=true` | 启用表格 HTML 重建 |
| 多表/合并表处理 | `enable_merged_table_split=true` | 启用合并表拆分判断 |
| 跨页表 | `enable_cross_page_table_merge=true` | 启用跨页表合并 |
| 表格存图 | `save_table_image_file=true` | 保存表格区域图片 |
| 表格转图片 | `cast_table_as_image=false` | 最终表格不降级为图片 |
| Markdown 表格图片 | `enable_table_image_in_markdown=false` | Markdown 不插入表格图片 |
| 公式修复 | `enable_formula_repair=true` | 启用公式后处理修复 |
| 列表/缩进修复 | `enable_list_marker_repair=true`、`enable_indent_detection=true` | 启用列表符号与缩进检测 |
| 碎片合并 | `enable_fragment_merge=false`、`enable_image_fragment_merge=false` | 本次未启用两类碎片合并 |
| 图片 OCR | `enable_image_ocr=false` | 批处理请求未启用图片 OCR |

完整 ParserConfig options 如下；这是从最终 ZIP 中读取的实际值，不是示例配置：

```yaml
enable_parser_pipeline: true
debug_enabled: true
max_workers: 16
pptx_normalize_before_pdf: false
save_table_image_file: true
cast_table_as_image: false
enable_table_html_regeneration: true
enable_table_embedded_image_extraction: true
enable_merged_table_split: true
enable_cross_page_table_merge: true
unmerge_table_cells: false
enable_table_inline_image_text: false
enable_table_image_in_markdown: false
enable_vlm_title_detection: true
enable_vlm_header_footer_detection: true
enable_formula_repair: true
enable_list_marker_repair: true
enable_indent_detection: true
enable_fragment_merge: false
enable_image_fragment_merge: false
enable_strikethrough_detection: false
ppt_title_detection_mode: block
enable_image_annotation_text: false
enable_decorative_icon_detection: true
flowchart_table_strategy: table
indent_spaces_per_level: 2
vlm_model: qwen3.5-27b
header_footer_similarity_threshold: 0.6
header_footer_short_text_threshold: 0.8
header_footer_min_text_threshold: 0.95
header_footer_block_coverage_threshold: 0.7
cross_page_merge_header_table: true
cross_page_table_vlm_timeout: 120.0
wps_file_type_detection_mode: null
title_detection_enable_reasoning: true
table_multi_table_judge_timeout: 30.0
table_multi_table_judge_retries: 2
table_multi_table_generate_timeout: 120.0
table_multi_table_generate_retries: 1
table_regenerate_timeout: 120.0
table_regenerate_retries: 1
l1_html_generation_timeout: 120.0
l1_html_generation_retries: 1
flowchart_detect_future_timeout: 60.0
l1_html_generation_future_timeout: 120.0
decorative_icon_ecc_threshold: 0.8
decorative_icon_max_dimension: 200
enable_cross_page_geometric_filter: true
enable_openxml_header_footer: true
enable_doc_libreoffice_openxml: true
enable_doc_uno_hf: false
enable_paddle_hf_geometric_filter: false
enable_header_footer_as_text: true
use_remote_paddle_layout: false
flowchart_table_ignore_judge: true
image_section_heading_level: bold
prompt_overrides: {}
save_ppt_page_as_image: false
```

## 3. 数据与评分输入

- 数据集：OmniDocBench v1.6，全量 1651 页；
- 原始解析输出：1651 个 ZIP，均可正常解压且各包含一个正式 `_parse.json`；
- Golden：官方 `OmniDocBench.json`；
- 预测：由结构化 `_parse.json` 转成与 Golden 一一对应的 1651 个 Markdown；
- 评分：官方 `end2end`，匹配方式为 `quick_match`；
- 有效样本：文本 1557 页、公式 2352 个（313 页）、表格 665 个（458 页）、
  阅读顺序 1638 页。

### 3.1 适配规则

适配器只解决 IDC 输出与官方评分输入之间的格式差异：

- 按最终块顺序保留 `text`、`title`、`table`、`code`；
- `title.level=1~6` 原样转成对应数量的 Markdown `#`；
- 过滤 `header`、`footer` 和 `image`；
- 只把被重复转义的数字型 `rowspan/colspan` 还原为合法 HTML 属性；
- 不修改 OCR 内容、公式、表格内容、标题层级或阅读顺序；
- 不对缺失块、错分块或空预测做人工补全。

标题层级没有单独的排行榜指标。适配器会保留 Markdown 标题层级，但官方最终
主指标仍以文本、公式、表格和阅读顺序为核心。页眉页脚和图片也不直接计入
Overall；但如果正文被错误标成 header/footer，适配时会被过滤，正文会按缺失
扣分。

## 4. 评分工具与复现环境

本次计分使用 [OmniDocBench 官方评测工具](https://github.com/opendatalab/OmniDocBench)
的 `end2end` 流程，而非自建文本相似度脚本。评分工具和实际执行环境记录如下：

| 项目 | 本次使用值 |
|---|---|
| 官方评测仓库 | `opendatalab/OmniDocBench` |
| 本地归档的评测源码版本 | commit `2b161d010d2e3aff77a0edef359ea3a6411d23cd` |
| 评分流程 | `pdf_validation.py` / `end2end_eval` |
| 匹配方式 | `quick_match` |
| Docker 镜像 | `ghcr.io/zeng-weijun/omnidocbench-eval:repro-ubuntu2204` |
| 评分配置 | `evaluate/moi-omnidocbench-final/end2end.docker.yaml` |
| 评分结果 | `evaluate/moi-omnidocbench-final/result/` |
| 环境快照 | `evaluate/moi-omnidocbench-final/result/omnidocbench-idc-4.1.14-official-md_quick_match_runtime_environment.json` |

评分配置中明确启用了文本 `Edit_dist`、公式 `Edit_dist + CDM`、
表格 `TEDS + Edit_dist` 和阅读顺序 `Edit_dist`；并发数为 13，单页匹配
超时为 420 秒，`quick_match` 截断超时为 300 秒。

容器内实际运行时依赖已随评分结果归档，关键版本为：

| 运行时依赖 | 版本 |
|---|---|
| 操作系统 | Ubuntu 22.04.5 LTS，glibc 2.35 |
| Python | 3.10.16，Conda 环境 `omnidocbench_v16_smoke_20260408_py310` |
| TeX | TeX Live 2025，pdfTeX `1.40.28` |
| CJK | `CJK.sty` 4.8.5，`c70gkai.fd` 4.8.5，字体族 `gkai` |
| ImageMagick | 7.1.1-47 Q16-HDRI |
| Ghostscript | 9.55.0 |
| 核心 Python 包 | Levenshtein 0.25.1，apted 1.0.3，lxml 4.9.1，numpy 1.24.4，pandas 2.0.3，Pillow 10.4.0，PyYAML 6.0.2，scipy 1.10.1 |

在 `document-parsing` 目录下可用以下命令复现评分。为避免覆盖归档结果，
复现输出单独写入 `reproduced-result`：

```bash
cd /Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark/document-parsing
mkdir -p evaluate/moi-omnidocbench-final/reproduced-result

docker run --rm \
  --entrypoint /opt/miniconda310/envs/omnidocbench_v16_smoke_20260408_py310/bin/python \
  -v "$PWD/datasets/omnidocbench/OmniDocBench.json:/workspace/gt/OmniDocBench.json:ro" \
  -v "$PWD/runs/omnidocbench-idc-4.1.14-vlm-final-1651-official-md:/workspace/data_md/omnidocbench-idc-4.1.14-vlm-final-1651-official-md:ro" \
  -v "$PWD/evaluate/moi-omnidocbench-final/end2end.docker.yaml:/workspace/configs/moi-omnidocbench-final.yaml:ro" \
  -v "$PWD/evaluate/moi-omnidocbench-final/reproduced-result:/workspace/result" \
  ghcr.io/zeng-weijun/omnidocbench-eval:repro-ubuntu2204 \
  pdf_validation.py --config configs/moi-omnidocbench-final.yaml
```

镜像 tag、本地官方源码 commit、评分配置和容器环境快照均已记录；
本次归档没有额外保存镜像 digest，因此长期严格复现时还应确认该 tag
仍指向同一镜像内容。

## 5. 评分细则

### 5.1 Text Edit Distance

官方匹配 Golden 与预测的文本块并计算归一化编辑距离，越低越好：

- `0` 表示文本完全一致；
- `1` 表示对应文本基本缺失或完全不匹配；
- Overall 使用 `1 - Text Edit Distance` 作为文本得分。

本次 Text Edit 为 `0.1002196469`，对应文本得分 `89.9780`。

### 5.2 Formula CDM

CDM 用于评价展示公式识别，越高越好。最终报告采用按页聚合的 `ALL`：

- 公式样本数：2352；
- 公式计分页：313；
- Formula CDM：`0.9403592033`，即 **94.04**。

### 5.3 Table TEDS 与 TEDS-S

TEDS 根据预测 HTML 与 Golden HTML 的树编辑相似度评价表格内容和结构，越高
越好；TEDS-S 只关注结构，不把单元格文本作为主要比较对象。

- 表格样本数：665；
- 表格计分页：458；
- TEDS：`0.8666337555`，即 **86.66**；
- TEDS-S：`0.8977578027`，即 **89.78**。

TEDS 进入 Overall，TEDS-S 仅作辅助分析。TEDS-S 比 TEDS 高 3.11 分，说明
除行列和合并单元格结构外，单元格文字识别、内容遗漏与内容错位也是重要失分
来源。

### 5.4 Reading Order Edit Distance

该指标比较块阅读顺序，越低越好。本次结果为 `0.3134844644`。它不进入
Overall，但反映复杂布局、块丢失、块类型错误和排序后处理带来的实际影响。

### 5.5 Overall

本报告延续官方结果中的 page-level `ALL` 聚合口径：

```text
Overall = ((1 - Text Edit) + Formula CDM + Table TEDS) / 3 × 100

        = ((1 - 0.100219646925)
           + 0.940359203319
           + 0.866633755480) / 3 × 100

        = 90.2257770625
```

Reading Order 和 TEDS-S 不进入 Overall。

## 6. MinerU 与 Paddle 公开模型对照

下表补充 OmniDocBench 官方 `v1.6_full` End-to-End 榜单中 MinerU、Paddle
系列的公开结果，并与本地 MOI 全量结果放在一起。公开分数是各项目自己的
**完整推理与后处理流程**，不是单个权重或 MOI 内部组件的消融分数。

| 系列 | 模型/流程 | 版本或参数量 | Overall↑ | Text Edit↓ | Formula CDM↑ | Table TEDS↑ | TEDS-S↑ | Reading Order Edit↓ |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **MOI（本地实测）** | **IDC 4.1.14 最终配置** | MinerU-2.5 + PP-DocLayout_plus-L + Qwen3.5-27B | **90.23** | 0.1002 | 94.04 | 86.66 | 89.78 | 0.3135 |
| MinerU | MinerU-Pipeline | 3.4.0 | 86.47 | 0.055 | 83.07 | 81.88 | 88.68 | 0.153 |
| MinerU | MinerU-2.5 | `MinerU2.5-2509-1.2B` | 93.04 | 0.045 | 95.77 | 87.88 | 91.47 | 0.130 |
| MinerU | MinerU2.5-Pro | `MinerU2.5-Pro-2605-1.2B` | 95.75 | 0.036 | 97.45 | 93.42 | 95.92 | 0.120 |
| Paddle | PaddleOCR-VL | 0.9B | 94.18 | 0.040 | 95.91 | 90.65 | 93.74 | 0.135 |
| Paddle | PaddleOCR-VL-1.5 | 0.9B | 94.93 | 0.038 | 96.89 | 91.67 | 94.37 | 0.130 |
| Paddle | PaddleOCR-VL-1.6 | 0.9B | 96.34 | 0.0326 | 97.5304 | 94.7619 | 97.1002 | 0.1278 |

来源：[OmniDocBench 官方 v1.6_full End-to-End 榜单与模型版本说明](https://github.com/opendatalab/OmniDocBench#end-to-end-evaluation)。

对照时需要注意：

1. **MOI 使用的是 MinerU-2.5 权重，不是 MinerU2.5-Pro。** MinerU 软件/镜像
   版本为 2.7.4，VLM backend 为 `vlm-vllm-async-engine`；
2. **MOI 没有调用 PaddleOCR-VL 系列端到端解析器。** `PP-DocLayout_plus-L`
   只负责本地版面/表格区域检测，所以 PaddleOCR-VL 的 94.18～96.34 不能当作
   MOI 内部 Paddle 环节的分数；
3. MOI 的输入预处理会遮盖 MinerU 所见的表格区域，随后再由 Paddle 表格结果
   和 MOI 后处理回填，因此其错误传播方式与独立 MinerU-2.5 不同；
4. MOI 的公式分数接近 MinerU-2.5，但 Text 和 Reading Order 差距更明显；
   表格分数也略低于独立 MinerU-2.5，和前文识别出的表格检测、拆分及回填问题
   一致；
5. 这些公开结果可用于定位量级，但不是相同服务环境、相同推理参数下的严格
   A/B 复现。

## 7. 主要扣分点

### 7.1 表格是 Overall 最大扣分来源

Table TEDS 距离满分 13.34 分，对 Overall 造成 **4.45 分**损失，占 Overall
全部失分的 45.5%。665 个表格中有 11 个 TEDS 为 0，56 个低于 0.5。

主要问题包括：

1. **表格区域检测过大或错误**：多个独立表格被 Paddle 识别为一个大区域；
2. **缺少 MinerU 兜底**：表格区域被涂白后，Paddle 误检会同时屏蔽 MinerU
   对该区域正文或表格的识别；
3. **多表拆分失败**：一个大区域没有恢复成 Golden 中的多张独立表格；
4. **HTML 重建损失**：出现空行、内容截断、单元格错位或下半张表缺失；
5. **表格类型漏判**：视觉表格被输出成列表或普通文本，文字可能可读，但
   Table TEDS 仍为 0；
6. **后续排序丢块**：表格已在中间阶段生成，最终排序后消失。

按官方属性分组，`layout_hard` 的 TEDS 为 80.94，`table_hard` 为 82.37；
新闻、笔记、传统中文和学术文献类表格也相对偏低。由于属性组样本量不同，
这些分组只用于定位方向，不应直接解释为稳定的文档类型排名。

### 7.2 文本失分包含识别错误和块类型错误

Text Edit 对 Overall 造成 **3.34 分**损失。1557 个文本计分页中：

- 14 页 Edit Distance 为 1；
- 24 页不低于 0.9；
- 4 页适配后为空，其中 2 页最终只有 image，2 页最终只有 header。

主要问题包括：

1. MinerU 或 Paddle 将正文整体识别为表格，导致文本指标找不到正文块；
2. 正文或标题被 MOI 后续页眉页脚检测重新标成 header/footer；
3. 图片页没有开启图片 OCR，最终只有 image block；
4. 表格占位和合并链路中正文被覆盖或没有回填；
5. 手写、历史文档、模糊内容、复杂环绕文字等场景 OCR 误差较高。

`enable_header_footer_as_text=true` 只保证 MinerU 已标成 header/footer 的内容先以
正文进入 MOI；它不能阻止 MOI 后续 VLM 页眉页脚检测再次把正确正文改成
header/footer。因此，最终结果中仍存在正文被过滤的情况。

### 7.3 公式总体较好，但复杂公式页仍有集中失分

Formula CDM 对 Overall 造成 **1.99 分**损失，是三个主指标中最小的一项。
2352 个公式中有 59 个 CDM 为 0，132 个低于 0.5。

主要问题包括：

- MinerU 漏掉公式，或把公式内容识别成正文、页脚等其他类型；
- 多栏、环绕文字、模糊扫描和笔记类页面的公式匹配较弱；
- 公式密集页面中的局部漏识别会产生多个低分样本；
- 公式修复无法恢复上游完全缺失的公式块。

按属性分组，三栏布局 CDM 为 51.29，O 型文字环绕为 46.55，模糊扫描为
65.95，是目前较明确的困难场景。

### 7.4 阅读顺序是独立的明显弱项

Reading Order Edit 为 0.3135，1638 个计分页中有 87 页为 1，132 页不低于
0.9。虽然该指标不进入 Overall，但会直接影响最终 Markdown 的可读性。

主要原因包括：

- 多栏、三栏和报纸布局的跨栏排序错误；
- 表格标题、表格块与正文块的相对顺序错误；
- 块丢失或块类型变化导致阅读序列无法正确匹配；
- 历史文档、手写和复杂几何变形页面的布局恢复不稳定。

## 8. 评分器异常及结果边界

本次官方评分完整处理 1651 页，但存在少量评分器边界情况：

- 2 页 `quick_match` 达到 300 秒后使用官方截断匹配回退，没有页面硬超时；
- 3 个公式样本因 CDM 临时目录清理异常被记为 0；
- 3 个超长表格达到 TEDS 120 秒上限，被按超时记为 0。

这 6 个样本对 Overall 的理论最大影响为 **0.239 分**：

- 3 个公式最多影响 Overall `0.021` 分；
- 3 个表格最多影响 Overall `0.218` 分；
- 即使全部按满分修正，Overall 上限也约为 `90.47`。

因此，正式结果仍采用官方实际输出 **90.23**；评分器异常不会改变“表格是最大
扣分项、文本其次、公式相对最好”的总体判断。

## 9. 最终评价

MOI 在本次统一配置下已经取得较高的公式和整体解析分数，但组合链路会放大
表格区域检测错误：表格区域一旦涂白，MinerU 无法再对该区域提供兜底，后续
多表拆分和 HTML 重建若继续失败，就会同时造成表格、正文和阅读顺序失分。

从最终全量结果看，当前质量瓶颈依次是：

1. 表格检测、拆分和 HTML 结构恢复；
2. 复杂布局中的正文保留与阅读顺序；
3. 页眉页脚后处理对正文和标题的误分类；
4. 图片页在关闭图片 OCR 时形成的内容缺失；
5. 多栏、模糊和公式密集页面中的局部公式漏识别。

最终原始输出、评分输入、评分配置和完整指标分别位于：

- `runs/omnidocbench-idc-4.1.14-vlm-final-1651/`
- `runs/omnidocbench-idc-4.1.14-vlm-final-1651-official-md/`
- `evaluate/moi-omnidocbench-final/end2end.yaml`
- `evaluate/moi-omnidocbench-final/result/`
