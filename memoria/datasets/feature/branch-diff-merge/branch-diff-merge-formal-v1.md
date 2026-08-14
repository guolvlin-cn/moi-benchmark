# Branch/Diff/Merge Formal v1 数据集说明

## 用途

该数据集正式验证 Memoria 的分支隔离、结构化 Diff、无冲突 Append Merge，以及冲突检测与 Main 状态保护，共包含 50 个确定性 case。

## 文件

- Case：`branch-diff-merge-formal-v1.jsonl`
- Schema：`branch-diff-merge-formal-v1.schema.json`
- 生成器：`memoria/scripts/features/build_branch_diff_merge_formal_dataset.py`
- Case 数量：50
- 操作数量：580
- 预声明必选断言：487
- Dataset SHA-256：`1ab31b80239af787c19724e76af010cb341f7066d88a0e73cf0a3ff535ed1560`
- Schema SHA-256：`158a8e140a9f6c4069b0a23ddb8265ae0b697ab614b54e9d98a67b07f5fa81a7`

## 分类

| 分类 | 数量 | 子场景 |
|---|---:|---|
| `branch_isolation` | 12 | Branch 新增、修改、删除、兄弟分支、重复 Checkout、Main 独立前进 |
| `diff_correctness` | 14 | 单 Add/Update/Remove、5 种混合形状、`behind_main`、重复 Diff |
| `merge_correctness` | 12 | Append 1/2/3/5 条、混合类型、Main 独立前进、重复 Merge、Merge 后写入 |
| `conflict_detection` | 12 | Update/Update、Update/Delete、Delete/Update，以及两个等价修改负例 |

## 冲突范围

冲突类只验证检测和 Main 状态保护，不包含冲突解决：

- 4 个不同值 Update/Update；
- 3 个 Branch Update/Main Delete；
- 3 个 Branch Delete/Main Update；
- 1 个双方更新为相同内容的负例；
- 1 个双方删除同一记忆的负例。

冲突 case 中不存在 Merge、Apply 或 Pick。两个负例预期不产生冲突，用于测量误报，不能根据当前产品行为修改预期。

## Merge 范围

所有 Merge case 都是逻辑上无冲突的新增合并，并且只使用 `append` 策略。该数据集不声称验证 Replace、Accept、选择性 Apply 或通用三方合并。

Memoria 0.4.0 的普通分支始终从 Main 创建，因此数据集不声称支持嵌套分支，使用兄弟分支与 `behind_main` 场景覆盖实际支持的拓扑。

## 判定原则

- Main、Branch 的活动记忆集合和状态哈希分别记录；
- Diff 五个分类必须与预期 alias 集合完全一致；
- 检索必须与当前活动分支及 Merge 后状态一致；
- Diff 检测不得修改 Main；
- 每个 case 后验证独立 Canary 用户未变化；
- 系统错误和普通失败都保留在 50-case 分母中。

## 对应结果

结果说明位于：

`memoria/evaluate/feature/branch-diff-merge/branch-diff-merge-formal-v1.md`
