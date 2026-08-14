# MOI IDC 4.1.14 OmniDocBench 最终全量评分

## 结论

MOI IDC 4.1.14 在 OmniDocBench v1.6 全量 1651 页上的正式分数为 **90.23**。

| 指标 | 全量结果 | 趋势 |
|---|---:|---|
| Overall | **90.23** | 越高越好 |
| Text Edit Distance | 0.1002 | 越低越好 |
| Formula CDM | 94.04 | 越高越好 |
| Table TEDS | 86.66 | 越高越好 |
| Table TEDS-S | 89.78 | 越高越好 |
| Reading Order Edit Distance | 0.3135 | 越低越好 |

Overall 使用 page-level `ALL` 口径：

```text
((1 - 0.100219646925) * 100 + 94.0359203319 + 86.6633755480) / 3
= 90.2257770625
```

## 输入与评分口径

- 页面：OmniDocBench v1.6 全量 1651 页，预测与 Golden 一一对应。
- MinerU 后端：`vlm-vllm-async-engine`。
- 关键配置：`enable_header_footer_as_text=true`、`enable_image_ocr=false`。
- 评分：OmniDocBench 官方 `end2end` + `quick_match`。
- 有效样本：文本计分页 1557，公式 2352 个，表格 665 个，阅读顺序计分页 1638。
- 结构化结果转 Markdown 时保留 `text/title/table/code`，过滤
  `header/footer/image`；不修复 OCR、公式、表格内容、标题层级或阅读顺序。
- 对数字型 `rowspan/colspan` 的双重引用只做序列化还原，不改变表格语义。

## 可复现性固定项

- 官方评测源码：`opendatalab/OmniDocBench` commit
  `2b161d010d2e3aff77a0edef359ea3a6411d23cd`；
- 官方 Docker 镜像 tag：
  `ghcr.io/zeng-weijun/omnidocbench-eval:repro-ubuntu2204`；
- Docker 镜像 digest：
  `sha256:6116ad72172e763b5c43e963d5efebf2093f2362b975f58156ce4f6c9142e617`；
- Golden SHA-256：
  `a45cd84b04ad8b793e775089640e6b681209abea33ead54c1828ddca35fae496`；
- 评分输入：1651 个 Markdown；适配清单逐文件记录 SHA-256，转换失败数为 0；
- 评分配置：本目录的 `end2end.docker.yaml`；
- 一键复现入口：
  `document-parsing/scripts/reproduce_omnidocbench_final_score.sh`。

该镜像构建于 `2026-04-08 18:21:23 +08:00`，GitHub Packages 显示版本发布于
约 4 个月前；本次正式评分前后两周内没有镜像版本或 tag 内容更新，因此可确认
正式评分使用的是上述 digest 对应版本。原始评分完成后因镜像体积较大，本地
镜像已删除；复现脚本直接以 digest 固定同一镜像内容。

## 评分器运行说明

- 4 页转换后为空：原始结构化结果仅包含官方适配规则过滤的图片或页眉块。
- 2 页 `quick_match` 达到 300 秒后使用官方截断匹配回退，未触发页面硬超时。
- 3 个公式样本因官方 CDM 临时目录清理异常被记为 0；这是评分器内部异常，
  不是 MOI 解析任务失败。
- 3 个超长表格达到官方 TEDS 120 秒上限并按超时规则计分。

完整指标及运行记录位于本目录的 `result/` 下。

## 相关文件

- [完整分析](../MOI_OmniDocBench评测分析.md)；
- [Golden 来源与校验](GOLDEN.md)；
- [官方评分配置](end2end.docker.yaml)；
- [最终评分输入说明](../../runs/omnidocbench-idc-4.1.14-vlm-final-1651-official-md/README.txt)；
- [IDC ZIP 适配器](../../scripts/adapt_idc_omnidocbench.py)；
- [一键复现](../../scripts/reproduce_omnidocbench_final_score.sh)；
- [复现结果校验器](../../scripts/verify_omnidocbench_final_score.py)。
