# OmniDocBench v1.6 Golden 获取与校验

复现 MOI 最终正式评分时需要官方 OmniDocBench v1.6 Golden：
`OmniDocBench.json`。数据文件较大，仓库只记录获取来源、版本与校验值，不提交
数据本体。

## 获取来源

- 官方仓库：<https://github.com/opendatalab/OmniDocBench>
- 本次评分器对应源码版本：
  <https://github.com/opendatalab/OmniDocBench/tree/2b161d010d2e3aff77a0edef359ea3a6411d23cd>
- 官方数据下载说明：
  <https://github.com/opendatalab/OmniDocBench/blob/2b161d010d2e3aff77a0edef359ea3a6411d23cd/README_zh-CN.md>

按官方说明下载 v1.6 数据集后，将 Golden 放到：

```text
document-parsing/datasets/omnidocbench/OmniDocBench.json
```

## 固定校验值

本次正式评分所用文件：

```text
数据集版本：OmniDocBench v1.6
页面数：1651
文件名：OmniDocBench.json
SHA-256：a45cd84b04ad8b793e775089640e6b681209abea33ead54c1828ddca35fae496
```

macOS 校验命令：

```bash
shasum -a 256 document-parsing/datasets/omnidocbench/OmniDocBench.json
```

Linux 校验命令：

```bash
sha256sum document-parsing/datasets/omnidocbench/OmniDocBench.json
```

只有校验值一致时，才能认为 Golden 与最终正式结果口径相同。一键复现脚本也会
在启动 Docker 前自动执行同一校验。

## 在正式评测链路中的位置

Golden 与
`runs/omnidocbench-idc-4.1.14-vlm-final-1651-official-md/` 中的 1651 个预测
Markdown 一一对应，由 `scripts/reproduce_omnidocbench_final_score.sh` 送入官方
evaluator。完整配置、适配规则和指标解释见
`evaluate/MOI_OmniDocBench评测分析.md`，正式结果摘要见本目录的 `summary.md`。
