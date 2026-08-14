# Enron NL2SQL 统一模型评测 SOP

本目录与历史目录 `../enron_eval/`、`../spider/` 及公开集新版入口 `../spidermix_SOP/` 并列，只整理采用统一模型 `qwen3.7-plus-2026-05-26` 和规范化数据库快照产生的新一轮评测资产。旧的非统一模型结果继续保留在原项目目录和Git历史中，本目录不移动、不覆盖、也不修改它们。

## 与历史评测的核心区别

| 项目 | 历史 `enron_eval/` | 本 `enron_eval_SOP/` |
|---|---|---|
| 生成模型 | 含不同模型和调试批次 | 三产品固定为同一Qwen3.7快照 |
| 数据库 | 本机过程文件较多 | 六个CSV、带注释Schema、行数和数据指纹全部冻结 |
| 运行次数 | 单轮、试跑和重跑并存 | 每题3轮，共150次，轮次定义统一 |
| MOI评分 | 曾只把SQL拿到MySQL执行 | 保存MatrixOne原生结果，与MySQL Golden结果对比 |
| 复现入口 | 多个开发脚本 | 建库、预检、一轮/三轮采集、验证和评分入口统一 |

当前目录已完成有效结果冻结、CSV分发与MySQL回环校验、三个产品的一轮和三轮运行入口、产物验证入口以及统一评分入口。项目级运行Skill当前负责一轮50题采集；评分Skill将在下一阶段基于现有评分入口封装。

## 已冻结的四组结果

| 结果集 | 运行编号 | 记录数 | 自动准确率 |
|---|---|---:|---:|
| Chat2DB | `chat2db_qwen37_20260813_3x` | 150 | 77/150（51.33%） |
| Wren（二次完整重跑） | `wren_qwen37_20260812_rerun_r3` | 150 | 49/150（32.67%） |
| MOI（无语义配置） | `moi_qwen37_no_semantic_20260811_r3` | 150 | 85/150（56.67%） |
| MOI（有语义配置） | `moi_qwen37_semantic_v2_20260812_r3` | 150 | 99/150（66.00%） |

这些成绩均为自动评分原始结果，不包含人工审核修正。

## 目录

```text
enron_eval_SOP/
├── README.md
├── benchmark/                 # 50题、Golden SQL和统一口径
├── data/snapshot/             # 数据快照预期统计
├── database/schema/           # MySQL建表结构
├── runners/                   # 三个产品的原始采集适配器快照
├── scripts/                   # 建库、一轮/三轮运行、验证和评分入口
├── config/                    # 数据库、产品与Wren脱敏配置模板
├── docs/一轮50题运行SOP.md    # 三产品逐步运行说明
├── docs/三轮150次复现SOP.md    # 从Git数据到三轮评分的端到端说明
├── docs/目录与文件说明.md       # 每个目录、脚本和冻结边界的解释
├── .agents/skills/            # Git随项目分发的Codex评测Skill
├── semantic/                  # MOI语义配置v2
├── scoring_code/              # 产生本批成绩的评分代码快照
├── reference_results/qwen37/  # 四组只读冻结结果
├── provenance/                # 来源、Git基线和校验值
└── verify_frozen_results.py   # 冻结结果完整性验证
```

正式产品版本见：[统一模型评测产品版本](provenance/PRODUCT_VERSIONS.md)。其中MOI精确到Matrixflow分支与Git commit，避免只用含糊的“local”描述。

## 冻结原则

- `reference_results/` 是只读参考结果，不作为下一次运行的输出目录。
- 新评测必须写入后续建立的 `runs/`，验证完成后才能另存为新的参考结果。
- 不静默覆盖失败或重跑记录。Chat2DB第二轮被替换的三条旧记录保存在 `chat2db/audit/`。
- MOI的结构化结果保留生成SQL、MatrixOne原生执行结果、耗时和Token，足以复核自动评分。
- MOI约198MB的原始HTTP响应保留在原本机目录，不复制到Git；其目录摘要哈希记录在冻结清单中。
- 不提交API Key、密码、Cookie、登录Token、商业软件安装包或数据库凭据。

## 验证

在本目录执行：

```bash
python3 verify_frozen_results.py
```

验证内容包括：

- 四组结果是否各有150条；
- 是否覆盖50题且每题正好3轮；
- 模型名称、问题文本和轮次是否一致；
- 自动评分核心指标是否与冻结清单一致；
- 冻结基准、数据、Schema、语义配置、评分代码和参考结果的SHA256是否发生变化；SOP说明与运行工具可以继续演进。

## 当前完成度与边界

已经完成：

1. Enron六个CSV的Git分发、MySQL导入、Schema注释和数据指纹校验；
2. Chat2DB、Wren、MOI的一轮50题统一运行和产物验证；
3. 三个产品的50题×3轮运行和150条产物验证；
4. Chat2DB/Wren的MySQL评分与MOI原生MatrixOne结果评分；
5. 四组统一模型参考结果冻结和SHA256回归验证；
6. 一轮50题项目级运行Skill。

尚未封装为Skill的部分只有统一评分和人工审核；对应Python评分入口和人工标注文件已经存在，可以继续在此基础上整理。商业产品安装、产品账号、本地部署和API Key不会随Git分发，复现者需要自行准备。

## 从Git数据建立MySQL

六个规范CSV已直接放在 `data/raw/`。建议使用项目虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config/database.env.example .env
# 修改为自己的MySQL连接信息后加载
source .env
.venv/bin/python scripts/verify_csv_files.py
.venv/bin/python scripts/setup_mysql.py
.venv/bin/python scripts/verify_mysql_snapshot.py
```

不清楚某个文件是否属于输入、运行产物或冻结证据时，查看：[目录与文件说明](docs/目录与文件说明.md)。

导入脚本默认保护已有同名数据库；只有明确使用 `--rebuild` 才会删除并重建。六个CSV已经通过隔离临时库的完整回环导入测试。

## 运行三个产品的一轮50题

完整步骤见：[Chat2DB、Wren、MOI一轮50题运行SOP](docs/一轮50题运行SOP.md)。

统一入口为：

```bash
.venv/bin/python scripts/run_one_round.py --help
```

一轮固定为50题各提交一次，每题使用独立新会话，模型固定为 `qwen3.7-plus-2026-05-26`。产物写入 `runs/<product>/<run-id>/`，并由 `scripts/validate_one_round.py` 自动检查完整性；冻结参考结果不会被覆盖。

## 运行并评分三轮150次

需要复现正式稳定性指标时，使用：[Enron 50题×3轮端到端复现SOP](docs/三轮150次复现SOP.md)。

统一入口：

```bash
.venv/bin/python scripts/run_three_rounds.py --help
.venv/bin/python scripts/validate_three_rounds.py --help
.venv/bin/python scripts/score_three_rounds.py --help
```

三个产品均生成统一的 `predictions.jsonl`。Chat2DB和Wren候选SQL在冻结MySQL快照评分；MOI使用保存的MatrixOne原生执行结果与MySQL Golden结果比较。

## 使用运行Skill

项目内已提供 `$run-enron-nl2sql-round`：

```text
使用 $run-enron-nl2sql-round，让Chat2DB运行Enron第一轮50题，run-id为chat2db_qwen37_round1。
```

该Skill会按产品执行只读预检、展开正式命令、运行或续跑50题、监控进度并验证产物。它不计算Golden准确率，也不进行人工审核。
