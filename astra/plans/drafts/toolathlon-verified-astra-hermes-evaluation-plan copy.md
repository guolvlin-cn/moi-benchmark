# Astra 与 Hermes：Toolathlon-Verified 评测执行方案

> 版本：v0.5  
> 日期：2026-08-06  
> 状态：紧急简化执行协议已批准；取消独立 108 题 Schema 预扫描和 gold/evaluator replay。M1 只保留单任务完整生命周期测试，并由 Astra、Hermes 在首个正式任务上各做一次真实端到端验证；通过逐运行工件门禁后，这两次运行直接计入首批 14 题，不重复执行  
> 参评系统：Astra、Hermes  
> 执行环境：8 vCPU、8 GiB RAM 的 Linux 虚拟机  
> 与总体计划的关系：本方案作为 v0.6 候选，批准后替代 [v0.5](v0.5.md) 第 4.3 节的 SWE-bench-Live 第二数据集方向；v0.5 保留为历史版本。Toolathlon-Verified 独立成榜，不与 Terminal-Bench 结果合成总分

## 0. 版本结论

本方案采用本地、解耦的 Toolathlon 执行架构，对 Astra 与 Hermes 做同任务、同模型、同预算的产品级对比：

```text
本地 Toolathlon 容器
  ├── preprocess
  ├── MCP Gateway
  └── evaluator
          ↑
    Astra / Hermes 本地 Adapter
```

本版相对上一版讨论作出六项修改：

1. 取消独立的 108 题 `tools/list`/Schema 预扫描，改为每次正式运行在 Gateway ready 后现场采集；
2. 取消 gold/evaluator replay 资格扫描，只做一个任务的完整生命周期测试；
3. 冻结的 14 个任务改为第一批正式结果，通过的运行不再作为 smoke 重跑；
4. 14 题完成后直接继续剩余 94 题，正式评测仍覆盖 108 题、两个系统各 **1 次**；
5. 运行时保存全部原始证据，每题结束只做结构、关键字段和哈希门禁，聚合推迟到 M4；
6. 全部任务在同一台 8C8G Linux 虚拟机上串行运行，固定 `workers=1`，不实现多 worker。

本次冻结的方案边界如下：

- 数据范围为冻结 commit 的 108 个正式任务；14 个固定任务是第一批正式结果；
- Astra 与 Hermes 各执行每个正式任务 1 次，正式结果不计算 Pass@3、Pass³ 或随机稳定性；
- 两侧使用同一远程模型端点、同一公共任务 Prompt、同一模型请求上限和同一 MCP 语义工具集合；
- 执行架构为本地解耦的 `preprocess → MCP Gateway → Adapter → evaluator`，8 vCPU、8 GiB RAM、`workers=1`；
- Swap 固定启用，规格见第 2.2 节；所有资格和正式运行必须使用相同 Swap 配置，不得按任务或产品调整。

阶段与产品运行量如下：

| 阶段 | 任务范围 | 每题每系统次数 | 产品运行数 | 是否计入正式结果 |
| --- | ---: | ---: | ---: | --- |
| M0 冻结证据与运行资格门禁 | 无 Benchmark 产品运行 | 0 | 0 | 否 |
| M1 最小 live qualification | 单任务生命周期；Astra/Hermes 各一次真实端到端 | 1 | 2 | 通过门禁后计入 M2 |
| M2 第一批正式评测 | 14 × 2 个系统 | 1 | 28（含 M1 的 2 次） | 是 |
| M3 剩余正式评测 | 94 × 2 个系统 | 1 | 188 | 是 |
| M4 分析与报告 | 不新增运行 | 0 | 0 | — |
| **合计** |  |  | **216** | 216 次正式运行 |

M1 固定使用 14 题清单中的第 1 题 `find-alita-paper`。若两侧运行均使用正式冻结项、Agent 终态为 completed、evaluator 返回 pass/no_pass、至少完成一次成功的 Agent 模型请求、Agent 启动前 provider 请求数为 0，并通过逐运行工件门禁，则直接成为 M2 的前两个正式槽位；否则原始失败证据保留，并按第 3.4 节的单次自动替代规则处理。冻结项发生影响执行的变化时，从变化后的首个未执行槽位停止，重新冻结后再继续，不回溯重跑此前有效正式结果。

## 1. 研究问题与结论边界

### 1.1 研究问题

- **RQ1 任务完成**：在冻结任务、模型、工具和预算下，Astra 与 Hermes 分别能通过多少 Toolathlon-Verified evaluator？
- **RQ2 运行可靠性**：两套产品有多少 timeout、模型传输失败、产品失败、Adapter/环境无效和 evaluator unavailable？
- **RQ3 工具工作负担**：两套产品分别使用多少终态工具调用、失败工具调用和模型请求？
- **RQ4 时间与用量**：两套产品的端到端、Agent、准备和 evaluator 时间如何；Token 数据覆盖和可靠性如何？
- **RQ5 任务类型差异**：两套产品在 Academic、Campus、Daily、Finance、Office、Shopping、Tech 七类任务上呈现什么描述性差异？

### 1.2 可以支持的结论

- 在冻结 Toolathlon-Verified 108 题上，本次单次运行的 evaluator 通过、正常端到端成功、timeout、工具负担和时间结果；
- 同一任务上 Astra 与 Hermes 的配对结果及失败根因差异；
- 在同一模型和统一预算成立时，两套 Agent 产品脚手架的系统效果；
- 8C8G、单 worker、本地解耦架构下的工程可运行性。

### 1.3 不能支持的结论

- 单次运行不能估计同一产品的随机波动、Pass@3、Pass³ 或结果稳定性；
- 公共 Benchmark 结果不能直接归因到 Astra 的 Git4Data、Reflection、状态恢复或权限机制；
- 如果模型、模型可见工具 Schema、Prompt、预算或权限不等价，只能解释为“冻结原生产品栈的系统效果”；
- 本地 Adapter 结果不是 Toolathlon 官方默认 Agent 排行榜成绩；
- Token 采集来源或缓存计量不一致时，不能得出跨产品 Token 成本或美元成本胜负。

## 2. 执行架构与 8C8G 约束

### 2.1 组件边界

| 组件 | 责任 | 禁止行为 |
| --- | --- | --- |
| Toolathlon 任务容器 | 创建任务工作区、运行 preprocess、启动单一 MCP Gateway、保存任务状态、运行原始 evaluator | 不运行 Astra/Hermes 产品循环；不向 Agent 暴露 ground truth 或 evaluator 私有文件 |
| 公共 Orchestrator | 创建容器、分配端口、生成 run ID、调度 Adapter、记录阶段时间、无条件调用 evaluator、执行清理 | 不生成任务解法、不补写 Agent 状态、不根据中间结果修改任务 |
| Astra Adapter | 将 trusted bundle、任务 Prompt 和 Gateway SSE 接入 Astra；导出统一事件和终态 | 不增加 Astra 原本没有的任务知识、上下文摘要、动作重放或静默重试 |
| Hermes Adapter | 将同一 trusted bundle、任务 Prompt 和 Gateway SSE 接入 Hermes；导出统一事件和终态 | 不增加 Hermes 原本没有的任务知识、上下文摘要、动作重放或静默重试 |
| Evaluator | 对最终任务环境和工件评分 | 不读取 Adapter 推断的成功状态替代真实评分 |

