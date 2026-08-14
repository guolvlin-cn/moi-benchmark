# Astra 与 Hermes：Toolathlon 逐题配对结果与失败原因分析

生成日期：2026-08-12  
范围：Toolathlon 第 1–108 题；采用正式结果投影，并用 `toolathlon-posthoc-unavailable-infra-rerun-v1` 的 11 个有效结果替补原 M3 中因 LLM 通讯或基础设施问题而无 evaluator 结果的 slot。

## 口径与限制

- `step` 在本文中指 effective run 的 `model_requests_started`，也就是 provider 模型请求次数，不等于用户可见对话轮数，也不等于工具调用数。
- 本批次 `max step` 是 100。`model_request_budget` 表示运行到请求预算终点；若终点时留下的任务状态仍通过 evaluator，正式结果仍是 pass。
- “具体原因”优先引用 `evaluator/eval_res.json` 和 `evaluator/eval.log`；`model_request_budget` 来自 `run.json`/`failure-evidence.json`。因此本文描述的是 evaluator 观察到的直接失败点，不把它进一步推断成模型内部心理过程。
- 全部 216 个正式 slot 最终均有效且有 evaluator 结果；本文没有把环境错误当作任务失败原因。`interview-report`、`music-analysis` 等采用最新正式投影/补跑结果。

## 总览

| 配对结果 | 题数 | 占 108 题 |
| --- | ---: | ---: |
| 双方通过 | 51 | 47.22% |
| 仅 Astra 通过 | 10 | 9.26% |
| 仅 Hermes 通过 | 21 | 19.44% |
| 双方未通过 | 26 | 24.07% |

| 配对组 | Astra step 中位数 | Hermes step 中位数 | Astra 到 100 | Hermes 到 100 |
| --- | ---: | ---: | ---: | ---: |
| 双方通过 | 27 | 18 | 3 | 0 |
| 仅 Astra 通过 | 31.5 | 19.5 | 0 | 0 |
| 仅 Hermes 通过 | 62 | 37 | 8 | 0 |
| 双方未通过 | 92 | 25.5 | 12 | 3 |

31 个结果不一致的任务中：

- 8 个是 Astra 到 100 step 后未通过，而 Hermes 在 25–82 step 内通过；这是明确的请求预算差异。
- 没有出现 Hermes 到 100 step 未通过、Astra 单独通过的情况。
- 排除上述 8 个预算终止任务后，剩余“完成运行但任务状态不满足 evaluator”的单方胜负为 Hermes 13、Astra 10。也就是说，Hermes 的 11 题总领先中有 8 题可直接联系到 Astra 的 100 请求预算，其余净领先为 3 题。
- 这不表示把 Astra 上限提高就一定能反转 8 题：这里只证明失败发生在预算终点，不能证明继续生成必然完成任务。

## 双方共同通过：51 题

这些任务中，两个系统最终状态都满足任务 evaluator。成功覆盖文件/表格生成、Canvas/Notion/GitHub 操作、Kubernetes、网页研究、财务分析和 WooCommerce 等多种任务，不是由单一工具类型贡献。

