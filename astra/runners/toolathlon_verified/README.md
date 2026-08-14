# Toolathlon-Verified product adapters

本目录实现最小单任务生命周期、公共单产品槽位 Orchestrator，以及 Astra、Hermes 两个薄 Adapter。Adapter 只负责把同一份 public bundle、同一 task-scoped MCP Gateway 和同一模型代理接入产品；不修复产品动作、不读取 evaluator/ground truth。`lifecycle.py` 负责 fresh 任务容器、preprocess、Gateway、现场 `tools/list`、evaluator、cleanup 和严格工件封存。

冻结边界：

- Agent 时钟从 Prompt 实际交给产品后开始；产品/Gateway 启动、preprocess、evaluator、reset 和 cleanup 使用独立基础设施安全超时。
- 本地模型代理把所有产品侧请求固定到官方 `https://api.deepseek.com` 的 `deepseek-v4-flash`，删除产品侧 Thinking/effort 值，并显式发送和审计 `thinking={"type":"enabled"}`、`reasoning_effort="max"`（`source=benchmark_override`）；同时发送并记录 `temperature=0`，但 Thinking 下 temperature 不生效。官方默认 `enabled/high` 只作为文档背景保留，不是本实验的实际 effort。
- Astra 与 Hermes 分别固定读取 `TOOLATHLON_DEEPSEEK_ASTRA_API_KEY`、`TOOLATHLON_DEEPSEEK_HERMES_API_KEY`。Orchestrator 在槽位开始前要求两者都存在且值不同，旧的共享 `DEEPSEEK_API_KEY` 被拒绝；本次代理只使用对应系统的 Key，工件仅记录两者的 SHA-256 指纹。
- 代理删除产品提交的 `user_id`，按 `toolathlon-<system_id>-<run_id 哈希>` 注入每系统、每运行不同的 DeepSeek `user_id`，隔离 KVCache、内容安全身份和调度身份。不同 API Key 不会拆分同一 DeepSeek 账号的并发额度；需要额度隔离时必须使用不同账号并另行记录账号条件。
- 第 100 次产品模型请求可以完整返回，返回后触发 `max_model_requests`；若产品更早准备发起第 101 次，则该请求被拒绝并触发同一终态。产品内部重试和辅助模型调用只要经过该代理都会计数。
- Astra 使用 `--no-resume --permission-mode auto`，并用 `--add-dir=...`、`--mcp-config=...` 防止 Clap 可变参数吞掉 `chat` 子命令；Hermes 使用 fresh `HERMES_HOME`、`approvals.mode=smart`、禁用 YOLO 与 hooks。未能证明属于本任务 Gateway 或 workspace 的交互式审批一律拒绝。
- 每次运行先通过 MCP `initialize` 和 `tools/list` 保存 Gateway 原始 Schema、哈希及 Gateway/Astra/Hermes/canonical 四元命名映射。
- Agent 完成、失败、崩溃、达到请求上限或 deadline 后都进入 evaluator；只有 Agent 之前的 Gateway/输入契约失败会中止槽位。
- 每次运行生成 12 项必需工件；cleanup 后执行结构、关键字段和完整哈希门禁。provider 未报告的 Token/finish/retry 字段使用结构化缺失对象，禁止填 0 或推测。

完整单任务入口：

```bash
python3 -m astra.runners.toolathlon_verified.lifecycle \
  --system astra \
  --run-id <unique-run-id> \
  --output-dir /absolute/path/to/fresh-output \
  --docker-via-sudo
```

`orchestrator.py` 是生命周期执行器内部使用的 prepared-slot 接口。GitHub 复现入口统一位于 `astra/runners/`，完整说明见 `astra/runners/TOOLATHLON_REPRODUCTION.md`。root 权限只用于读取 root-only 凭据并运行 Docker，真实 provider key 仍只进入 Model Proxy。流程固定 Astra→reset→Hermes，基础设施无效最多自动替代一次，其他结果不重跑。

M2 第一批入口复用同一单任务生命周期，固定 `workers=1`，并直接引用 M1 的两个 `find-alita-paper` 正式槽位：

```bash
sudo -E astra/runners/toolathlon_verified/scripts/run_astra_hermes_108.sh \
  "$PWD/astra/results/toolathlon-astra-hermes-108"
```

首次运行要求 M2 输出根为空；中断后使用完全相同的两个参数即可续跑。调度器只跳过已经通过工件门禁的槽位，不覆盖任何 attempt 目录。产品/模型失败、timeout、请求预算耗尽和 evaluator no-pass 均作为正式结果保留；只有完整工件明确分类为公共 `environment_error` 或 `evaluator_error` 时自动替代一次。工件缺失、哈希损坏、`adapter_error`、reset/生命周期分类不明或替代再次无效都会停止批次等待检查。最终门禁要求 14 题、28 个有效正式槽位、冻结顺序和全局一次性产品身份均成立，并生成 `m2-batch-artifacts.sha256`。

配置契约和示例位于 `astra/benchmark/toolathlon-verified/config/`。示例含占位符，必须先用 M0/M1 产生的绝对路径和 SHA-256 渲染。两把真实 provider key 只通过上述两个固定环境变量进入受信 Orchestrator；运行配置不得选择其他 Key 变量，也不得保存 Key 值。Astra/Hermes 产品进程、Astra admin CLI 和 evaluator 的环境都会剥离两把 Key；外层生命周期执行器还必须保证任务容器和 Astra server 不继承它们。Hermes 进程中名为 `DEEPSEEK_API_KEY` 的固定值 `toolathlon-run-proxy` 只是访问回环代理的非秘密占位符，不是真实 DeepSeek Key。

Astra Adapter 要求外部 supervisor 已启动冻结的共享回环 API server，且 `deepseek-v4-flash` 模型行已在计分运行前预配置；run 内只更新 base URL、active 和 quirks，禁止 model add、API key 更新及连通性探测。每个 attempt 通过现有 `/auth/register` 创建独占产品用户，并以 `/auth/me` 核验。用户名和密码保存到 run-local `product-identity.private.json`（0600、禁止发布），JWT/refresh token 仅存于临时凭据目录。Astra/Hermes 在 Agent 启动前的 provider 请求数必须为 0。Hermes Adapter 每 attempt 使用随机 session_id、临时 `HERMES_HOME`、新 Gateway/API key，并显式禁用外部 memory provider；收到产品终态后最多等待 120 秒，让已经启动的内部辅助模型请求落到终态，再销毁 Gateway，避免 cleanup 人为制造 `downstream_disconnected`。取消独立 108 题 Schema 预扫描和 gold/evaluator replay；M1 只要求 `find-alita-paper` 上 Astra/Hermes 各一次真实完整生命周期；GO 还要求 Agent completed、evaluator 可用、至少一个成功 Agent 模型请求且无 setup 模型请求。失败的内部辅助请求保留为正式观测值，但只要模型请求证据完整且至少一次成功，就不单独否决 M1。
