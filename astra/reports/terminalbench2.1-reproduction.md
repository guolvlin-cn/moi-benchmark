# Terminal-Bench 2.1 C0 当前结果与复现流程

更新日期：2026-08-14

本文记录 Astra、Hermes 和 Pi 三个 Terminal-Bench 2.1 baseline 的当前结果、结果生成实现，以及后续重跑和重新汇总的标准流程。文中的命令均从仓库根目录执行，不依赖个人绝对路径。

## 相关结果文件

- [Astra、Hermes 与 Pi 的 83 题严格配对结果](TerminalBench2.1-analysis/astra-hermes-pi-latest-83-task-comparison.md)
- [Astra、Hermes 与 Pi 的逐任务明细附录（CSV）](TerminalBench2.1-analysis/terminalbench2.1-astra-hermes-pi-task-detail-appendix.csv)

## 1. 统计口径

任务得分的唯一权威来源是 Harbor `result.json` 中的数值 verifier reward：

- `reward = 1`：verify pass；
- `reward = 0`：no-pass；
- reward 缺失或非数值：该次尝试没有可用评分，不按 0 分计入。

结果选择采用以下规则：

1. 发现指定结果根目录下所有合法 attempt；
2. 按 batch 目录时间、`finished_at` 和结果路径确定每题最新 attempt；
3. 排除 `tune-mjcf`；
4. 只保留最新 attempt 的 reward 为数值 0 或 1 的任务；
5. 最新 attempt 没有数值 reward 时，不回退到更早的已评分 attempt。

Timeout 是独立观测维度。`verify pass` 且没有 timeout 才记作 normal end-to-end pass；发生 timeout 后 verifier 仍通过的任务保留为 pass，但单独列示。

## 2. 实验环境与配置

| 项目                      | Astra                                                                                                            | Hermes                                  | PI                                      |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------- | --------------------------------------- | --------------------------------------- |
| 产品版本                  | Astra CLI 本地 AMD64 release build，`v0.0.5-4-g844473c68`；commit `844473c68649d8ea43e10b616dc4fbf98e2321e8` | `v2026.7.20`                          | `0.73.1`                              |
| API 模型 ID               | `glm-5.2`                                                                                                      | `zai/glm-5.2`                         | `zai/glm-5.2`                         |
| 模型提供方                | BigModel，经 Astra 的 OpenAI-compatible provider                                                                 | Z.AI                                    | Z.AI                                    |
| 推理参数                  | `temperature=0`；其余默认                                                                                      | `temperature=0`；其余默认             | `temperature=0`；其余默认             |
| 配置的 max turns          | 50                                                                                                               | 90                                      | 未显式设置                              |
| 本批实际最高 Agent 回合数 | 未单列                                                                                                           | 47                                      | 122                                     |
| 超过 50 回合的任务        | 未单列                                                                                                           | 0 / 88                                  | 9 / 84                                  |
| 产品实际执行预算          | 每题原始`[agent].timeout_sec` 的 2 倍                                                                          | 每题原始`[agent].timeout_sec` 的 2 倍 | 每题原始`[agent].timeout_sec` 的 2 倍 |

Hermes 虽配置 `max_turns=90`，但本批保存事件中实际最高为 47 回合；PI 未设置显式 max-turn 限制，9 个任务实际超过 50 回合，最高为 `make-mips-interpreter` 的 122 回合。因此，本报告如实保留上述差异，而不将历史运行重述为统一 50 回合。后续 Astra 相关对比测试将统一调整 max-turn 口径；该调整不追溯改变本报告的历史结果。

| 环境项         | 配置                                                                                     |
| -------------- | ---------------------------------------------------------------------------------------- |
| 数据集         | Terminal-Bench 2.1；三方使用同一任务 ID 集合，严格横向比较取三方均有验证结果的 83 个任务 |
| 任务环境       | Docker；每个 trial 使用独立任务容器，按任务声明的资源配置运行                            |
| Host OS        | macOS 15.6（24G84）                                                                      |
| CPU 架构与规格 | Apple M3，ARM64，8 核（4 性能核 + 4 能效核）                                             |
| 主机内存       | 16 GB                                                                                    |
| Docker         | Docker Desktop 4.82.0                                                                    |
| Harbor         | 0.20.0                                                                                   |

## 数据覆盖

