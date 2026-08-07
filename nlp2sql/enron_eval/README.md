# Enron私有数据集NL2SQL评测

本目录是 `moi-benchmark/nlp2sql` Track 的私有数据集评测子项目，目标路径为：

```text
nlp2sql/enron_eval/
```

项目使用同一份 Enron 邮件数据库、同一组 50 道中文问题和同一套 Golden SQL，对 MOI、Wren AI 和 Chat2DB 的最终 NL2SQL 产品能力进行比较。

与 `nlp2sql/` 中既有的 Spider mix50 公开数据集评测不同，本项目强调中文自然语言、真实邮件 Schema、字段注释、产品语义配置和本地部署环境。原始六张 CSV 属于私有评测数据，不提交 GitHub。

## 正式评测集

- 数据库：`enron_eval`
- SQL 方言：MySQL 8
- 表数量：6 张
- 字段数量：32 个
- 问题数量：50 题
- 难度：Easy 20、Medium 20、Hard 10
- 表达方式：25 道口语化问题、25 道原始详细问题
- 主指标：Execution Accuracy，即候选 SQL 与 Golden SQL 的执行结果是否等价

50 道正式问题位于：[questions_enron_50_user_mix.txt](benchmark/questions/user/questions_enron_50_user_mix.txt)。

详细题意、统一评测口径和 Golden SQL 属于评分资产，不应发送给被测产品：

- [详细题意](benchmark/questions/spec/questions_enron_50_detailed_spec.txt)
- [统一评测口径](benchmark/questions/spec/evaluation_conventions.md)
- [Golden SQL](benchmark/golden/questions_enron_50_golden.sql)

## 参评产品

| 产品或批次 | 使用方式 | 执行结果正确 | 通过率 |
|---|---|---:|---:|
| Chat2DB 会员桌面版 | 商业客户端、本地连接数据库 | 42/50 | 84% |
| MOI，启用语义配置 | Matrixflow `dev` 本地部署 | 41/50 | 82% |
| MOI，未启用语义配置 | Matrixflow `dev` 本地部署 | 35/50 | 70% |
| Wren AI | Canner/WrenAI 本地 Docker 部署 | 24/50 | 48% |

这里是三个产品、四个评测批次。MOI 的“启用语义配置”和“未启用语义配置”是同一产品的两个独立批次，不能当作两个产品。

产品来源、版本、部署方式和不可统一变量见：[参评产品说明](products/README.md)。

## 目录结构

```text
enron_eval/
├── README.md                       # 项目总说明
├── requirements.txt                # 评测脚本依赖
├── benchmark/                      # 50题、Golden SQL和评测口径
│   ├── benchmark.json
│   ├── cases/
│   ├── golden/
│   ├── metadata/
│   └── questions/
├── database/                       # MySQL建库建表和字段注释迁移
│   ├── schema/
│   └── migrations/
├── data/                           # 私有数据准备说明和快照行数
│   ├── README.md
│   ├── snapshot/
│   └── private/                    # 本机私有文件，Git忽略
├── products/                       # 产品版本、配置、SQL和运行记录
│   ├── README.md
│   ├── moi/
│   ├── wren/
│   └── chat2db/
├── results/                        # 三产品统一评分结果和横向报告
├── scripts/
│   ├── adapters/                   # MOI、Wren采集脚本
│   ├── database/                   # 数据导入脚本
│   └── evaluation/                 # cases构建和统一执行评分
├── config/                         # 不含密码的配置模板
└── docs/                           # 评测设计、格式和集成说明
```

## 数据准备

Git 仓库不包含六张原始 CSV。请将私有 CSV 放到 `data/private/`，支持以下两种文件名：

```text
enron_email.csv
enron_emailinfo.csv
enron_emailorig.csv
enron_emailto.csv
enron_emailxto.csv
enron_source.csv
```

或者保留 MOI 导出时的 `表名__kb_*.csv` 文件名。导入脚本会在每张表只有一个匹配文件时自动识别。

预期行数见：[expected_counts.json](data/snapshot/expected_counts.json)。

## 快速开始

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

通过环境变量提供数据库连接，真实密码不能写入仓库：

```bash
export ENRON_DB_HOST=127.0.0.1
export ENRON_DB_PORT=3306
export ENRON_DB_USER=root
export ENRON_DB_PASSWORD='your-private-password'
export ENRON_DB_NAME=enron_eval
```

建库并导入六张 CSV：

```bash
python3 scripts/database/import_mysql.py
```

重新生成统一 cases YAML：

```bash
python3 scripts/evaluation/build_cases.py
```

对一个产品的候选 SQL 进行统一执行评分：

```bash
python3 scripts/evaluation/evaluate_mysql.py \
  --product moi_with_semantic \
  --run-id 2026-08-07_moi_with_semantic_01 \
  --predictions products/moi/results/with_semantic/predictions.jsonl \
  --output results/moi_with_semantic_evaluation.regenerated.json
```

MOI 和 Wren 的采集方法分别见：

- [MOI评测说明](products/moi/README.md)
- [Wren AI评测说明](products/wren/README.md)
- [Chat2DB评测说明](products/chat2db/README.md)

## 公平性与结果解释

三个产品统一使用相同数据快照、问题文本、Golden SQL、只读数据库权限和单题重试规则。以下变量无法完全统一，必须随结果一起披露：

- 产品使用的底层模型可能不同；
- 产品的 Schema 检索和自动纠错能力不同；
- MOI 和 Wren 为本地部署，Chat2DB 为商业桌面客户端；
- 各产品支持的语义配置形式不同；
- Chat2DB 的内部模型调用和重试过程可能无法完整观测。

因此，本项目衡量的是相同任务条件下的最终产品表现，不把差异解释为单纯的大模型能力差异。

## 与公开Spider评测的关系

`nlp2sql/` 顶层既有的 `datasets/`、`results/` 和 `scripts/` 记录 Spider mix50 公开数据集评测，应继续作为历史公开基线保留。

本目录是新的私有数据集阶段，采用自包含结构，不与 Spider 文件混放。早期 `nlp2sql/enron/` 仅包含旧版 SQLite 方案和未完成结果，合入时应由本目录替代或在 Git 历史中保留，不应同时保留两个当前 Enron 入口。

详细合入步骤见：[nlp2sql集成说明](docs/nlp2sql-integration.md)。

## 安全边界

禁止提交：

- 六张原始 CSV 和其他私有数据文件；
- MOI、Wren、Chat2DB 的真实账号和密码；
- 数据库密码和模型 API Key；
- Cookie、Token、License、激活凭证和会员信息；
- MOI/Wren 完整产品源码副本；
- 大型产品内部事件日志和本地容器数据卷。

提交 Git 前必须执行敏感信息和大文件检查。
