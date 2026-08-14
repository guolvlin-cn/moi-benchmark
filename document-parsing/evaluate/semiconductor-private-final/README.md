# 半导体场景私有数据集正式结果复现说明

本目录记录 50 份半导体场景私有文档的正式评分输入关系、评分器版本和可机读结果。正式结论以当前仓库中提交的原始结果为准：MOI 使用 50 个 ZIP 内的 `*_parse.json`，MinerU 和 PaddleOCR-VL 使用各自 `converted_parsed/` 下的统一 Parse Blocks。

## 正式结果

| 产品 | 文件内维度等权、文件间等权 | 文件内元素数加权、文件间等权 |
|---|---:|---:|
| MOI IDC 4.1.14 | 84.5% | 89.4% |
| PaddleOCR-VL | 58.6% | 70.5% |
| MinerU Precision | 56.8% | 66.7% |

历史评分表曾引用较早导入的一批 MOI Parse Blocks，而仓库保留的 50 个正式 ZIP 已是后续结果。为保证“报告、评分表、可机读得分、仓库原始 ZIP”能够闭环复算，本目录及主报告统一以当前提交的 ZIP 为权威输入。

## 评分器与聚合口径

- 评分器仓库：`matrixorigin/moi-parse-bench`
- 固定 commit：`06faf76112c998835f0f9ca174a5f2d311d559f2`
- Python package：`moi-parsing-benchmark 1.0.0`
- Runner：`parsing_benchmark.runner.BenchmarkRunner(strict_contract=false)`
- 正式评分日期：2026-07-31；上述 commit 是该日期前该仓库的最新提交。

每个文件先独立评分。文件内维度等权分对该文件的有效维度 F1 求平均；文件内元素数加权分使用各维度 `total_count` 加权。两种总分最后都对 50 个文件等权平均，解析失败也保留在分母中。

## 一键复算

依赖本机已有的 `moi-parse-bench` Git 对象，但不会使用其当前工作区代码。脚本通过 `git archive` 导出固定 commit 后评分：

```bash
cd /Users/wangyaqi/Documents/cursor_project/agent评估/moi-benchmark
bash document-parsing/scripts/reproduce_semiconductor_private_score.sh
```

默认评分器仓库为 `/Users/wangyaqi/Documents/cursor_project/moi-parse-bench`。其他位置可显式指定：

```bash
MOI_PARSE_BENCH_DIR=/path/to/moi-parse-bench \
  bash document-parsing/scripts/reproduce_semiconductor_private_score.sh
```

输出写入本目录的 `reproduced-score.json`。脚本会校验 3 个产品的两种正式总分；任一输入变化导致分数不一致时以非零状态退出。

## 从竞品原始结果重新适配

正常复算直接使用仓库已保留的 `converted_parsed/`，不需要重跑适配器。如需审核转换过程，可先导出固定版本的 MinerU 适配器，再统一转换到临时目录：

```bash
source /Users/wangyaqi/Documents/cursor_project/.venv/bin/activate

SCORER_REPO=/Users/wangyaqi/Documents/cursor_project/moi-parse-bench
SCORER_COMMIT=06faf76112c998835f0f9ca174a5f2d311d559f2
TMP_DIR="$(mktemp -d)"
git -C "$SCORER_REPO" archive "$SCORER_COMMIT" tools/parsing_benchmark \
  | tar -x -C "$TMP_DIR"

python document-parsing/scripts/adapt_semiconductor_private_outputs.py \
  --mineru-adapter "$TMP_DIR/tools/parsing_benchmark/tools/mineru_content_list_to_parsed" \
  --output-dir /tmp/semiconductor-private-converted \
  --force
```

- MinerU：`*_content_list.json` 经固定 commit 自带的 `mineru_content_list_to_parsed` 转换。
- PaddleOCR-VL：每个 case 的 `result.json` 经 `scripts/adapt_paddleocr_vl_to_parsed.py` 转换。
- MOI：不做结构适配，直接从每个正式 ZIP 提取唯一的 `*_parse.json`。

## 输入、配置与完整性

- 源文件：`document-parsing/datasets/半导体场景模拟数据/`
- Golden：`document-parsing/datasets/半导体场景模拟数据golden/`
- MOI 原始结果：`document-parsing/runs/半导体场景私有数据集-idc-4.1.14/`
- MinerU 原始及转换结果：`document-parsing/runs/半导体场景模拟数据-mineru-precision/`
- PaddleOCR-VL 原始及转换结果：`document-parsing/runs/半导体场景模拟数据-paddleocr-vl/`
- 详细分析：`document-parsing/evaluate/半导体场景私有数据集评测报告.md`
- 逐文件评分：`reproduced-score.json`
- 逐文件来源、SHA-256、页数、Golden 状态和 MOI 配置分组：`manifest.json`

MOI 的 50 个结果来自 4 个历史配置小批次。当前批跑脚本是后来整理的统一配置，不能代替正式 ZIP 中的实际配置；复现时以 `manifest.json` 记录和 ZIP 内 `parser_config` 为准。

Git 时间线也支持这一取舍：正式结果、初版报告与批跑脚本在 2026-07-31 的 `bf82faa` 一并提交；配置说明报告随后在 2026-08-04 的 `3d403d0` 更新，而当前批跑脚本工作区版本形成于 2026-08-03。因此，后更新的报告负责说明历史结果，脚本只代表后续统一重跑方式；若两者与单个 ZIP 的配置存在差异，仍以 ZIP 内配置为最高优先级。

Golden 已按源文件 SHA-256 与 `/Users/wangyaqi/Documents/cursor_project/moi-parse-bench/datasets/parse` 最新工作区逐份核对：50 份内容完全一致且均标记为 reviewed。2026-08-14 更新的 8 份 Golden 仅清除了 `_todo`、`_todo_no_split_texts` 等待复核字段并确认 `_reviewed=true`，计分字段未变化，因此重新评分后正式分数保持不变。

页数分组采用正式评分表中的源文件/Golden 页数。`112跨页表解析两次.docx` 和 `145页眉下的图片被识别为表格一部分.docx` 的解析器输出页码与该口径不同，manifest 中保留了 `parser_page_count`，同时用 `page_count` 固定正式分析口径。