必须在每次正式运行前记录 `git rev-parse HEAD`。这是为了把 runner/adapter 的具体实现与结果关联；仅记录产品版本无法区分本仓库中后续的监督、超时和 verifier 修订。

## 3. 当前结果快照

### 3.1 各产品自身的最新有效结果

下表来自三个 `analysis/v2/output/*-latest-verified-summary.json`。各行分母不同，只描述各产品当前已取得数值 verifier reward 的覆盖范围。

| 产品   | 最新有效任务 | verify pass | no-pass | pass rate | timeout | pass 且无 timeout |
| ------ | -----------: | ----------: | ------: | --------: | ------: | ----------------: |
| Astra  |           86 |          44 |      42 |     51.2% |      37 |                41 |
| Hermes |           88 |          50 |      38 |     56.8% |      10 |                47 |
| Pi     |           84 |          52 |      32 |     61.9% |      14 |                47 |

这里的最后一列统一按 `verify pass AND timeout=false` 计算，不采用 Astra extractor 中还要求产品 lifecycle 正常的旧 `normal_e2e_pass` 字段；这与本文“不把 lifecycle 字段作为评分门槛”的口径一致。

当前缺少最新数值 reward 的任务：

- Astra：`train-fasttext`、`torch-tensor-parallelism`；
- Hermes：无；
- Pi：`path-tracing-reverse`、`sam-cell-seg`、`torch-pipeline-parallelism`、`torch-tensor-parallelism`。

### 3.2 83 题严格配对结果

严格配对样本只保留 Astra、Hermes、Pi 三方均有数值 verifier reward 的 83 个任务。

| 指标               | Astra | Hermes |    Pi |
| ------------------ | ----: | -----: | ----: |
| verify pass        |    43 |     47 |    52 |
| no-pass            |    40 |     36 |    31 |
| pass rate          | 51.8% |  56.6% | 62.7% |
| normal E2E pass    |    40 |     45 |    47 |
| pass after timeout |     3 |      2 |     5 |
| timeout            |    35 |      8 |    13 |

三方均通过 26 题，三方均未通过 14 题。按任务作者难度标签统计：

| 难度         | Astra | Hermes | Pi |
| ------------ | ----: | -----: | -: |
| Easy（4）    |     3 |      4 |  4 |
| Medium（54） |    32 |     31 | 35 |
| Hard（25）   |     8 |     12 | 13 |

83 题配对样本的运行时间：

| 产品   | E2E 总计 |  E2E median / P90 | Agent 总计 | Agent median / P90 | Verifier 总计 |
| ------ | -------: | ----------------: | ---------: | -----------------: | ------------: |
| Astra  |  39.16 h | 16.48 / 61.51 min |    30.86 h |  14.90 / 50.64 min |        5.52 h |
| Hermes |  28.97 h | 12.87 / 38.86 min |    26.91 h |  11.75 / 36.13 min |        1.58 h |
| Pi     |  31.87 h | 13.34 / 61.79 min |    29.01 h |  11.25 / 60.05 min |        2.02 h |

工具调用和 token 的采集口径不同，不能直接解释为产品效率或成本排名。配对样本中：

- Astra 统计主 Agent provider usage，不包含 Intent Judge；80/83 有完整 token，total 为 30,980,584；
- Hermes 使用 `agent/hermes-run.json.usage`；74/83 有完整 token，total 为 86,584,173；
- Pi 使用 `input + cache + output`；83/83 有完整 token，total 为 176,757,631。

不统计美元成本。

## 4. 结果实现链路

每个产品的结果都经过同一条逻辑链路：

```text
固定 Terminal-Bench task
  -> 产品专属 C0 adapter
  -> Harbor 0.20 trial/result.json
  -> 产品专属 analysis/v2 extractor
  -> latest verified CSV/JSON/Markdown
  -> 三方 task_id 严格内连接后的 paired report
```

### 4.1 Astra

- runner：`astra/runners/scripts/astra-terminal-bench-all-c0.sh`
- adapter/config：`astra/runners/astra_terminal_bench/`
- extractor：`astra/runs/astra-c0-all-jobs/analysis/v2/extract_astra_c0_trials.py`
- 当前历史结果同时扫描：
  - `work/astra-c0-all-jobs`
  - `work/astra-c0-rerun-from-scratch-33/jobs`