| 题号 | Case | Astra step | Hermes step |
| ---: | --- | ---: | ---: |
| 1 | find-alita-paper | 19 | 9 |
| 2 | set-conf-cr-ddl | 11 | 7 |
| 4 | canvas-homework-grader-python | 37 | 18 |
| 7 | price-comparison | 18 | 9 |
| 9 | excel-data-transformation | 14 | 17 |
| 10 | notion-hr | 71 | 16 |
| 13 | git-bug-hunt | 38 | 8 |
| 15 | ab-testing | 25 | 18 |
| 16 | academic-pdf-report | 55 | 47 |
| 17 | academic-warning | 38 | 28 |
| 19 | apply-phd-email | 24 | 23 |
| 20 | canvas-arrange-exam | 21 | 9 |
| 22 | canvas-art-quiz | 11 | 8 |
| 25 | canvas-new-students-notification | 28 | 41 |
| 26 | canvas-submit-late-work | 27 | 32 |
| 29 | courses-ta-hws | 41 | 13 |
| 33 | dietary-health | 16 | 9 |
| 35 | excel-market-research | 14 | 7 |
| 39 | flagged-transactions | 26 | 15 |
| 40 | game-statistics | 33 | 16 |
| 41 | gdp-cr5-analysis | 26 | 33 |
| 42 | git-milestone | 15 | 6 |
| 43 | git-repo | 18 | 9 |
| 45 | huggingface-upload | 39 | 50 |
| 50 | inventory-sync | 50 | 42 |
| 52 | invoice-org | 19 | 7 |
| 57 | k8s-redis-helm-upgrade | 74 | 86 |
| 58 | landing-task-reminder | 55 | 20 |
| 60 | latex-prompt-box | **100** | 72 |
| 61 | live-transactions | 30 | 29 |
| 62 | llm-training-dataset | 17 | 41 |
| 64 | machine-operating | 44 | 23 |
| 65 | meeting-assign | 16 | 18 |
| 69 | nhl-b2b-analysis | 69 | 34 |
| 70 | notion-find-job | 31 | 5 |
| 71 | notion-personal-website | 24 | 7 |
| 73 | nvidia-stock-analysis | 28 | 20 |
| 76 | payable-invoice-checker | 49 | 20 |
| 77 | personal-website-construct | **100** | 53 |
| 78 | ppt-analysis | 23 | 15 |
| 82 | sales-accounting | 17 | 9 |
| 84 | sla-timeout-monitor | 45 | 16 |
| 86 | student-interview | 13 | 8 |
| 88 | sync-todo-to-readme | 72 | 49 |
| 90 | train-ticket-plan | 21 | 7 |
| 93 | trip-adviser | 32 | 25 |
| 94 | trip-itinerary-generator | 25 | 18 |
| 96 | update-material-inventory | 19 | 23 |
| 101 | wandb-shortest-length | **100** | 26 |
| 102 | woocommerce-customer-survey | 27 | 15 |
| 106 | woocommerce-update-cover | 29 | 18 |

值得单独说明的是第 60、77、101 题：Astra 都使用到第 100 次请求，但终点任务状态通过 evaluator。因此“到达 100”不自动等于任务失败；真正的判定仍是终点状态是否满足 evaluator。共同通过集合中 Astra step 中位数为 27、Hermes 为 18，说明即使最终都成功，Astra 通常也使用更多模型请求。

## 仅 Astra 通过：10 题

这 10 题中 Hermes 都没有触及 100 step，失败均为运行完成后产物或远端状态不满足 evaluator。Astra 的 step 一并列出，作为同题成功路径的参考。

| 题号 | Case | Astra 通过 step | Hermes step | Hermes 未通过的直接原因 |
| ---: | --- | ---: | ---: | --- |
| 3 | course-schedule | 18 | 8 | 第 3 条课程名写成“算法分析与设计-01班”，期望“算法分析与设计-01、02班”。 |
| 14 | k8s-safety-audit | 40 | 41 | Google Sheet 中 `net-tapper...` Pod 的 Risk Score 为 6，期望 7。 |
| 18 | add-bibtex | 71 | 43 | BibTeX 作者字段错误，并缺少 `yang2024qwen25math` 条目。 |
| 34 | email-paper-homepage | 52 | 20 | 尚未发布的 Optimizing LLMs 论文不应包含 `codeurl`，Hermes 却写入了 GitHub URL。 |
| 47 | imagenet | 22 | 9 | `survey.tex` 内容与基准不一致，模型行额外写入 `cfg=1.50` 等内容。 |
| 54 | k8s-deployment-cleanup | 33 | 16 | 应收通知的 `stephen_mitchell@mcp.com` 未收到/邮件不正确。 |
| 83 | search-ca-school | 30 | 59 | 未生成 `AI_univ_LA_500miles_Top30_2024.json`。 |
| 97 | upenn-campus-route | 44 | 25 | 路线节点名称不连续：`Benjamin Franklin Statue` 与 evaluator 要求的 `Benjamin Franklin Statue (in front of College Hall)` 不一致。 |
| 98 | verl-dataset | 23 | 7 | Parquet schema 错误：缺 `data_source/prompt/ability/reward_model/extra_info`，多出 `question/answer/idx/solution`。 |
| 107 | yahoo-analysis | 22 | 19 | Hit Rate 与基准差异超过 2%。 |

