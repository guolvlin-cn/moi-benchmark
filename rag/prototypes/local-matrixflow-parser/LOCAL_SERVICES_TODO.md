# MatrixFlow API-only 本地测试配置 TODO

> 2026-08-03 更新：解析器已经改为直接调用 MinerU 官方服务，不再使用 302.AI。
> `--pipeline precision` 使用官方精准解析 API 和 `MINERU_API_TOKEN`；
> `--pipeline agent` 使用无需 Token 的官方 Agent 轻量解析 API。本文后续涉及
> 302.AI 的内容仅保留为历史方案，不再是当前实现说明；实际用法以 README 为准。

目标：本机不部署 MinerU、VLM、Embedding、Rerank 或问答模型。本机只保留：

- `local-matrixflow-parser` 适配器；
- `local-matrixflow-rag`；
- MatrixOne；
- 测试数据和结果；
- 少量不包含模型推理的文件转换代码。

所有模型推理和文档解析均通过外部 HTTPS API 完成。

## 结论：使用 302.AI + MatrixOrigin TaaS

默认架构改为：

| 服务 | 负责能力 | API Key | 接口 |
| --- | --- | --- | --- |
| 302.AI | 文件临时上传、MinerU 云解析 | `AI302_API_KEY` | `/302/upload-file`、`/mineru/api/v4/extract/task` |
| MatrixOrigin TaaS | VLM 视觉增强 | `TAAS_API_KEY` | `/v1/chat/completions` |
| MatrixOrigin TaaS | Embedding | `TAAS_API_KEY` | `/v1/embeddings` |
| MatrixOrigin TaaS | Chat/答案生成 | `TAAS_API_KEY` | `/v1/chat/completions` |
| MatrixOrigin TaaS | Rerank | `TAAS_API_KEY` | `/v1/rerank` |

这比把所有模型都迁到 302.AI 更接近当前 MatrixFlow 开发环境：模型侧继续复用
MatrixOrigin TaaS，只有本地无法直接运行的 MinerU 解析能力通过 302.AI 补齐。

TaaS 的本地代码契约已经确认：

```text
Base URL: https://api-taas.moi.matrixorigin.cn/v1
Authentication: Authorization: Bearer $TAAS_API_KEY
VLM: qwen3-vl-plus -> POST /chat/completions
Embedding: bge-m3 -> POST /embeddings
Chat: qwen3.6-flash -> POST /chat/completions
Rerank: qwen3-rerank -> POST /rerank
```

302.AI 只需要使用以下能力：