执行顺序固定为：

```text
恢复任务初始状态
  -> container preprocess
  -> 导出 schema-v2 trusted bundle
  -> 隐藏 evaluator / ground truth
  -> container MCP Gateway /sse ready
  -> Astra 或 Hermes Adapter
  -> 保存 Agent 终态与完整轨迹
  -> 恢复原始 evaluator
  -> container evaluator
  -> 收集工件与清理
```

Agent 成功、失败、timeout、崩溃或达到步数上限后都必须进入 evaluator；只有 preprocess、Gateway 或 evaluator 自身无法建立时才可能形成实验基础设施无效。

### 2.2 8C8G 固定执行约束

| 项目 | 本方案要求 |
| --- | --- |
| VM | Linux，8 vCPU，8 GiB RAM；正式前记录发行版、kernel、CPU 架构、虚拟化类型 |
| 并发 | `workers=1`；一次只保留一个计分任务容器和一个产品 Adapter |
| 产品顺序 | 同一任务先运行一个产品，完整恢复初始状态后再运行另一产品；奇偶任务交替产品先后顺序 |
| 模型 | 使用远程模型端点；8C8G VM 不部署本地 LLM |
| 其他负载 | 正式运行期间不得在 VM 上运行其他构建、训练或评测任务 |
| Swap | **固定启用**；禁用 zram，仅使用预分配 `/swapfile`，类型为普通 swapfile，容量 `8 GiB = 8589934592` bytes，priority=`-2`，`vm.swappiness=10`；任务 cgroup 的 `memory.swap.max=8589934592` bytes；运行期间不得创建、删除、扩容、缩容、切换 priority 或调整 swappiness |
| 资源采样 | 至少每秒记录 VM、任务容器和 Adapter 的 RSS/working set、CPU、磁盘、网络、当前/峰值 Swap 使用量及 swap in/out 计数 |
| OOM | 必须记录被杀进程/cgroup：产品或 Adapter 自身资源耗尽属于有效产品失败；公共任务容器、preprocess 或 evaluator 的基础设施资源耗尽才可判为 `infra_invalid` |
| 时间预算 | Agent execution 按任务固定为 R1=`1,800`、R2=`2,700`、R3=`3,600`、R4=`5,400` 秒；公共上限为 `100` 次产品侧模型请求；工具调用不设数量上限；preprocess、Gateway readiness、产品启动、evaluator、reset、cleanup 和工件固化使用第 3.3 节独立基础设施安全超时，不占用 Agent 时限 |
| 运行隔离 | 每个产品、每个任务使用新的 run/session ID、任务容器、工作区和产品状态目录 |

`k8s-safety-audit` 被有意纳入第一批 14 题的最后一项，用来验证 Kubernetes 类任务在 8G 内存下能否完成 preprocess、Gateway、Agent 和 evaluator 全链路。该任务 evaluator 不通过不构成容量失败；OOM、Gateway 无法启动或 evaluator 无法运行才构成容量门禁失败。

如果 Toolathlon 所需的全部应用后端也必须与任务容器共同常驻这台 VM，M0 必须先做空载内存审计。只要基础服务常驻后不能为单任务容器和 Adapter 留出稳定内存，8C8G 方案即为 No-Go，不能通过开启并发或缩短 timeout 掩盖。产品或 Adapter 自身因固定资源上限触发的 OOM 记录为产品失败；任务容器、Gateway 或 evaluator 因内存压力不可用才是容量门禁失败。

## 3. 冻结清单

状态含义：

- **已冻结**：已有明确值；
- **M0 已冻结、M1 PENDING**：静态来源、实物或契约已不可变；真实凭据、应用状态或运行时证据在 M1 采集，M1 完成前禁止进入 M2/M3；
- **本方案固定**：本文已经给出值，M0 需要写入机器可读 Manifest；
- **M1 待资格**：不增加 M0 冻结根，在 M1 产生 live qualification 证据并由正式运行配置引用。

第 3.1、3.2 节的机器可读冻结根目录为 `astra/benchmark/toolathlon-verified/freeze/`；聚合校验文件为 `sections-3.1-3.2.sha256`，其 SHA-256 为 `a7a3ff6d0387bb172adcb2e2d429a123d7d2c602f89ab24328768453bb16f80c`。二进制归档放在不入库的 `astra/work/toolathlon-verified/`，归档路径、大小和 SHA-256 已写入对应冻结 Manifest。

### 3.1 数据、任务与 evaluator

| 冻结项 | 值或要求 | 状态 |
| --- | --- | --- |
| Toolathlon Git commit | commit=`2aed2468858f15818acafa178518390cc4b0f5cb`，tree=`a739a794e514734e320be0010511dceed26704bd`；源码归档 SHA-256=`a8f4cb71c4da143003796694ef426be88617eb86a1001abc4542d0efe42543fa` | **已冻结** |
| 正式任务 Manifest | `tasks/finalpool` 的 108 个任务、1,812 个文件；`task-manifest.sha256` 的 SHA-256=`b5faf6db99505bfe57f92f0f6d097d0eccac1dd22cd1ceb71e86169c7e2f9609` | **已冻结** |
| 首批 Manifest | 14 个任务的固定顺序写入 `section-3.1.freeze.json`，与第 6.3 节一致 | **已冻结** |
| 冲突与调度元数据 | `tasks/finalpool/task_conflict.json`，SHA-256=`d7f0732ddebd6d775295c8889c0d16202c447476e38041e4e5d1fb312fe4cce1` | **已冻结** |
| 任务文件哈希 | instruction、system prompt、preprocess、initial workspace、ground truth、evaluator、`task_config.json` 等全部实际文件均由 1,812 行清单覆盖 | **已冻结** |
| Bundle 协议 | `schema_version=2`、trusted resolved task config、Agent 不可见 ground truth/evaluator；10 个核心生成/校验文件的哈希写入 `section-3.1.freeze.json` | **已冻结** |
| Evaluator 行为 | 227 个 evaluator 文件，清单 SHA-256=`0afe377a285dff5cc224578e65f9ff7bb442e21846edb730b05f5cdcdaea0dc6`；`allow_resume=false`；whole-check 默认 3 次、间隔 5 秒；`pass ∈ {true,false,null}`；独立 evaluator 安全超时已由 3.3 固定 | **M0 已冻结** |
| Gold/evaluator 资格检查 | 紧急执行协议取消独立 replay；正式运行仍无条件调用冻结 evaluator，并完整保存原始结果与日志 | **已豁免独立预扫描；不豁免逐运行 evaluator** |

数据 commit 可以冻结源码，但不能替代运行时镜像、外部应用状态和实际输出目录的哈希。

### 3.2 容器、应用与工具

