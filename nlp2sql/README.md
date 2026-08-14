# NL2SQL产品评测

本项目比较MOI、Wren AI和Chat2DB三款产品的NL2SQL能力。目前正式结果以两套新版SOP为准：三个产品统一使用 `qwen3.7-plus-2026-05-26`，数据库结构、数据内容、题目、Golden SQL、运行轮次和评分程序均已冻结。

## 当前正式结果

### Enron Eval 50：中文私有数据集，三轮

入口：[enron_eval_SOP](enron_eval_SOP/README.md)｜[完整评测报告](enron_eval/docs/enron-qwen37-evaluation-report.md)

- 6张邮件表，10,401封邮件；
- Easy 20、Medium 20、Hard 10；
- 25道明确语义题、25道用户口语化题；
- 每题独立运行3次，共150次；
- Chat2DB与Wren使用同一MySQL快照；MOI使用同源MatrixOne数据和产品原生执行结果。

自动评测冻结结果：

| 产品配置 | Execution Accuracy | SQL Success Rate | Repeat Correct Rate | P50 | P95 |
|---|---:|---:|---:|---:|---:|
| MOI有语义 | **99/150（66.00%）** | 146/150（97.33%） | **29/50（58%）** | 21.22s | 173.25s |
| MOI无语义 | 85/150（56.67%） | **150/150（100%）** | 26/50（52%） | 25.76s | 116.90s |
| Chat2DB | 77/150（51.33%） | **150/150（100%）** | 21/50（42%） | **20.01s** | **69.91s** |
| Wren AI | 49/150（32.67%） | 114/150（76.00%） | 12/50（24%） | 90.68s | 180.89s |

人工复核是附加结果，不覆盖自动评分：

| 产品配置 | 人工严格正确率 | 人工加权正确率 | 人工稳定正确率 |
|---|---:|---:|---:|
| Chat2DB | **131/150（87.33%）** | 131.5/150（87.67%） | **41/50（82%）** |
| MOI有语义 | 130/150（86.67%） | **132/150（88.00%）** | 38/50（76%） |
| MOI无语义 | 115/150（76.67%） | 124/150（82.67%） | 35/50（70%） |
| Wren AI | 66/150（44.00%） | 69.5/150（46.33%） | 15/50（30%） |

MOI加入语义配置后，人工严格正确率提高10个百分点，口语题严格正确率从62.67%提高到82.67%。

### Spider Mix50：英文公开数据集，单轮

入口：[spidermix_SOP](spidermix_SOP/README.md)｜[完整评测报告](spidermix_SOP/reports/Spider_Mix50_三产品统一模型评测报告.md)

- 从Spider dev抽取50题：Easy 30、Medium 15、Hard 5；
- `pets_1`、`concert_singer`、`car_1`三个数据库，13表960行；
- 每题只涉及一个数据库，没有跨库JOIN；
- 三个产品各运行一轮50题。

| 产品 | Execution Accuracy | SQL Success Rate | P50 | P95 | Token总量 |
|---|---:|---:|---:|---:|---:|
| Wren AI | **42/50（84%）** | 48/50（96%） | 40.442s | 87.177s | 未获取 |
| MOI | 40/50（80%） | **50/50（100%）** | 16.108s | 29.166s | 2,084,012 |
| Chat2DB | 40/50（80%） | **50/50（100%）** | **11.230s** | **19.838s** | 757,422 |

SpiderMix当前只有一轮，因此不能计算Repeat Correct Rate。Chat2DB正式结果按题目所属数据库分三批切库，Schema候选范围比Wren和MOI更小，解读排名时需要保留该限制。

## 新版SOP统一了什么

| 项目 | 新版统一口径 |
|---|---|
| 生成模型 | 三个产品固定 `qwen3.7-plus-2026-05-26` |
| 数据库 | CSV、Schema、表行数和数据指纹冻结；MySQL与MatrixOne使用同源数据 |
| 输入 | 固定问题、难度、题目所属数据库和Golden SQL |
| 会话 | 每题独立新会话，不携带上一题历史 |
| 语义 | Spider不注入额外语义；Enron仅MOI增加独立“有语义”实验组 |
| 评分 | Wren/Chat2DB在MySQL评分；MOI保存MatrixOne原生结果后与MySQL Golden结果比较 |
| 指标 | Execution Accuracy、SQL Success Rate、P50/P95、可获取Token；三轮时增加Repeat Correct Rate |
| 追溯 | 保存运行配置、预测SQL、执行结果、冻结清单和产品版本 |

统一模型不是统一产品内部提示词。Schema检索、Agent编排、SQL修复、反思和执行流程本身就是被评产品能力的一部分。

## 历史评测及模型记录

历史目录用于追溯，不再作为当前公平横评结果。

### 历史Enron单轮评测

| 产品/配置 | 当时模型 | 历史Execution Accuracy |
|---|---|---:|
| MOI无语义 | `deepseek-v4-flash` | 35/50（70%） |
| MOI有语义 | `deepseek-v4-flash` | 41/50（82%） |
| Wren AI | `qwen-plus-2025-12-01` | 24/50（48%） |
| Chat2DB | 未可靠记录 | 42/50（84%） |

证据见 [Enron历史产品清单](enron_eval/products/product_manifest.yaml)。由于底层模型不同，以上分数不能用于判断三个产品在同等模型条件下谁更强。

### 历史Spider Mix50评测

| 产品 | 当时模型 | 历史Execution Accuracy |
|---|---|---:|
| MOI | 未可靠记录 | 33/50（66%） |
| Wren AI | 未可靠记录 | 41/50（82%） |
| Chat2DB | 未可靠记录 | 47/50（94%） |

历史Spider只保存了问题、预测SQL和执行报告，没有保存可核验的模型字段，因此不能事后推断模型。其执行引擎和产品接入方式也与新版SOP不同。

## 目录

```text
nlp2sql/
├── README.md                       # 当前总入口
├── NL2SQL评测汇总报告.md            # 新版结果、历史对照和综合结论
├── enron_eval_SOP/                 # Enron统一Qwen3.7正式复现入口
├── spidermix_SOP/                  # Spider Mix50统一Qwen3.7正式复现入口
├── enron_eval/                     # Enron历史材料、分析报告和开发过程
├── spider/                         # Spider历史材料和旧评测结果
├── plans/                          # 方案版本
├── refs/                           # NL2SQL参考资料
└── systems/                        # 参评系统信息
```

## 复现入口

Enron：

```bash
cd nlp2sql/enron_eval_SOP
python3 verify_frozen_results.py
```

Spider Mix50：

```bash
cd nlp2sql/spidermix_SOP
python3 verify_sop.py
python3 scripts/verify_csv_snapshot.py
```

完整建库、产品运行和评分命令分别见：

- [Enron三轮150次复现SOP](enron_eval_SOP/docs/三轮150次复现SOP.md)
- [Spider Mix50一轮50题运行SOP](spidermix_SOP/docs/一轮50题运行SOP.md)

## 评测原则

- 当前正式横向比较优先引用两套统一模型SOP，不把历史旧模型分数混入排名；
- SQL成功执行不等于答案正确，Execution Accuracy仍是自动评分主指标；
- 原始自动结果、人工复核和产品运行失败分别保留；
- 准确率、延时、Token和稳定性分别报告，不合成为人为加权总分；
- 不向产品注入Golden SQL、其他产品答案、账号、密码、API Key或测试结果；
- Chat2DB商业安装包、License以及MOI/Wren完整源码不复制进本仓库，只记录版本和上游地址。

后续计划见 [plans/README.md](plans/README.md)。