- [MinerU 创建解析任务](https://doc.302.ai/331077222e0)；
- [MinerU 查询解析结果](https://doc.302.ai/331170720e0)；
- [文件上传并获得 URL](https://doc.302.ai/232294379e0)；
- [大额充值、转账和发票咨询](https://help.302.ai/docs/lian-xi-wo-men)。

## 必须接受的两个差异

### 差异 1：云端 MinerU 不是 MatrixFlow 仓库中的固定实例

MatrixFlow 仓库当前固定的是：

```text
MinerU 2.7.4
双 NVIDIA GPU
mineru-api /file_parse
```

302.AI 提供的是当前 MinerU 官方云 API 中转：

```text
POST /mineru/api/v4/extract/task
GET  /mineru/api/v4/extract/task/{task_id}
```

它是异步任务接口，返回 ZIP 下载地址，不是 MatrixFlow 当前直接调用的同步
`/file_parse`。

因此需要在本地写一个适配器，将：

```text
MatrixFlow MinerUClient
  -> 上传文件
  -> 创建云端任务
  -> 轮询
  -> 下载 ZIP
  -> 转换成 MatrixFlow 期望的返回结构
```

这可以测试完整 RAG 产品流程和解析质量，但报告中必须记录：

```text
parser_provider=302ai-mineru-cloud
matrixflow_exact_mineru_deployment=false
```

不能把 302.AI 的排队和网络延迟直接当成 MatrixFlow 自建 MinerU 的服务器性能。

### 差异 2：Office/XLSX 的严格网页路线和全云路线不同

MatrixFlow 网页端路线是：

```text
DOC/DOCX/PPT/PPTX -> 转 PDF -> MinerU
XLS/XLSX -> OpenXML
```

如果要最大程度保持 MatrixFlow 路线：

- Office 转 PDF 可以继续使用本机 LibreOffice；它不是模型，不进行 AI 推理。
- XLSX 可以继续使用本机 OpenXML；它不是模型。
- MinerU、VLM、Embedding、Rerank 和生成模型全部走外部 API。
- MinerU 走 302.AI；其他四类模型走 TaaS。

如果要求本机连 LibreOffice/OpenXML 服务也不运行，可以把 Office 直接交给云端
MinerU、把 XLSX 交给另一家云端文档解析服务，但这时必须标记：

```text
web_equivalent=false
```

本手册推荐：**模型全部外部 API；LibreOffice/OpenXML 作为非模型工具按需保留。**

---

## 第 0 步：测试数据合规确认

在注册或上传文件前，先确认：

- [ ] 测试文件不包含客户敏感数据、商业秘密或个人敏感信息。
- [ ] 公司允许把测试文件上传到第三方中转平台及其下游模型服务商。
- [ ] 公司允许使用境外或跨境中转节点；如果不允许，向 302.AI 确认中国区节点。
- [ ] 已确认文件保存期限、日志保存策略和删除方式。
- [ ] 用 mock data 完成第一轮，不直接上传真实生产资料。

这一步无法由代码代替。没有公司数据合规确认时，只使用当前 mock data。

---

## 第 1 步：注册 302.AI，并在充值前确认发票

### 1.1 注册

1. 打开 [302.AI 官网](https://302.ai/)。
2. 点击登录/注册。
3. 使用公司允许的手机号或邮箱创建账号。
4. 不要使用个人账号长期承载公司测试费用。
5. 如果页面提供企业认证，使用与最终发票抬头一致的公司主体完成认证。

### 1.2 充值前联系客户经理

302.AI 官方帮助中心写明：大额充值、转账和开发票需要联系客户经理。

打开：

[302.AI 联系我们](https://help.302.ai/docs/lian-xi-wo-men)

通过网页右下角客服或页面提供的客户经理联系方式，发送：

```text
我们计划使用 302.AI 的文件上传和 MinerU 云 API 做企业内部 RAG 文档解析评测。
请确认：
1. 是否可以对公转账；
2. 发票开具主体；
3. 是否可以开增值税专用发票或普通发票；
4. 发票项目名称；
5. 是按充值金额还是实际消费金额开票；
6. MinerU 官方免费版接口是否计入发票；
7. 是否有企业 SLA、并发额度和中国区数据处理节点；
8. 是否保存上传文件、Prompt、响应和 API 日志，保存多久；
9. 是否可以签署数据处理或保密协议。
```

只有收到书面确认后再进行较大金额充值。

### 1.3 第一轮只充值小额

第一轮只需要：

- 3～5 个小 PDF；
- 3～5 次 MinerU 解析。

先使用平台试用额度或最小可充值金额。不要一开始充值正式压测预算。

---

## 第 2 步：配置两把受限 API Key

### 2.1 创建 302.AI API Key

官方操作说明：

[302.AI API Key 管理](https://help.302.ai/en/docs/API-guan-li)

操作步骤：

1. 登录 302.AI 管理后台。
2. 打开 **使用 API**。
3. 打开 **API Keys**。
4. 点击添加 API Key。
5. 名称填写：

   ```text
   local-matrixflow-benchmark
   ```

6. 有效期先设置为 1 个月；不要一开始使用永不过期。
7. 关闭无限额度。
8. 设置较小的总额度和每日额度。
9. 如果页面提供 `allow_save_logs`，第一轮设置为 `false`。
10. 不授予管理其他 API Key 的权限。
11. 创建后复制 Key。

在终端中设置：

```sh
export AI302_API_KEY='粘贴你的302 API Key'
```

只检查是否设置成功，不打印 Key：

```sh
test -n "$AI302_API_KEY" && echo "AI302_API_KEY 已设置"
```

不要执行：

```sh
echo "$AI302_API_KEY"
```

每次打开新终端都需要重新设置。暂时不要写入 `.zshrc`。

### 2.2 获取并配置 TaaS API Key

TaaS 是公司服务，不需要再去第三方模型网站分别注册 VLM、Embedding、Chat 和
Rerank。向 MatrixOrigin 内部的 TaaS 管理员申请一把用于 benchmark 的受限 Key，
并确认它具有以下模型权限：

```text
qwen3-vl-plus
bge-m3
qwen3.6-flash
qwen3-rerank
```

同时确认：

- [ ] TaaS 生产/开发环境的 Base URL；本地代码当前默认是
      `https://api-taas.moi.matrixorigin.cn/v1`。
- [ ] Key 的有效期、请求额度和并发限制。
- [ ] 四个模型是否都在同一个 Base URL 下开放。
- [ ] 测试数据是否允许发送到该 TaaS 环境。
- [ ] 是否有调用日志、用量和错误追踪入口。

在终端中设置：

```sh
export TAAS_API_KEY='粘贴你的TaaS API Key'
```

只检查变量存在，不打印 Key：

```sh
test -n "$AI302_API_KEY" && echo "AI302_API_KEY 已设置"
test -n "$TAAS_API_KEY" && echo "TAAS_API_KEY 已设置"
```

后续规则：

```text
AI302_API_KEY -> 只用于文件上传和 MinerU
TAAS_API_KEY  -> 只用于 VLM、Embedding、Chat 和 Rerank
```

---

## 第 3 步：建立统一的新运行目录规则

用户要求每次 run 都新开文件夹。后续每次测试前执行：

```sh
cd /Users/muuushroom/gitrepos/moi-benchmark/rag

RUN_DIR="runs/api-only-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN_DIR"
echo "$RUN_DIR"
```

同一轮测试中的请求和响应保存在这个目录。下一轮重新执行，不复用旧目录。

每个运行目录必须保留：

```text
request metadata
response JSON
HTTP 状态
request_id / trace_id
上传耗时
排队耗时
解析耗时
下载耗时
模型耗时
总耗时
服务商和模型名称
```

不能保存 API Key。

---

## 第 4 步：测试 302 文件上传

MinerU 云接口需要一个外网可下载的文件 URL。先用 302 文件上传 API 把本地文件
转换成 URL。

官方接口：

[Upload-File](https://doc.302.ai/232294379e0)

限制：公开文档当前写明单文件不超过 50 MB。

### 4.1 准备小 PDF

```sh
TEST_PDF="/绝对路径/你的测试文件.pdf"
test -f "$TEST_PDF"
```

第一轮使用 1～3 页、不含敏感信息的 PDF。

### 4.2 上传

```sh
RUN_DIR="runs/upload-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN_DIR"

curl --fail --show-error \
  -X POST https://api.302.ai/302/upload-file \
  -H "Authorization: Bearer ${AI302_API_KEY}" \
  -F "file=@${TEST_PDF}" \
  --output "$RUN_DIR/upload-response.json"

jq '.' "$RUN_DIR/upload-response.json"
```

### 4.3 取得文件 URL

```sh
DOCUMENT_URL="$(jq -r '.data' "$RUN_DIR/upload-response.json")"
echo "$DOCUMENT_URL"
```

验收：

- [ ] `.code` 为 200。
- [ ] `.data` 是 `https://` URL。
- [ ] URL 可以下载。
- [ ] 下载后的 SHA-256 与原始文件一致。

验证文件：

```sh
curl --fail --show-error \
  "$DOCUMENT_URL" \
  --output "$RUN_DIR/downloaded.pdf"

shasum -a 256 "$TEST_PDF" "$RUN_DIR/downloaded.pdf"
```

两个哈希值必须相同。

---

## 第 5 步：测试 302 的 MinerU 云解析

302 文档称这个接口为“MinerU 官方免费版”，每日额度有限。因此：

- 可以用于首轮接线和质量评测；
- 不能作为稳定压测服务；
- 压测前必须向客户经理确认企业额度和 SLA；
- 解析延迟必须拆分排队时间和执行时间。

### 5.1 创建解析任务

继续使用第 4 步的 `DOCUMENT_URL`：

```sh
RUN_DIR="runs/mineru-cloud-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN_DIR"

jq -n \
  --arg url "$DOCUMENT_URL" \
  '{
    url: $url,
    model_version: "vlm",
    is_ocr: false,
    enable_formula: true,
    enable_table: true,
    language: "ch",
    no_cache: true
  }' \
  > "$RUN_DIR/mineru-request.json"

curl --fail --show-error \
  -X POST https://api.302.ai/mineru/api/v4/extract/task \
  -H "Authorization: Bearer ${AI302_API_KEY}" \
  -H "Content-Type: application/json" \
  --data-binary "@$RUN_DIR/mineru-request.json" \
  --output "$RUN_DIR/mineru-submit-response.json"

jq '.' "$RUN_DIR/mineru-submit-response.json"
```

这里选择 `model_version=vlm`，因为 MatrixFlow 仓库使用的是
`mineru-vllm` 镜像。但云端具体模型和 MatrixFlow 2.7.4 仍可能不同。

MatrixFlow 原接口使用 `parse_method=auto`，而 MinerU 云 API 公开参数只有
`is_ocr=true/false`，两者不能完全一一对应。本次文本 PDF 先使用
`is_ocr=false`；测试扫描件时复制本次请求并改成：

```json
{"is_ocr": true}
```

适配器最终需要实现自动检测文本层，再决定是否启用 OCR，并在结果中记录决定。

### 5.2 保存 task_id

```sh
TASK_ID="$(jq -r '.data.task_id' "$RUN_DIR/mineru-submit-response.json")"
test -n "$TASK_ID"
echo "$TASK_ID"
```

### 5.3 查询任务

```sh
curl --fail --show-error \
  "https://api.302.ai/mineru/api/v4/extract/task/${TASK_ID}" \
  -H "Authorization: Bearer ${AI302_API_KEY}" \
  --output "$RUN_DIR/mineru-status.json"

jq '.' "$RUN_DIR/mineru-status.json"
```

查看状态：

```sh
jq -r '.data.state' "$RUN_DIR/mineru-status.json"
```

可能看到：

```text
pending
running
done
failed
```

如果是 `pending` 或 `running`，等待几秒后手工重新执行 5.3。不要高频轮询。

### 5.4 下载 ZIP

状态为 `done` 后：

```sh
ZIP_URL="$(jq -r '.data.full_zip_url' "$RUN_DIR/mineru-status.json")"
test -n "$ZIP_URL"

curl --fail --show-error \
  "$ZIP_URL" \
  --output "$RUN_DIR/mineru-result.zip"

unzip -l "$RUN_DIR/mineru-result.zip"
unzip "$RUN_DIR/mineru-result.zip" -d "$RUN_DIR/unpacked"
```

验收：

- [ ] ZIP 可以解压。
- [ ] 存在 `full.md` 或等价 Markdown。
- [ ] 存在 `layout.json`；MinerU 官方文档说明它对应 middle JSON。
- [ ] 扫描 PDF 能产生 OCR 文本。
- [ ] 表格能输出 HTML 或结构化表格。
- [ ] 公式能输出 LaTeX。
- [ ] 保存 `trace_id` 和 `task_id`。

### 5.5 同一文件测两次时禁用缓存

质量测试可以使用缓存，延迟测试必须：

```json
{"no_cache": true}
```

否则第二次调用可能命中 MinerU 云端缓存，延迟结果无效。

---

## 第 6 步：测试 `qwen3-vl-plus`

这是 MatrixFlow 默认 VLM 模型名称，用于图片 OCR、Caption 和表格增强。
模型推理由 TaaS 完成；302 只临时托管供 TaaS 读取的图片 URL。

### 6.1 准备无敏感信息的图片

```sh
TEST_IMAGE="/绝对路径/测试图片.png"
test -f "$TEST_IMAGE"
```

上传图片并取得 `IMAGE_URL`：

```sh
IMAGE_UPLOAD_DIR="runs/image-upload-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$IMAGE_UPLOAD_DIR"

curl --fail --show-error \
  -X POST https://api.302.ai/302/upload-file \
  -H "Authorization: Bearer ${AI302_API_KEY}" \
  -F "file=@${TEST_IMAGE}" \
  --output "$IMAGE_UPLOAD_DIR/upload-response.json"

IMAGE_URL="$(jq -r '.data' "$IMAGE_UPLOAD_DIR/upload-response.json")"
test -n "$IMAGE_URL"
echo "$IMAGE_URL"
```

### 6.2 调用

```sh
RUN_DIR="runs/qwen3-vl-plus-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN_DIR"

jq -n \
  --arg image "$IMAGE_URL" \
  '{
    model: "qwen3-vl-plus",
    messages: [{
      role: "user",
      content: [
        {type: "image_url", image_url: {url: $image}},
        {type: "text", text: "请识别图片中的文字，并简要描述图片内容。"}
      ]
    }],
    temperature: 0
  }' \
  > "$RUN_DIR/request.json"

curl --fail --show-error \
  -X POST https://api-taas.moi.matrixorigin.cn/v1/chat/completions \
  -H "Authorization: Bearer ${TAAS_API_KEY}" \
  -H "Content-Type: application/json" \
  --data-binary "@$RUN_DIR/request.json" \
  --output "$RUN_DIR/response.json"

jq '.' "$RUN_DIR/response.json"
```

验收：

- [ ] 返回 `choices`。
- [ ] 返回模型名为 `qwen3-vl-plus` 或可追踪的等价版本。
- [ ] 图片文字能够识别。
- [ ] API 响应包含 usage。
- [ ] 记录 request id、延迟和 Token 数。

如果返回 401/403，先向 TaaS 管理员确认 Key 是否具有 `qwen3-vl-plus` 权限；
如果返回 404，确认该环境是否使用本地代码默认的 `/v1/chat/completions` 契约。
不要自动回退到另一个模型。

---

## 第 7 步：测试 TaaS `bge-m3` Embedding

当前 `local-matrixflow-rag/config.example.json` 使用的是 `bge-m3`、1024 维。

### 7.1 调用

```sh
RUN_DIR="runs/bge-m3-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN_DIR"

jq -n '{
  model: "bge-m3",
  input: [
    "MatrixFlow 是一个 RAG 应用。",
    "这是用于向量接口测试的第二句话。"
  ],
  encoding_format: "float"
}' > "$RUN_DIR/request.json"

curl --fail --show-error \
  -X POST https://api-taas.moi.matrixorigin.cn/v1/embeddings \
  -H "Authorization: Bearer ${TAAS_API_KEY}" \
  -H "Content-Type: application/json" \
  --data-binary "@$RUN_DIR/request.json" \
  --output "$RUN_DIR/response.json"

jq '.' "$RUN_DIR/response.json"
```

### 7.2 检查维度

```sh
jq '.data[0].embedding | length' "$RUN_DIR/response.json"
```

必须输出：

```text
1024
```

验收：

- [ ] 两条输入返回两个向量。
- [ ] 每个向量都是 1024 维。
- [ ] 相同文本重复调用得到相同或数值误差可接受的向量。
- [ ] 模型 ID 固定，不自动回退到其他 embedding。

---

## 第 8 步：测试 `qwen3.6-flash` 问答生成

当前本地 RAG 示例配置使用 `qwen3.6-flash`。

```sh
RUN_DIR="runs/qwen3.6-flash-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN_DIR"

jq -n '{
  model: "qwen3.6-flash",
  messages: [
    {
      role: "system",
      content: "你是知识库问答助手。只能根据给定资料回答。"
    },
    {
      role: "user",
      content: "资料：MatrixFlow 使用 RAG 进行知识库问答。\n问题：MatrixFlow 用什么方式做知识库问答？"
    }
  ],
  temperature: 0
}' > "$RUN_DIR/request.json"

curl --fail --show-error \
  -X POST https://api-taas.moi.matrixorigin.cn/v1/chat/completions \
  -H "Authorization: Bearer ${TAAS_API_KEY}" \
  -H "Content-Type: application/json" \
  --data-binary "@$RUN_DIR/request.json" \
  --output "$RUN_DIR/response.json"

jq '.' "$RUN_DIR/response.json"
```

验收：

- [ ] 能够回答“RAG”。
- [ ] 返回 usage。
- [ ] 固定 `temperature=0` 后重复结果基本稳定。
- [ ] 记录 TTFT、总延迟、输入 Token、输出 Token 和费用。

---

## 第 9 步：测试 `qwen3-rerank`（可选）

当前 `local-matrixflow-rag` 还没有接入外部 reranker，因此这一步先独立验证，
以后再决定是否加入对比实验。

仓库中的 TaaS Dify 插件已经实现该接口契约。

```sh
RUN_DIR="runs/qwen3-rerank-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN_DIR"

jq -n '{
  model: "qwen3-rerank",
  query: "MatrixFlow 如何进行知识库问答？",
  documents: [
    "MatrixFlow 使用 RAG 检索知识并生成回答。",
    "今天上海天气晴朗。",
    "向量数据库可以用于语义检索。"
  ],
  top_n: 2,
  return_documents: false
}' > "$RUN_DIR/request.json"

curl --fail --show-error \
  -X POST https://api-taas.moi.matrixorigin.cn/v1/rerank \
  -H "Authorization: Bearer ${TAAS_API_KEY}" \
  -H "Content-Type: application/json" \
  --data-binary "@$RUN_DIR/request.json" \
  --output "$RUN_DIR/response.json"

jq '.' "$RUN_DIR/response.json"
```

验收：第一条 MatrixFlow 文档应排在最前。

---

## 第 10 步：配置 `local-matrixflow-rag`

复制示例配置：

```sh
cd /Users/muuushroom/gitrepos/moi-benchmark/rag/prototypes/local-matrixflow-rag

cp config.example.json config.taas.local.json
```

将模型部分改成：

```json
{
  "embedding": {
    "mode": "taas",
    "base_url": "https://api-taas.moi.matrixorigin.cn/v1",
    "model": "bge-m3",
    "api_key_env": "TAAS_API_KEY",
    "dimension": 1024,
    "timeout_seconds": 60
  },
  "generation": {
    "enabled": true,
    "provider": "taas",
    "base_url": "https://api-taas.moi.matrixorigin.cn/v1",
    "model": "qwen3.6-flash",
    "api_key_env": "TAAS_API_KEY",
    "timeout_seconds": 120
  }
}
```

不要覆盖 MatrixOne、workspace、chunk size 等现有字段。

执行检查：

```sh
RUN_DIR="runs/check-taas-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN_DIR"

go run . check \
  --config config.taas.local.json \
  > "$RUN_DIR/check.log" 2>&1
```

当前代码已经接受 `embedding.mode=taas`，并会在 `base_url` 后调用
`/embeddings`；生成客户端会在 `base_url` 后调用 `/chat/completions`。
不要使用 hash embedding 代替真实 API。

---

## 第 11 步：实现 parser 的 302 MinerU + TaaS VLM adapter

这一部分当前尚未完成，是 API-only 方案真正的代码阻塞点。

### 11.1 新配置

计划配置文件：

```json
{
  "file_upload": {
    "provider": "302ai",
    "api_key_env": "AI302_API_KEY",
    "url": "https://api.302.ai/302/upload-file",
    "max_bytes": 52428800
  },
  "mineru": {
    "provider": "302ai",
    "api_key_env": "AI302_API_KEY",
    "submit_url": "https://api.302.ai/mineru/api/v4/extract/task",
    "result_url_template": "https://api.302.ai/mineru/api/v4/extract/task/{task_id}",
    "model_version": "vlm",
    "ocr_mode": "auto",
    "enable_formula": true,
    "enable_table": true,
    "language": "ch",
    "no_cache": true,
    "poll_interval_seconds": 3,
    "timeout_seconds": 900
  },
  "vlm": {
    "provider": "taas",
    "api_key_env": "TAAS_API_KEY",
    "base_url": "https://api-taas.moi.matrixorigin.cn/v1",
    "chat_path": "/chat/completions",
    "model": "qwen3-vl-plus"
  },
  "office_converter": {
    "mode": "local-soffice"
  },
  "xlsx_parser": {
    "mode": "local-openxml"
  },
  "paddle": {
    "enabled": false
  }
}
```

JSON 里不放真实 API Key。

### 11.2 MinerU adapter 实现清单

- [ ] CLI 增加 `--services-config FILE`。
- [ ] 实现 302 文件上传 client。
- [ ] 从上传响应读取文档 URL。
- [ ] 检测 PDF 是否有可靠文本层，将 `ocr_mode=auto` 映射成云 API 的
      `is_ocr=true/false`。
- [ ] 在 run metadata 中记录最终 `is_ocr` 值和判断原因。
- [ ] 调用 MinerU submit API。
- [ ] 保存 `task_id` 和 `trace_id`。
- [ ] 以不低于 3 秒的间隔轮询。
- [ ] 遇到 `pending/running` 继续等待。
- [ ] 遇到 `failed` 输出完整错误并停止。
- [ ] 任务完成后下载 `full_zip_url`。
- [ ] 校验下载域名和 HTTPS。
- [ ] 限制 ZIP 大小。
- [ ] 防止 ZIP path traversal。
- [ ] 解压到本次新 run 目录。
- [ ] 将 `layout.json` 映射为 MatrixFlow 所需 middle JSON。
- [ ] 读取 `full.md`。
- [ ] 将云端输出转换成现有 `clients.MinerUClient` 返回类型。
- [ ] 不把云端 URL 或 Token 写进文档 metadata。
- [ ] 将上传、排队、解析、下载分别计时。

### 11.3 TaaS VLM adapter 实现清单

- [ ] 使用 `TAAS_API_KEY`，不能误用 `AI302_API_KEY`。
- [ ] 调用 `POST /v1/chat/completions`。
- [ ] 使用精确模型名 `qwen3-vl-plus`。
- [ ] 支持 OpenAI 兼容的 `image_url` + `text` 多模态消息。
- [ ] 将本地图片转换为 TaaS 可访问的 URL；第一版可复用 302 文件上传。
- [ ] 保留 MatrixFlow 当前的 OCR/Caption Prompt。
- [ ] 分别记录 OCR、Caption、表格 HTML 请求。
- [ ] 保存模型名、request id、usage、耗时和错误码。
- [ ] 禁止模型名自动降级。
- [ ] 429/5xx 有限重试。
- [ ] 401/403 立即失败。

### 11.4 PDF V2 provider 传递修复

- [ ] `UnifiedParseService.parsePDFV2` 创建 `PDFParserV2` 时传入本地 provider。
- [ ] Office 转换后的 PDF 继续使用同一个 provider。
- [ ] dependency probe 成功后状态才是 `online`。
- [ ] API-only 模式不允许静默降级成 V3 Native。

### 11.5 等价性标记

首次接入后应报告：

```json
{
  "profile": "web-default-api-only",
  "matrixflow_pipeline_equivalent": true,
  "matrixflow_exact_model_deployment": false,
  "parser_provider": "302ai-mineru-cloud",
  "mineru_api": "v4",
  "mineru_model_version": "vlm",
  "vlm_model": "qwen3-vl-plus"
}
```

只有拿到与 MatrixFlow 相同的 MinerU 2.7.4 托管实例后，
`matrixflow_exact_model_deployment` 才能改成 `true`。

---

## 第 12 步：完整 API-only pipeline 验收

准备：

- [ ] 文本 PDF。
- [ ] 扫描 PDF。
- [ ] 表格 PDF。
- [ ] 图片较多的 PDF。
- [ ] DOCX。
- [ ] PPTX。
- [ ] 10～20 条 mock 问题。

首次不测 XLSX；XLSX 属于 OpenXML 路线，单独测试。

每次创建新的 pipeline root：

```sh
cd /Users/muuushroom/gitrepos/moi-benchmark/rag/prototypes/local-matrixflow-pipeline

RUN_ROOT="runs/api-only-e2e-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN_ROOT"

python3 pipeline.py \
  --input "/绝对路径/测试文件.pdf" \
  --config ../local-matrixflow-rag/config.taas.local.json \
  --question "这个文档主要讲了什么？" \
  --run "$RUN_ROOT"
```

验收：

- [ ] parser 使用 302 MinerU。
- [ ] PDF 产生 documents。
- [ ] chunking 使用 MatrixFlow 512/50 配置。
- [ ] embedding 通过 TaaS 使用 `bge-m3`。
- [ ] 向量维度是 1024。
- [ ] 数据写入 MatrixOne。
- [ ] 检索使用 MatrixFlow 本地实现。
- [ ] 回答生成通过 TaaS 使用 `qwen3.6-flash`。
- [ ] VLM 触发时通过 TaaS 使用 `qwen3-vl-plus`。
- [ ] 每个子阶段都有独立新目录。
- [ ] 所有请求保留服务商、模型、request id、延迟和 usage。
- [ ] 所有输出不包含 API Key。

---

## 第 13 步：质量和延迟评测规则

### 13.1 解析质量

分别评估：

- 文本完整率；
- 标题层级；
- 阅读顺序；
- 表格单元格；
- 公式；
- 图片 OCR；
- 页码和来源 metadata；
- chunk 边界。

### 13.2 解析延迟必须拆分

```text
本地读取
302 文件上传
MinerU 排队
MinerU 执行
ZIP 下载
ZIP 解压/转换
总解析时间
```

不能只记录一个总时间。

### 13.3 RAG 延迟必须拆分

```text
Embedding
MatrixOne 初检索
多级索引/关键词检索
Rerank（若启用）
Prompt 构造
Generation TTFT
Generation total
端到端
```

### 13.4 召回评测

至少保存：

- Recall@1、Recall@5、Recall@10；
- MRR；
- 命中 chunk ID；
- 命中文档和页码；
- 各 route 的候选；
- 是否经过 rerank；
- 最终引用是否支持答案。

### 13.5 解释结果时的限制

可以得出：

```text
MatrixFlow 本地 RAG 逻辑 + 指定外部 API 组合的质量和端到端延迟
```

不能直接得出：

```text
MatrixFlow 官方部署的 MinerU 2.7.4 服务延迟
```

---

## 第 14 步：备选方案

### 14.1 如果 302 MinerU 免费额度不够

优先顺序：

1. 联系 302 客户经理申请企业 MinerU 配额/SLA。
2. 直接申请
   [MinerU 官方 Token](https://mineru.net/apiManage/token)。
3. MinerU 使用官方 Token，其他模型继续使用 TaaS。
4. 如果 MinerU 官方不能满足采购/发票要求，再改用阿里云 Document Mind。

MinerU 官方 API 文档：

[MinerU 文档解析 API](https://mineru.net/apiManage/docs)

官方 API 支持：

- 创建任务；
- 本地文件预签名上传；
- 异步轮询；
- PDF/DOC/DOCX/PPT/PPTX/图片；
- Markdown、JSON、ZIP；
- 表格、公式和 OCR。

但公开页面未明确说明企业开票流程，采购前必须向 MinerU 官方确认。

### 14.2 如果公司只允许采购阿里云

使用同一个阿里云企业账号：

- 文档解析：
  [阿里云 Document Mind](https://help.aliyun.com/zh/document-mind/)；
- VLM：`qwen3-vl-plus`；
- Embedding：`text-embedding-v4`；
- Rerank：`qwen3-rerank`；
- Generation：千问系列。

阿里云 Document Mind 支持 PDF、Office、图片、扫描件、表格和 Markdown 输出，
并按页/字符计费：

[Document Mind 计费](https://help.aliyun.com/zh/document-mind/product-overview/billing-overview)

阿里云官方支持企业账单开票：

[阿里云发票申请指南](https://help.aliyun.com/zh/user-center/invoice-application-guide)

这个方案采购最规范，但文档解析不再是 MinerU，因此只能作为另一套 parser
对比组，不能标成 MatrixFlow 默认解析。

### 14.3 如果只想用 SiliconFlow

SiliconFlow 可以覆盖：

- VLM；
- Embedding；
- Rerank；
- 生成模型；
- 企业发票。

开票说明：

[SiliconFlow 开具发票](https://docs.siliconflow.cn/cn/faqs/invoice)

但是它没有公开证明能提供 MatrixFlow 所需的 MinerU 云解析契约，而且提供的是
开源 Qwen3-VL 型号，不是精确的阿里云 `qwen3-vl-plus`。因此不作为首选。

---

## 第 15 步：费用和安全

### 15.1 费用

- [ ] API Key 设置每日额度。
- [ ] 第一轮只使用小文件。
- [ ] 禁用不必要的重复解析。
- [ ] 延迟测试才设置 `no_cache=true`。
- [ ] 质量调试可以使用缓存节省费用。
- [ ] 每次 run 保存 usage 和平台扣费记录。
- [ ] 每天核对 302 MinerU 消费明细和 TaaS 用量。
- [ ] 压测前分别确认 302 MinerU 和 TaaS 的并发限制。

### 15.2 Key 安全

- [ ] 302 Key 只通过 `AI302_API_KEY` 环境变量读取。
- [ ] TaaS Key 只通过 `TAAS_API_KEY` 环境变量读取。
- [ ] 两把 Key 不混用。
- [ ] 配置文件只保存环境变量名称。
- [ ] 不把 Key 写进 JSON、日志、命令历史或 Git。
- [ ] 不使用 MatrixFlow 仓库中已有的 `.env`。
- [ ] Key 泄漏后立即禁用并重新生成。
- [ ] 测试结束后删除临时 Key。

### 15.3 文件安全

- [ ] 只上传批准的数据。
- [ ] 日志关闭时确认平台确实不保存请求内容。
- [ ] 记录上传文件 URL 的有效期。
- [ ] 测试结束后按平台能力删除上传文件。
- [ ] 不把临时文件 URL 写入公开报告。
- [ ] 对下载 ZIP 做大小、域名和路径安全校验。

---

## 最终执行顺序

严格按顺序完成：

1. [ ] 公司数据合规确认。
2. [ ] 联系 302 客户经理确认发票、节点、SLA 和数据保留。
3. [ ] 注册 302.AI。
4. [ ] 小额充值。
5. [ ] 创建受限的 `AI302_API_KEY`。
6. [ ] 向内部管理员申请并配置 `TAAS_API_KEY`，确认四个模型权限。
7. [ ] 测试 302 文件上传。
8. [ ] 测试 302 MinerU 创建、轮询和下载。
9. [ ] 测试 TaaS `qwen3-vl-plus`。
10. [ ] 测试 TaaS `bge-m3`，确认 1024 维。
11. [ ] 测试 TaaS `qwen3.6-flash`。
12. [ ] 测试 TaaS `qwen3-rerank`。
13. [ ] 配置 `local-matrixflow-rag`。
14. [ ] 实现 parser 的 302 MinerU + TaaS VLM adapter。
15. [ ] 跑 parser 单测。
16. [ ] 跑建库测试。
17. [ ] 跑检索测试。
18. [ ] 跑知识问答测试。
19. [ ] 跑质量、召回和延迟评测。
20. [ ] 对照 302 消费明细和 TaaS 用量。
21. [ ] 生成报告并明确“云端模型部署非 MatrixFlow 固定实例”的限制。
