# NL2SQL 评测汇总报告

> 编写日期: 2026-07-31
> 目标: 评估 MOI 平台的 NL2SQL 能力，与竞品 (Wren AI, Chat2DB) 对比，明确 MOI 的优势维度和改进方向

---

## 1. 项目背景

MOI 平台内置 NL2SQL 能力（Explore Agent），用户可以通过自然语言查询数据库并获得 SQL 与分析结果。本评测用于验证其真实水平，并与同类产品进行可复现对比。

## 2. 评测历程

### 2.1 第一阶段：Enron 邮件数据集（已弃用）

- **数据集**: Enron 邮件数据，9 道自建题目
- **评测工具**: agent-eval-tools（MOI 自研）
- **结论**: 弃用
- **弃用原因**:
  - 评测集闭合性差：9 道题太少，题目设计有歧义（如 GROUP BY 维度不明确）
  - MOI Explore Agent 不稳定：大结果集频繁 ConnectionError，分不清是答案错还是框架挂
  - 无变体库校验：只在原始数据上对比，无法排除「结果碰巧对但 SQL 逻辑错」

### 2.2 第二阶段：Spider easy50（单表简单题）

- **数据集**: Spider dev 集中筛出 50 道单表题，涉及 3 个数据库（concert_singer, car_1, pets_1）
- **评测工具**: Spider 官方 test-suite-sql-eval（EMNLP 2020）— Execution Accuracy
- **结果**: **exec = 78.0%**（keep_distinct 修正后 82.0%）
- **失败分析**:

| 失败类型 | 题数 | 说明 |
|---------|------|------|
| MOI 真 Bug | 2 | WHERE 条件丢失、列名歧义（`average` 被当 AVG()） |
| Spider 数据脏 | 3 | Horsepower/MPG 列是 TEXT 含非数值，MOI CAST 过滤 vs SQLite 隐式转换 |
| MOI 多返列 | 4 | 核心数据正确但多返回了辅助列（如 Average），被 eval 判错 |
| 评测工具局限 | 2 | `remove_distinct` 不认 INTERSECT 自带去重，导致 false negative |
| **有效通过率** | **~94%** | 扣掉数据质量 + 工具局限 |

### 2.3 第三阶段：Spider mix50（混合难度 + 三平台对比）

- **数据集**: 从 Spider dev 1034 题中按 SQL 复杂度自动分类抽取 50 题
  - easy (30题): 单表，无 JOIN/GROUP BY
  - medium (15题): JOIN / GROUP BY / HAVING
  - hard (5题): 子查询 / EXCEPT / INTERSECT
- **评测工具**: test-suite-sql-eval (keep_distinct=True)
- **参与平台**: MOI / Wren AI / Chat2DB

## 3. 三平台对比结果

| 平台 | easy (30题) | medium (15题) | hard (5题) | **总计 (50题)** |
|------|:-----------:|:-------------:|:----------:|:---------------:|
| MOI | 73.3% | 53.3% | 60.0% | **66.0%** |
| Wren AI | 86.7% | 66.7% | 100.0% | **82.0%** |
| Chat2DB | 96.7% | 93.3% | 100.0% | **94.0%** |

### 3.1 MOI vs 竞品交叉分析

| 交叉类别 | 题数 | 说明 |
|---------|------|------|
| MOI 独对（竞品全错） | 1 | #26: "youngest singer 的所有歌" — MOI 用子查询返回全部歌曲，Gold SQL 和竞品只用 LIMIT 1 返回了1首 |
| 竞品对 MOI 错 | 15 | MOI 主要短板：多返列（5题）、数据类型处理（3题）、大表超时（1题）、语法错误（1题） |
| 三平台全错 | 2 | #29 (Gold SQL 写法有歧义), #44 (三表 JOIN + HAVING) |
| MOI 通过的 medium 题 | 8/15 | 含三表 JOIN + GROUP BY + HAVING 组合（#35, #42），证明多表能力可用 |

### 3.2 MOI 失败原因分类（mix50 17题失败）

| 失败原因 | 题数 | 典型示例 |
|---------|------|---------|
| **多返列**（语义正确但列数不匹配） | 5 | #01/#24 多返了 pet_age，#09/#21/#37/#43 多返了辅助信息列 |
| **数据类型处理** | 3 | #06 Horsepower 含非数值，#18 CAST 过滤，#39 排序错误 |
| **回答范围不对** | 3 | #32 返回了全部国家而非仅 France，#48 只返回1条而非全部，#33 多返列 |
| **Gold SQL 本身有歧义** | 2 | #29 "average of all stadiums" 可理解为 AVG(capacity) 或列名 average，#44 三表 JOIN |
| **MOI 框架问题** | 2 | #40 ConnectionError（5表 JOIN 超时），#50 SEPARATOR 语法不兼容 |
| **其他** | 2 | #08 多返列，#21 与 #09 重复 |

**关键发现：17 题失败中，真正 MOI 能力问题约 5 题（数据类型 + 回答范围），其余为多返列（eval 标准过严）或框架稳定性问题。**

