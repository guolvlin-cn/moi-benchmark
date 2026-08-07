# 参评产品

本项目使用同一套 Enron 数据库、同一组 50 道问题和同一套 Golden SQL，对 MOI、Wren AI 和 Chat2DB 三个 NL2SQL 产品进行评测。

v0.4 仍以这三个已参评产品为正式范围；如时间和接入条件允许，再增加“阿里云 Data Agent（具体产品待核验）”独立批次。只有通过数据库接入、SQL导出、5题 Smoke Test 和数据合规检查后，才进入正式50题评测。

这是一项“最终产品能力评测”，不只是底层大模型能力评测。三个产品的部署方式、产品形态、内置工作流、语义配置能力和模型不完全相同，因此报告结果时必须同时披露这些条件。

## 产品概览

| 产品 | 产品形态 | 本次使用方式 | 源码或产品来源 | 仓库中保存的内容 |
|---|---|---|---|---|
| MOI | 可本地部署的 AI 数据分析平台 | Mac 本地部署，通过本地知识库批量提问 | [MatrixOrigin/Matrixflow `dev`](https://github.com/matrixorigin/matrixflow/tree/dev) | 版本信息、批量运行脚本、语义配置、生成 SQL 和评测结果 |
| Wren AI | 开源语义层和 GenBI/NL2SQL 产品 | Mac 本地 Docker 部署，通过本地 API 批量生成 SQL | [Canner/WrenAI](https://github.com/Canner/WrenAI) | 上游版本、脱敏部署配置、批量运行脚本、生成 SQL 和评测结果 |
| Chat2DB | 商业数据库客户端 | 使用已购买会员的 Chat2DB 桌面客户端连接本地数据库并生成 SQL | Chat2DB 商业软件 | 产品版本和测试说明、导出的 SQL、耗时记录与评测结果；不保存软件本体或会员信息 |

## MOI

MOI 基于 MatrixOrigin 的 Matrixflow 项目，本次使用本机运行的 MOI，而不是云端网页服务。

评测环境包括：

- MOI 地址：`http://localhost:18002`；
- 工作区：`local_project`；
- 知识库：`邮件问答`；
- 数据库：`enron_eval`；
- 模型：`deepseek-v4-flash`；
- 正式批次：未配置语义信息、配置语义信息后两组。

MOI 的完整源码不会复制到本评测仓库，而是通过 GitHub 地址、`dev` 分支和评测时的 commit 建立关联。详细信息见：[MOI评测说明](moi/README.md)。

## Wren AI

Wren AI 使用 [Canner/WrenAI](https://github.com/Canner/WrenAI) 的开源版本，但本次不是使用 Wren Cloud，而是在本机通过 Docker 部署。

本次部署主要包括：

- Wren UI；
- Wren Engine；
- Wren AI Service；
- Ibis Server；
- Qdrant；
- 本地批量提问脚本。

本地部署连接 `enron_eval` 的六张表，并通过 Wren 的语义模型描述表关系。评测问题通过本地 API 提交，记录生成 SQL、HTTP 状态、错误信息和生成耗时。

Wren 的完整上游源码仓库约 1.4 GB，不会复制进本评测项目，也不会作为 Git Submodule。后续只整理并保存：

- 上游仓库地址和 commit；
- Docker 镜像版本；
- 不含 API Key 的 `docker-compose.yaml`；
- `config.example.yaml` 和 `.env.example`；
- Enron 50 题批量运行脚本；
- 正式生成结果和评测报告。

真实 `.env`、模型 API Key、数据库密码、容器数据卷和完整上游源码不会提交。

## Chat2DB

Chat2DB 是购买会员后使用的商业桌面软件，不是本项目自行部署或修改的开源组件。

本次使用方式是：

1. 在 Chat2DB 桌面客户端中连接本地 `enron_eval` 数据库；
2. 让 Chat2DB 读取六张表的结构和字段注释；
3. 输入同一组 50 道评测问题；
4. 保存 Chat2DB 生成的 SQL；
5. 在统一数据库快照中执行 SQL，并与 Golden SQL 的结果比较。

评测仓库只保存 Chat2DB 的评测证据：

- 客户端版本和运行环境；
- 是否使用会员能力；
- 数据库和语义配置说明；
- 50 道题生成的 SQL；
- 能够取得的生成耗时；
- SQL 执行结果和错误；
- 与 Golden SQL 的比较报告。

仓库不会保存：

- Chat2DB 安装包或软件二进制；
- 会员账号、订单或付款信息；
- License、激活凭证或登录 Token；
- 数据库真实密码；
- Chat2DB 内部不可公开的文件。

由于 Chat2DB 是商业客户端，如果它没有提供稳定的批量 API，就需要如实记录人工输入、导出 SQL 和计时方法，不能把人工流程伪装成完全自动化评测。

## 公平性说明

三个产品应尽量保持以下条件一致：

- 使用同一份 `enron_eval` 数据快照；
- 使用同一组 50 道混合问题，其中 25 道为口语化问题、25 道保留原始详细表达；
- 使用同一套 Golden SQL 和评测口径；
- 使用等价的只读数据库权限；
- 每道题使用独立会话或清空上下文；
- 统一单题超时和人工重试规则；
- 不根据某个产品的失败结果临时修改题目或 Golden SQL。

同时必须披露无法统一的变量：

- MOI、Wren 和 Chat2DB 可能使用不同模型；
- 各产品的 Schema 检索、自动修复和语义层能力不同；
- MOI 和 Wren 是本地部署，Chat2DB 是商业桌面客户端；
- Chat2DB 的模型调用和内部重试过程可能无法完全观测；
- 语义配置的信息量必须单独记录，配置前后结果不能混为同一个批次。

## 仓库边界

本目录只保存与评测直接相关的内容：产品来源与版本、经过脱敏的部署配置、评测适配器、生成 SQL 和评测结果。

不保存第三方或产品的完整源码副本，而是通过源码地址、分支、版本或 commit 建立关联。也不保存商业软件安装包、会员信息、真实密码、API Key、Cookie、Token 和原始数据库数据。
