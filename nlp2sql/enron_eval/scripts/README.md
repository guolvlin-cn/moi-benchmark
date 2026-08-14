# 评测脚本

## adapters

负责从产品取得生成 SQL，并保存问题编号、SQL、错误和耗时：

- `run_moi.py`：通过本地 MOI 会话和 A2A 流式接口逐题运行；
- `run_wren.py`：通过本地 Wren `/api/v1/generate_sql` 接口逐题运行；
- `run_chat2db_desktop.py`：在 macOS 上驱动真实 Chat2DB Pro 桌面界面，每题新建独立对话，并从应用日志提取 SQL、端到端耗时、SQL 执行耗时、Token、模型和会话信息。

Chat2DB 为商业桌面客户端。自动采集方式属于“桌面界面自动化 + 本地日志解析”，不是 Chat2DB 官方批量 API。

## MOI自动采集

MOI基线使用未导入额外业务规则的知识库，并固定模型为 `qwen3.7-plus-2026-05-26`。正式运行50题、每题3个独立会话：

```bash
python3 scripts/adapters/run_moi.py \
  --knowledge-name '邮件问答-baseline-qwen37' \
  --model 'qwen3.7-plus-2026-05-26' \
  --repeats 3 \
  --output-root products/moi/results/automated \
  --run-id moi_qwen37_no_semantic_r3
```

脚本保存生成SQL、MatrixOne原生 `query_sql` 结果、最终答案引用的结果集、端到端和SQL执行耗时以及精确Token事件。无语义批次不要传入 `--semantic-rules`。每次运行的完整A2A事件保存在 `raw/` 并由Git忽略。

## Wren自动采集

先确认Wren已启动、当前项目已连接 `enron_eval`，并已将生成模型固定为 `qwen3.7-plus-2026-05-26`。

单题验证：

```bash
python3 scripts/adapters/run_wren.py \
  --case e01_sender_count \
  --repeats 1 \
  --run-id wren_qwen37_pilot
```

正式运行50题，每题创建3个独立线程：

```bash
python3 scripts/adapters/run_wren.py \
  --repeats 3 \
  --run-id wren_qwen37_3x
```

结果保存到 `products/wren/results/automated/<run-id>/`。脚本支持使用相同 `run-id` 续跑，不把产品失败自动重试为同一轮。当前Wren接口没有直接返回Token用量，相关字段记录为 `null`，后续只接受日志或用量回调得到的精确值。

## database

- `import_mysql.py`：执行 MySQL 8 Schema，并正确解析可能包含多行正文的六张 CSV；
- 数据库账号通过 `ENRON_DB_*` 环境变量提供，脚本不保存密码。

## evaluation

- `build_cases.py`：根据正式问题和 Golden SQL 生成 `cases_enron_50.yaml`；
- `evaluate_mysql.py`：兼容旧版单轮预测，执行 Golden SQL 与候选 SQL 的结果比较；
- `evaluate_repeated_mysql.py`：读取三个产品统一的多轮 `predictions.jsonl`，计算 Execution Accuracy、SQL Success Rate、Repeat Correct Rate、端到端延迟 P50/P95 和 Token 汇总。

## Chat2DB自动采集

运行前要求：

- 已启动 Chat2DB Pro 5.3.0；
- 当前 AI 对话已选择 `enron_eval/enron_eval`；
- 模型已选择本次评测规定的模型；
- 运行期间不要人工操作 Chat2DB；
- 执行脚本的终端已获得 macOS“辅助功能”权限。

先跑单题验证：

```bash
python3 scripts/adapters/run_chat2db_desktop.py \
  --case e01_sender_count \
  --repeats 1 \
  --run-id chat2db_pilot
```

正式运行50题，每题3个独立对话：

```bash
python3 scripts/adapters/run_chat2db_desktop.py \
  --repeats 3 \
  --run-id chat2db_qwen37_3x
```

脚本逐条写入结果，可以用同一个命令和 `run-id` 续跑。模型未生成SQL或SQL执行失败时，脚本记录产品失败并继续；若检测到新会话含历史消息、数据库不是 `enron_eval`、界面操作失败或等待超时，则立即停止，因为后续上下文已经不可信。正式评测不自动重试失败题。

## 三产品统一评分

首次使用先在 `enron_eval` 目录安装项目依赖：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Wren和Chat2DB的候选SQL都在统一MySQL快照中评分：

```bash
export ENRON_DB_HOST='::1'
export ENRON_DB_PORT='3306'
export ENRON_DB_USER='root'
export ENRON_DB_PASSWORD=''

.venv/bin/python scripts/evaluation/evaluate_repeated_mysql.py \
  --predictions products/chat2db/results/automated/chat2db_qwen37_3x/predictions.jsonl \
  --product chat2db \
  --run-id chat2db_qwen37_3x \
  --expected-repeats 3 \
  --output products/chat2db/results/automated/chat2db_qwen37_3x/evaluation.json
```

Wren只需替换 `--predictions`、`--product`、`--run-id` 和输出路径。

MOI不使用这条MySQL复跑结果作为主要Execution Accuracy。MOI的主要成绩比较其 `selected_native_results`（MatrixOne原生执行结果）与Golden标准结果；把MOI候选SQL放入MySQL执行只保留为跨引擎SQL逻辑诊断指标。对于MOI一次回答引用多个SQL结果集的题目，必须保留全部 `selected_native_results`，不能只取最后一条SQL。

所有脚本使用相对于项目根目录的路径，不依赖某台电脑上的绝对路径。
