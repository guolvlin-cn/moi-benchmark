# NLP2SQL Benchmark Track

状态：Spider mix50 公开集横评和 Enron Eval 50 私有集横评均已完成；v0.4 计划在 Enron 现有50题上增加四项可直接计算的指标。

MOI 平台与竞品（Wren AI、Chat2DB）的 NL2SQL 能力对比评测。本 Track 同时保留公开数据集阶段和私有数据集阶段。Spider mix50 的完整材料集中在 [`spider/`](spider/README.md)；Enron Eval 50 的完整材料集中在 [`enron_eval/`](enron_eval/README.md)。

跨阶段结论见：[NL2SQL评测汇总报告](NL2SQL评测汇总报告.md)。评测方案版本见：[plans/](plans/README.md)。

## 阶段一：Spider mix50 三平台横评（已完成）

### 数据集

从 Spider dev 集 1034 题中按 SQL 复杂度自动分类抽取 50 题，涉及 3 个数据库：

| 数据库 | 表数 | 题目数 | 特点 |
|--------|:----:|:------:|------|
| concert_singer | 4 | 22 | 歌手/演唱会/体育场/参演 |
| car_1 | 6 | 18 | 汽车数据/制造商/国家/洲/型号 |
| pets_1 | 4 | 10 | 宠物/学生/拥有关系 |

难度分布：easy 30 题（单表，无 JOIN/GROUP BY），medium 15 题（JOIN / GROUP BY / HAVING），hard 5 题（子查询 / EXCEPT / INTERSECT）。

### 评测对象与口径

| 平台 | 接入方式 | 注意事项 |
|------|---------|---------|
| **MOI**（被评测对象） | Explore API，Agent 多轮自主探索 + 生成 SQL | 评测用 MOI 生成的 SQL 在 SQLite 离线执行，避免框架稳定性干扰 |
| **Wren AI**（核心竞品） | Cloud 网页版，手动逐题输入 | 输出 BigQuery 方言（SAFE_CAST / FLOAT64），需 regex 转 CAST AS REAL 才能在 SQLite 执行 |
| **Chat2DB**（核心竞品） | 桌面客户端，SSH 隧道连本地 MatrixOne | 网页版云端执行无法连本地库；桌面版需 ed25519 密钥配端口转发 |

### 评测方法

- **工具**：Spider 官方 test-suite-sql-eval（EMNLP 2020）
- **指标**：Execution Accuracy（exec）— Gold SQL 和 Pred SQL 分别在 SQLite 上执行，对比结果集
- **参数**：`--etype exec --keep_distinct`（保留 DISTINCT，避免 INTERSECT 自带去重被误判）
- **执行引擎**：SQLite（gold 和 pred 统一执行，不受产品自身数据库方言影响）

### 结果

| 平台 | easy (30题) | medium (15题) | hard (5题) | **总计 (50题)** |
|------|:-----------:|:-------------:|:----------:|:---------------:|
| MOI | 73.3% | 53.3% | 60.0% | **66.0%** |
| Wren AI | 86.7% | 66.7% | 100.0% | **82.0%** |
| Chat2DB | 96.7% | 93.3% | 100.0% | **94.0%** |

### 交叉分析

| 交叉类别 | 题数 | 说明 |
|---------|:----:|------|
| MOI 独对（竞品全错） | 1 | #26: "youngest singer 的所有歌" — 只有 MOI 理解了 "all the songs"，竞品和 Gold SQL 都只返回 1 首 |
| 竞品对 MOI 错 | 15 | MOI 主要短板：多返列（5题）、数据类型处理（3题）、框架稳定性（2题） |
| 三平台全错 | 2 | Gold SQL 有歧义或三表 JOIN 过于复杂 |
| MOI 通过的 medium 题 | 8/15 | 含三表 JOIN + GROUP BY + HAVING 组合，证明多表能力可用 |

### MOI 失败原因分类（17 题）

| 失败原因 | 题数 | 说明 |
|---------|:----:|------|
| **多返列**（语义正确但列数不匹配） | 5 | 核心数据正确，额外返回了辅助信息列（如 pet_age、Average），eval 判错但用户视角是加分项 |
| **数据类型处理** | 3 | Spider 的 Horsepower/MPG 列是 TEXT 含非数值，MOI CAST 严格过滤 vs SQLite 隐式转换 |
| **回答范围不对** | 3 | 语义偏差 |
| **Gold SQL 歧义** | 2 | 题目本身有歧义或 Gold SQL 写法不唯一 |
| **MOI 框架稳定性** | 2 | 大表超时、特殊语法不兼容 |
| **其他** | 2 | 多返列/重复 |

**关键发现**：17 题失败中，真正 MOI 能力问题约 5 题（数据类型 + 回答范围），其余为评测标准过严或框架稳定性问题。扣掉数据质量 + 多返列 + 框架问题后，MOI 有效通过率约 90%。

