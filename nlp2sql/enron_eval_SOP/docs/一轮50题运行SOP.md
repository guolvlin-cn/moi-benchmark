# Chat2DB、Wren、MOI一轮50题运行SOP

## 1. 一轮的固定定义

如果通过Codex操作，可直接调用项目内的 `$run-enron-nl2sql-round` Skill；以下内容也是该Skill执行时遵循的正式口径。

一轮不是“成功生成50条SQL”，而是对冻结问题集提交50次独立请求：

- 问题文件固定为 `benchmark/questions/user/questions_enron_50_user_mix.txt`；
- 50个题号各出现一次，`repeat_index` 全部为 `1`；
- 每题必须建立新对话或新会话，不能继承上一题上下文；
- 生成模型固定为 `qwen3.7-plus-2026-05-26`；
- temperature 等产品设置沿用正式统一模型配置；
- 空SQL、SQL执行失败和产品报错均作为本轮真实失败保存，不能自动重试为成功后覆盖；
- 采集器自身中断可以使用同一 `run-id` 从缺失题目继续；
- 新产物只写入 `runs/<product>/<run-id>/`，不得写入或覆盖 `reference_results/`。

先完成一轮50题，才进入后续评分。需要正式复现三轮稳定性评测时，使用[三轮150次复现SOP](三轮150次复现SOP.md)，不要手工拼接三份结果。

## 2. 共用准备

在 `enron_eval_SOP/` 目录执行：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config/database.env.example .env
# 修改.env中的本机MySQL连接信息
source .env
.venv/bin/python scripts/verify_csv_files.py
.venv/bin/python scripts/verify_mysql_snapshot.py
```

如果数据库还没有建立，先运行：

```bash
.venv/bin/python scripts/setup_mysql.py
```

`verify_mysql_snapshot.py` 必须通过。它确认六张表的数据、NULL、字段顺序、类型和字段注释与冻结快照一致。

统一入口会在开始前确认问题数正好为50，并在结束后自动运行产物验证：

```bash
.venv/bin/python scripts/run_one_round.py --help
```

建议先加 `--dry-run` 查看最终命令，不会向产品提问。

## 3. Chat2DB一轮

### 3.1 产品内准备

1. 启动购买会员的 Chat2DB Pro 桌面客户端。
2. 连接本机 MySQL 的 `enron_eval`。如果本机真正的MySQL只监听IPv6，连接地址使用 `::1:3306`，不要误连被SSH转发占用的 `127.0.0.1:3306`。
3. 确认客户端能看到六张表、表注释和字段注释，并能执行简单查询。
4. 新建OpenAI兼容模型：模型 `qwen3.7-plus-2026-05-26`，Base URL `https://dashscope.aliyuncs.com/compatible-mode/v1`，Temperature `0`，Max Tokens `4096`，API Key填本机私有DashScope Key。
5. 在AI对话中选中该模型，并将数据库上下文固定为 `enron_eval/enron_eval`。
6. 给运行脚本所在的终端或Codex应用授予macOS“辅助功能”权限。

### 3.2 运行

运行期间脚本会接管 Chat2DB 窗口，不能同时手动操作、移动或缩放该窗口：

```bash
.venv/bin/python scripts/run_one_round.py \
  --product chat2db \
  --run-id chat2db_qwen37_round1
```

脚本每题点击“新建对话”，输入问题，再从本地应用日志提取最终SQL、执行状态、端到端耗时、SQL执行耗时、Token、模型和数据库上下文。日志中的模型、数据库或 `historySize=0` 任一不符合要求，采集立即停止。

界面位置变化、日志超时或上下文不可信时，先修复原因，再用同一命令和 `run-id` 继续。已经写入的题目会跳过。产品正常返回空SQL属于真实失败，不应手工重跑覆盖。

## 4. Wren一轮

### 4.1 部署与模型

本SOP使用本地 Docker 部署的 Canner/WrenAI。复制示例配置到Wren部署使用的私有目录：

```bash
cp config/wren/.env.example /path/to/wren/.env
cp config/wren/config.example.yaml /path/to/wren/config.yaml
```

在私有 `.env` 中填入 `DASHSCOPE_API_KEY`。`config.yaml` 必须包含：

```yaml
model: openai/qwen3.7-plus-2026-05-26
```

修改配置后应重建或重启Wren AI Service，不能只改文件而不让容器加载新配置。

### 4.2 数据库连接

Wren运行在Docker中，容器里的 `127.0.0.1` 不是Mac宿主机。通常连接 `host.docker.internal` 和数据库 `enron_eval`。

如果宿主机MySQL只在 `::1:3306` 正确监听，可另开终端启动只做网络转发的数据桥：

