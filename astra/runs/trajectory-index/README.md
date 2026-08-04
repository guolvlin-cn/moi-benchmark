# Astra / Hermes 轨迹索引

索引由仓库内三个运行目录生成，每行对应一个 task attempt，不改写或移动已复制的轨迹文件：

| 索引                                                | 原始目录                                 | 轨迹记录                                                                                    |
| --------------------------------------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------- |
| [Astra initial batch](astra-c0-all-jobs.csv)            | `runs/astra-c0-all-jobs/`              | `astra-trajectory/`、`step_events.jsonl`、`server-events.jsonl`、`controller.jsonl` |
| [Astra rerun-33](astra-c0-rerun-from-scratch-33.csv) | `runs/astra-c0-rerun-from-scratch-33/` | 同上，位于 `jobs/` 下的 task attempt |
| [Hermes batch](hermes-c0-all-jobs.csv)                  | `runs/hermes-c0-all-jobs/`             | `hermes-run.json`、`hermes-driver.stdout.txt`、`controller.jsonl`                     |

## 字段

索引只保留用于定位和审计的元数据：批次、task、attempt 路径、session/run ID、Verifier reward、产品终态、轨迹状态、manifest SHA-256、事件/文件计数和时间戳。轨迹文件本身保存在对应的 `runs/` 批次目录中。

`raw_relative_path` 是相对于仓库根目录的路径，可直接定位到对应的 `runs/` 记录。

## 重新生成

在仓库根目录执行：

```bash
python3 astra/runs/trajectory-index/build_index.py
```

脚本只读取上述三个目录，输出三个 CSV 和一个合并的 `trajectory-index.json`。它不会修改运行记录。
