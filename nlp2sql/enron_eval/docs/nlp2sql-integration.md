# 合入moi-benchmark/nlp2sql记录

## 合入位置

本项目已按以下路径整理到 `matrixorigin/moi-benchmark`：

```text
nlp2sql/enron_eval/
```

GitHub 目标仓库：<https://github.com/matrixorigin/moi-benchmark/tree/main/nlp2sql>

## 旧目录的处理

远端当前存在一个早期 `nlp2sql/enron/`，内容仍是 SQLite 方案，并写有“评测待完成”。新的 `enron_eval/` 已经包含 MySQL 8 私有快照、50 道正式混合问题、三产品结果以及 MOI 语义配置前后对比。

本次变更在同一个工作分支中：

1. 删除了旧的 `nlp2sql/enron/` 当前工作树内容；
2. 新增了 `nlp2sql/enron_eval/`；
3. 依靠 Git 历史保留旧版，没有额外复制 `archive/enron/`；
4. 更新了 `nlp2sql/README.md`，将 Enron 50 题作为正式私有数据集阶段；
5. 更新了 `nlp2sql/systems/manifest.yaml`，记录 MOI、Wren 和 Chat2DB 的实际部署形态与版本。

不建议同时保留 `nlp2sql/enron/` 和 `nlp2sql/enron_eval/` 两个当前入口，否则读者无法判断哪一个是正式版本。

## nlp2sql顶层结构

```text
nlp2sql/
├── README.md                       # Track总览，列出公开和私有两个阶段
├── NL2SQL评测汇总报告.md            # Spider与Enron跨阶段汇总
├── spider/                         # Spider mix50公开集完整评测包
│   ├── README.md
│   ├── NL2SQL评测汇总报告.md
│   ├── datasets/
│   ├── results/
│   └── scripts/
├── enron_eval/                     # 新的私有Enron 50题评测
├── plans/
├── refs/
└── systems/
```

## 顶层README摘要

```markdown
## 私有数据集阶段：Enron Eval 50

- 数据：Enron 邮件私有固定快照，6 表，原始 CSV 不入库；
- 问题：50 道中文问题，25 道口语化、25 道原始详细表达；
- 产品：MOI 本地部署、Wren AI 本地 Docker、Chat2DB 会员桌面版；
- 主指标：MySQL 8 Execution Accuracy；
- 当前结果：Chat2DB 84%、MOI 语义配置 82%、MOI 无语义 70%、Wren 48%；
- 详细材料：[enron_eval/](enron_eval/README.md)。
```

原 README 中“第一阶段：Enron 邮件数据集（已弃用）”描述的是早期 9 题版本。应改名为“早期 Enron 9 题探索（已归档）”，避免与现在的 Enron Eval 50 混淆。

## systems/manifest.yaml记录格式

```yaml
private_dataset_systems:
  - id: moi-local
    role: system_under_test
    source: https://github.com/matrixorigin/matrixflow/tree/dev
    revision: 75018903911da5712cb0c6763267d42e430fcfcf
    deployment: local
  - id: wren-ai-local
    role: product_candidate
    source: https://github.com/Canner/WrenAI
    revision: 74bf59e1d8400988f5269048cdeed983e77dc20d
    deployment: local_docker
  - id: chat2db-membership-desktop
    role: product_candidate
    source: commercial_desktop
    revision: null
    deployment: local_desktop
```

Chat2DB 的准确版本号确认后，应替换 `revision: null`。

## 提交前检查

- `benchmark/questions/user/` 恰好 50 题；
- Golden SQL 恰好 50 条；
- 三个平台结果都能映射到正式题号；
- README 全部为中文说明；
- 不包含 `.env`、API Key、账号、密码、Cookie 或 Token；
- 不包含 `data/private/`；
- 不包含 `raw/` 大型事件日志；
- 所有 JSON、JSONL、YAML 和 Python 文件通过格式检查；
- Markdown 相对链接均存在。