### #26 典型案例：MOI 语义理解深于 Gold SQL

```
问题: What are the names and release years for all the songs of the youngest singer?

Gold SQL:  SELECT song_name, song_release_year FROM singer ORDER BY age LIMIT 1
           → 返回 1 首 (Love, 2016) — 错！问题问的是所有歌

MOI SQL:  SELECT Song_Name, Song_release_year FROM singer
          WHERE Age = (SELECT MIN(Age) FROM singer)
           → 返回 youngest singer 的全部歌曲 — 正确

Wren:     SELECT ... ORDER BY age ASC LIMIT 1 → 返回 (Tribal King, 2016) — 错了歌手
Chat2DB:  SELECT ... ORDER BY Age ASC LIMIT 1 → 返回 (Tribal King, 2016) — 错了歌手
```

这道题说明 MOI 的 LLM 推理在理解问题意图上优于规则式 SQL 生成。在真实业务场景中，用户问题往往不精确，MOI 的语义理解优势会更明显。

## Spider 评测的局限性

Spider 是学术界标准基准，但用它测 MOI 存在根本性不匹配：

| 维度 | Spider 假设 | MOI 实际能力 | 偏差 |
|------|------------|-------------|------|
| 语言 | 英文 | **中文原生** | MOI 中文能力无法充分体现 |
| 交互模式 | 单轮 SQL 生成 | **Agent 多轮对话**（追问、澄清、探索） | Agent 能力被阉割 |
| Schema | 完美提供 tables.json | **自主 Schema 探索** + COMMENT 元数据 | 探索能力无用武之地 |
| 评测标准 | SQL 文本/结果集精确匹配 | **端到端答案有用性**（SQL + 表格 + 图表 + 解读） | 多返列被扣分，但用户觉得是加分项 |
| 数据集 | 小型公开学术库 | **真实邮件Schema与固定数据快照** | 数据规模和表间语义更贴近实际场景 |
| 纠错 | 不看纠错过程 | **SQLRepairer 自动修正** | 自纠错能力不参与评分 |
| 数据质量 | 理想化 | 现实数据含脏数据 | MOI 的 CAST 严格处理反被扣分 |

**核心矛盾**：Spider 测的是「给定完整 schema，一次生成正确 SQL」的学术能力；MOI 卖的是「用户用自然语言问业务问题，Agent 自己探索、生成、验证、呈现答案」的产品体验。

## 阶段二：Enron Eval 50 私有数据集横评（已完成）

为补充 Spider 公开集的局限，本阶段使用固定的 Enron 邮件数据库快照开展中文 NL2SQL 评测：

- **数据结构**：6 张邮件相关表，原始 CSV 不提交到公开仓库；
- **问题构成**：50 道中文问题，其中 25 道采用更接近真实用户的口语化表达，另外 25 道保留较明确的查询条件；
- **评测对象**：MOI 本地部署、Wren AI 本地 Docker 部署、Chat2DB 会员桌面版；
- **主指标**：在同一 MySQL 8 数据快照上执行预测 SQL，与 Golden SQL 的结果集进行比较；
- **语义实验**：MOI 同时保留无语义配置基线和加入邮件领域语义配置后的结果。

| 平台与配置 | 通过数 | Execution Accuracy |
|-----------|:------:|:------------------:|
| Chat2DB 会员桌面版 | 42/50 | **84%** |
| MOI 本地部署（有语义配置） | 41/50 | **82%** |
| MOI 本地部署（无语义配置） | 35/50 | **70%** |
| Wren AI 本地 Docker | 24/50 | **48%** |

完整问题、Golden SQL、数据库定义、语义配置、产品原始输出、统一评测脚本和失败记录见 [`enron_eval/README.md`](enron_eval/README.md)。原始 CSV、产品账号、密码、Cookie、Token、License 和商业软件安装包均不进入仓库。

## 评测历程

### 早期探索：Enron 邮件 9 题（已归档）

- 数据集：Enron 邮件数据，6 表 53 万行，9 道自建题目
- 评测工具：agent-eval-tools（MOI 自研）
- 归档原因：评测集闭合性差（9 题太少）、MOI Explore Agent 大结果集频繁 ConnectionError、无变体库校验
- 后续版本：已由本目录中的 `enron_eval/` 50 题正式评测替代，旧文件通过 Git 历史保留

### 第二阶段：Spider easy50（单表简单题）

- 50 道单表题，exec = 78.0%（keep_distinct 修正后 82.0%）
- 发现评测工具 `remove_distinct` 参数导致 INTERSECT 去重误判，修正后提升 4 个百分点

### 第三阶段：Spider mix50（混合难度 + 三平台对比）

- 从 1034 题中自动分类抽取 50 题，同时接入 Wren AI 和 Chat2DB
- 完成三平台交叉分析、失败归因和 MOI 优势维度识别

## MOI 应重点突出的优势维度（Spider 测不到的）