这一组的特征是“局部正确性失败”：Hermes 通常很快结束，但漏了一个严格字段、文件、收件人、schema 或数值。没有证据表明增加 step 就一定能修复，因为系统已经认为任务完成并退出。

## 仅 Hermes 通过：21 题

### Astra 因 100 step 终止、Hermes 通过：8 题

下表按要求给出通过方 Hermes 的实际 step。它直接展示了同题存在低于 100 step 的成功路径。

| 题号 | Case | Astra step | Astra 终点状态为何仍未通过 | Hermes 通过 step |
| ---: | --- | ---: | --- | ---: |
| 21 | canvas-art-manager | **100** | 27 门要求发布的课程仍未发布。 | 44 |
| 23 | canvas-do-quiz | **100** | 只完成 13/14 个 quiz 满分。 | 70 |
| 38 | filter-low-selling-products | **100** | 5 个低销量商品只移动了 4 个，遗漏 `Phone case iPhone X`。 | 34 |
| 48 | inter-final-performance-analysis | **100** | 未生成 `sheet_url.txt`，evaluator 无法读取 Google Sheet。 | 61 |
| 53 | ipad-edu-price | **100** | 未生成 `result.json`。 | 82 |
| 56 | k8s-pr-preview-testing | **100** | 未建立可持续访问，HTTP health check 被 connection reset。 | 65 |
| 103 | woocommerce-new-product | **100** | 折扣邮件发送 0/41。 | 75 |
| 104 | woocommerce-new-welcome | **100** | 客户 welcome 标记/日期、BigQuery 数据和邮件收件人均不完整，仅 1/4 检查通过。 | 25 |

这 8 题并非“刚好差一个统一步骤”：有的只差一个对象（第 23、38 题），有的核心输出文件或大批远端动作仍未完成（第 48、53、103、104 题）。因此提高上限的潜在收益需要逐题判断。

### Astra 完成运行但 evaluator 未通过、Hermes 通过：13 题

| 题号 | Case | Astra step | Astra 未通过的直接原因 | Hermes 通过 step |
| ---: | --- | ---: | --- | ---: |
| 6 | notion-movies | 16 | Star Wars 条目的 YouTube trailer 链接不是期望 video ID `5UnjrG_N8hU`。 | 14 |
| 12 | woocommerce-stock-alert | 31 | Sheet 只有 5/8 条记录，邮件只有 4/8 封。 | 14 |
| 24 | canvas-list-test | 60 | `quiz_info.csv` 有 14 行，基准为 13 行。 | 54 |
| 27 | cooking-guidance | 36 | 食材覆盖率仅 25%，低于 50% 门槛。 | 18 |
| 30 | cvpr-research | 27 | top-3 researcher 文件未包含 evaluator 要求的研究者组合。 | 53 |
| 31 | dataset-license-issue | 63 | GitHub issue 最后一条评论内容不符合接受模板。 | 40 |
| 37 | fillout-online-forms | 14 | Google Form 已存在，但没有任何 responses。 | 26 |
| 46 | identify-all-songs | 58 | 漏掉 `Dance Monkey` 和 `This Is Home`。 | 19 |
| 55 | k8s-mysql | 62 | 第一问 CSV 第 2 行 constructor 错：写成 Alfa Romeo，期望 Ferrari。 | 82 |
| 80 | profile-update-online | 34 | 两篇文章标题错误（SimpleRL-Zoo、B-STaR）。 | 37 |
| 81 | reimbursement-form-filler | 28 | 报销表内容与基准不一致。 | 17 |
| 85 | stock-build-position | 24 | 美团股票代码缺失，期望 `3690.HK`。 | 14 |
| 100 | wandb-best-score | 96 | 选错 W&B 记录：step 60、score 0.4167，期望 step 230、score 0.43542。 | 31 |

该组说明 Astra 的差距不全是请求上限：13 题在低于 100 step 时主动结束，但状态仍存在精确内容错误或漏操作。与 Astra-only 的 10 题相同，这些更接近执行完整性、检索准确性和最终自检问题。

## 双方都未通过：26 题及原因

