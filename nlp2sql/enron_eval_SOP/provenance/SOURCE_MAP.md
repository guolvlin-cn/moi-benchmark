# 冻结结果来源映射

冻结日期：2026-08-13（Asia/Shanghai）

Git基线：`71c1d9cbd8fe91d2f5afbd4c106d373bbac39a2e`

工作分支：`codex/enron-eval`

冻结时工作区存在尚未提交的新评测文件，因此Git基线只用于说明旧版项目来源。`CHECKSUMS.sha256` 保存生成时的全目录清单；验证器强制保护其中的基准题集、数据、Schema、语义配置、评分代码、冻结清单和参考结果，允许README及后续SOP工具继续演进。

| 冻结目标 | 原始来源 |
|---|---|
| `reference_results/qwen37/chat2db/` | `products/chat2db/results/automated/chat2db_qwen37_20260813_3x/` |
| `reference_results/qwen37/wren/` | `products/wren/results/automated/wren_qwen37_20260812_rerun_r3/` |
| `reference_results/qwen37/moi_no_semantic/` | `products/moi/results/automated/moi_qwen37_no_semantic_20260811_r3/`，不含 `raw/` |
| `reference_results/qwen37/moi_with_semantic/` | `products/moi/results/automated/moi_qwen37_semantic_v2_20260812_r3/`，不含 `raw/` 和人工审核文件 |
| `semantic/` | `products/moi/semantic/moi_email_qa_semantic_config_v2.json` |
| `scoring_code/` | 当前 `scripts/evaluation/` 中用于本批成绩的三个评分脚本 |
| `runners/` | 当前 `scripts/adapters/` 中三个正式产品采集器的SOP快照 |
| `config/wren/` | `products/wren/deployment/` 的脱敏部署配置；模型已统一为Qwen 3.7固定快照 |
| `scripts/mysql_ipv4_proxy.py` | 当前 `scripts/database/mysql_ipv4_proxy.py` 的SOP快照 |
| `.agents/skills/run-enron-nl2sql-round/` | 基于本目录一轮50题SOP封装的项目级Codex Skill |

## Chat2DB三轮来源

- 第一轮：`chat2db_qwen37_20260812_r1`
- 第二轮：`chat2db_qwen37_20260812_r2`
- 第三轮：`chat2db_qwen37_20260813_r3`

第二轮的 `m10`、`m20`、`h03` 曾因采集超时或问题文本污染而重跑。正式选用记录在三轮合并文件中，被替换的原始记录保存在 `reference_results/qwen37/chat2db/audit/replaced_predictions.jsonl`。

## 未复制的大体积MOI原始证据

下列目录继续保留在冻结机器的原路径，不进入Git：

| 结果集 | 原始目录 | 文件数 | 实际字节数 | 目录内容摘要SHA256 |
|---|---|---:|---:|---|
| MOI无语义 | `products/moi/results/automated/moi_qwen37_no_semantic_20260811_r3/raw/` | 150 | 93,117,094 | `7ec8271937cf9be87e861f7e79522254f5faa2464f6e89287e8757d87b2f54ee` |
| MOI有语义 | `products/moi/results/automated/moi_qwen37_semantic_v2_20260812_r3/raw/` | 150 | 108,295,542 | `497e3fbe3cbed7c700e71de86972c70b35a9c0f4c82cc03866388996de13da30` |

目录内容摘要通过对目录内相对路径排序后的每个文件SHA256清单再次计算SHA256得到。

## 隐私说明

冻结结果不包含API Key、数据库密码、Cookie或登录Token。MOI结构化记录中形如 `task-<UUID>_llm_<序号>` 的值是模型调用追踪ID，不是API Key。知识库ID、会话ID和工作区UUID属于本地运行追踪信息，不能用于登录或调用服务。

## 六个公开CSV的来源

SOP中的 `data/raw/*.csv` 由2026-08-13时实际用于Chat2DB、Wren和Golden评分的本机MySQL `enron_eval` 权威快照只读导出。导出脚本为 `scripts/export_mysql_snapshot.py`，SQL `NULL` 统一写为字面值 `\N`，真正的空字符串保持为空字符串。

没有直接分发历史中间CSV，因为核对发现其中部分正文、X-To和来源字段曾经过MySQL反斜杠转义；直接使用中间文件无法保证跨机器还原出本次评测实际使用的数据值。规范CSV已经通过“导入临时空库—计算六表内容和Schema指纹—删除临时库”的完整回环测试。