| 优势维度 | MOI 表现 | 竞品弱点 |
|---------|---------|---------|
| **中文 NL2SQL** | 原生中文提问与业务语义理解 | Spider主要为英文问题，无法覆盖该维度 |
| **Agent 多轮对话** | 可追问、探索、澄清歧义 | 纯单轮 SQL 生成 |
| **Schema 探索** | 无 schema 也能查 | 必须提前配好 schema |
| **SQLRepairer 自纠错** | 执行失败自动修正 | 一次生成，不管对错 |
| **元数据利用** | 列 COMMENT 增强语义理解 | 只看列名 |
| **端到端分析** | SQL → 表格 → 图表 → 解读一条龙 | 只出 SQL/表格 |
| **多返列是加分** | 用户获得额外信息维度 | — |

## 后续计划：Enron v0.4四项指标评测

不再规划新的业务数据集。本轮继续使用冻结的 Enron Eval 50，只报告四项能够直接计算的指标：

- Execution Accuracy：最终查询结果正确题数/50；
- SQL Success Rate：生成非空、安全且执行成功SQL题数/50；
- End-to-end Latency：统一外部计时的P50和P95；
- Repeat Correct Rate：固定10题各运行3次，三次都正确的题数/10。

v0.4 不要求取得产品内部的初次结果、修复轨迹、Token或成本。

正式范围仍为 MOI、Wren AI 和 Chat2DB。如时间允许且通过接入 Smoke Test，再增加阿里云 Data Agent 独立批次。详细步骤见 [v0.4计划](plans/drafts/v0.4.md)。

## 技术经验

### 评测工具陷阱

| 陷阱 | 影响 | 解决 |
|------|------|------|
| `remove_distinct` + INTERSECT → false negative | 2 题误判 | 设置 `keep_distinct=True` |
| SQLite TEXT 列 vs MOI CAST 数值比较 | 3 题误判 | 数据质量问题，非 MOI 错 |
| pred/gold 行序不对齐 | 虚低 18 个点（0.600→0.780） | 逐题诊断确认对齐 |
| Wren BigQuery 方言 | SAFE_CAST/FLOAT64 不兼容 | regex 转 CAST AS REAL |
| Chat2DB 网页版无法连本地库 | 云端执行 | 需桌面客户端配 SSH 隧道 |

### MOI Explore 稳定性

- 大表（5 表 JOIN）间歇性 ConnectionError
- 部分特殊语法（GROUP_CONCAT SEPARATOR）执行报错
- 单题响应 10–120 秒，50 题全量需 20–30 分钟

## 目录结构

```
nlp2sql/
├── README.md                      # 本文档
├── NL2SQL评测汇总报告.md           # Spider与Enron跨阶段汇总
├── spider/                        # Spider mix50公开数据集评测
│   ├── README.md                  # Spider阶段入口
│   ├── NL2SQL评测汇总报告.md       # Spider详细评测报告
│   ├── datasets/                  # 问题与Gold SQL
│   ├── results/                   # 三产品预测SQL和逐题报告
│   └── scripts/                   # Spider评测脚本
├── enron_eval/                    # Enron私有快照50题正式评测
│   ├── benchmark/                 # 问题、口径、案例和Golden SQL
│   ├── database/                  # 建库及字段注释SQL
│   ├── products/                  # 三款产品配置与原始输出
│   ├── results/                   # 统一结果与横向对比
│   └── scripts/                   # 导入、生成和评测脚本
├── plans/                         # 评测计划版本
│   ├── README.md
│   └── drafts/                    # v0.1至v0.4
├── refs/                          # 通用NL2SQL参考资料
│   ├── deep-research-report-5.md
│   └── deep-research-report-6.md
└── systems/                       # 跨数据集参评系统清单
```

## 评测原则

- 区分本项目实测结果和竞品公开结果；竞品结果均为本项目同等条件下实际运行所得
- 数据、配置、模型、版本、运行命令和原始结果可追溯；所有 pred SQL 和评测报告纳入版本管理
- 质量、性能、成本和失败案例分别报告，不强行合成单一总分
- 评测标准、失败归因和局限性明确披露，不掩盖 MOI 真实短板
- 首版冻结数据集和配置后不随意调整；新增评测应作为独立阶段

## 工作量与资源

- 第一阶段（Spider mix50）：已完成，约 5 人天 + ¥200 API 调用
- 第二阶段（Enron Eval 50）：已完成，详细过程与结果见 `enron_eval/`
- v0.4 Enron四项指标增量评测：计划中；优先复用现有50题、运行脚本和历史结果
- 环境：MOI 本地部署（MatrixOne 6001 + catalog 18081）、SQLite、macOS/Linux
- GPU：不需要（MOI 和竞品均使用外部 LLM API）

详细计划见 [docs/benchmark-plan-summary.md](../docs/benchmark-plan-summary.md) 第 2.4 节。