| 题号 | Case | Astra step 与直接原因 | Hermes step 与直接原因 |
| ---: | --- | --- | --- |
| 5 | arrange-workspace | 7；目录/文件放错层级，缺 `Work/Job_Application_Materials`、`Work/Offer_Galary` 等。 | 6；同样的目录层级错误及缺文件。 |
| 8 | quantitative-financial-analysis | 19；表格 shape 164×7，期望 168×7。 | 9；同样是 164×7 而非 168×7。 |
| 11 | shopping-helper | **100**；3 个推荐均缺 canonical URL/title/price/store，0/3 有效。 | 52；3 个 ASIN 都无法验证当前 USD offer，0/3 有效。 |
| 28 | course-assistant | 25；Michelle Brooks 未收到 `nlp-course-emergency` 邮件。 | 7；同一收件人漏发同主题邮件。 |
| 32 | detect-revised-terms | 17；法律条文映射文本不精确，且输出 9 行而备选基准为 8 行。 | 20；另一处《物权法》到《民法典》映射文本错误，同样存在行数不匹配。 |
| 36 | experiments-recordings | **100**；两个 W&B run 都未写入 Notion。 | **100**；目标 Notion database/page 404，未找到数据库。 |
| 44 | hk-top-conf | **100**；结果第 1 行第 2 列为 93，期望 108。 | **100**；未生成 `result.md`。 |
| 49 | interview-report | **100**；DOCX 文本格式/内容与基准不一致，缺精确的 `Name: Anna Taylor` 内容。 | 60；相似度 99.5%，但同样缺精确的 `Name: Anna Taylor` 内容。 |
| 51 | investment-decision-analysis | **100**；Fundamental Analysis 至少 8 个单元格错位/数值错误。 | 17；Investment Decision Reference 的 C2、C3 数值错误。 |
| 59 | language-school | 96；某校 TOEFL 最低分写 105，期望 100。 | 27；另一校 TOEFL 最低分写 95，期望 80。 |
| 63 | logical-datasets-collection | 66；LaTeX 表内容或格式不匹配。 | 18；未生成 `datasets.tex`。 |
| 66 | merge-hf-datasets | 29；工具 schema 缺 `type.default=game`。 | 28；工具 schema 把 `List[int]` 写成 `array`。 |
| 67 | mrbeast-analysis | **100**；`duration_seconds` 为 1043，期望 1044。 | 22；统计时长写成 `00:23:18.59`，期望 `00:23:18`。 |
| 68 | music-analysis | **100**；未生成 `music_analysis_result.xlsx`。 | 72；1940 sheet 的最长连续上榜周数写 5，期望 4。 |
| 72 | nvidia-market | **100**；存在 152 个重复行，Position Adjustment 全 NaN，4 个 sheet 均失败。 | 93；出现相同的重复行/NaN/多 sheet 失败。 |
| 74 | oil-price | **100**；回测只有 2 笔交易，期望 4 笔。 | 17；年化收益、Sharpe、回撤及逐笔 PnL 多项数值错误。 |
| 75 | paper-checker | 30；`sections/5_tradeoff.tex` 与期望段落不一致。 | 19；同一文件、同一段落不一致。 |
| 79 | privacy-desensitization | 20；6 个脱敏输出文件内容不匹配。 | 13；9 个脱敏输出文件内容不匹配。 |
| 87 | subway-planning | 12；结果 13 行，期望 25 行。 | 7；同样为 13 行而非 25 行。 |
| 89 | task-tracker | **100**；仓库不存在 `finalpool` branch，Notion/GitHub 检查失败。 | **100**；`voice-processor` 未进入 `tasks/finalpool`，Notion/GitHub 检查失败。 |
| 91 | travel-exchange | 18；Grace expenses 和 Total Cost 偏差约 109,410。 | 17；相同两项出现同量级偏差。 |
| 92 | travel-expense-reimbursement | **100**；claim `EXP2024015` 的 FLAG 写 1，期望 0。 | 40；同一个 FLAG 错误。 |
| 95 | university-course-selection | 41；4 个选课表均有单元格差异，24 种排列无精确匹配。 | 24；同样无精确匹配，差异数量略少。 |
| 99 | vlm-history-completer | 63；20 个模型均匹配，但 LAION CLIP 来源 URL 错，得分 97.5% 仍未过。 | 57；Make-a-Scene 架构错误，且 LAION CLIP、AltCLIP、AltDiffusion 来源错误。 |
| 105 | woocommerce-product-recall | 88；未创建/记录 Google Form，召回邮件也没有表单链接，仅 1/3 通过。 | 41；同样缺 Google Form 和邮件表单链接，仅 1/3 通过。 |
| 108 | youtube-repo | **100**；未生成 `ml_tech.md`。 | 45；文件存在但缺 Qwen3-Coder、OpenHands 两个 GitHub 链接，只找到 5/7。 |

