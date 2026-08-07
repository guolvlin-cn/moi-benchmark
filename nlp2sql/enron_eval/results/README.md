# 统一评测结果

本目录保存三产品四批次的统一 MySQL 执行评分结果。

| 文件 | 含义 | 通过率 |
|---|---|---:|
| `chat2db_evaluation.json` | Chat2DB 会员桌面版 | 42/50（84%） |
| `moi_with_semantic_evaluation.json` | MOI 启用语义配置 | 41/50（82%） |
| `moi_baseline_evaluation.json` | MOI 未启用语义配置 | 35/50（70%） |
| `wren_evaluation.json` | Wren AI 本地 Docker | 24/50（48%） |

`product_comparison.md` 提供跨产品摘要。产品生成阶段的 SQL、延迟、错误和运行元数据保存在 `products/<product>/results/`。

这里的通过率表示候选 SQL 与 Golden SQL 的执行结果等价，不等同于“产品成功返回 SQL”的比例。
