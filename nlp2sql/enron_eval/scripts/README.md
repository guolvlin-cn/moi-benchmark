# 评测脚本

## adapters

负责从产品取得生成 SQL，并保存问题编号、SQL、错误和耗时：

- `run_moi.py`：通过本地 MOI 会话和 A2A 流式接口逐题运行；
- `run_wren.py`：通过本地 Wren `/api/v1/generate_sql` 接口逐题运行。

Chat2DB 为商业桌面客户端，目前使用人工提问或客户端导出，不把它描述成自动 API 运行。

## database

- `import_mysql.py`：执行 MySQL 8 Schema，并正确解析可能包含多行正文的六张 CSV；
- 数据库账号通过 `ENRON_DB_*` 环境变量提供，脚本不保存密码。

## evaluation

- `build_cases.py`：根据正式问题和 Golden SQL 生成 `cases_enron_50.yaml`；
- `evaluate_mysql.py`：执行 Golden SQL 与候选 SQL，进行有序或无序结果比较，并输出 JSON 报告。

所有脚本使用相对于项目根目录的路径，不依赖某台电脑上的绝对路径。
