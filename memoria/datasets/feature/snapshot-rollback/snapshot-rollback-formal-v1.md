# Snapshot/Rollback Formal v1 数据集说明

## 用途

该数据集用于正式验证 Memoria Snapshot/Rollback 的状态恢复、检索恢复、多快照行为、回滚后继续写入、幂等性和失败路径，共包含 50 个确定性 case。

## 文件

- Case：`snapshot-rollback-formal-v1.jsonl`
- Schema：`snapshot-rollback-formal-v1.schema.json`
- 生成器：`memoria/scripts/features/build_snapshot_rollback_formal_dataset.py`
- Case 数量：50
- 操作数量：496
- 预声明必选断言：451
- Dataset SHA-256：`be11f4e1355564eb56fc2e8586de2b937f795a84bd2aee419b8642e9a50677d9`
- Schema SHA-256：`9c5dfc0ec75d18c914feff878bcdd6b841fc595001826744fe9633f428239c8d`

## 分类

| 分类 | 数量 | 覆盖内容 |
|---|---:|---|
| `single_operation` | 12 | 4 个修改、4 个新增、4 个删除 |
| `mixed_operation` | 14 | 不同比例和复杂度的新增、修改、删除组合 |
| `multi_snapshot` | 8 | 两个快照及跨层级回滚 |
| `post_rollback_continue` | 6 | 回滚后继续新增、修改或删除 |
| `idempotency` | 4 | 重复执行同一回滚，状态不得再次变化 |
| `edge_failure` | 6 | 空操作、名称规范化、不存在、已删除和重复快照等路径 |

## 判定原则

- 成功回滚必须恢复预期活动记忆状态和严格状态哈希；
- 回滚前必须先证明状态确实发生了目标变化；
- 声明检索断言的 case 必须同时恢复检索可见性；
- 预期失败的 API 请求必须返回指定状态，并保持记忆状态与检索不变；
- 每个 case 使用独立用户，并在 case 后验证独立 Canary 用户未变化；
- 运行生成的 memory ID 使用 case 内 alias 绑定，不写入记忆正文。

## 对应结果

正式结果位于：

`memoria/evaluate/feature/snapshot-rollback/snapshot-rollback-formal-v1.md`
