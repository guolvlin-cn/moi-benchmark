# Enron私有数据集NL2SQL评测

本项目使用一份自建的 Enron 邮件数据库、50道中文问题和对应 Golden SQL，评测 MOI、Wren AI 与 Chat2DB 的产品级 NL2SQL 能力。

## 当前正式入口

本目录保存形成 Enron 基线时的原始项目材料和历史结果。新用户和跨机器复现统一从与本目录并列的 [`../enron_eval_SOP/`](../enron_eval_SOP/) 开始。该目录自包含：

- 六个规范CSV及数据指纹；
- 带完整表、字段注释的MySQL Schema；
- 50题、Golden SQL和评测口径；
- Chat2DB、Wren、MOI采集器；
- 一轮50题与三轮150次统一运行入口；
- MySQL评分和MOI原生MatrixOne结果评分入口；
- 四组统一模型冻结参考结果；
- 脱敏配置模板、来源清单和SHA256校验。

快速入口：

- [SOP总览](../enron_eval_SOP/README.md)
- [目录与文件说明](../enron_eval_SOP/docs/目录与文件说明.md)
- [一轮50题运行SOP](../enron_eval_SOP/docs/一轮50题运行SOP.md)
- [三轮150次端到端复现SOP](../enron_eval_SOP/docs/三轮150次复现SOP.md)
- [冻结参考结果说明](../enron_eval_SOP/reference_results/README.md)
- [统一模型评测报告](docs/enron-qwen37-evaluation-report.md)

## 正式评测口径

| 项目 | 固定值 |
|---|---|
| 数据集 | `enron_eval_v1` |
| 数据库 | 6张表、32个字段、10,401封邮件 |
| 问题 | 50题：Easy 20、Medium 20、Hard 10 |
| 表达 | 25道明确语义题、25道用户口语化题 |
| 重复 | 每题3次，共150次请求 |
| 模型 | `qwen3.7-plus-2026-05-26` |
| 核心指标 | Execution Accuracy、SQL Success Rate、End-to-end Latency、Repeat Correct Rate |

Chat2DB和Wren连接同一份MySQL `enron_eval`。MOI使用同源CSV建立MatrixOne知识库，并保存产品原生执行结果，再与MySQL Golden结果比较。

## 已冻结的统一模型自动结果

| 产品条件 | Execution Accuracy | SQL Success Rate | Repeat Correct Rate |
|---|---:|---:|---:|
| Chat2DB | 77/150（51.33%） | 150/150（100%） | 21/50（42%） |
| Wren AI（二次完整重跑） | 49/150（32.67%） | 114/150（76%） | 12/50（24%） |
| MOI无语义配置 | 85/150（56.67%） | 150/150（100%） | 26/50（52%） |
| MOI语义配置v2 | 99/150（66%） | 146/150（97.33%） | 29/50（58%） |

以上是严格自动评分，不包含人工审核修正。人工审核是附加证据，不能覆盖原始预测和自动分数。

## 目录分工

```text
enron_eval/
├── ../enron_eval_SOP/    # 与本目录并列的当前跨机器复现入口
├── docs/                 # 项目报告和历史研究说明
├── benchmark/            # SOP建立前的同源题集副本
├── database/             # SOP建立前的Schema和迁移文件
├── products/             # 开发过程运行记录和产品说明
├── results/              # 开发过程汇总与人工审核结果
├── runs/                 # 本机调试运行记录
└── scripts/              # SOP建立前的采集和评分脚本
```

本目录全部内容是形成当前基线时的开发过程和历史证据。它们暂时保留以便追溯，但不再作为新用户的运行入口，也不应与并列SOP中的冻结参考结果混合修改。

## 最短复现路径

```bash
cd nlp2sql/enron_eval_SOP
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config/database.env.example .env
# 填写本机MySQL连接后：
source .env
.venv/bin/python scripts/verify_csv_files.py
.venv/bin/python scripts/setup_mysql.py
.venv/bin/python scripts/verify_mysql_snapshot.py
.venv/bin/python verify_frozen_results.py
```

产品运行和评分命令见[三轮150次端到端复现SOP](../enron_eval_SOP/docs/三轮150次复现SOP.md)。

## 安全与数据边界

- “私有数据集”表示本项目自建评测集，不是Spider官方题集；当前六个固定CSV按项目既定方案直接随Git分发。
- Enron邮件内容可能包含真实姓名、邮箱和历史通信文本。公开前应由仓库维护者完成数据许可与隐私合规确认。
- 禁止提交API Key、数据库密码、产品账号、Cookie、登录Token、License或会员凭证。
- 不提交MOI/Wren完整源码副本、商业软件安装包、大型产品日志和本地容器数据卷。
- Golden SQL、详细口径和其他产品答案不得注入被测产品上下文。