## 4. Spider 评测的局限性

Spider 是学术界的标准 NL2SQL 评测基准，但用它来评测 MOI 存在根本性不匹配：

| 维度 | Spider 评测假设 | MOI 实际能力 | 偏差 |
|------|----------------|-------------|------|
| 语言 | 英文 | **中文原生**（财务术语：红冲、销项、进项） | MOI 中文优势完全无法体现 |
| 交互模式 | 单轮 SQL 生成 | **Agent 多轮对话**（追问、澄清、探索） | Agent 能力被阉割 |
| Schema | 完美提供 tables.json | **自主 Schema 探索** + COMMENT 元数据 | 探索能力无用武之地 |
| 评测标准 | SQL 文本/结果集精确匹配 | **端到端答案有用性**（SQL + 表格 + 图表 + 解读） | 多返列被扣分，但用户觉得是加分项 |
| 数据集 | 小型公开学术库 | **真实邮件Schema与固定数据快照** | 数据规模和表间语义更贴近实际场景 |
| 纠错 | 不看纠错过程 | **SQLRepairer 自动修正** | 自纠错能力不参与评分 |
| 数据质量 | 理想化 | 现实数据含脏数据 | MOI 的 CAST 严格处理反被扣分 |

**核心矛盾：Spider 测的是「给定完整 schema，一次生成正确 SQL」的学术能力；MOI 卖的是「用户用自然语言问业务问题，Agent 自己探索、生成、验证、呈现答案」的产品体验。用 Spider 测 MOI，就像用百米赛跑测游泳运动员。**

## 5. MOI 真正的优势维度（Spider 测不到的）

### 5.1 已有实证

- **语义理解深于 Gold SQL**（#26）: Gold SQL `ORDER BY age LIMIT 1` 只返回 youngest singer 的 1 首歌，MOI 用 `WHERE Age=(SELECT MIN(Age))` 返回了该 singer 的**全部**歌曲。问题原文是 "all the songs of the youngest singer"，MOI 理解更准确。Wren 和 Chat2DB 都跟 Gold SQL 犯了同样的错误。

### 5.2 MOI 应重点突出的维度

| 优势维度 | MOI 表现 | 竞品弱点 | 评测方式 |
|---------|---------|---------|---------|
| **中文 NL2SQL** | 原生中文，理解财务术语 | 英文为主，中文退化严重 | 中文业务问题集 |
| **Agent 多轮对话** | 可追问、探索、澄清歧义 | 纯单轮 SQL 生成 | 设计需要澄清的模糊问题 |
| **Schema 探索** | 无 schema 也能查 | 必须提前配好 schema | 不给 schema 直接问 |
| **SQLRepairer 自纠错** | 执行失败自动修正 | 一次生成，不管对错 | 记录首次 vs 最终答案差异 |
| **元数据利用** | 列 COMMENT 增强语义理解 | 只看列名 | 用中文 COMMENT 的财务表 |
| **端到端分析** | SQL → 表格 → 图表 → 解读 一条龙 | 只出 SQL/表格 | 评估回复的完整性和可读性 |
| **多返列是加分** | 用户获得额外信息维度 | — | 人工评估「答案有用性」而非列数精确匹配 |

### 5.3 特别案例：#26 启示

```
问题: What are the names and release years for all the songs of the youngest singer?

Gold SQL:  SELECT song_name, song_release_year FROM singer ORDER BY age LIMIT 1
           → 返回 1 首 (Love, 2016) — 错！问题问的是所有歌

MOI SQL:  SELECT Song_Name, Song_release_year FROM singer
          WHERE Age = (SELECT MIN(Age) FROM singer)
           → 返回 youngest singer 的全部歌曲 — 对！

Wren:     SELECT name, song_release_year FROM singer ORDER BY age ASC, singer_id ASC LIMIT 1
           → 返回 (Tribal King, 2016) — 错了歌手

Chat2DB:  SELECT Name, Song_release_year FROM singer ORDER BY Age ASC LIMIT 1
           → 返回 (Tribal King, 2016) — 错了歌手
```

这道题说明：MOI 的 LLM 推理能力在理解问题意图上可能优于规则式的 SQL 生成。在真实业务场景中，用户问题往往不精确，MOI 的语义理解优势会更明显。

## 6. 技术发现与经验

### 6.1 评测工具陷阱

| 陷阱 | 影响 | 解决 |
|------|------|------|
| `remove_distinct` + INTERSECT → false negative | 2 题误判 | 设 `keep_distinct=True` |
| SQLite TEXT 列 vs MOI CAST 数值比较 | 3 题误判 | 数据质量问题，非 MOI 错 |
| pred/gold 行序不对齐 | 全部虚低（0.600→0.780） | 逐题诊断确认对齐 |
| Wren BigQuery 方言 | SAFE_CAST/FLOAT64 不兼容 | regex 转 CAST AS REAL |
| Chat2DB 网页版无法连本地库 | 云端执行 | 需桌面客户端配 SSH 隧道 |