Astra runner 每次启动完整 89 题，不是 pending/resume runner。每次完整复现必须使用新的 `--run-name`；建议同时使用新的 `--jobs-dir`，避免历史 attempt 参与 latest selection。

当前 runner 的 timeout 策略为产品任务预算 `upstream timeout x 2.25`，Harbor agent phase 为 `upstream timeout x 2.5`。

### 4.2 Hermes

- runner：`astra/runners/scripts/hermes-terminal-bench-all-c0.sh`
- adapter/config：`astra/runners/hermes_terminal_bench/`
- extractor：`astra/runs/hermes-c0-all-jobs/analysis/v2/extract_hermes_c0_trials.py`
- 默认结果根：`work/hermes-c0-all-jobs`

Hermes 使用共享预构建 runtime 和按题构建的薄 task image。runner 通过 pending queue 恢复未完成任务，并通过 cohort fingerprint 防止修改后的 adapter、Dockerfile、C0 core 或配置继续写入旧结果 cohort。

当前本机旧 `work/hermes-c0-all-jobs` 的 fingerprint 与现有代码不同，不能直接向该目录追加结果。`--state-dir` 只改变队列/汇总目录，不改变 jobs root，也不能绕过这一限制。后续正式复现应满足二者之一：

1. 在干净 workspace 中生成全新的 `work/hermes-c0-all-jobs`；或
2. 先为 Hermes runner实现显式 `--jobs-dir`，再使用全新的结果根。

不要删除 fingerprint 或混写旧目录；否则无法判断结果来自哪一版 adapter。

### 4.3 Pi

- runner：`astra/runners/scripts/pi-terminal-bench-all-c0.sh`
- adapter/config：`astra/runners/pi_terminal_bench/`
- extractor：`astra/runs/pi-c0-all-jobs/analysis/v2/extract_pi_c0_trials.py`
- 默认结果根：`work/pi-c0-all-jobs`

Pi runner 的 canonical cohort 为 88 题，生成队列时排除 `tune-mjcf`。调度器使用 3 个 memory token：

- 8 GB task 独占；
- 4 GB task 最多与一个 2 GB task并行；
- 最多三个 2 GB task并行。

`UV_CONCURRENT_DOWNLOADS=2` 只作用于 verifier；在单个 all-C0 runner 内，最坏 uv 下载并发为 6。不要在同一宿主同时启动多个 Pi all-C0 runner，否则该上限不再是宿主全局上限。

当前 Pi runner 会准备 verifier-only 的 uv 0.9.5 与 CPython standalone bootstrap cache。它在 Agent phase 结束后注入，不向 Agent 提供任务答案或额外能力。大型 PyTorch/Hugging Face/package wheel cache 尚未启用；相应 verifier 或 Agent 下载仍依赖网络与代理。

## 5. 通用复现准备

先从仓库根目录设置公共变量：

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

export MOI_BENCH_DATA_ROOT="$repo_root"
export HARBOR_BIN="${HARBOR_BIN:-$HOME/.local/share/uv/tools/harbor/bin/harbor}"
export PYTHONPATH="$repo_root${PYTHONPATH:+:$PYTHONPATH}"

git status --short
git rev-parse HEAD
"$HARBOR_BIN" --version
docker version
```

运行前必须确认：

1. Harbor 输出 `0.20.0`；
2. `work/terminal-bench-2-1` 的 HEAD 是固定 dataset commit；
3. `work/terminal-bench-2-1/tasks` 没有本地改动；
4. Docker Desktop 资源为 8 CPU、8 GB memory、1 GB swap；
5. 代理端口如使用 7892，容器应通过 `host.docker.internal:7892` 访问；不要在容器内使用宿主的 `127.0.0.1:7892`；
6. 同一宿主一次只运行一个 full-run scheduler；
7. 正式运行期间使用 `caffeinate -dimsu`，防止 macOS 因空闲进入睡眠。

`caffeinate -dimsu` 的含义是运行命令期间阻止 display、idle system、disk 和 user-idle system sleep；它不改变任务 CPU、内存或 timeout。

## 6. Astra 全量复现

准备 Astra endpoint 和 Linux AMD64 binary：

```bash
export ASTRA_API_URL="http://host.docker.internal:17001"
export ASTRA_TBENCH_LINUX_BINARY="$repo_root/work/astra-linux-build-amd64/target/release/astra"
export ASTRA_TBENCH_MODEL="c5bde5de-9805-48d4-a016-1db6e6018fc4"
export ASTRA_TBENCH_READ_MEMORY="false"