| 冻结项 | 要求 | 状态 |
| --- | --- | --- |
| Toolathlon 任务镜像 | 正式引用=`docker.io/lockon0927/toolathlon-task-image@sha256:4d04fe4e0a6fdb4946f51bb05120cb44a0eef980231c11252f93b62897afcb9f`；linux/amd64 OCI 归档 SHA-256=`74f3ec444af1ef46564fe2f4e58431f2e136f2481aa101513fa3108bd59bc3de`；已由 Docker 按 digest 拉取并核验 | **已冻结** |
| Docker/Podman | rootful Docker Engine `29.1.3`、API `1.52`、`overlayfs`、cgroup v2、containerd `2.2.1`、runc `1.3.4`；见 `container-runtime-manifest.json` | **已冻结** |
| 依赖锁 | `uv.lock`、`pyproject.toml`、`package-lock.json`、`package.json`、Dockerfile 和 GitHub MCP binary 均已哈希；`task-image-software-manifest.json`（SHA-256=`e0f9621668326fca1bf1dd8b565de3cd2386fe6955bcde0dc50f17fee49d5427`）记录 378 个 dpkg 包、26 个 Python 包、Node 全局包，以及 Chromium `136.0.7103.25`/`139.0.7258.31`、Playwright `1.55.0-alpha-1752701791000` 等浏览器运行时 | **已冻结** |
| 外部应用 | 17 个辅助镜像均已解析 linux/amd64 registry digest，`image-manifest.json` SHA-256=`0003e9545870748bde986f629efee8aa9381904cd94874340b0370da20e7426f`；10 个部署文件和 8 个基线/重置来源已哈希；tenant、初始数据库快照和 reset replay 在 live qualification 采集 | **M0 镜像/源码已冻结；M1 待资格** |
| 凭据 | DeepSeek Key 和 Astra admin token 只冻结指纹、不保存真实值；Astra 每 attempt 注册独占产品账号，用户名和明文密码保存到该 run 的 `product-identity.private.json`（0600、禁止发布），access/refresh token 不保存 | **M0 契约已冻结；M1 待 provision** |
| MCP servers | 108 题要求的 33 个 MCP server、34 个配置文件、依赖锁与启动配置来源已记录；服务 URL、账号语义及可达性在 M1 复验 | **M0 源码已冻结；M1 待资格** |
| 模型可见工具 | 已冻结每题 required MCP/local-tool 需求；取消 108 题预扫描，每次运行在 Gateway ready 后采集真实 `tools/list`、完整 Schema 和内容哈希；每个 attempt 只连接当前任务 Gateway，禁止混入其他任务 MCP 工具 | **M0 需求与逐 attempt 隔离已冻结；逐运行采集** |
| Local tools | 7 个 required local tool 及 8 个实现来源文件已哈希；真实模型可见 Schema 与 MCP 工具在每次运行中一并采集 | **M0 实现已冻结；逐运行采集** |
| 工具命名映射 | Adapter 已冻结 Gateway/Astra/Hermes/canonical 四元映射规则并通过 Mock `tools/list` 测试；Astra 保留连字符，Hermes 将连字符改为下划线 | **M0 规则已冻结；M1 采集真实映射** |
| 网络 | Gateway 固定单任务、`127.0.0.1` bind；一次性 tenant 对应的 DNS、代理、出口、TLS 和 endpoint 证据在 M1 resolved config 记录 | **M0 边界已冻结；M1 待资格** |

Tool name 前缀或参数 Schema 只要对模型可见，就属于产品输入，不能仅在分析时视作无关差异。受控主比较要求 Astra 与 Hermes 看到语义等价的工具集合；无法满足时必须降级为原生产品栈结果。

因此，第 3.1、3.2 节的可复现数据/源码/镜像/容器运行时已经满足 M0。`m1-app-state-live.json` 中本地应用基线与 reset replay 已取得 GO；任务容器可按已冻结凭据清单接收真实应用凭据。旧 `tool-schema-manifest.json` 的预扫描状态不再构成门禁，真实工具证据由每个运行目录中的现场 `tools/list` 工件承担。

### 3.3 产品、模型与 Adapter

第 3.3 节机器可读冻结入口为 `freeze/section-3.3.freeze.json`，聚合清单为 `freeze/section-3.3.sha256`；实际 SHA-256 由该清单和 `execution-protocol.freeze.json` 机器读取，不在本文复制易漂移的派生值。产品源码和 Adapter 的确定性归档位于不入库的 `astra/work/toolathlon-verified/freeze-3.3/`，路径、大小和哈希已写入各自 freeze。

