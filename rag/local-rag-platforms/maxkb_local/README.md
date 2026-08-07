# MaxKB local（v2.10.4-lts）

本方案只在 Dify 停止后运行 MaxKB；MOI 的 `moi-openxml-parser` 与
`matrixone` 必须保持运行。MaxKB 服务留在本机 Colima，LLM/Embedding
仅通过 MatrixOrigin TaaS 出网，因此部署类型是 `LOCAL_VARIANT`，不是
fully offline。

## 已核对的不变量

- 镜像：`1panel/maxkb:v2.10.4-lts`
- 本地架构：`linux/arm64`
- OCI index digest：`sha256:20205df1ba6eef4e4276e48c892038de72cf8618d1e1c1d50eb1f535d45dfedc`
- arm64 manifest digest：`sha256:4d8c2807cf0fdd271d4e06ffa6645faa7ac87c09f6ad2fdb1a1e2035731f2386`
- 本地 image ID：`sha256:20205df1ba6eef4e4276e48c892038de72cf8618d1e1c1d50eb1f535d45dfedc`
- 镜像配置：内部端口 `8080`，`PGDATA=/opt/maxkb/data/postgresql/pgdata`，声明卷 `/opt/maxkb`
- 映射：仅监听 `127.0.0.1:8090`，持久化到 `.local-services/maxkb_local/data:/opt/maxkb`

镜像环境记录的 build commit 是 `69701d4`，而官方 tag checkout
`v2.10.4-lts` 是 `fd6141e...`。所以源码候选路由只能帮助 discovery，运行
实例中智能体概览显示的 API 文档/Base URL 才是最终合约。

当前阶段只能执行只读核对，不能执行 `start`：

```bash
local-rag-platforms/maxkb_local/maxkb-local.sh verify-image
```

## Dify 停止后的启动

脚本会拒绝在任何 `moi_dify_local-*` 容器运行、MOI 两个容器未运行、8090
已占用、镜像/digest/架构不符或同名 MaxKB 容器已存在时启动。

```bash
local-rag-platforms/maxkb_local/maxkb-local.sh start
```

它实际执行的固定命令为：

```bash
mkdir -p "$PWD/.local-services/maxkb_local/data"
docker run -d \
  --name moi-maxkb-local \
  --restart unless-stopped \
  --platform linux/arm64 \
  --pull never \
  -p 127.0.0.1:8090:8080 \
  -v "$PWD/.local-services/maxkb_local/data:/opt/maxkb" \
  1panel/maxkb@sha256:20205df1ba6eef4e4276e48c892038de72cf8618d1e1c1d50eb1f535d45dfedc
```

等待 `http://127.0.0.1:8090/admin/` 可访问。不要停止 MOI，也不要把 8080
映射给 MaxKB。

## 管理员与 TaaS provider

1. 打开 `http://127.0.0.1:8090/admin/`，使用官方初始账号 `admin` /
   `MaxKB@123..` 登录，立即在个人信息中修改密码；新密码只保存在本地
   密码管理器或 `.local-services/maxkb_local/runtime.env`，不要写入日志。
2. 在“模型 → 全部模型 → OpenAI → 添加模型”分别创建两个记录：
   - 大语言模型：基础模型填 `TAAS_CHAT_MODEL`；API URL 填
     `https://api-taas.moi.matrixorigin.cn/v1`；API Key 填 `TAAS_API_KEY`。
   - 向量模型：基础模型填 `TAAS_EMBEDDING_MODEL`（当前 TaaS `/models`
   返回的 endpoint ID 为 `bge-m3`）；同一 API URL/API Key；Dimensions
     留空（TaaS 不接受自定义 `dimensions`）。
3. 两个记录都要通过 MaxKB 的保存时连通性验证。不要把 TaaS key 放入
   智能体提示词、API discovery artifact 或 shell history。

千帆作为独立备用 Provider 时，再创建两个 OpenAI 记录，不覆盖 TaaS：

- LLM：API URL `https://qianfan.baidubce.com/v2`，模型
  `deepseek-v4-flash`；
- 向量：同一 API URL，模型 `qwen3-embedding-8b`，固定维度 4096；
- 重排：模型 `qwen3-reranker-8b`，接口 `/v2/rerank`；
- Dimensions 可留空时优先留空，避免发送千帆未支持的 `dimensions` 参数；
- 使用新的知识库重新向量化，禁止切换原 TaaS 知识库的 Embedding。
- 三个模型名先作为候选接入点 ID，最终以千帆 `/v2/models` 返回为准。

