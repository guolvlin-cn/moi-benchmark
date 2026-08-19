# Lenovo 本地 RAG 基准测试操作指南

本文档对应当前本地环境和隔离式串行基准脚本。所有命令都在仓库根目录执行：

```bash
cd /Users/muuushroom/gitrepos/moi-benchmark/rag
```

本指南只处理明确指定的镜像和容器启停，不删除数据库 Volume，不扩容 Colima，不在未确认模型账户前切换 MaxKB 供应商。

## 1. 记录清理前状态

以下命令只读，不会修改环境：

```bash
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker system df
colima ssh -- df -h /var/lib/docker
```

本轮观察到：Colima Docker 数据盘约 62% 使用率，但宿主机根文件系统约 94%；Dify 的 Weaviate 数据目录是宿主机绑定目录。四个平台如果同时运行会使 11GB Colima 内存发生 OOM，因此正式测试采用“每次只保留目标平台栈”的隔离式串行方式。

## 2. 定向清理未使用镜像

先确认候选镜像仍然没有被任何容器引用：

```bash
docker system df -v
docker ps -a --format '{{.Image}}' | sort -u
```

本轮已删除且验证不存在的镜像如下：

```text
ghcr.io/zeng-weijun/omnidocbench-eval:repro-ubuntu2204
infiniflow/ragflow:v0.26.4
```

原删除命令为：

```bash
docker image rm \
  ghcr.io/zeng-weijun/omnidocbench-eval:repro-ubuntu2204 \
  infiniflow/ragflow:v0.26.4
```

如果某个镜像提示正在被引用，跳过该镜像，不要强制删除。不要执行以下命令：

```bash
docker system prune --volumes
docker volume prune
```

清理后重新确认空间：

```bash
docker system df
colima ssh -- df -h /var/lib/docker
```

本轮删除后未执行 `prune`，也未删除任何数据卷。

## 3. 恢复 FastGPT

```bash
docker compose \
  -p moi_fastgpt_local \
  -f .local-services/fastgpt_local/compose/docker-compose.pg.yml \
  up -d
```

检查状态：

```bash
docker compose \
  -p moi_fastgpt_local \
  -f .local-services/fastgpt_local/compose/docker-compose.pg.yml \
  ps

docker logs --tail 100 fastgpt-pg
docker logs --tail 100 fastgpt-mongo
curl -sS -o /dev/null -w '%{http_code}\n' --max-time 10 http://127.0.0.1:3000/
```

预期结果：

- PostgreSQL 不再出现 `No space left on device`；
- MongoDB 不再是 `unhealthy`；
- `fastgpt-app` 由 `Created` 变为运行状态；
- 3000 端口不再返回连接拒绝。

如果仍失败，保留日志并跳过 FastGPT，不要删除 FastGPT 的数据库 Volume。Mongo 曾因磁盘满后只剩外层 bash 而不健康，使用一次正常重启即可恢复：

```bash
docker restart fastgpt-mongo
```

## 4. MaxKB 模型账户处理

MaxKB 当前检索接口正常，但公共应用返回 HTTP 500。此前捕获的具体原因是上游模型账户 `account_overdue`，这不能通过本地脚本修复。

先刷新本地管理员 Token：

```bash
python3 local-rag-platforms/maxkb_local/maxkb_refresh_admin_token.py
```

然后打开：

```text
http://127.0.0.1:8090/admin/
```

在 MaxKB 管理后台检查当前应用绑定的聊天模型：

1. 确认模型供应商账户仍有效；
2. 确认 API Key、余额和调用权限正常；
3. 在模型管理页面执行一次最小测试；
4. 优先恢复原模型账户，不要为了跑基准擅自切换供应商。

如果没有可用模型账户，则跳过 MaxKB 公共应用事件测试；MaxKB 的检索延迟仍可保留，Event Throughput 和 TTFE 记为 N/A。

## 5. 隔离式串行执行基准