run_name="astra-c0-$(date '+%Y%m%d-%H%M%S')"
jobs_dir="$repo_root/work/astra-c0-reproductions/$run_name"
```

先预检，再运行：

```bash
/bin/bash astra/runners/scripts/astra-terminal-bench-all-c0.sh \
  --check \
  --concurrency 1 \
  --run-name "$run_name" \
  --jobs-dir "$jobs_dir"

caffeinate -dimsu /bin/bash astra/runners/scripts/astra-terminal-bench-all-c0.sh \
  --yes \
  --concurrency 1 \
  --run-name "$run_name" \
  --jobs-dir "$jobs_dir"
```

runner 在结果根的 `.reproduction/<run-name>.tsv` 写入不含 secret 的复现 manifest，包括 workspace/dataset commit、Harbor、Astra binary 描述、模型、并发、timeout policy 和退出码。

## 7. Hermes 全量复现

安全读取 API key，避免把 key 写入 shell history：

```bash
read -rsp "GLM_API_KEY: " GLM_API_KEY
echo
export GLM_API_KEY
```

在干净且没有旧 Hermes cohort 的 workspace 中先预检：

```bash
/bin/bash astra/runners/scripts/hermes-terminal-bench-all-c0.sh --check
```

预检通过后运行全部 pending task：

```bash
caffeinate -dimsu /bin/bash \
  astra/runners/scripts/hermes-terminal-bench-all-c0.sh
```

分批运行可使用：

```bash
caffeinate -dimsu /bin/bash \
  astra/runners/scripts/hermes-terminal-bench-all-c0.sh \
  --max-tasks 5
```

正常 resume 不需要 `--rerun-all`。后续实验不使用 `--retry-audit-failures`，因为 lifecycle audit 不属于评分门槛。

如果预检报告 `full-run cohort changed; refusing to mix result generations`，应停止；当前脚本尚不能通过参数选择新的 jobs root。

## 8. Pi 全量复现

准备 Z.AI key：

```bash
read -rsp "ZAI_API_KEY: " ZAI_API_KEY
echo
export ZAI_API_KEY
```

Pi 的 uv/CPython bootstrap cache由宿主下载。需要让这一步使用本机 7892 端口时设置：

```bash
export PI_TBENCH_CACHE_PROXY_URL="http://127.0.0.1:7892"
```

这个变量只影响宿主执行的 cache preparation，不会把代理注入 task container。容器内 Agent/verifier 的公网流量仍使用 Docker Desktop 的代理设置；如果 Docker Desktop 配置为本机 7892，它会负责把容器流量转发到该端口。

预检 canonical 88 题队列：

```bash
/bin/bash astra/runners/scripts/pi-terminal-bench-all-c0.sh --check
```

正常运行只调度尚未取得 terminal result 的任务：

```bash
caffeinate -dimsu /bin/bash \
  astra/runners/scripts/pi-terminal-bench-all-c0.sh
```

先做单题 smoke：

```bash
caffeinate -dimsu /bin/bash \
  astra/runners/scripts/pi-terminal-bench-all-c0.sh \
  --max-tasks 1
```

指定任务时，从 canonical queue 复制完整 TSV 行，不能只写 task id：

```bash
task_id="filter-js-from-html"
retry_queue="$repo_root/work/pi-c0-all-state/manual-retry.queue.tsv"
grep -F "${task_id}"$'\t' \
  "$repo_root/work/pi-c0-all-state/resource.queue.tsv" \
  > "$retry_queue"

caffeinate -dimsu /bin/bash \
  astra/runners/scripts/pi-terminal-bench-all-c0.sh \
  --retry-queue "$retry_queue"
```

重跑完整 88 题可把 canonical queue 作为 retry queue，但这会把新 attempt 写入现有 jobs root。正式、可独立归档的复现更适合使用新的 `MOI_BENCH_DATA_ROOT`，其中必须同时包含固定 dataset checkout：

```bash
caffeinate -dimsu /bin/bash \
  astra/runners/scripts/pi-terminal-bench-all-c0.sh \
  --retry-queue "$repo_root/work/pi-c0-all-state/resource.queue.tsv"
