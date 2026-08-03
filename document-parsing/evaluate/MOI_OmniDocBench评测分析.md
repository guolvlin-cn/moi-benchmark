# MOI OmniDocBench 当前跑分、模型版本与低分原因记录

更新时间：2026-08-03

## 1. 评测口径

- 数据集：OmniDocBench v1.6，共 1651 页。
- 评分方式：官方 `end2end`、`quick_match`。
- Overall 公式：

  ```text
  ((1 - Text Edit Distance) * 100 + Formula CDM + Table TEDS) / 3
  ```

- MOI 输出由 `_parse.json` 无损转换为官方评分所需的逐页 Markdown：保留
  `text/title/table/code`，过滤 `header/footer/image`，不修复 OCR、公式、
  表格内容、标题层级或阅读顺序。
- 表格分数只对 5 个输出中被双重引用的纯数字 `rowspan/colspan` 属性做了
  序列化还原。这些 span 属性语义合法，归一化不改变表格内容和结构。

## 2. MOI 全量及分批实测分数

最早对 1651 页混合结果直接评分得到 Overall **87.07**。后续发现这 1651 页
并非使用同一 MinerU 接口和后端完成，因此该数字只能作为历史全量结果，不能
作为当前 MOI 的代表分数。

| 结果口径 | 页数 | Overall↑ | Text Edit↓ | Formula CDM↑ | Table TEDS↑ | TEDS-S↑ | Reading Order Edit↓ |
|---|---:|---:|---:|---:|---:|---:|---:|
| 历史全量混合结果 | 1651 | **87.07** | 0.1083 | 86.47 | 85.58 | 88.83 | 0.3212 |
| 第一批：老 MinerU 接口、VLM 后端 | 1239 | **90.04** | 0.1099 | 95.91 | 85.21 | 88.64 | 0.3293 |
| 第二批：新 MinerU 接口、误用 Pipeline 后端 | 412 | **78.14** | 0.1034 | 57.95 | 86.81 | 89.45 | 0.2967 |

当前暂以第一批正常 VLM 链路的 1239 页均值 **90.04** 作为 MOI 全量表现的
近似值，但它不是完整 1651 页同配置重跑所得的正式全量分数。

两批拆分后，最显著的差异集中在公式：第一批 Formula CDM 为 **95.91**，
第二批只有 **57.95**。第二批 585 个公式样本中有 106 个预测为空；第一批
1767 个公式样本中只有 12 个预测为空。因此，异常 Pipeline 批次和低分存在
很强的相关性。

需要保留的主要限制是：两批页面不是同一批页面的严格 A/B。第二批运行期间
虽然遇到火山云欠费、远程 Paddle 服务无法访问，但该服务只用于图片后处理的
OCR；表格区域检测调用的是本地 CPU 上的 Paddle，不受此次服务不可用影响。
因此，火山云问题预计对 OmniDocBench 主要分数影响很小，不能解释第二批明显
偏低的 Overall 和 Formula CDM；当前差异主要仍与 MinerU 后端从 VLM 变为
`pipeline` 及其输出适配问题相关。不过，由于不是同页 A/B，仍不能据此精确
量化单独切换后端带来的分数变化。

## 3. MOI 实际使用的模型和链路

本次被评测的产品版本为 IDC 4.1.14。核心链路为：

1. Paddle `PP-DocLayout_plus-L` 检测表格区域；
2. 将检测到的表格区域涂白或插入占位符；
3. MinerU 解析处理后的 PDF；
4. MOI V2 Pipeline 合并 MinerU 文本块和 Paddle 表格块，并执行表格 HTML、
   多表拆分、跨页表、标题、页眉页脚、排序等后处理。

| 批次 | MinerU 软件/接口 | MinerU 后端 | 对应模型 | 页数 |
|---|---|---|---|---:|
| 第一批 | MinerU 2.7.4 老接口 | `vlm-vllm-async-engine` | `MinerU2.5-2509-1.2B`，1.2B | 1239 |
| 第二批 | 新 MinerU API | `pipeline` | MinerU Pipeline，不是 MinerU2.5 VLM | 412 |

MinerU 2.7.4 官方默认 VLM 权重是
`OpenDataLab/MinerU2.5-2509-1.2B`，因此当前将第一批记作 MinerU2.5。
但尚未进入 MOCloud 私有镜像核实其 `mineru.json` 和实际权重是否被替换过，
这一对应关系仍保留镜像侧未核验的限制。

MOI 使用的 Paddle 模型是表格区域检测模型 `PP-DocLayout_plus-L`，不是公开
榜单中的完整 PaddleOCR-VL 文档解析流程，两者不能直接视为同一个模型。