为避免 Weaviate 因 OOM 在恢复阶段被杀死，新增了 `--platforms` 参数。每个平台使用完全相同的 Query、seed、连接数和超时，单独启动目标平台后执行：

```bash
COMMON='--count 10 --seed 20260814 --connections 4 --timeout 120 --platform-execution serial'
python3 local-rag-platforms/scripts/benchmarks/lenovo/lenovo_latency_benchmark.py $COMMON --platforms dify
python3 local-rag-platforms/scripts/benchmarks/lenovo/lenovo_latency_benchmark.py $COMMON --platforms fastgpt
python3 local-rag-platforms/scripts/benchmarks/lenovo/lenovo_latency_benchmark.py $COMMON --platforms moi
python3 local-rag-platforms/scripts/benchmarks/lenovo/lenovo_latency_benchmark.py $COMMON --platforms maxkb
```

四次运行的 `selected-queries.jsonl` SHA-256 应一致。将四个独立结果合并为最终报告：

```bash
python3 local-rag-platforms/scripts/reports/merge_lenovo_latency_reports.py \
  --output runs/lenovo-local-latency/<final-run-id> \
  --moi runs/lenovo-local-latency/<moi-run-id> \
  --dify runs/lenovo-local-latency/<dify-run-id> \
  --fastgpt runs/lenovo-local-latency/<fastgpt-run-id> \
  --maxkb runs/lenovo-local-latency/<maxkb-run-id>
```

脚本会在 `runs/lenovo-local-latency/<run-id>/` 下生成：

- `report.md`：汇报版报告；
- `results.json`：机器可读结果；
- `selected-queries.jsonl`：本轮固定的 10 个 Query；
- 各平台的采样和错误信息。

## 6. Empty Workflow QPS

当前四个平台都没有配置独立的空工作流，因此脚本会正确显示 `N/A`，不会把真实 RAG 请求伪装成空工作流。

如果后续要补测，需要在每个平台创建一个只返回固定文本的应用或工作流：

- 不连接 Lenovo 知识库；
- 不执行向量检索；
- 不调用外部模型；
- 使用统一的固定响应；
- 为每个平台记录独立的 endpoint、应用 ID 和认证信息。

这些资源准备好后，还需要为基准脚本增加对应配置；在此之前该指标应继续保留为 N/A。

## 7. 当前不可完成项

以下项目在没有额外运行时条件时跳过：

| 项目 | 原因 | 报告处理 |
|---|---|---|
| MaxKB 公共应用事件指标 | 当前本地公开 Chat API 返回 HTTP 500，响应指向上游模型账户/模型配置 | retrieval 保留；Event Throughput、TTFE 记为 N/A，账户恢复后再补测 |
| MOI TTFE/Event Throughput | 当前是 CLI，不是流式 HTTP API | 保留检索延迟，其他 N/A |
| 四个平台 Empty Workflow QPS | 没有标准化空工作流 | N/A，不填 0 |

## 8. 2026-08-17 MaaS-aware 横向实测

本轮使用同一批 Lenovo Query（10 条、seed `20260814`），平台之间串行执行；MOI、Dify、MaxKB 的 embedding 资源核对为 Huawei MaaS `bge-m3/1024d`，FastGPT 当前 Lenovo 资源实际绑定 MatrixOrigin TaaS `bge-m3`。另外单独测量了 Huawei MaaS embedding 直连基线，避免把上游模型耗时误当成纯本地数据库耗时。

当前资源中 Dify、FastGPT 和 MaxKB 的聊天应用绑定 Qianfan，MOI 的 MaaS generation 配置未启用，所以生成 TTFE/Event Throughput 只代表当前部署，不作严格同模型排名；四个平台的本地检索结果仍可作为本轮主对比轨道。

[MaaS-aware 最终横向报告](runs/lenovo-local-latency/20260817-final-maas-aware-v4/report.md)

[MaaS-aware 机器可读结果](runs/lenovo-local-latency/20260817-final-maas-aware-v4/results.json)
