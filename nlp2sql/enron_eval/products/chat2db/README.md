# Chat2DB评测说明

本次评测使用购买会员后的 Chat2DB 商业桌面客户端。Chat2DB 不是本项目自行部署或修改的开源产品。

## 使用方式

1. 在 Chat2DB 桌面客户端中连接本地 `enron_eval` 数据库；
2. 让客户端读取六张表的结构和字段注释；
3. 通过真实桌面界面为每道题创建独立对话并输入问题；
4. 从本地应用日志提取生成 SQL、最终答案、端到端耗时、SQL 执行耗时和 Token；
5. 每道题独立运行3次，共150次；
6. 在统一评测数据库中执行 SQL，并与 Golden SQL 的结果比较。

## 目录

```text
products/chat2db/
├── README.md
├── product.yaml
└── results/
    ├── manual_export/
    │   ├── raw_sql_export.txt
    │   └── generated_sql_50.sql
    └── automated/<run_id>/
        ├── run.json
        ├── predictions.jsonl
        └── evaluation.json
```

Chat2DB 没有使用本项目中的开源部署代码。Chat2DB Pro 5.3.0 的 AI 对话通过桌面 JCEF 内部通信，没有对外提供可直接调用的本地批量 HTTP API。本项目使用 `scripts/adapters/run_chat2db_desktop.py` 驱动真实客户端界面，并解析本地应用日志。因此采集方式应描述为“桌面界面自动化”，不能描述为官方 API 调用。

## 自动采集保护条件

- 每次提问前点击“新建对话”；
- 日志中的 `historySize` 必须为0；
- 日志中的数据库必须为 `enron_eval`；
- 运行时模型必须与 `run.json` 记录一致；
- 运行期间不能人工操作 Chat2DB；
- 任一上下文校验失败立即停止，避免污染剩余结果；
- 原始应用日志可能包含敏感配置，不能提交到Git，只提交脱敏后的结构化结果。

详细运行命令见 [评测脚本说明](../../scripts/README.md)。

## 商业软件边界

仓库只保存测试说明、导出的 SQL 和评测结果，不保存 Chat2DB 安装包、软件二进制、会员账号、订单信息、License、激活凭证、登录 Token 或数据库真实密码。