| 冻结项 | 冻结值 | 状态 |
| --- | --- | --- |
| Astra | commit=`844473c68649d8ea43e10b616dc4fbf98e2321e8`，tree=`bfd88d2fe30ad7a04b2611a42c70d5dc993280bf`，`v0.0.5-4-g844473c68`；使用 clean detached worktree；Linux/amd64 CLI SHA-256=`80ce54af219ff162e911ca208a83e660bb8acb2e68c2b5f8e7e54afa500a1e5b`，server SHA-256=`48a67ff31cf3747ecc0998dbac803d335ccd424d81eb0e55dd08d87cceec74e3`，rendered runtime config 已绑定 | **3.3 运行产物资格 GO** |
| Hermes | commit=`f4df260f26c93f15694698869f3ea8e965eea301`，tree=`40f0136a9995a9a1712a3ab28c231a2812748cdf`，release=`v2026.7.20-63-gf4df260f2`，project=`0.19.0`；clean checkout；CPython=`3.11.15`，Hermes executable SHA-256=`16b9840ed1cc44541d758f790d1b6db5afba1f4193ee9d59f1f15871029875fa`，`uv.lock`、完整包清单、`uv pip check` 与 rendered runtime config 已绑定 | **3.3 运行产物资格 GO** |
| Adapter | 公共单产品槽位 Orchestrator、Astra/Hermes Adapter、模型代理、MCP inspector、权限/状态/进程/资源/轨迹模块按逐文件哈希冻结；无第三方 Python 依赖；确定性归档哈希见 `adapter.freeze.json`；公共事件 Schema=`toolathlon.adapter.events.v1`；外层最小 container/preprocess/Gateway/reset/cleanup 生命周期和严格工件门禁已纳入冻结。每次请求额外记录模型可见工具名称、数量和哈希；任何请求均不得出现其他任务 MCP 名称，且至少一个请求的 MCP 集合必须完整等于本题现场 `tools/list`（允许产品终态后的辅助请求不携带工具）。Astra 原生 `tool_transport_started` 必须与 `tool_transport_completed` 或 `tool_transport_failed` 按 call ID 完整配对并各规范化一次，失败 terminal 必须记为 `state=failed`，所有 terminal 均继承对应 start 的参数哈希，且服务端声明的工具调用数必须等于成功与失败 terminal transport 总数；缺失或重复证据由工件门禁 fail closed。两产品终态后 Model Proxy 最多等待 120 秒，并在 forwarded=completed 后连续静默 1 秒才关闭，以保留 auto-title 等辅助请求的完整 terminal 证据 | **3.3 内容已重新冻结；真实双系统 E2E 必须重做** |
| 模型 | 官方直接 API，provider=`deepseek`，base URL=`https://api.deepseek.com`，请求 ID=`deepseek-v4-flash`，2026-08-05 官方文档对应版本=`DeepSeek-V4-Flash-0731`；context=`1,000,000` tokens，最大输出能力=`384,000` tokens，支持 Tool Calls | **已冻结** |
| 模型凭据与请求身份 | Astra/Hermes 分别使用固定环境变量 `TOOLATHLON_DEEPSEEK_ASTRA_API_KEY` / `TOOLATHLON_DEEPSEEK_HERMES_API_KEY` 中的不同 Key；Orchestrator 启动前校验两值存在且不相同，拒绝旧共享真实 `DEEPSEEK_API_KEY`。两者仍调用同一 `https://api.deepseek.com` 与同一 `deepseek-v4-flash`；仅对应 Key 进入本次模型代理配置，Astra/Hermes、Astra admin、evaluator、任务容器和 Astra server 均不得获得真实 Key，工件只记录 SHA-256 指纹。Hermes 内部同名变量仅允许固定非秘密代理占位符；代理强制注入每系统、每运行不同的 `user_id` | **M0 契约与实现已冻结；真实 Key 在 M1 provision** |
| 生成参数 | 官方默认仍记录为 `enabled/high`，但本实验采用显式 benchmark override：Model Proxy 删除产品侧 Thinking/effort 值，并在每个 provider 请求发送 `thinking={"type":"enabled"}`、`reasoning_effort="max"`；`resolved-config.json` 与每条 `model_request.started` 审计均记录 `enabled/max`、`wire_behavior=sent`、`source=benchmark_override`。发送并记录 `temperature=0`，但 Thinking 下不生效；top-p、penalties、max output、tool choice、parallel tool calls 均省略并采用 provider 默认；产品原生 stream 值保留 | **已重新冻结；回归测试按用户指令未重跑** |
| Prompt | 108 题 task/system prompt 由 `task-manifest.sha256` 绑定；两产品核心 Prompt 源逐文件哈希；Adapter 不增加包装 Prompt，只分别透传原始 task/system 字段 | **已冻结** |
| 预算 | 唯一权威为 `toolathlon-trajectories-runtime-budget-addendum.md` SHA-256=`85efd2f7b10679e744b9f75bc601c25b6e1e486a6e5f43b696e35a282f9217d5`；108 题 R1/R2/R3/R4 数量=`8/15/11/74`，Agent 时限=`1,800/2,700/3,600/5,400` 秒；产品侧模型请求上限=`100`，工具调用上限=`null`，不增加 Token 或费用上限 | **已冻结；覆盖旧 5,400 秒 end-to-end 口径** |
| 基础设施安全超时 | preprocess=`3,600`、Gateway readiness=`600`、模型代理 readiness=`60`、终态后模型请求排空=`120`（forwarded=completed 后静默 `1` 秒）、产品启动=`600`、evaluator=`3,600`、应用 reset=`3,600`、cleanup=`1,800`、工件固化=`600` 秒；各阶段独立，不加到或扣减 Agent 时限 | **已冻结** |
| 重试 | Adapter 整槽位重试=`0`；Astra/Hermes 采用对应冻结 commit 的解析值，不由 Adapter 改写；Astra LLM transient=`3`、TPM=`5`、tool=`2`、MCP connect=`5`；Hermes app-level model attempts=`3`、OpenAI SDK retries=`2`、MCP initial/reconnect=`3/5`；Gateway/evaluator 继承第 3.1/3.2 的冻结来源 | **已冻结** |
| 权限 | 保留产品内部语义：Astra 源码默认 prompt，但非交互边界解析为 `permission-mode=auto`；Hermes 保持默认 `smart`，禁止 YOLO/hooks；仅当前 loopback Gateway 和 fresh workspace 属于共同任务范围，无法证明在范围内的审批统一 deny，Adapter 不解析并自动批准 shell 字符串 | **已冻结** |
| 状态 | 每 attempt fresh home/session/workspace，`resume=false`；Astra 复用冻结的共享 loopback server/DB，以 attempt 级新注册用户隔离服务端状态（original=a1，replacement=a2），原生 `/chat/stream` 请求省略 `session_id`，由 server 在该一次性用户下自动创建新 session，并从 SSE 记录实际 session ID；Hermes 使用随机 session_id、临时 `HERMES_HOME`、新 Gateway/API key 且 `memory.provider=""`；Agent 终态后先完成公共 Model Proxy 请求排空再执行 evaluator，产品启动与排空均不消耗 Agent 时限 | **已重新冻结；需重做真实双系统 E2E** |
| Agent 默认与工具面 | “采用 Agent 内部默认配置”不再表示笼统继承全部默认值，只保留 `astra.freeze.json` / `hermes.freeze.json` 中逐项解析列出的产品默认值。共同隔离、权限/`no-resume` 和任务级工具面是明确 benchmark override：Astra 使用冻结 server 已有的原生 `/chat/stream` API，把本 attempt 的 fresh 单任务 Gateway 作为 `runtime_profile=request_scoped_runtime_mcp` binding 交给 Astra 服务端发现、注册并执行；Adapter 只负责原生请求传输和 SSE 证据采集，不实现 Agent 循环。Hermes 继续使用本 attempt 的 fresh 单任务 Gateway。两者均不得暴露其他任务 MCP 工具；Astra 使用冻结服务端的产品内置工具，Hermes 自带非 MCP 工具按冻结产品默认保留 | **已重新冻结；需重做真实双系统 E2E** |

`deepseek-v4-flash` 是 provider alias，而不是可直接请求的不可变版本 ID。正式批次开始前必须复核官方文档仍将其解析为 `DeepSeek-V4-Flash-0731`；若 alias 已更新，当前 model freeze 失效，必须重新冻结并重新执行受影响的资格槽位，不能在同一批次混用版本。官方 Thinking 工具调用要求回传 `reasoning_content`；Adapter 不替产品修复该历史，缺失回传导致的 provider 400 属于有效产品结果。

DeepSeek 官方规定并发上限按账号计算、与 API Key 无关。因此“两把 Key”用于凭据归属、审计和防止系统间误用，不等于额度隔离；代理额外用不同 `user_id` 隔离 KVCache、内容安全身份和调度身份。若正式实验还要求并发/额度相互独立，必须改为两个 DeepSeek 账号，并在 M1 记录账号服务等级和配额一致性；当前 `workers=1` 串行协议不依赖 Key 级并发隔离。

上述产品源码 commit 不变；Adapter、工具暴露契约和 3.3 内容哈希已按本次修订整体重新冻结。进入 M2 前须重新执行 `find-alita-paper` 的单任务完整生命周期，并让 Astra/Hermes 各一次真实端到端运行通过新的逐运行工具面与工件门禁；旧 M1/M2 结果仅保留为诊断证据，不得复用为正式槽位。仍不要求 108 题预扫描或 gold replay。

### 3.4 VM 与执行协议