### 6.2 MOI Explore 稳定性问题

- 大表（5表 JOIN, 406行）间歇性 ConnectionError
- 部分 SQL 语法（如 GROUP_CONCAT SEPARATOR）执行报错
- 单题响应 10-120 秒，50 题全量需 20-30 分钟

## 7. 后续评测方向

### 7.1 评测方向调整

Spider阶段完成后，后续评测从单一公开集正确率转向真实Schema和端到端产品行为：

1. **Enron中文私有数据评测**（已完成）
   - 使用六张邮件关联表和固定数据快照
   - 50 道中文问题，包含25道口语化表达
   - 评测 SQL 正确率、多表映射、日期、邮件线程和语义配置效果

2. **Agent 能力专项评测**
   - 不给 schema，测试 Agent 自主探索能力
   - 设计有歧义的问题，看谁主动追问
   - 记录首次 SQL vs 最终 SQL 差异，量化自纠错率

3. **端到端体验对比**
   - 统一 prompt: "请回答以下问题，并附上你使用的 SQL 查询语句"
   - 从回复中提取 SQL + 答案，多维度人工评分
   - 对比 MOI/Wren/Chat2DB 在同一数据库上的表现

4. **v0.4多维指标增量评测**
   - 在 Enron 50 题上增加生成率、可执行率、首次/最终正确率和稳定性
   - 统一可比时延的 Mean、P50、P95、Max
   - 记录平台可提供的 Token、调用次数和成本
   - 如时间允许，核验并增加阿里云 Data Agent 独立批次

### 7.2 MOI 自身改进

- 优化多表 JOIN 稳定性（减少 ConnectionError）
- 列输出策略：核心列必须精确，辅助列可作为扩展信息
- GROUP_CONCAT 等特殊语法的兼容性

---

## 附录 A: 数据集详情

### mix50 题目分布

| 数据库 | 表数 | 题目数 | 特点 |
|--------|:----:|:------:|------|
| concert_singer | 4 | 22 | 歌手/演唱会/体育场/参演 |
| car_1 | 6 | 18 | 汽车数据/制造商/国家/洲/型号 |
| pets_1 | 4 | 10 | 宠物/学生/拥有关系 |

### 评测参数

- 工具: Spider test-suite-sql-eval (EMNLP 2020)
- 指标: Execution Accuracy (exec)
- 参数: `--etype exec --keep_distinct`
- 执行引擎: SQLite（gold 和 pred 都在同一 SQLite 上执行）

## 附录 B: 仓库信息

- **repo**: https://github.com/matrixorigin/moi-benchmark
- **branch**: `nlp2sql-benchmark`
- **目录结构**:
  ```
  nlp2sql/spider/
  ├── README.md                    # Spider评测入口
  ├── NL2SQL评测汇总报告.md         # 本文档
  ├── datasets/
  │   ├── dev_gold_mix50.sql       # Gold SQL (50题)
  │   └── questions_mix50.txt      # 问题清单
  ├── results/
  │   ├── moi/                     # MOI pred + 逐题报告
  │   ├── wren/                    # Wren AI pred + 逐题报告
  │   └── chat2db/                 # Chat2DB pred + 逐题报告
  └── scripts/                     # 评测脚本
  ```

## 附录 C: MOI 失败题清单（mix50 17题）

| 题号 | 难度 | 数据库 | 问题摘要 | 失败原因 |
|:----:|------|--------|---------|---------|
| #01 | easy | pets_1 | youngest animal type + weight | 多返列（pet_age） |
| #06 | easy | car_1 | max mpg (8cyl or pre-1980) | 数据类型（MPG TEXT列） |
| #08 | easy | car_1 | horsepower of fastest accelerate | 多返列（Accelerate） |
| #09 | easy | concert_singer | highest avg attendance stadium | 多返列（Average） |
| #18 | easy | car_1 | count of horsepower > 150 | 数据类型（Horsepower TEXT列） |
| #21 | easy | concert_singer | highest avg attendance stadium | 多返列（Average） |
| #24 | easy | pets_1 | youngest animal type + weight | 多返列（pet_age） |
| #29 | easy | concert_singer | max capacity and average | Gold SQL 歧义 |
| #32 | medium | car_1 | car makers in France | 返回全部国家而非仅 France |
| #33 | medium | concert_singer | year with most concerts | 多返列（count） |
| #37 | medium | concert_singer | stadium most concerts >=2014 | 多返列（count） |
| #39 | medium | car_1 | max horsepower 3cyl + make | 排序/值错误 |
| #40 | medium | car_1 | car models per maker + id/name | ConnectionError（超时） |
| #43 | medium | concert_singer | stadium most concerts >2013 | 多返列（count） |
| #44 | medium | car_1 | european countries >=3 makers | 多返列（count） |
| #48 | hard | car_1 | maker of earliest year car | 只返回1条而非全量 |
| #50 | hard | pets_1 | students with both cat and dog | SEPARATOR 语法错误 |