```bash
.venv/bin/python scripts/mysql_ipv4_proxy.py \
  --bind-host 127.0.0.1 --bind-port 13306 \
  --target-host ::1 --target-port 3306
```

此时Wren数据源端口填 `13306`。桥接进程必须在整轮运行期间保持开启。连接建立后确认Wren项目只关联 `enron_eval` 六张表；本轮不额外添加业务语义规则、问答对或指令。

### 4.3 运行

先确认 `http://localhost:3000` 和生成SQL接口可用，然后执行：

```bash
.venv/bin/python scripts/run_one_round.py \
  --product wren \
  --run-id wren_qwen37_round1 \
  --wren-config /path/to/wren/config.yaml
```

脚本为每题请求一个独立Wren线程，记录SQL、HTTP状态、端到端耗时和线程ID。Wren当前接口若不返回精确Token，用量字段必须为 `null`，不能估算。同一 `run-id` 可以补齐采集器中断后尚未提交的题目；已经记录的产品失败不会被自动替换。

## 5. MOI一轮

### 5.1 产品内准备

1. 启动本地 Matrixflow/MOI，确认前端、Backend、Catalog、Mowl、UC和MatrixOne相关服务可用。
2. 在MOI中建立或选择目标知识库。数据由MOI导入并存储于MatrixOne体系，不要求知识库直接连接评测MySQL。
3. 无语义基线使用未导入额外语义规则的知识库；有语义实验使用另一份已导入 `semantic/moi_email_qa_semantic_config_v2.json` 的知识库。两个条件不能混用同一运行编号。
4. MOI模型列表中必须存在 `qwen3.7-plus-2026-05-26`。
5. 复制产品环境模板，并只在本机填写账号信息：

```bash
cp config/products.env.example .products.env
source .products.env
```

### 5.2 无语义基线运行

```bash
.venv/bin/python scripts/run_one_round.py \
  --product moi \
  --run-id moi_qwen37_no_semantic_round1 \
  --knowledge-name '你的无语义知识库名称'
```

### 5.3 有语义配置运行

```bash
.venv/bin/python scripts/run_one_round.py \
  --product moi \
  --run-id moi_qwen37_semantic_v2_round1 \
  --knowledge-name '你的有语义知识库名称' \
  --semantic-rules 'moi_email_qa_semantic_config_v2'
```

MOI每题创建独立固定知识库会话。除了生成SQL，必须保存MatrixOne原生执行结果 `native_query_results`、最终答案引用的 `selected_native_results`、执行状态、自然语言回答、端到端耗时、SQL执行耗时和LLM Token事件。因为MOI和MySQL方言及执行环境不同，后续MOI主评分依赖这里保存的原生结果。

MOI基础设施故障达到阈值时脚本会停止。服务恢复后添加 `--resume` 并使用同一 `run-id`，只补齐未记录题目。

## 6. 完成判定与产物

每个产品成功结束后会自动生成并验证：

```text
runs/<product>/<run-id>/
├── run.json
├── predictions.jsonl
├── validation.json
└── run_summary.json          # Wren和MOI生成；Chat2DB核心汇总在run.json/validation.json
```

MOI还会生成 `raw/` 原始事件目录；它体积大且可能包含本地元数据，已被Git忽略。

可单独再次验证：

```bash
.venv/bin/python scripts/validate_one_round.py \
  --product chat2db --run-dir runs/chat2db/chat2db_qwen37_round1

.venv/bin/python scripts/validate_one_round.py \
  --product wren --run-dir runs/wren/wren_qwen37_round1 \
  --wren-config /path/to/wren/config.yaml

.venv/bin/python scripts/validate_one_round.py \
  --product moi --run-dir runs/moi/moi_qwen37_no_semantic_round1
```

`validation.json` 显示 `validation: passed` 才代表一轮采集完整。它验证50题覆盖、唯一轮次、问题文本、统一模型、基本指标字段和MOI原生结果字段；SQL是否与Golden结果一致属于下一阶段评分，不在本SOP中计算。

## 7. 公平性与安全红线

- 三个产品使用同一问题文本和同一固定模型版本。
- Chat2DB与Wren读取同一份已校验MySQL快照；MOI读取同源CSV构建的MatrixOne知识库。
- 产品失败必须如实保留，采集器故障与产品失败分开处理。
- 不把Golden SQL、Golden执行结果或其他产品答案注入产品上下文。
- 不提交API Key、产品账号密码、Cookie、CSRF、数据库密码、商业软件安装包或本地日志。
- 不手工修改 `predictions.jsonl`；如确需纠正采集污染，必须保留旧记录和替换原因，另开审计文件。
