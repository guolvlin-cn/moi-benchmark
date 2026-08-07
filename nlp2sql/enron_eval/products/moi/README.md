# MOI评测说明

本目录保存 Enron 50 题 NL2SQL 评测中与 MOI 直接相关的配置和结果，不包含 MOI/Matrixflow 的完整产品源码。

## 产品源码与评测部署

- 源码仓库：<https://github.com/matrixorigin/matrixflow>
- 评测分支：[`dev`](https://github.com/matrixorigin/matrixflow/tree/dev)
- 评测时本地源码 commit：`75018903911da5712cb0c6763267d42e430fcfcf`
- commit 短编号：`750189039`
- commit 时间：`2026-08-05 12:19:50 +0800`
- commit 说明：`fix(local-deploy): isolate multi-profile AI Studio cookies by host (#14627)`
- 部署方式：macOS 本地部署
- MOI 地址：`http://localhost:18002`
- 工作区：`local_project`
- 知识库：`邮件问答`，知识库 ID 为 `2`
- 数据库：`enron_eval`
- SQL 生成模型：`deepseek-v4-flash`

这里的 commit 是 Git 对某一次源码快照生成的唯一编号。`dev` 分支会随着后续开发不断变化，而 commit `75018903911da5712cb0c6763267d42e430fcfcf` 永远指向本次评测所依据的源码版本，因此可以用于版本追踪和复现。

本项目不会复制完整 Matrixflow 仓库，也不会把它作为 Git Submodule。评测使用的是一套已经运行的 MOI 部署，因此通过“源码仓库地址 + 分支 + commit + 运行配置 + 评测结果”建立关联，比把产品源码混入评测仓库更清晰。

记录版本信息时，本地 Matrixflow 工作区不是完全干净的状态：

- `scripts/uc-sso-v2/start-backend-local.sh` 存在未提交修改；
- 工作区存在本地 DDL 和输出文件；
- 这些本地文件没有复制到本评测项目中。

因此，commit 表示本地源码的基础版本，但当前部署还可能受到未提交本地修改的影响。这个信息需要在评测可复现性说明中保留。

## 目录内容

```text
products/moi/
├── README.md
├── product.yaml
├── semantic/
│   └── moi_email_qa_semantic_config.json
└── results/
    ├── baseline_no_semantic/
    │   ├── run.json
    │   ├── predictions.jsonl
    │   ├── generated_sql_50.sql
    │   ├── evaluation.json
    │   └── evaluation.txt
    ├── with_semantic/
    │   ├── run.json
    │   ├── predictions.jsonl
    │   ├── generated_sql_50.sql
    │   └── evaluation.json
    └── baseline_failure_analysis.md
```

MOI 批量运行适配器位于：[run_moi.py](../../scripts/adapters/run_moi.py)。

## 正式评测批次

当前保留两个正式批次：

| 批次 | 语义配置 | MOI 内部成功生成并执行 | Golden 结果评测 |
|---|---|---:|---:|
| `baseline_no_semantic` | 未启用 | 29/50 | 35/50（70%） |
| `with_semantic` | 已启用 | 45/50 | 41/50（82%） |

“MOI 内部成功生成并执行”和“Golden 结果评测”是两个不同指标：

- MOI 内部状态记录 SQL 在产品内部是否成功生成和执行；
- Golden 结果评测会取得 MOI 暴露出来的候选 SQL，在统一评测数据库中执行，然后与 Golden SQL 的结果比较。

因此，MOI 可能因为内部 SQL 包装器或 MatrixOne 解析器报错而把某题记为失败，但候选 SQL 仍然被捕获，并且可能在统一 MySQL 评测环境中正常执行。

启用语义配置的批次使用：[moi_email_qa_semantic_config.json](semantic/moi_email_qa_semantic_config.json)。

该配置主要提供：

- 六张表和字段的语义解释；
- 人名、邮箱和归档目录的映射；
- 邮件与收件人的计数粒度；
- 空值、文件夹和文本搜索规则；
- RFC 邮件日期解析规则；
- 回复主题和历史邮件头的处理方式；
- 排名、百分比和结果列要求；
- `from`、`to` 等保留字及 SQL 方言规则。

语义配置不包含 50 道题的 Golden SQL 答案。

## 重新运行MOI评测

首先按照关联的 Matrixflow `dev` 部署说明启动 MOI。然后通过环境变量提供本地账号，不能把真实账号和密码写入仓库：

```bash
export MOI_EMAIL='your-local-account@example.com'
export MOI_PASSWORD='your-local-password'

python3 scripts/adapters/run_moi.py \
  --output-root products/moi/results \
  --run-id your_run_id \
  --semantic-rules your_semantic_config_label
```

运行脚本会为每道题创建独立的固定知识库会话，防止不同题目之间发生上下文污染，并记录：

- 用户问题；
- MOI 生成的 SQL；
- 自然语言回答；
- 生成状态和错误；
- 端到端耗时；
- 会话、任务、模型和知识库信息。

完整 A2A 原始事件适合在本机排查问题，但文件很大，也可能包含本地环境元数据，因此不放入面向 GitHub 的精简评测目录。

## 安全说明

本目录不保存：

- MOI 管理员邮箱和密码；
- 数据库账号和密码；
- Cookie、CSRF Token 或登录会话；
- 模型 API Key；
- Matrixflow 完整源码副本；
- Enron 原始 CSV 数据。

所有敏感配置都必须通过环境变量或本机私有 `.env` 文件提供。