| 冻结项 | 值或要求 | 状态 |
| --- | --- | --- |
| VM 配额 | 8 vCPU、8 GiB RAM | **已冻结** |
| 并发 | `workers=1`，Astra/Hermes 串行 | **本方案固定** |
| 正式重复次数 | 每个系统每个正式任务 1 次 | **本方案固定** |
| OS/Kernel | Ubuntu 22.04.5 LTS、kernel `5.15.0-186-generic`、x86_64、Etc/UTC；systemd-timesyncd active/enabled 且采集时已同步 | **M0 已冻结** |
| 磁盘 | `/dev/sda1`、ext4；总量 `208097689600` bytes，采集时可用量见 `vm.freeze.json`；Docker root=`/var/lib/docker` | **M0 已冻结** |
| Swap | `/swapfile` 普通文件，分配容量 `8589934592` bytes、priority=`-2`、`vm.swappiness=10`、zram 禁用；root:root/0600，fstab/sysctl/modprobe 持久化 | **M0 已冻结并实测** |
| cgroup | cgroup v2；无网络临时任务容器实测 `memory.max=8589934592`、`memory.swap.max=8589934592`、CPU controller=`800000 100000` | **M0 已冻结并实测** |
| OOM 行为 | 固定采集 cgroup `memory.events*`、Docker `State.OOMKilled`、exit code、kernel journal 和每秒资源样本；产品/Adapter OOM 为有效产品失败，共享任务基础设施 OOM 为 `infra_invalid` | **M0 契约已冻结** |
| 任务顺序 | 附录 A 字典序；同题产品先后按奇偶位置交替 | **本方案固定** |
| 随机性 | `PYTHONHASHSEED=0`；不覆盖任务源码内由 Task Manifest 绑定的固定 seed（已知值 7、42） | **M0 已冻结** |
| 时间 | Etc/UTC；wall clock=`CLOCK_REALTIME`，monotonic=`CLOCK_MONOTONIC/time.monotonic_ns`，kernel clocksource=`tsc`，NTP 已同步 | **M0 已冻结** |
| 重跑规则 | 仅实验故障域外且有独立证据的 infra invalid 可替换；产品/模型 timeout 不重跑 | **本方案固定** |
| 证据保留 | 原始运行、替代运行、配置、日志和映射均只读保留 | **本方案固定** |

M0 使用最小权威根，不为派生内容重复建立冻结文件。`experiment.freeze.json` 内嵌结果目录 Schema、失败优先级、重跑与凭据隔离契约；第 3.1–3.3 节的明细文件通过两个聚合根传递绑定。最终只要求：

```text
freeze/
  sections-3.1-3.2.sha256
  section-3.3.sha256
  vm.freeze.json
  experiment.freeze.json
  m0.sha256
```

`vm.freeze.json`、`experiment.freeze.json` 和最终 `m0.sha256` 的实际 SHA-256 只由冻结目录中的机器可读清单提供，避免计划文本与内容寻址根形成循环引用；在 `freeze/` 目录执行 `sha256sum -c m0.sha256` 必须四项全通过。

其中 `vm.freeze.json` 的 Swap 部分必须至少解析为以下固定配置；实际采集值必须与之完全一致，不能以宿主机默认值代替：

```json
{
  "swap": {
    "enabled": true,
    "type": "file",
    "path": "/swapfile",
    "size_bytes": 8589934592,
    "priority": -2,
    "zram_enabled": false,
    "vm_swappiness": 10,
    "cgroup_memory_swap_max_bytes": 8589934592
  }
}
```

## 4. Adapter 契约

### 4.1 公共输入

两个 Adapter 必须接受同一组逻辑输入；具体 CLI 名称可以不同，但 resolved config 必须能证明字段等价：

| 输入 | 说明 |
| --- | --- |
| `bundle_file` | preprocess 生成的 schema-v2 trusted bundle 的宿主侧副本 |
| `gateway_url` | 当前任务唯一的 MCP Gateway SSE URL，例如 `http://127.0.0.1:<port>/sse` |
| `task_id` | 冻结任务目录名 |
| `experiment_id` / `run_id` | 全局唯一实验和运行标识 |
| `output_dir` | 当前系统、任务、运行独占的结果目录 |
| `deadline_s` | 公共端到端或 Agent deadline |
| `max_model_requests` | 公共模型请求/决策步上限 |
| `model_freeze` | 精确模型、provider 和生成参数 |
| `task_requirements_manifest` | 冻结任务声明的 required MCP/local-tool 需求；不是运行时 Schema 预扫描结果 |
| `permission_policy` | 仅授权当前任务 Gateway 和预注册工作区/外部服务范围 |

Adapter 只能读取 Agent 可见的 bundle 副本。Ground truth、evaluator 实现、私有恢复工件和 evaluator token 不得进入 Adapter 的文件系统可见范围。

### 4.2 工具接入要求

1. 每个 Adapter 只连接当前任务的单一 Gateway，不直接旁路连接其他 MCP server；
2. Agent 启动前调用 `list_tools`，保存原始返回、完整 Schema 和内容哈希；不依赖独立预扫描根；
3. 同时保存 `gateway_tool_name`、`model_visible_tool_name` 和 `canonical_tool_name`；
4. 工具调用用稳定 `tool_call_id` 去重，开始事件和终态事件分开记录；
5. 统计工具调用时只计有终态的成功或失败调用，不能把 retry attempt 或 started-only 事件当作完成调用；
6. `claim_done` 使用统一停止语义；产品退出、达到步数上限或异常退出也必须形成明确终态；
7. `python_execute`、`web_search` 等任务语义相关 local tools 必须由两侧使用同一实现和 Schema，明确记录它们由 Gateway 还是公共 host-side bridge 提供；
8. `manage_context`、`history`、`handle_overlong_tool_outputs` 等脚手架辅助能力不得只为一侧额外注入。若由产品原生实现，作为产品系统效果保留并记录；
9. Adapter 不得自动改写工具参数、猜测缺失字段、重放副作用或把工具错误改写为成功。

### 4.3 执行与终止要求

- 每次运行创建 fresh product session，不读取其他任务或先前运行记忆；
- 传入完全相同的 Toolathlon task/system prompt；不可消除的产品核心 Prompt 必须保存哈希；
- Adapter 不生成恢复摘要、任务规划或上下文压缩内容；
- Adapter 级静默重试固定为 0；若 provider SDK 或产品内部有重试，必须显式冻结并逐次记录；
- 每个模型请求、工具调用和终止信号均写入 append-only 事件流；
- Agent timeout 后终止其完整进程树，但不得删除已经产生的任务状态；
- Agent 任意终态后 Orchestrator 都调用原始 evaluator；
- 清理阶段删除当前产品私有状态和任务容器，外部应用通过冻结 reset 流程恢复。

### 4.4 Adapter 与 Orchestrator 的输出

每次产品运行至少形成以下 12 项门禁工件；支持诊断和私有隔离的其他文件可以额外保留：

```text
runs/<system>/<task_id>/<run_id>/
  resolved-config.json
  lifecycle-events.jsonl
  adapter-events.jsonl
  trajectory.jsonl
  tool-calls.jsonl
  model-usage.jsonl
  resource-usage.jsonl
  evaluator/
    eval_res.json
    eval.log
  failure-evidence.json
  run.json
  artifacts.sha256
```

`task-bundle.public.json` 和 `tool-schema-observed.json` 作为支持证据额外保留；前者只能是 Agent 实际可见副本，不得把 trusted/private bundle 发布给产品。`artifacts.sha256` 是 cleanup 完成后生成的最终封存清单，必须覆盖上述全部必需工件及同目录内的其他证据文件，且不得覆盖自身。

所有运行必须先通过机器可执行的工件 Schema、关键字段、事件配对和哈希校验，才可进入下一个运行。缺少任一原始证据或必需字段时立即 fail closed；不能静默跳过。只有数据源确实未提供指标时才允许使用以下完整观测对象，禁止填 0 或从其他值推测：

```json
{
  "value": null,
  "source": "provider_response",
  "reliability": "missing",
  "missing_reason": "provider_not_reported"
}
```