## 4. 公开 MinerU 与 Paddle 分数

### 4.1 OmniDocBench v1.6 同口径结果

以下数字来自 OmniDocBench 官方仓库当前 v1.6_full End-to-End 榜单，与本次
本地 v1.6 评测最接近。公开结果包含各项目自己的完整推理和后处理流程，并非
只评单一权重，因此只能作为公开基线，不能视为严格复现实验。

| 系列 | 公开模型/流程 | 参数量或版本 | Overall↑ | Text Edit↓ | Formula CDM↑ | Table TEDS↑ | TEDS-S↑ | Reading Order Edit↓ |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| MinerU | MinerU-Pipeline | MinerU 3.4.0 | 86.47 | 0.055 | 83.07 | 81.88 | 88.68 | 0.153 |
| MinerU | MinerU-2.5 | 1.2B | 93.04 | 0.045 | 95.77 | 87.88 | 91.47 | 0.130 |
| MinerU | MinerU2.5-Pro | 1.2B | 95.75 | 0.036 | 97.45 | 93.42 | 95.92 | 0.120 |
| Paddle | PaddleOCR-VL | 0.9B | 94.18 | 0.040 | 95.91 | 90.65 | 93.74 | 0.135 |
| Paddle | PaddleOCR-VL-1.5 | 0.9B | 94.93 | 0.038 | 96.89 | 91.67 | 94.37 | 0.130 |
| Paddle | PaddleOCR-VL-1.6 | 0.9B | 96.34 | 0.0326 | 97.5304 | 94.7619 | 97.1002 | 0.1278 |

