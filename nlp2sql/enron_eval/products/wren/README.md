# Wren AI评测说明

本次评测使用 [Canner/WrenAI](https://github.com/Canner/WrenAI) 的本地 Docker 部署，不使用 Wren Cloud。

## 评测环境

- 上游源码：<https://github.com/Canner/WrenAI>
- 关联 commit：`74bf59e1d8400988f5269048cdeed983e77dc20d`
- Wren Product：`0.29.1`
- Wren Engine：`0.22.0`
- Wren AI Service：`0.29.0`
- Ibis Server：`0.22.0`
- Wren UI：`0.32.2`
- Wren Bootstrap：`0.1.5`
- 运行方式：本地 Docker Compose
- 本地页面：`http://localhost:3000`
- SQL 生成接口：`http://localhost:3000/api/v1/generate_sql`
- 历史批次生成模型：`qwen-plus-2025-12-01`
- 新统一批次生成模型：`qwen3.7-plus-2026-05-26`
- Embedding 模型：`text-embedding-v4`
- 数据库：`enron_eval`
- 项目语言：简体中文

完整 WrenAI 源码约 1.4 GB，不复制到本评测仓库，也不作为 Git Submodule。项目只保存上游地址、commit、固定镜像版本、脱敏配置、批量运行脚本和正式评测结果。

## 目录

```text
products/wren/
├── README.md
├── product.yaml
├── deployment/
│   ├── docker-compose.yaml
│   ├── config.example.yaml
│   └── .env.example
└── results/
    └── 2026-08-06_local/
        ├── predictions.jsonl
        ├── predictions.csv
        ├── generated_sql_50.sql
        └── run_summary.json
```

批量运行脚本位于：[run_wren.py](../../scripts/adapters/run_wren.py)。

## 正式运行结果

2026-08-06 本地正式批次共提交 50 道题：

- 成功取得 SQL：47 题；
- 未生成 SQL：3 题；
- 平均生成耗时：19.992 秒；
- 最短生成耗时：11.149 秒；
- 最长生成耗时：34.733 秒。

SQL 是否生成成功不等于最终结果正确。最终准确率以统一评测数据库执行候选 SQL 并与 Golden SQL 比较后的报告为准。

## 部署

将 `.env.example` 复制为本机私有 `.env`，填写 DashScope API Key，然后启动：

```bash
cd products/wren/deployment
docker compose --env-file .env up -d
```

Wren 容器连接宿主机数据库时应使用 `host.docker.internal`，不能在仓库中写入真实数据库密码。

## 新统一批次运行

1. 在Wren私有配置中把生成模型改为 `openai/qwen3.7-plus-2026-05-26`，并保持 `temperature: 0`、`max_tokens: 4096`；Embedding继续使用 `text-embedding-v4`。
2. 启动Wren后访问 `http://localhost:3000`，确认当前项目连接 `host.docker.internal:3306/enron_eval`，包含六张表和五条关系。
3. 先运行单题Smoke Test。脚本每次请求都会创建独立Wren线程：

```bash
cd nlp2sql/enron_eval
python3 scripts/adapters/run_wren.py \
  --case e01_sender_count \
  --repeats 1 \
  --run-id wren_qwen37_pilot
```

4. 检查单题结果中的模型、SQL、耗时和 `thread_id`，并在MySQL中确认SQL可以执行且结果正确。
5. 正式运行50题、每题3次，共150个独立请求：

```bash
python3 scripts/adapters/run_wren.py \
  --repeats 3 \
  --run-id wren_qwen37_3x
```

6. 使用统一评分器计算正确率、SQL成功率、三次重复正确率和时延：

```bash
export ENRON_DB_HOST='::1'
export ENRON_DB_PORT='3306'
export ENRON_DB_USER='root'
export ENRON_DB_PASSWORD=''

.venv/bin/python scripts/evaluation/evaluate_repeated_mysql.py \
  --predictions products/wren/results/automated/wren_qwen37_3x/predictions.jsonl \
  --product wren \
  --run-id wren_qwen37_3x \
  --expected-repeats 3 \
  --output products/wren/results/automated/wren_qwen37_3x/evaluation.json
```

运行文件会逐条落盘；中断后使用相同 `run-id` 可从未完成的题目继续。Wren接口当前返回SQL和请求标识，但不直接返回模型Token用量，因此Token字段必须暂记为 `null`，待验证AI Service日志或接入精确用量采集后再补，不能用估算值代替。

## 安全边界

仓库不保存真实 `.env`、DashScope API Key、数据库密码、容器数据卷、用户 UUID、完整上游源码或本地登录信息。
