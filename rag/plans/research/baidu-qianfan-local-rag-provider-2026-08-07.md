# 百度千帆作为本地 RAG 外部模型 Provider 的接入调研

> 调研日期：2026-08-07  
> 资料范围：仅使用百度智能云 / 百度千帆官方文档。  
> 目标系统：Dify Local、FastGPT Local、MaxKB Local、RAGFlow Local、MOI Local。

## 1. 结论摘要

百度千帆当前应通过 **推理服务 API V2 的 OpenAI-compatible 协议**接入本项目，而不是为五套 RAG 系统分别开发旧版千帆原生 API 适配器。千帆官方将 V2 描述为兼容 OpenAI 的身份认证和接口协议，并同时提供 Chat、Embedding 和模型列表接口。[推理服务 API V2](https://cloud.baidu.com/doc/qianfan/s/qmh4sv5vi)

统一配置为：

```dotenv
QIANFAN_BASE_URL=https://qianfan.baidubce.com/v2
QIANFAN_API_KEY=<secret>
QIANFAN_CHAT_MODEL=deepseek-v4-flash
QIANFAN_EMBEDDING_MODEL=qwen3-embedding-8b
QIANFAN_EMBEDDING_DIMENSIONS=4096
QIANFAN_EMBEDDING_BATCH_SIZE=16
QIANFAN_RERANKER_MODEL=qwen3-reranker-8b
# 可选，仅在需要按应用拆分调用量/账单或 Key 权限绑定 AppID 时使用
QIANFAN_APPID=<optional-app-id>
```

> 2026-08-07 implementation decision: the user selected the three model IDs
> above as the desired condition. `qwen3-embedding-8b` and
> `qwen3-reranker-8b` appear in the official model table; the exact
> `deepseek-v4-flash` endpoint ID remains pending the account's `/v2/models`
> response. None of the three is marked ready until that discovery and the
> corresponding live probes pass.

对应 endpoint：

| 能力 | 方法与完整 URL | 必要 Body 字段 |
|---|---|---|
| 模型发现 | `GET https://qianfan.baidubce.com/v2/models` | 无 |
| Chat | `POST https://qianfan.baidubce.com/v2/chat/completions` | `model`, `messages` |
| Embedding | `POST https://qianfan.baidubce.com/v2/embeddings` | `model`, `input` |

所有请求使用：

```http
Authorization: Bearer <QIANFAN_API_KEY>
Content-Type: application/json
```

官方快速开始明确给出的 OpenAI SDK `base_url` 是 `https://qianfan.baidubce.com/v2`；SDK 或兼容 Provider 会自行追加 `/chat/completions`、`/embeddings` 等路径。[快速开始：模型服务调用](https://cloud.baidu.com/doc/qianfan/s/rmh4stn9m)

用户给出的 [API 文字版入门指南](https://cloud.baidu.com/doc/APIGUIDE/s/1k1mysgan) 是百度智能云通用 API 入门页，不是千帆模型推理服务的 endpoint 规范。实际接入参数应以千帆 V2、文本生成、向量和认证鉴权文档为准。

## 2. 鉴权和权限

### 2.1 API Key

千帆 V2 使用 API Key Bearer 鉴权，不需要先用 AK/SK 换取 access token，也不需要实现百度云签名算法。官方示例中的 Key 形态为 `bce-v3/...`，但实现中应将 Key 当作不透明字符串，不对前缀做硬编码校验。[认证鉴权](https://cloud.baidu.com/doc/qianfan/s/Kmh4sutww)

API Key 应仅保存在本地 `0600` secret/env 文件中，不提交 Git、不写入脱敏前 artifact、不从浏览器前端直接调用千帆。官方也要求 API Key 只授予必要权限，泄露后删除或轮换。[API KEY 管理](https://cloud.baidu.com/doc/qianfan/s/wmh8l6tnf)

### 2.2 AppID 与接入点权限

`appid` 是可选自定义 Header，用于区分应用调用量和账单；普通接入不需要填写。若 API Key 在控制台配置了 AppID 和接入点粒度权限，则请求中的 AppID 与 `model` 对应接入点必须同时命中授权范围，否则请求会被拒绝。预置接入点与自定义接入点权限相互独立。[快速开始：appid 说明](https://cloud.baidu.com/doc/qianfan/s/rmh4stn9m)、[API Key 粒度权限](https://cloud.baidu.com/doc/qianfan/s/wmh8l6tnf)

因此初版建议：

1. 创建一个仅供本地 benchmark 后端使用的千帆 API Key；
2. 至少授权计划使用的 Chat 与 Embedding 预置接入点；
3. 初版不传 `appid`；如需按平台拆分账单，再为五个平台配置独立 AppID 或独立 API Key；
4. 以 `GET /v2/models` 实测 Key 能看到的模型，而不是仅凭公开模型表判断可调用性。

## 3. OpenAI-compatible Chat

### 3.1 请求协议

```http
POST https://qianfan.baidubce.com/v2/chat/completions
Authorization: Bearer <API Key>
Content-Type: application/json
```

最小请求：

```json
{
  "model": "deepseek-v4-flash",
  "messages": [
    {"role": "system", "content": "请仅依据提供的上下文回答。"},
    {"role": "user", "content": "问题文本"}
  ],
  "stream": false,
  "temperature": 0,
  "max_tokens": 1024
}
```

`model` 和非空 `messages` 是必要字段；支持 `user`、`assistant`、`system` 角色，最后一条消息不能是空白内容。消息总长度受具体模型的输入字符数和 token 上限约束。[文本生成 API](https://cloud.baidu.com/doc/qianfan-api/s/3m7of64lb)

预置模型的 `model` 使用官方模型表中的 `model参数/接入点ID`；自定义或训练后发布的服务使用控制台服务详情中显示的 **API 名称**，不是控制台展示名称，也不是完整 URL。[文本生成 API：model 字段](https://cloud.baidu.com/doc/qianfan-api/s/3m7of64lb)

### 3.2 流式和返回结构

`stream=false` 默认返回 OpenAI 风格的 `choices[].message.content`、`finish_reason` 和 `usage`。`stream=true` 使用 SSE，最后以 `data: [DONE]` 结束；`stream_options.include_usage=true` 可在最后一个 chunk 返回整次请求的 usage。[文本生成 API：流式返回](https://cloud.baidu.com/doc/qianfan-api/s/3m7of64lb)

初版 smoke 应先使用 `stream=false`，避免各平台 SSE 解析差异掩盖基础连通性问题；非流式通过后再验证各平台 Native QA 所需的流式模式。

### 3.3 推荐 Chat 模型

初版建议使用：

```text
deepseek-v4-flash
```

这是用户指定的目标模型字符串；当前文档快照尚未证明该精确接入点 ID，执行时必须通过 `GET /v2/models` 验证当前 Key 的可用性。若返回的是其他 DeepSeek V4 ID，应先报告差异，不自动替换。[模型列表](https://cloud.baidu.com/doc/qianfan/s/rmh4stp0j)、[获取模型列表](https://cloud.baidu.com/doc/qianfan-api/s/Dmba8k71y)

`GET /v2/models` 返回 `id`、`type`、上下文长度、最大输入/输出和模态信息。Provider probe 应确认目标 Chat 模型的 `type` 为 `chat`，而不是只确认同名 ID 存在。[获取模型列表](https://cloud.baidu.com/doc/qianfan-api/s/Dmba8k71y)

## 4. OpenAI-compatible Embeddings

### 4.1 请求协议

```http
POST https://qianfan.baidubce.com/v2/embeddings
Authorization: Bearer <API Key>
Content-Type: application/json
```

最小请求：

```json
{
  "model": "qwen3-embedding-8b",
  "input": ["第一段文本", "第二段文本"],
  "encoding_format": "float"
}
```

`model` 和 `input` 必填。文本 `input` 可为单个字符串或字符串数组；数组不能为空，成员也不能为空字符串。返回结构为 OpenAI 风格的 `data[].embedding`、`data[].index` 和 `usage`。[向量 API](https://cloud.baidu.com/doc/qianfan-api/s/Fm7u3ropn)

### 4.2 推荐 Embedding 模型

初版建议：

```text
model = qwen3-embedding-8b
dimension = 4096
max_batch_size = 16
max_input_per_text = 8192 tokens
```

官方模型表同时列出了以下文本向量模型：[模型列表：文本向量](https://cloud.baidu.com/doc/qianfan-docs/s/7m95lyy43)

| model | 固定维度 | 单请求最大文本数 | 每文本上下文 |
|---|---:|---:|---:|
| `embedding-v1` | 384 | 16 | 384 tokens |
| `tao-8k` | 1024 | 1 | 8192 tokens |
| `bge-large-zh` | 1024 | 16 | 512 tokens |
| `bge-large-en` | 1024 | 16 | 512 tokens |
| `qwen3-embedding-0.6b` | 1024 | 16 | 8192 tokens |
| `qwen3-embedding-4b` | 2560 | 16 | 8192 tokens |
| `qwen3-embedding-8b` | 4096 | 16 | 8192 tokens |

用户选择 `qwen3-embedding-8b` 作为统一向量条件；官方表列出其固定维度为 4096、单请求最多 16 条、单条最长 8192 tokens。是否有额度及权限必须由用户的 API Key 通过 `/models` 和真实 Embedding probe 确认。

### 4.3 强制兼容性限制

- 千帆向量 API 的 `encoding_format` 当前只支持 `float`。如果某平台发送 `base64`，需要关闭该选项或在 adapter 中改为 `float`。[向量 API：encoding_format](https://cloud.baidu.com/doc/qianfan-api/s/Fm7u3ropn)
- 官方请求参数未提供 OpenAI 的 `dimensions` 覆盖字段；应使用模型固定维度，不能请求动态裁剪维度。
- `tao-8k` 每次只能处理 1 条文本；其他上述文本向量模型每次最多 16 条。五个平台的 embedding batch 必须设为 `<=16`，否则 adapter 需要自行拆批。[向量 API：input 限制](https://cloud.baidu.com/doc/qianfan-api/s/Fm7u3ropn)
- 不同模型的输入长度不同。切片长度必须同时满足 RAG 平台 chunk 配置和千帆模型上限。
- 更换 Embedding 模型后必须创建新的索引/collection 并完整重建 corpus。即使两个模型维度相同，向量空间也不相同，不能在同一个索引中混写，也不能在查询时临时切换模型。

最后一条属于基于向量检索机制的实现约束，不是百度文档原文，但它是保证索引可用性和 benchmark 公平性的必要条件。

## 5. OpenAI 兼容性边界

千帆官方将 V2 定义为兼容 OpenAI 标准，但“协议兼容”不等于所有 OpenAI 参数在所有模型上行为完全一致：

1. `temperature`、`top_p`、惩罚参数等支持范围依具体模型而定；不应向所有模型无条件透传平台默认的全部高级参数。[文本生成 API：生成参数](https://cloud.baidu.com/doc/qianfan-api/s/3m7of64lb)
2. `seed`、`stop`、`response_format`、Function Calling、思考控制参数均存在模型级支持差异。[文本生成 API](https://cloud.baidu.com/doc/qianfan-api/s/3m7of64lb)
3. `max_tokens` 只限制最终回答；对支持深度思考的模型，`max_completion_tokens` 才包含思维链和回答，二者同时存在时以后者为准。[文本生成 API：输出长度](https://cloud.baidu.com/doc/qianfan-api/s/3m7of64lb)
4. 流式协议是 SSE，但 beam-search 模型只能使用 `stream=false`。[文本生成 API：stream](https://cloud.baidu.com/doc/qianfan-api/s/3m7of64lb)
5. Embedding 固定输出 `float`，且没有文档化的动态 `dimensions` 参数。
6. 错误响应包含 `code`、`message`、`type`；runner 应同时保存 HTTP 状态码与这些字段，不能只解析 OpenAI SDK 异常文本。[文本生成 API：错误返回](https://cloud.baidu.com/doc/qianfan-api/s/3m7of64lb)

因此，初版统一发送最小公共参数集：

```text
Chat: model, messages, stream=false, temperature=0, max_tokens
Embedding: model, input, encoding_format=float
```

待最小 smoke 通过后，再逐项启用流式、tools、JSON Schema 等能力。

## 6. 五个平台的接入选择

下表是依据千帆 V2 协议和当前本地部署架构作出的实现决策；平台行为属于本项目接入设计结论，不表示百度官方为这些具体版本提供了兼容性承诺。

| 系统 | 推荐接入方式 | Chat | Embedding | 原生千帆 API 是否推荐 |
|---|---|---|---|---|
| Dify Local | OpenAI-compatible / Custom OpenAI provider | Base URL `/v2` + Chat model ID | 同一 Base URL + Embedding model ID，维度 4096 | 否。除非已安装的原生插件明确使用 V2 Bearer API Key；否则容易落入旧 AK/SK/access-token 配置路径 |
| FastGPT Local | AIProxy 的 OpenAI-compatible provider | `/v2/chat/completions` | `/v2/embeddings`，batch `<=16` | 否。统一 OpenAI provider 最容易与现有 TaaS 配置并存 |
| MaxKB Local | 自定义 OpenAI-compatible LLM 与 Embedding provider | Base URL 填 `/v2`，不要重复追加完整 path | 固定维度 4096，建库前确定模型 | 否。优先走公开 V2 合同，减少专用 provider 的版本差异 |
| RAGFlow Local | OpenAI-compatible provider | 使用普通 Chat 模型 | 使用文本 Embedding 模型，维度 4096 | 默认否。只有当前版本原生 Baidu provider 已验证使用 V2 Bearer 且支持 Embedding 时才考虑原生项 |
| MOI Local | 直接复用 OpenAI-compatible HTTP/client adapter | `chat/completions` | `embeddings`，adapter 拆分 16 条批次 | 否。MOI 可直接控制请求和 raw artifact，无需额外 SDK |

每个平台都应分别保存 Chat 与 Embedding 配置，不要假设“一个 Provider 条目”自动覆盖两种模型类型。UI 中若要求完整 endpoint，则填完整 URL；若字段名是 Base URL 或底层使用 OpenAI SDK，则只填 `https://qianfan.baidubce.com/v2`，避免出现 `/v2/v1/chat/completions` 或重复 `/chat/completions`。

## 7. Provider 冗余与 benchmark 规则

千帆可以作为 TaaS 之外的备用 Provider，但不能采用对评估过程不可见的自动切换：

- **Chat Provider**：可以按一次 attempt 选择 TaaS 或千帆；同一 question/repeat 内固定 Provider。超时后如切换，必须新建 attempt，并记录 `provider_id`、模型、错误和重试原因。
- **Embedding Provider**：按独立 corpus/index namespace 固定，严禁查询时自动切换。建议分别建立 `*_taas_<model>` 与 `*_qianfan_qwen3_embedding_0_6b` 索引。
- 每次结果记录 `provider_id=qianfan`、Base URL host、model ID、embedding dimension、batch size、是否 external egress、请求时间和脱敏 raw response。
- 供应商故障切换只提高可运行性；正式横向比较仍须使用同一 Chat 模型、同一 Embedding 模型、同一 corpus 和同一参数条件，不能把不同 Provider 的结果混成一个系统得分。

## 8. 上线前 Probe

用户需要提供的唯一秘密是一个已授权且有余额/额度的千帆 API Key；如使用 AppID 粒度计费，再额外提供 AppID。不要在聊天中发送 Key，应通过本地管理台或 `0600` env 文件写入。

### 8.1 模型发现

```bash
curl -sS 'https://qianfan.baidubce.com/v2/models' \
  -H "Authorization: Bearer ${QIANFAN_API_KEY}" \
  -H 'Content-Type: application/json'
```

确认至少存在：

```text
id=deepseek-v4-flash, type=chat
id=qwen3-embedding-8b, type=embeddings
id=qwen3-reranker-8b, type=reranker
```

For the selected condition, replace the first line with
`id=deepseek-v4-flash` only if that exact ID is returned by the account.

### 8.2 Chat probe

```bash
curl -sS 'https://qianfan.baidubce.com/v2/chat/completions' \
  -H "Authorization: Bearer ${QIANFAN_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"deepseek-v4-flash",
    "messages":[{"role":"user","content":"仅回复 OK"}],
    "stream":false,
    "temperature":0,
    "max_tokens":8
  }'
```

验收：HTTP 2xx、`choices[0].message.content` 非空、保存 `usage` 与请求 ID。

### 8.3 Embedding probe

```bash
curl -sS 'https://qianfan.baidubce.com/v2/embeddings' \
  -H "Authorization: Bearer ${QIANFAN_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"qwen3-embedding-8b",
    "input":["固定探针文本"],
    "encoding_format":"float"
  }'
```

验收：HTTP 2xx、`data` 长度为 1、`data[0].embedding` 长度严格为 4096、所有元素为有限数值。

### 8.4 Rerank probe

`POST https://qianfan.baidubce.com/v2/rerank`，请求字段为 `model`、`query`、
`documents`，当前候选模型为 `qwen3-reranker-8b`。验收要求 HTTP 2xx 且
`results` 非空。[重排序 API](https://cloud.baidu.com/doc/qianfan-api/s/2m7u4zt74)

以上 probe 需要真实 API Key 才能验证账户权限和实时服务状态。本调研只核对了截至 2026-08-07 的官方公开合同，没有使用或生成用户凭据，也没有声称已完成实时调用。

## 9. 实施验收清单

- [ ] 千帆 API Key 以 `0600` 权限保存，未进入 Git；
- [ ] `GET /v2/models` 能发现选定 Chat 与 Embedding 模型及正确 `type`；
- [ ] 五个平台的千帆配置均使用独立 `provider_id`；
- [ ] Base URL 不重复追加 `/v1`、`/v2` 或 endpoint path；
- [ ] Chat 最小非流式 probe 成功；
- [ ] Embedding 返回维度为 4096；
- [ ] Rerank `/v2/rerank` 返回非空 results；
- [ ] Embedding batch 不超过 16；
- [ ] 千帆 Embedding 使用独立索引并完成全量重建；
- [ ] 任意 Provider 切换都进入 attempt ledger；
- [ ] raw request/response 已脱敏，不包含 API Key；
- [ ] 正式 benchmark 不混合不同 Provider/模型条件。

## 10. 官方资料索引

- [用户指定：百度智能云 API 文字版入门指南](https://cloud.baidu.com/doc/APIGUIDE/s/1k1mysgan)
- [千帆推理服务 API V2](https://cloud.baidu.com/doc/qianfan/s/qmh4sv5vi)
- [快速开始：模型服务调用](https://cloud.baidu.com/doc/qianfan/s/rmh4stn9m)
- [认证鉴权](https://cloud.baidu.com/doc/qianfan/s/Kmh4sutww)
- [API KEY 管理与接入点权限](https://cloud.baidu.com/doc/qianfan/s/wmh8l6tnf)
- [文本生成 API](https://cloud.baidu.com/doc/qianfan-api/s/3m7of64lb)
- [向量 API](https://cloud.baidu.com/doc/qianfan-api/s/Fm7u3ropn)
- [向量模型 OpenAI SDK 示例](https://cloud.baidu.com/doc/qianfan-docs/s/Um8r1tpwy)
- [模型列表](https://cloud.baidu.com/doc/qianfan/s/rmh4stp0j)
- [获取模型列表 API](https://cloud.baidu.com/doc/qianfan-api/s/Dmba8k71y)