### 双方未通过组的结构

- 双方都到 100：3 题（36、44、89）。这些任务对两边都形成长链路压力，但终点失败状态不同，不能简单归为同一个模型问题。
- 仅 Astra 到 100、Hermes 低于 100 但也未通过：9 题（11、49、51、67、68、72、74、92、108）。这说明提高 Astra 上限可能改变其完成度，但不会自动让这些题通过，因为 Hermes 的较短路径也留下了 evaluator 错误。
- 双方都低于 100 后未通过：14 题。主要是共同遗漏、基准所要求的精确格式/数值不一致，或同一个远端动作漏做。

## 综合原因分析

### 1. 请求预算是 Astra 相对 Hermes 的最大结构性失分源

Astra 47 个 no-pass 中有 20 个以 100 请求预算结束，Hermes 36 个 no-pass 中只有 3 个。单方结果中，8 题表现为“Astra 100 step 未过、Hermes 较少 step 通过”；这 8 题占 Hermes-only 的 38.10%，也解释了总净胜差 11 题中的大部分。

不过，Astra 也有 3 题在 100 step 时通过，说明问题不是上限事件本身，而是 Astra 更频繁把大量请求消耗在任务尚未完成之前。预算增加可能帮助“只差一个对象”的任务，但对缺核心产物或仍有大量远端动作的任务收益不确定。

### 2. 去除预算终止后，两边都存在严格字段与局部完整性错误

仅 Astra 通过的 10 题与非预算 Hermes-only 的 13 题，失败形态高度相似：

- 漏文件或输出 schema 错：83、98；24、53 等。
- 漏远端动作或通知：54；12、37 等。
- 单字段/单数值不精确：3、14、34、107；6、55、80、85、100 等。
- 搜索/集合不完整：18；27、30、46 等。

因此，在请求预算之外，Hermes 仍有 10 个单方失败，Astra 仍有 13 个单方失败。Hermes 的剩余优势较小，但确实存在。

### 3. 双方共同失败多为相同任务难点，但不总是相同错误

26 个共同失败中，有一些产生几乎相同错误（5、8、28、72、75、87、91、92、105），提示任务的严格基准、数据处理口径或共同工具路径是主要难点。另一些虽然同题失败，但路径不同（36、44、51、63、67、68、74、89、99、108），不能把“共同失败”理解为同一个根因。

### 4. Step 少不等于执行更好，step 多也不等于更完整

Hermes 在双方通过组的 step 中位数更低（18 vs 27），且能在 8 个 Astra 预算失败任务上用 25–82 step 通过，说明其主循环通常更紧凑。但 Hermes 也会在很少 step 时过早结束并留下严格错误，例如第 3 题 8 step、第 98 题 7 step、第 47 题 9 step。Astra 的高 step 则既可能产生成功（60、77、101），也可能在核心产物仍缺失时耗尽预算（48、53、68、108）。

## 数据来源

- 正式逐 slot 数据：[`astra-hermes-toolathlon-108-task-results.csv`](astra-hermes-toolathlon-108-task-results.csv)
- 正式汇总：[`astra-hermes-toolathlon-108-task-summary.json`](astra-hermes-toolathlon-108-task-summary.json)
- 总体对比报告：[`astra-hermes-toolathlon-108-task-comparison.md`](astra-hermes-toolathlon-108-task-comparison.md)
- 每个失败原因对应 CSV `run_directory` 下的 `evaluator/eval_res.json`、`evaluator/eval.log` 和 `failure-evidence.json`。
