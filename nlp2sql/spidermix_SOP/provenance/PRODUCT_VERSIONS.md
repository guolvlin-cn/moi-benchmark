# 统一模型评测产品版本

Spider Mix50复测与Enron新版SOP使用同一套本地产品环境和同一生成模型：

| 产品 | 部署/版本依据 | 正式生成模型 |
|---|---|---|
| MOI | Matrixflow `dev`，commit `75018903911da5712cb0c6763267d42e430fcfcf`；本地部署配置存在未提交修改 | `qwen3.7-plus-2026-05-26` |
| Wren AI | 本地Docker；Wren产品 `0.29.1`，Engine `0.22.0`，AI Service `0.29.0`，UI `0.32.2`；源码基线 `74bf59e1d8400988f5269048cdeed983e77dc20d` | `qwen3.7-plus-2026-05-26` |
| Chat2DB | 购买会员的商业桌面客户端；本批未可靠记录客户端构建号 | `qwen3.7-plus-2026-05-26` |

三个产品的数据库上下文口径见 `../docs/多数据库产品运行策略.md`。凭据、License和商业软件安装包不进入Git。