运行期间保存 append-only 原始证据。Token 汇总、工具开始/终态配对、阶段统计和总表统一在 M4 离线计算；聚合表未生成不阻塞下一运行，但聚合所需的原始证据缺失必须阻塞。

### 4.5 指标反推的必需字段

指标口径参考 [Astra 与 Hermes：Terminal-Bench 常规任务对比](../../reports/TerminalBench2.1-analysis/astra-hermes-c0-latest-88-task-comparison.md)。Adapter 和 Orchestrator 必须共同提供以下字段：

| 指标需求 | 必需字段 | 采集责任 |
| --- | --- | --- |
| 配对与冻结核验 | `experiment_id`、`system_id`、`task_id`、`run_id`、所有 freeze hash | Orchestrator + Adapter |
| verify pass/no-pass/unavailable | `verify_status`、`reward`、`evaluator_exit_code`、`evaluator_error` | Orchestrator/Evaluator |
| 正常端到端成功 | `verify_status`、`timeout`、`timeout_scope` | Orchestrator 汇总 |
| 产品终态 | `terminal_status`、`product_exit_code`、`termination_reason`、`claim_done_seen` | Adapter |
| timeout | `deadline_s`、明确 timeout signal、发生阶段、被终止 PID/容器 | Adapter + Orchestrator |
| 失败根因 | `primary_failure_category`、原始错误码、错误证据路径 | Adapter + Orchestrator |
| 阶段时间 | 每阶段 monotonic start/end 与 wall-clock timestamp | 各阶段 Owner |
| 工具调用 | `tool_call_id`、三种工具名、参数 hash、终态、错误类型、开始/结束时间 | Adapter |
| Token | 每次请求的 input/output/cache-read/cache-write、来源、可靠性、缺失原因 | Adapter/provider response |
| 模型轮次 | `model_request_id`、attempt、finish reason、重试关系 | Adapter |
| 资源 | VM/container/Adapter 的 CPU、memory、disk、network、OOM signal | Orchestrator |
| 有效性 | `run_validity`、`invalid_scope`、独立证据、替代 run ID | Orchestrator |

字段枚举至少固定为：

```text
verify_status:
  pass | no_pass | unavailable

terminal_status:
  completed | failed | max_steps | timeout | interrupted | crashed

timeout_scope:
  none | preprocess | gateway | model | tool | agent | evaluator | cleanup

run_validity:
  valid | infra_invalid

primary_failure_category:
  none
  llm_request_timeout
  stream_transport_error
  agent_deadline
  product_resource_exhausted
  infra_resource_exhausted
  model_error
  model_request_budget
  tool_error
  product_error
  adapter_error
  environment_error
  evaluator_error
  completed_but_no_pass
```

一个运行只能有一个首要失败根因，但可以保留多个辅助错误标签。首要根因必须由预注册优先级和原始证据决定，不能根据产品名称或最终分数人工调整。

## 5. 指标与报告口径

### 5.1 任务完成

沿用指定 Terminal-Bench 报告的三分法：

- `pass`：evaluator 明确通过；
- `no-pass`：evaluator 有效运行但未通过；
- `verify unavailable`：未得到可信 evaluator 结果，单列，不计入 no-pass，也不进入有效结果通过率分母。

固定计算：

```text
verify_pass_rate
= N_verify_pass / (N_verify_pass + N_no_pass)

normal_end_to_end_success
= verify_status == pass AND timeout == false

outcome_coverage
= (N_verify_pass + N_no_pass) / 108

full_frame_pass_lower_bound
= N_verify_pass / 108

full_frame_normal_end_to_end_success
= N_normal_end_to_end_success / 108
```

产品退出码、`claim_done` 和轨迹完整性单列，不额外加入 `normal_end_to_end_success` 定义，以保持与参考报告一致。

### 5.2 配对结果

在双方都有有效 evaluator 结果的共同任务集上报告：

- 双方均通过；
- 双方均未通过；
- 仅 Astra 通过；
- 仅 Hermes 通过。

Timeout 配对分布单独报告：双方均无 timeout、仅 Astra timeout、双方 timeout、仅 Hermes timeout。Timeout 属于产品运行结果，不能自动解释为应重跑的基础设施错误。

正式阶段只有一次运行，因此主报告以原始计数、比例和逐任务配对表为主。可以提供 task bootstrap 或 exact McNemar 作为描述性敏感性分析，但必须明确它不能估计同一任务的运行随机性。

### 5.3 失败根因

至少分别统计：

- LLM 请求 timeout；
- stream/transport 中断；
- Agent/controller deadline；
- 模型非 timeout 错误；
- 任务语义相关工具错误；
- 产品进程错误；
- Adapter/Orchestrator 基础设施错误；
- 任务环境或 Gateway 错误；
- evaluator unavailable/error；
- 产品完成但 evaluator 未通过。

`reward=0`、未产生 reward、产品异常退出和实验基础设施无效不得合并为同一种失败。

### 5.4 时间

对以下阶段分别报告总计、中位数和 P90：

- 端到端；
- Agent 执行；
- 环境/容器准备；
- Adapter/Agent 准备；
- evaluator；
- cleanup。

另外报告同任务配对的 Astra-Hermes 时间差中位数。时间统计包含产品 timeout；成功任务速度另表展示，不能用全部任务总时间代替成功任务效率。

### 5.5 工具调用

- 只统计有终态的工具事件；
- 报告有工具计数任务数、调用总数、单任务中位数和 P90；
- 对失败工具调用使用相同统计；
- 报告最常见的 canonical 工具类型；
- 同时展示双方都有工具数据任务上的配对调用差；
- 若模型可见工具封装或命名不等价，只解释为工作负担，不解释为完全等价的工具效率。

### 5.6 Token 与模型请求

- 保存每个模型响应原始 usage；
- 每条记录标记 `reported`、`reconciled`、`estimated` 或 `missing`；
- 只有 `reported/reconciled` 进入保守 Token 汇总；
- 分别报告 input、output、cache-read、cache-write 和 total；
- 报告覆盖率、缺失数、每任务中位数以及 pass/no-pass 任务用量；
- 仅当双方使用同一 provider meter、缓存拆分和重试覆盖时，才做跨产品 Token 效率结论；否则仅描述各产品内部用量足迹。

### 5.7 分类与资源

- 七类任务分别报告 pass/有效结果任务、正常端到端成功和 timeout；
- 报告每任务所需 MCP server 数量分组的描述性结果；
- 报告 peak memory、CPU time、OOM scope、磁盘和网络覆盖率；
- 报告 Swap 当前/峰值使用量及 swap in/out；Swap 配置不一致的运行不得进入跨产品资源比较；
- CPU/RAM 只有在 cgroup 采集位置完全一致时进入跨产品比较；
- 不把成功率、时间、Token 和资源合成一个加权总分。

## 6. 各阶段任务清单

### 6.1 M0：冻结证据采集与运行资格门禁

本文件的评测方案已经冻结。M0 只冻结不可变输入、产品/模型/Adapter 契约、执行协议和资格主机；DeepSeek Key、Astra admin token 等外部 secret 不复制进 M0。Astra attempt 级产品用户名和密码是唯一例外：运行时保存到该 run 的 0600 私有工件并禁止发布，access/refresh token 不保存。未完成 M0 前不得进入 M1，未完成 M1 前禁止进入 M2/M3。

