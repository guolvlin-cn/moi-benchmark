# Spider Mix50 统一模型评测 SOP

本目录是 Spider Mix50 在统一模型和规范化数据库条件下的可复现入口，与历史目录 `../spider/`、私有数据集目录 `../enron_eval/` 和 `../enron_eval_SOP/` 并列。三个产品统一使用 `qwen3.7-plus-2026-05-26`。Chat2DB 与 Wren 读取同一份本地 MySQL 快照；MOI 使用同源 CSV 在 MatrixOne/MOI 中建立对应数据。

`../spider/` 保存早期未统一模型、接入方式和数据库环境的历史评测；本目录不覆盖或改写这些旧结果。

## 与历史评测的核心区别

| 项目 | 历史 `spider/` | 本 `spidermix_SOP/` |
|---|---|---|
| 生成模型 | 三产品未完全统一 | 三产品固定为同一Qwen3.7快照 |
| 数据库 | SQLite、MatrixOne和临时连接方式并存 | 冻结同源三库13表；MySQL和MatrixOne数据逐表对齐 |
| 输入 | 问题和Golden散落在历史目录 | 50题、库映射、难度、Golden SQL全部自包含 |
| 运行结果 | 早期横评证据 | 每产品一轮50题，保留SQL、耗时、可获取Token和执行结果 |
| 复现 | 依赖原机器过程 | 提供建库、校验、采集、评分和冻结验证入口 |

## 冻结范围

| 数据库 | 表数 | 数据行数 | Mix50 题数 |
|---|---:|---:|---:|
| `pets_1` | 3 | 40 | 17 |
| `concert_singer` | 4 | 31 | 17 |
| `car_1` | 6 | 889 | 16 |
| 合计 | 13 | 960 | 50 |

文件说明：

```text
spidermix_SOP/
├── README.md
├── requirements.txt                # 复现脚本Python依赖
├── config/database.env.example     # 三库MySQL连接变量模板
├── benchmark/
│   ├── questions/                  # 50题、难度和所属数据库
│   └── golden/dev_gold_mix50.sql   # 50条Golden SQL
├── database/
│   ├── csv/                         # 三个数据库的13个冻结CSV
│   ├── data/moi_matrixone_data.sql  # 13张表的MatrixOne INSERT数据
│   ├── schema/mysql_schema.sql      # 本地MySQL精确建库建表语句
│   ├── schema/moi_matrixone_schema.sql
│   │                                # MOI/MatrixOne建库建表语句
│   └── snapshot.json                # 行数、MySQL CHECKSUM和CSV SHA256
├── runners/                        # Chat2DB、Wren、MOI采集器
├── evaluation/                     # MySQL和MOI原生结果评分脚本
├── scripts/                        # 建库、快照校验和结果维护工具
├── runs/                           # 已完成的一轮Qwen3.7结果
├── reports/                        # 三产品统一模型报告
├── provenance/                     # 正式批次清单和产品版本
├── verify_sop.py                   # 验证三组正式结果与冻结指标
└── docs/
    ├── 一轮50题运行SOP.md           # 从数据库到评分的完整操作
    └── 多数据库产品运行策略.md       # 三产品多库上下文口径
```

## 数据一致性说明

冻结基准以 2026-08-13 本机 MySQL 实际数据为准。旧来源文件 `car_1/model_list.csv` 原有一行 `14,10,hi`，但父表 `car_makers` 不存在 `Id=10`，因此本机 MySQL 在外键检查下没有导入该行。冻结 CSV 已删除这条无效记录，使 MySQL 与 MOI 都固定为 `model_list=35` 行。

## 建库

推荐用Git内CSV自动建库：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config/database.env.example .env
# 修改为自己的MySQL连接信息后加载
source .env
.venv/bin/python scripts/verify_csv_snapshot.py
.venv/bin/python scripts/setup_mysql.py
.venv/bin/python scripts/verify_mysql_snapshot.py
```

导入脚本默认保护已有的 `pets_1`、`concert_singer`、`car_1`；只有明确传入 `--rebuild` 才会删除并重建这三个固定数据库。完整流程见[一轮50题运行SOP](docs/一轮50题运行SOP.md)。

在 MOI/MatrixOne 中执行 [moi_matrixone_schema.sql](database/schema/moi_matrixone_schema.sql)，然后按数据库分别导入相应 CSV。Wren一个项目、MOI一个知识库均可看到同一组13张表；Chat2DB使用同一个MySQL连接，但正式采集时按题目所属数据库分三批切换当前库。每道题仍只涉及其中一个数据库。

如果已经建好空表，直接在MOI SQL编辑器执行 [moi_matrixone_data.sql](database/data/moi_matrixone_data.sql)。该文件包含960行冻结数据以及13张表的导入后行数校验语句。只能对空表执行一次，避免重复主键。

## 语义信息口径

本次是公开 Spider 数据集复测，不额外加入业务描述或人工语义规则。表名、列名、类型、主键和外键属于原始 Schema 信息，可以提供给三个产品；额外表注释、问答样例和规则注入均不使用。

## 评测报告

统一使用 `qwen3.7-plus-2026-05-26` 完成一轮 Mix50 后的三产品结果见：

- [Spider Mix50 三产品统一模型评测报告](reports/Spider_Mix50_三产品统一模型评测报告.md)

运行 `python3 verify_sop.py` 可以确认三组正式结果均为50题、模型均为固定Qwen3.7且核心指标没有变化。产品版本依据见[PRODUCT_VERSIONS.md](provenance/PRODUCT_VERSIONS.md)。
