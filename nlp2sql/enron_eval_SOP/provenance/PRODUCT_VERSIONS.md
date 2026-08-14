# 统一模型评测产品版本

本文件记录Enron统一模型正式批次使用的产品环境。`run.json`中的 `product_version: local` 只表示本地部署，不能单独作为版本依据。

| 产品 | 部署/版本依据 | 正式生成模型 |
|---|---|---|
| MOI | Matrixflow `dev`，commit `75018903911da5712cb0c6763267d42e430fcfcf`；评测机器工作区存在未提交的本地部署配置修改 | `qwen3.7-plus-2026-05-26` |
| Wren AI | 本地Docker；Wren产品 `0.29.1`，Engine `0.22.0`，AI Service `0.29.0`，UI `0.32.2`；源码基线 `74bf59e1d8400988f5269048cdeed983e77dc20d` | `qwen3.7-plus-2026-05-26` |
| Chat2DB | 购买会员的商业桌面客户端；源码和内部重试不可见，本批未可靠记录客户端构建号 | `qwen3.7-plus-2026-05-26` |

MOI和Wren源码没有复制进本仓库，只记录上游仓库与版本。Chat2DB安装包、License、账号、API Key和Cookie均不进入Git。