具体工作：

1. 校验 `sections-3.1-3.2.sha256`：Toolathlon detached source、108 题/首批 14 题、任务与 evaluator、任务/辅助镜像、Docker 和依赖明细；
2. 校验 `section-3.3.sha256`：Astra、Hermes、Adapter、模型、预算、权限、状态和 rendered runtime config；
3. 生成 `vm.freeze.json`：8C8G、Docker/cgroup、磁盘、固定 Swap、OOM/随机性/时钟证据；
4. 生成 `experiment.freeze.json`，内嵌执行、凭据隔离、结果目录、失败优先级和重跑契约，再以 `m0.sha256` 绑定上述四个权威根。

退出条件：`experiment.freeze.json:m0_qualification.status=GO`、`vm.freeze.json:qualification=GO`，且在 `freeze/` 目录执行 `sha256sum -c m0.sha256` 四项全通过。本次 M0 已满足退出条件；`m1_live_qualification=PENDING` 不回写为 M0 NO-GO。

### 6.2 M1：Adapter 与 live qualification

具体工作：

1. 使用已经冻结的内部/外部凭据指纹；真实应用凭据允许进入 fresh 任务容器，真实 DeepSeek Key 只进入各自 Model Proxy；
2. 引用已经通过的本地应用基线与 reset replay；`find-alita-paper` 不依赖共享可写应用，其逐运行 reset 为 fresh 工作区、fresh 任务容器和 fresh 产品状态；
3. 完成最小状态机：`reset → fresh task container → preprocess → Gateway → tools/list → Adapter/Agent → evaluator → 完整指标工件 → cleanup → 最终 artifact hash`；
4. 在 `find-alita-paper` 上按正式冻结配置运行 Astra 一次、reset 后运行 Hermes 一次；
5. 两次运行分别执行工件 Schema、关键字段、事件配对和哈希校验；
6. 验证任务容器、产品和公开工件不含 Model Proxy 的真实 Key，且 evaluator/ground truth 在 Agent 阶段不可见。

退出条件：两次运行均完成真实端到端链路并通过工件门禁。evaluator `no_pass` 是正式能力结果，不阻塞；基础设施 unavailable 或原始证据缺失按第 3.4 节只允许一次自动替代。通过门禁的两次运行直接计入 M2，不重复运行。

### 6.3 M2：14 题第一批正式评测

14 题按七个官方任务类型各取两题；选择依据是工具和副作用覆盖，不依据 Astra/Hermes 既有成绩。

| 顺序 | 类别 | 任务 ID | 主要覆盖 | 同题产品顺序 |
| ---: | --- | --- | --- | --- |
| 1 | Academic | `find-alita-paper` | `arxiv_local`、filesystem、scholarly；检索与下载 | Astra → reset → Hermes |
| 2 | Academic | `set-conf-cr-ddl` | emails、Google Calendar、`python_execute`；跨应用副作用 | Hermes → reset → Astra |
| 3 | Campus | `course-schedule` | filesystem、memory、Excel、PDF、fetch、web search | Astra → reset → Hermes |
| 4 | Campus | `canvas-homework-grader-python` | Canvas、filesystem、terminal、emails、Python | Hermes → reset → Astra |
| 5 | Daily | `arrange-workspace` | filesystem、terminal、PDF、Excel；本地文件变更 | Astra → reset → Hermes |
| 6 | Daily | `notion-movies` | Playwright、Notion、fetch、web search | Hermes → reset → Astra |
| 7 | Finance | `price-comparison` | filesystem、terminal、PDF、Google Cloud | Astra → reset → Hermes |
| 8 | Finance | `quantitative-financial-analysis` | Yahoo Finance、Google Sheets、Notion、terminal、filesystem | Hermes → reset → Astra |
| 9 | Office | `excel-data-transformation` | Excel、filesystem、terminal、Python | Astra → reset → Hermes |
| 10 | Office | `notion-hr` | filesystem、emails、Notion、PDF；跨应用写入 | Hermes → reset → Astra |
| 11 | Shopping | `shopping-helper` | Playwright、filesystem；网页检索与结构化工件 | Astra → reset → Hermes |
| 12 | Shopping | `woocommerce-stock-alert` | WooCommerce、Google Sheets、emails、filesystem | Hermes → reset → Astra |
| 13 | Tech | `git-bug-hunt` | Git、terminal、filesystem、emails | Astra → reset → Hermes |
| 14 | Tech | `k8s-safety-audit` | Kubernetes、Google Sheets、filesystem；8G 容量门禁 | Hermes → reset → Astra |

所有 14 题还要求统一的 `claim_done` 终止语义；task config 中的 context/history/overlong 辅助工具按第 4.2 节的共同策略处理。

第一批具体执行任务：

1. 每题先 reset，创建 fresh 任务容器，运行 preprocess，并在 Gateway ready 后现场保存 `tools/list` 与 Schema；
2. 按表中顺序运行第一个产品，随后无条件 evaluator；
3. 完整销毁任务容器并恢复外部应用状态；
4. 对同题重新 preprocess，再运行第二个产品和 evaluator；
5. 验证所有运行目录均满足第 4.4 节文件 Schema、关键字段与哈希门禁；
6. 验证 verify、timeout、时间、工具、Token、资源和根因原始证据存在；聚合留到 M4；
7. 检查未授权副作用、重复副作用、状态泄漏、OOM 和残留进程；
8. 前 14 题结束后不重复运行，直接继续剩余 94 题。

第一批不设置任务通过率门槛。某产品 evaluator no-pass 是能力结果，不阻塞后续评测；阻塞条件是协议、状态、资源、评分链或必需原始证据不可用。

### 6.4 M3：剩余 94 题正式评测

具体工作：

1. 使用附录 A 中除首批 14 题以外的 94 个任务，不因第一批成绩、难度、时长或任一产品失败删除任务；
2. 每题每个产品只保留 1 次正式有效运行；
3. 按附录 A 字典序执行，奇数位置 Astra 先、偶数位置 Hermes 先，共 54 题各自先运行；
4. 两个产品之间必须销毁任务容器、清空产品状态并运行冻结的应用 reset；
5. `workers=1`，不得同时运行两个任务或两个产品；
6. 每次运行结束后立即校验结果目录 Schema、哈希、evaluator 和资源记录；
7. 产品失败、模型失败、任务 timeout 或 evaluator no-pass 不重跑；
8. 只有独立证据确认的 Adapter 外、环境或 evaluator infra invalid 才允许获得一次替代运行；原运行和替代映射均保留；
9. 全部 216 个正式槽位具有 pass、no-pass、unavailable 或预注册 infra-invalid 终态后才退出本阶段。

正式任务清单完整列于附录 A。

### 6.5 M4：分析与报告

具体工作：

1. 校验 216 个正式槽位、freeze hash 和替代运行映射；
2. 生成任务完成总表和共同有效任务配对表；
3. 生成 timeout 配对分布和失败根因表；
4. 生成端到端、Agent、准备、evaluator 和 cleanup 时间表；
5. 生成终态工具调用与失败工具调用表；
6. 生成保守 Token 覆盖、输入/输出/缓存用量表；
7. 生成七类任务和 MCP server 数量分组结果；
8. 生成 8C8G 资源、OOM、磁盘和网络诊断；
9. 输出逐任务附录、无效运行附录、配置矩阵和复现 Manifest；
10. 在报告中明确单次运行、Adapter 接入和非官方排行榜口径的限制。

