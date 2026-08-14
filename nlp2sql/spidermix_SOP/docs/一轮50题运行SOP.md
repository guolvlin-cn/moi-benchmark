# Spider Mix50三产品一轮50题运行SOP

## 1. 固定口径

- 模型：`qwen3.7-plus-2026-05-26`；
- 题目：`benchmark/questions/questions_mix50.tsv`，共50题；
- 数据：`pets_1`、`concert_singer`、`car_1`，合计13表960行；
- 会话：每题独立新会话，每题只运行一次；
- 语义：只使用原始表结构和主外键，不注入额外业务规则或Golden SQL；
- Chat2DB与Wren使用同一MySQL快照；MOI使用同源CSV导入MatrixOne并保存原生执行结果。

## 2. 建立并校验MySQL

在 `nlp2sql/spidermix_SOP/` 中执行：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config/database.env.example .env
# 编辑.env后加载
source .env
.venv/bin/python scripts/verify_csv_snapshot.py
.venv/bin/python scripts/setup_mysql.py
.venv/bin/python scripts/verify_mysql_snapshot.py
```

如果三个数据库已经存在，导入脚本会停止，防止覆盖。只有确认要重建时才使用 `scripts/setup_mysql.py --rebuild`。

## 3. 准备三个产品

### Chat2DB

建立一个MySQL连接，确保账号能够访问这三个数据库。正式结果按数据库分三批运行；每批开始前人工把Chat2DB当前库切到对应数据库。库映射见 `benchmark/questions/case_databases.tsv`。在Chat2DB中选中固定模型Qwen3.7后依次执行：

```bash
.venv/bin/python runners/run_chat2db_global.py \
  --run-id chat2db_spidermix_car_1_round1 \
  --database-only car_1 --fixed-database car_1 --repeats 1 \
  --new-chat-shortcut

# 人工切到concert_singer后执行
.venv/bin/python runners/run_chat2db_global.py \
  --run-id chat2db_spidermix_concert_singer_round1 \
  --database-only concert_singer --fixed-database concert_singer --repeats 1 \
  --new-chat-shortcut

# 人工切到pets_1后执行
.venv/bin/python runners/run_chat2db_global.py \
  --run-id chat2db_spidermix_pets_1_round1 \
  --database-only pets_1 --fixed-database pets_1 --repeats 1 \
  --new-chat-shortcut
```

该采集器控制桌面界面并读取本地Chat2DB日志，运行期间不要操作Chat2DB窗口。三批完成后合并：

```bash
.venv/bin/python scripts/merge_chat2db_database_runs.py \
  --input-run runs/chat2db/chat2db_spidermix_car_1_round1 \
  --input-run runs/chat2db/chat2db_spidermix_concert_singer_round1 \
  --input-run runs/chat2db/chat2db_spidermix_pets_1_round1 \
  --output-dir runs/chat2db/chat2db_spidermix_qwen37_round1
```

### Wren AI

建立一个包含13个模型的项目。物理表名使用完整库名，例如 `pets_1.Pets`；只建立原始库内关系。确认Wren生成模型为固定Qwen3.7后运行：

```bash
.venv/bin/python runners/run_wren.py \
  --run-id wren_spidermix_qwen37_round1 \
  --repeats 1
```

### MOI

在MatrixOne执行 `database/schema/moi_matrixone_schema.sql`，再执行 `database/data/moi_matrixone_data.sql`，创建包含13张表且无额外语义规则的知识库。配置本机MOI登录环境变量后运行：

```bash
export MOI_EMAIL='你的本地管理员邮箱'
export MOI_PASSWORD='你的本地管理员密码'
.venv/bin/python runners/run_moi.py \
  --run-id moi_spidermix_qwen37_round1 \
  --knowledge-name 'Spider-Mix50-three-databases-qwen37' \
  --model 'qwen3.7-plus-2026-05-26' \
  --repeats 1
```

MOI产物必须同时保留生成SQL和MatrixOne原生执行结果；不能只把SQL拿到MySQL重新执行后代替产品端到端结果。

## 4. 评分

Chat2DB和Wren均在冻结MySQL快照执行候选SQL与Golden SQL：

```bash
.venv/bin/python evaluation/evaluate_wren_mysql.py \
  --product wren \
  --run-id wren_spidermix_qwen37_round1 \
  --predictions runs/wren/wren_spidermix_qwen37_round1/predictions.jsonl \
  --questions benchmark/questions/questions_mix50_with_metadata.txt \
  --gold benchmark/golden/dev_gold_mix50.sql \
  --output runs/wren/wren_spidermix_qwen37_round1/evaluation.json
```

Chat2DB使用同一命令，将 `--product`、`--run-id`、输入和输出目录改为Chat2DB。MOI使用原生结果评分：

```bash
.venv/bin/python evaluation/evaluate_moi_native.py \
  --run-id moi_spidermix_qwen37_round1 \
  --predictions runs/moi/moi_spidermix_qwen37_round1/predictions.jsonl \
  --questions benchmark/questions/questions_mix50_with_metadata.txt \
  --gold benchmark/golden/dev_gold_mix50.sql \
  --output runs/moi/moi_spidermix_qwen37_round1/evaluation.json \
  --summary runs/moi/moi_spidermix_qwen37_round1/evaluation_summary.md
```

正式报告至少保留Execution Accuracy、SQL Success Rate、端到端延时P50/P95和可获取的Token；单轮不计算Repeat Correct Rate。
