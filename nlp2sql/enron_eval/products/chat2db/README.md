# Chat2DB评测说明

本次评测使用购买会员后的 Chat2DB 商业桌面客户端。Chat2DB 不是本项目自行部署或修改的开源产品。

## 使用方式

1. 在 Chat2DB 桌面客户端中连接本地 `enron_eval` 数据库；
2. 让客户端读取六张表的结构和字段注释；
3. 输入统一的 50 道 Enron 评测问题；
4. 保存客户端生成的 SQL；
5. 在统一评测数据库中执行 SQL，并与 Golden SQL 的结果比较。

## 目录

```text
products/chat2db/
├── README.md
├── product.yaml
└── results/
    └── manual_export/
        ├── raw_sql_export.txt
        └── generated_sql_50.sql
```

Chat2DB 没有使用本项目中的开源部署代码。若客户端没有提供稳定的批量 API，应将本次采集方式明确记录为人工提问或客户端导出，不能描述为完全自动化运行。

## 后续需要补充

- Chat2DB 的准确版本号；
- 客户端实际使用的模型，如果界面能够查看；
- 是否启用了额外语义配置；
- 每道题的耗时取得方式；
- 客户端内部重试过程是否可观测。

## 商业软件边界

仓库只保存测试说明、导出的 SQL 和评测结果，不保存 Chat2DB 安装包、软件二进制、会员账号、订单信息、License、激活凭证、登录 Token 或数据库真实密码。