## 7. 逐运行 Go/No-Go 门禁

### 7.1 Go

每个运行只有同时满足以下条件才允许启动下一个运行：

1. 完成 reset、fresh 容器、preprocess、Gateway、现场 `tools/list`、Adapter/Agent、evaluator 和 cleanup；
2. 第 4.4 节 12 项必需工件全部存在、可解析且通过机器 Schema；
3. `artifacts.sha256` 覆盖同目录全部证据并逐项校验成功；
4. 所有冻结哈希、运行身份、阶段 wall-clock/monotonic 时间、模型请求和工具事件均有原始证据；
5. 每个模型请求都有 Token 观测字段、attempt、finish reason 和重试关系；provider 未报告的值使用结构化缺失对象；
6. evaluator 明确形成 pass/no-pass/unavailable，任意 Agent 终态都进入 evaluator；
7. failure root、原始错误码和证据路径存在；无失败时也生成明确的 `failure-evidence.json`；
8. 无 ground truth/evaluator 泄漏、跨任务记忆、残留产品进程或未登记外部副作用；
9. Astra/Hermes 实际模型端点、生成参数、权限和状态边界与冻结配置一致；
10. 原始证据完整；M4 聚合表是否已经生成不参与此门禁。

Token usage 不要求 provider 每个字段都上报，但每次模型请求必须保留完整规范字段和原始 provider response usage；缺失必须使用结构化缺失原因，不能静默缺失、填 0 或推测。

### 7.2 No-Go 或降级

- 任一运行在 8G 内存下因公共任务容器/Gateway/evaluator 无法建立可评分链路：暂停后续运行并保留基础设施证据；不得通过删除同类任务规避；
- Astra/Hermes 不能看到语义等价的工具 Schema：降级为原生产品栈结果，禁止做受控脚手架因果解释；
- 无法统一模型端点或生成参数：降级为原生产品栈结果；
- 状态不能稳定 reset、产品间存在任务污染：No-Go；
- Adapter 必须为某一侧增加额外重试、上下文辅助或动作修复才能运行：No-Go，先修 Adapter 边界；
- evaluator 或 ground truth 对 Agent 可见：该运行无效，并进行泄漏审计；
- Token 计量来源不等价：保留用量描述，取消跨产品 Token 效率结论。

## 8. 运行时间边界

以下只计算冻结的 Agent execution 正式槽位上界；产品/Gateway 启动、preprocess、evaluator、reset、cleanup 和工件固化使用第 3.3 节独立安全超时，不属于 Agent 预算，需另计日历时间。

```text
全部正式运行槽位时间上界
= (8 × 1,800 + 15 × 2,700 + 11 × 3,600 + 74 × 5,400) × 2 systems
= 988,200 seconds
= 274.5 aggregate hours
```

由于固定 `workers=1`，274.5 小时约为 11.44 天的纯 Agent 槽位上界；独立基础设施阶段、跨运行 reset 和无效运行处置会继续增加日历时间。正式排期在首批 14 题后使用实际端到端中位数和 P90 重算，不直接借用 Terminal-Bench 的吞吐估计，也不能把基础设施安全超时简单全部相加当作预期工期。

## 9. 预期报告结构

正式报告至少包含：

1. 口径、冻结配置与结论边界；
2. 108 题任务完成结果；
3. 共同有效任务配对结果；
4. timeout 配对分布；
5. Astra/Hermes no-pass 和 unavailable 根因；
6. 阶段时间；
7. 终态工具调用；
8. Token 数据口径与覆盖率；
9. 七类任务和工具广度结果；
10. 8C8G 资源诊断；
11. 逐任务结果与配置附录；
12. 单次运行、Adapter 和非官方排行榜限制。

## 附录 A：冻结 commit 的 108 个正式任务

来源：Toolathlon commit `2aed2468858f15818acafa178518390cc4b0f5cb` 的 `tasks/finalpool` 目录；不包含文件 `task_conflict.json`。

```text
ab-testing
academic-pdf-report
academic-warning
add-bibtex
apply-phd-email
arrange-workspace
canvas-arrange-exam
canvas-art-manager
canvas-art-quiz
canvas-do-quiz
canvas-homework-grader-python
canvas-list-test
canvas-new-students-notification
canvas-submit-late-work
cooking-guidance
course-assistant
course-schedule
courses-ta-hws
cvpr-research
dataset-license-issue
detect-revised-terms
dietary-health
email-paper-homepage
excel-data-transformation
excel-market-research
experiments-recordings
fillout-online-forms
filter-low-selling-products
find-alita-paper
flagged-transactions
game-statistics
gdp-cr5-analysis
git-bug-hunt
git-milestone
git-repo
hk-top-conf
huggingface-upload
identify-all-songs
imagenet
inter-final-performance-analysis
interview-report
inventory-sync
investment-decision-analysis
invoice-org
ipad-edu-price
k8s-deployment-cleanup
k8s-mysql
k8s-pr-preview-testing
k8s-redis-helm-upgrade
k8s-safety-audit
landing-task-reminder
language-school
latex-prompt-box
live-transactions
llm-training-dataset
logical-datasets-collection
machine-operating
meeting-assign
merge-hf-datasets
mrbeast-analysis
music-analysis
nhl-b2b-analysis
notion-find-job
notion-hr
notion-movies
notion-personal-website
nvidia-market
nvidia-stock-analysis
oil-price
paper-checker
payable-invoice-checker
personal-website-construct
ppt-analysis
price-comparison
privacy-desensitization
profile-update-online
quantitative-financial-analysis
reimbursement-form-filler
sales-accounting
search-ca-school
set-conf-cr-ddl
shopping-helper
sla-timeout-monitor
stock-build-position
student-interview
subway-planning
sync-todo-to-readme
task-tracker
train-ticket-plan
travel-exchange
travel-expense-reimbursement
trip-adviser
trip-itinerary-generator
university-course-selection
update-material-inventory
upenn-campus-route
verl-dataset
vlm-history-completer
wandb-best-score
wandb-shortest-length
woocommerce-customer-survey
woocommerce-new-product
woocommerce-new-welcome
woocommerce-product-recall
woocommerce-stock-alert
woocommerce-update-cover
yahoo-analysis
youtube-repo
```

## 10. 主要依据

- [Toolathlon frozen commit](https://github.com/hkust-nlp/Toolathlon/tree/2aed2468858f15818acafa178518390cc4b0f5cb)
- [Toolathlon decoupled agent loop](https://github.com/hkust-nlp/Toolathlon/blob/2aed2468858f15818acafa178518390cc4b0f5cb/DECOUPLED_AGENT_LOOP.md)
- [Toolathlon decoupled run script](https://github.com/hkust-nlp/Toolathlon/blob/2aed2468858f15818acafa178518390cc4b0f5cb/scripts/run_single_decoupled.sh)
- [Astra 与 Hermes：Terminal-Bench 常规任务对比](../../reports/TerminalBench2.1-analysis/astra-hermes-c0-latest-88-task-comparison.md)
- [Astra Agent 产品评测计划 v0.5](v0.5.md)