可从脱敏模板准备仅本机配置：

```bash
install -m 600 local-rag-platforms/maxkb_local/runtime.env.example \
  .local-services/maxkb_local/runtime.env
# 手工编辑后：set -a; source .local-services/maxkb_local/runtime.env; set +a
```

## 三文档 smoke 初始化

1. “知识库 → 创建知识库”：名称 `moi-maxkb-smoke-3docs`，类型“通用型”，
   向量模型选上面的 TaaS Embedding。
2. 上传且仅上传：
   - `local-rag-platforms/fixtures/smoke/001-project-boundary.md`
   - `local-rag-platforms/fixtures/smoke/002-service-ports.md`
   - `local-rag-platforms/fixtures/smoke/003-run-policy.md`
3. 等三个文档完成处理并记录原始状态码；本轮落盘证据中的三份文档状态为 `nnn2`，
   不把它推断为 ready。可以在 UI 做命中测试，但在发现稳定、认证的公开
   retrieval API 前，统一结果仍记 `direct retrieval = unsupported`。
4. 创建“简易智能体” `moi-maxkb-smoke`，选择 TaaS LLM，关联上述知识库，
   发布；在概览 → API Key 创建本地 application key，并打开“API 文档”。

## API discovery

先抓取实例级 Swagger 候选（不发送凭据）：

```bash
local-rag-platforms/maxkb_local/maxkb-local.sh discover
```

结果写入 `.local-services/maxkb_local/logs/api-discovery-<UTC>/`，仅包含 HTTP
状态、所有可访问的 schema 和 path 列表。源码 tag 的候选为：

- `/admin/api-doc/schema/`、`/admin/api-doc/`
- `/chat/api-doc/schema/`、`/chat/api-doc/`
- OpenAI 候选总路径：`/chat/api/<application_id>/chat/completions`

若智能体概览给出的 URL 不同，以 UI/API 文档为准。把完整
`.../chat/completions` 拆成 `MAXKB_OPENAI_BASE_URL`（末尾不含该段）与
`MAXKB_OPENAI_PATH=/chat/completions`；不要把 API key 写进 URL。

## Native QA smoke

配置 `runtime.env` 后执行：

```bash
set -a; source .local-services/maxkb_local/runtime.env; set +a
local-rag-platforms/maxkb_local/maxkb-local.sh smoke
```

脚本先要求三个 fixture 文件存在，再调用现有统一 adapter。用
当前 smoke adapter 每次只提交一个显式 `question`；三类问题的批量循环留到
Stage 1 adapter，不宣称本轮已执行。raw artifact 由 adapter 脱敏。当前能力基线为 `ingest = partial`、
`direct retrieval = unsupported`、`native QA = partial`；只有取得稳定公开
retrieval API 或三题均返回有效回答后才能提升结论。

## 2026-08-06 实例验证结果

- `/admin/` 健康检查 200；管理员登录、OpenAI provider、TaaS LLM/Embedding
  均由本地管理 API 自动完成。
- TaaS LLM 与 Embedding 模型保存/连通性成功。三份 fixture 已创建，但现存
  证据为 3/3 文档状态 `nnn2`，因此 ingest 记为 `partial`，不宣称 ready。
- 简易应用已创建、发布并生成 application key。原生
  `/chat/api/<application_id>/chat/completions` 返回 OpenAI 格式 HTTP 200，但
  本轮回答未正确消费问题，故 Native QA 记为 `partial`。
- Swagger schema 候选受浏览器 cookie 会话保护，未取得稳定的机器可读
  OpenAPI；状态、bundle 路由和脱敏结果保存在
  `.local-services/maxkb_local/discovery/`。
- 未完成稳定公开 direct retrieval 验证，记为 `unsupported`；Native QA
  虽获 HTTP 200，但回答未正确消费问题，记为 `partial`。
- 统一汇总位于
  `.local-services/maxkb_local/logs/smoke-partial-2026-08-06/smoke-result.json`；
  其中 ingest/native 按统一 schema 记为 `error`，并在 `details` 保留上述
  partial 原因，retrieval 记为 `unsupported`。

停止 MaxKB（保留持久化数据）：

```bash
local-rag-platforms/maxkb_local/maxkb-local.sh stop
```

当前容器已保留。Dify 停止且 MOI 正常运行后，准确恢复命令为：

```bash
local-rag-platforms/maxkb_local/maxkb-local.sh resume
```

不要删除 `.local-services/maxkb_local/data`。