```

## 9. 重新生成 analysis/v2

### 9.1 当前历史 Astra 汇总

```bash
python3 astra/runs/astra-c0-all-jobs/analysis/v2/extract_astra_c0_trials.py \
  --root "$repo_root/work/astra-c0-all-jobs" \
  --root "$repo_root/work/astra-c0-rerun-from-scratch-33/jobs" \
  --output-dir "$repo_root/work/astra-c0-all-jobs/analysis/v2/output" \
  --matrixone-token-source off
```

新 Astra 完整 reproduction 应只把该次新的 `jobs_dir` 传给 `--root`，不要自动混入历史目录。

### 9.2 Hermes 汇总

```bash
python3 astra/runs/hermes-c0-all-jobs/analysis/v2/extract_hermes_c0_trials.py \
  --root "$repo_root/work/hermes-c0-all-jobs" \
  --output-dir "$repo_root/work/hermes-c0-all-jobs/analysis/v2/output"
```

### 9.3 Pi 汇总

```bash
python3 astra/runs/pi-c0-all-jobs/analysis/v2/extract_pi_c0_trials.py \
  --root "$repo_root/work/pi-c0-all-jobs" \
  --output-dir "$repo_root/work/pi-c0-all-jobs/analysis/v2/output"
```

每个 extractor 至少产生：

- `*-latest-verified-trials.csv`
- `*-latest-verified-no-pass.csv`
- `*-latest-verified-summary.json`
- `*-latest-verified-report.md`

## 10. 三方严格配对报告

当前三方报告的输入为：

```text
work/astra-c0-all-jobs/analysis/v2/output/astra-c0-latest-verified-trials.csv
work/hermes-c0-all-jobs/analysis/v2/output/hermes-c0-latest-verified-trials.csv
work/pi-c0-all-jobs/analysis/v2/output/pi-c0-latest-verified-trials.csv
```

配对算法必须：

1. 对三个 CSV 按 `task_id` 做严格内连接；
2. 检查连接后每个产品每题只有一行；
3. 以交集任务数作为所有横向比例的共同分母；
4. 分开统计 verifier reward、timeout、normal E2E pass、时间、工具和 token；
5. 不把缺 reward 当作 0，不使用更早 attempt 回填。

当前 83 题三方 Markdown 是结果快照，仓库尚没有已提交的三方 report generator。因此目前可以由三个 extractor 复现单产品 v2 输出，但还不能用一条受版本控制的命令重建三方 Markdown。正式发布前应把 paired join/report 生成器纳入仓库并增加行数、唯一键和分母测试；在此之前，三方报告中的数值需要与三个 CSV 交叉核验。

## 11. 复现验收清单

每次完整实验归档以下内容：

- workspace commit 与 `git status --short`；
- dataset commit；
- Harbor、产品、模型和 provider 版本；
- Docker Desktop 版本及 CPU/memory/swap；
- runner 配置、命令和非 secret 环境变量；
- 产品和 Harbor timeout policy；
- task queue 与排除项；
- 每个 trial 的 `result.json`、Agent 轨迹、stdout/stderr 和 verifier artifacts；
- extractor 版本和完整 `analysis/v2/output`；
- 缺 reward、timeout、API 余额/通信故障与 verifier infrastructure failure 清单；
- 三方比较所使用的严格 task-id 交集。

API 余额不足、模型通信失败、verifier 网络失败和真实任务 no-pass 必须分别归因，但只有数值 verifier reward 进入当前分数。C0 lifecycle 字段继续保存用于诊断，不参与后续实验的有效性门槛。

## 12. 当前已知复现边界

1. 当前 83 题报告为分批运行，不是由现有三个 runner 在同一时间窗口一次性重跑产生。
2. 历史三方 max-turn 和 timeout 配置并不完全一致；新实验必须统一或明确披露差异。
3. Astra token 不含 Intent Judge，Hermes 和 Pi 的 cache token 口径也不同。
4. Hermes 旧 jobs root 与当前 cohort fingerprint 不一致，不能原地追加。
5. Pi 的 verifier bootstrap cache只覆盖 uv/CPython；大 wheel、模型、Git 和任务资源仍可能受到网络影响。
6. 三方 paired-report generator 尚未提交；当前可自动复现的是三个单产品 v2 数据集。