来源：[OmniDocBench 官方 v1.6 End-to-End 榜单](https://github.com/opendatalab/OmniDocBench#end-to-end-evaluation)。
榜单同时标注 MinerU-2.5 权重为 `MinerU2.5-2509-1.2B`，MinerU-Pipeline
评测版本为 3.4.0。

### 4.2 之前查到的 v1.5 历史数字

这些数字来自较早的 v1.5 公开材料，不应和上面的 v1.6 分数直接横向排序：

| 模型/流程 | OmniDocBench 版本 | 公开 Overall |
|---|---|---:|
| MinerU 3.0 Pipeline | v1.5 | 86.2 |
| MinerU2.5 | v1.5 | 90.67 |
| PaddleOCR-VL | v1.5 | 92.86 |
| PaddleOCR-VL-1.5 | v1.5 | 94.5 |

来源：

- [MinerU 官方 README](https://github.com/opendatalab/MinerU/blob/master/README_zh-CN.md)：记录 MinerU 3.0 Pipeline 在 v1.5 上为 86.2。
- [MinerU2.5 论文](https://openreview.net/pdf/f7e33cc67eec3a7907d32d5b5ba389a28e3c9e0d.pdf)：记录 MinerU2.5 在当时口径下为 90.67。
- [PaddleOCR-VL 论文](https://arxiv.org/abs/2510.14528)：对应初代 0.9B PaddleOCR-VL 的公开评测。
- [PaddleOCR-VL 官方文档](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.md)：记录 PaddleOCR-VL-1.5 在 v1.5 上为 94.5，并说明完整 PaddleOCR-VL 包含版面分析和 VLM 识别两个阶段。

## 5. 两批 MinerU 接口差异及其影响

全量运行到后 412 页时切换了 MinerU API。切换时没有注意后端参数，新接口
调用成了 `backend=pipeline`，而不是第一批使用的 VLM 后端。

这不仅改变了底层解析能力，也可能改变中间 JSON 的结构和 block 类型。当前
MOI 适配链路最初按 VLM 输出设计，Pipeline 可能输出此前未完整适配的类型或
字段，例如 `index` 类 block，造成内容没有进入公式、正文或最终 Markdown。
这一点目前是基于输出差异提出的机制假设，尚未对 412 页所有中间 block 做完
逐类型统计。

分批计分结果支持“第二批链路异常”的判断：第二批 Overall 比第一批低
**11.90** 分，Formula CDM 低 **37.96** 分；将其混入全量后，Overall 从第一批
近似值 90.04 降到 87.07。火山云上的远程 Paddle 不可用只影响图片后处理
OCR，表格检测使用本地 CPU Paddle，预计对这些官方主指标影响很小。因此，
第二批的显著低分主要指向 MinerU `pipeline` 后端及其 block 输出适配差异；
但由于两批不是同页 A/B，现阶段仍不把 11.90 分直接等同于切换后端的净影响。

## 6. 第一批仍低于公开 MinerU-2.5 的原因分析

排除第二批后，第一批 Overall 为 90.04，仍低于公开 v1.6 榜单中
MinerU-2.5 的 93.04。逐页检查已确认 MOI 组合与后处理链路会在部分页面上
新增错误，主要包括以下问题。

### 6.1 表格区域检测和涂白会放大 Paddle 错误

- Paddle 把多个独立表格检测成一个大区域；对应区域随后从 MinerU 输入中
  被涂白，MinerU 无法再提供独立表格或正文作为兜底。
- Paddle 表格区域漏检、误检或覆盖范围过大时，错误会直接传递到最终合并结果。

### 6.2 多表拆分失败

- 页面实际包含多张独立表格，但 Paddle 只返回一个大区域。
- MOI 的 `multi_table_split` 后处理没有将大区域恢复为多张表，最终多个 Golden
  表格只能匹配到一张输出，其余表格直接得到 0 分。
- 已确认案例包括 Character Sheet 页面 6 张表合成 1 张，以及两个年度财务表
  合成 1 张残缺表。

### 6.3 表格 HTML 重建产生结构损失

- 表格重建后出现大量空行、内容截断、下半张表丢失或单元格结构变化。
- 这类错误不是 `rowspan/colspan` 序列化引号导致；完成无损 span 归一化后，
  对应表格仍然低分或为 0。

### 6.4 后续排序阶段丢失已经生成的表格

- 有效表格在前序合并阶段已经存在，但经过最终排序阶段后消失。
- 已在两个 KET 页面复现；最终 Markdown 可能只剩被过滤的 header/footer，
  从而形成整页空预测。

### 6.5 正确正文或标题被页眉页脚后处理改错

- MinerU 原始结果是正确的 `text/title`，MOI 后续页眉页脚检测将其改成
  `header/footer`，最终在评分适配时被过滤。
- 已确认 PPT 首页作者与单位信息被改为 footer。
- 已确认教材顶部导航和正文主标题文字相同，页眉相似度规则将正文主标题一起
  归为 header，造成主标题丢失。

### 6.6 页眉页脚产品语义与 Golden 口径不一致

- 部分位于页边的考试提示语从产品语义看可以视作 footer，但 OmniDocBench
  Golden 将其标成正文。
- 这类页面会形成实际产品策略与 benchmark 标注口径之间的分数损失，和明显的
  正文误删需要分开理解。

上述问题只记录当前已经观察到的现象。MinerU 自身把正文识别为表格、把表格
识别为列表、漏识别公式或误识别页脚等上游问题也存在，但这些问题理论上也会
影响公开 MinerU，不足以单独解释 MOI 和 MinerU-2.5 公开分数之间的差距。

详细 case 和中间阶段证据见：

- [低分样本初步分析](./omnidocbench-idc-4.1.14-official/low-score-cases.md)
- [后处理导致的低分样本](./omnidocbench-idc-4.1.14-official/postprocessing-low-score-cases.md)

## 7. 412 页重跑计划与待验证问题

当前计划重跑之前使用新 MinerU 接口的 412 页，做两项关键调整：

1. MinerU 后端从误用的 `pipeline` 改为 `vlm`；
2. `enable_header_footer_as_text` 从 `false` 改为 `true`。

`enable_header_footer_as_text=true` 会把 MinerU 原始输出中已经标成
`header/footer` 的块先按普通正文送入 MOI 后续链路，避免 MinerU 把正文、
标题附近内容等误标成页眉页脚后被直接过滤。本次重跑用于观察正确 VLM 后端
和该配置下，这 412 页的 Overall、Text Edit、Formula CDM、Table TEDS、
Reading Order 以及空预测页数是否明显改善。

该配置不能覆盖所有已发现的页眉页脚问题：如果 MinerU 原始结果是正确的
`text/title`，但 MOI 后续 VLM 页眉页脚检测又将其改成 `header/footer`，错误
仍可能发生。同时，开启该参数也可能让真实页眉页脚作为正文进入评分。因此，
重跑结果应被记录为“412 页新配置结果”，不能在未完成同页 A/B 前把全部变化
只归因于这一参数。

重跑完成前，当前正式记录保持为：

- 历史 1651 页混合分：**87.07**，不作为代表分；
- 当前代表分：第一批 1239 页正常 VLM 链路 **90.04**；
- 第二批旧异常结果：412 页 Pipeline 链路 **78.14**，仅用于原因定位；
- 412 页 VLM + `enable_header_footer_as_text=true`：待完成后补充。
