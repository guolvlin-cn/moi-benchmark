# 冻结参考结果

本目录保存统一模型 `qwen3.7-plus-2026-05-26` 下已经完成并校验的四组50题×3轮结果。

| 目录 | 产品条件 | 记录数 | 主评分文件 |
|---|---|---:|---|
| `qwen37/chat2db/` | Chat2DB，无额外语义配置 | 150 | `evaluation.json` |
| `qwen37/wren/` | Wren二次完整重跑，无额外业务语义 | 150 | `evaluation.json` |
| `qwen37/moi_no_semantic/` | MOI无语义配置 | 150 | `evaluation_native.json` |
| `qwen37/moi_with_semantic/` | MOI语义配置v2 | 150 | `evaluation_native.json` |

这些文件是只读参考基线：

- 新运行必须写入 `runs/<product>/<run-id>/`；
- 不得直接修改参考预测来提高分数；
- 合法的采集纠正必须保存原始记录、替换原因和审计文件；
- MOI大体积原始HTTP事件不进入Git，其目录摘要记录在 `provenance/SOURCE_MAP.md`；
- 自动评测不包含人工审核修正。

运行以下命令验证冻结结果：

```bash
python3 verify_frozen_results.py
```

完整来源、审计和未复制原始证据见：

- [冻结清单](../provenance/freeze_manifest.json)
- [来源映射](../provenance/SOURCE_MAP.md)
