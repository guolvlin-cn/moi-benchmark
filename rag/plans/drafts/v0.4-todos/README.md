# v0.4 单人一周 TODO 导航

> 状态：Draft TODO ｜ 母计划：[`../v0.4.md`](../v0.4.md)

本目录把 v0.4 拆成一人、五天、40 小时可执行的清单。母计划是范围、指标和结论口径的唯一权威；出现冲突时停止执行、更新 decision log，不现场发明新口径。

## 冻结规模

- [ ] 系统：MOI only；Quick-start / Native 默认路径；无 comparator。
- [ ] Corpus：6 PDFs = 4 existing + 2 fresh fictional/private。
- [ ] 数据：6 Smoke/dev + 20 sealed scored pilot questions。
- [ ] 配额：6/4/4/2/4；fresh scored=4；citation-required answerable=10。
- [ ] 运行：2 initial repeats，共 40 initial attempts；失败保留在分母。
- [ ] 校准：8 Smoke outputs；必须在 scored run 前完成 rubric freeze。
- [ ] 自审：预抽 6 questions × 2 repeats = 12 rows；不声称独立复核。
- [ ] 工时：D1–D5 每天 8h，D5 内含 2h contingency。

## 统一状态

`[ ]` 未开始；`[>]` 进行中；`[x]` 完成；`[!]` 阻塞/失败；`[-]` 有意不适用。
使用 `[-]` 时必须填写 reason，例如 `TRACE_UNAVAILABLE`；不能用 N/A 隐藏产品失败。

## 文件

- [`01-five-day-execution-plan.md`](01-five-day-execution-plan.md)：逐时任务、依赖、DoD 和降级顺序。
- [`02-acceptance-and-result-template.md`](02-acceptance-and-result-template.md)：G0–G4 验收、结果表、自审表和最终结论。

## 本周不能声称

- 不比较其他产品或模型，不给赢家、排行榜或加权总分。
- 不做显著性检验、McNemar、bootstrap 或生产级外推。
- 不把 Smoke、retry、自审或 trace 缺失写成 scored 成功。
