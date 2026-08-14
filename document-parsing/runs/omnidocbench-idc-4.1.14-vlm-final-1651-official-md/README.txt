MOI IDC 4.1.14 OmniDocBench v1.6 最终评分输入
================================================

本目录是 OmniDocBench 官方 end2end evaluator 的 Prediction 输入，不是原始解析
输出。目录包含：

- 1651 个与官方 Golden 页面名称一一对应的 Markdown；
- adapter-report.json：适配清单，记录原始 ZIP、输出文件、块类型统计和每个
  Markdown 的 SHA-256；清单中 output_count=1651、failed=0、empty_output_count=4。

生成关系
--------

原始 IDC 解析 ZIP（不入库，约 7.4 GB）
  -> scripts/adapt_idc_omnidocbench.py
  -> 本目录的 1651 个 Markdown + adapter-report.json
  -> scripts/reproduce_omnidocbench_final_score.sh
  -> evaluate/moi-omnidocbench-final/result/

适配器只映射输出格式，不人工修复 OCR、公式、表格内容、标题层级或阅读顺序。
完整规则见：

  ../../evaluate/MOI_OmniDocBench评测分析.md

重新生成评分输入
----------------

从 moi-benchmark 仓库根目录运行：

  python3 document-parsing/scripts/adapt_idc_omnidocbench.py \
    --input-dir document-parsing/runs/omnidocbench-idc-4.1.14-vlm-final-1651 \
    --output-dir document-parsing/runs/omnidocbench-idc-4.1.14-vlm-final-1651-official-md \
    --golden document-parsing/datasets/omnidocbench/OmniDocBench.json \
    --overwrite

原始 ZIP 不属于从已归档预测复算 90.23 的必要输入。只复算正式评分时，请直接
运行：

  document-parsing/scripts/reproduce_omnidocbench_final_score.sh

相关入口
--------

- Track 首页：../../README.md
- Golden 获取与校验：../../evaluate/moi-omnidocbench-final/GOLDEN.md
- 评分摘要：../../evaluate/moi-omnidocbench-final/summary.md
- 评分配置：../../evaluate/moi-omnidocbench-final/end2end.docker.yaml
- 完整归档结果：../../evaluate/moi-omnidocbench-final/result/
