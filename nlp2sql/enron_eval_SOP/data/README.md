# Enron六表数据

`data/raw/`中的六个CSV就是本评测的公开、固定数据快照 `enron_eval_v1`。文件直接进入Git，用户不需要访问额外下载地址。

## 文件与用途

| CSV | 表 | 行数（不含表头） | 含义 |
|---|---|---:|---|
| `enron_email.csv` | `enron_email` | 10,401 | 邮件所属员工、文件夹和原始序号 |
| `enron_emailinfo.csv` | `enron_emailinfo` | 10,401 | 当前邮件头、主题、正文和显示地址 |
| `enron_emailorig.csv` | `enron_emailorig` | 1,161 | 正文引用块中的历史邮件头 |
| `enron_emailto.csv` | `enron_emailto` | 71,670 | 当前邮件的标准To地址明细 |
| `enron_emailxto.csv` | `enron_emailxto` | 72,349 | 当前邮件的X-To原始显示值明细 |
| `enron_source.csv` | `enron_source` | 10,401 | 邮件来源员工和原始文件位置 |

## 数据来源说明

这些CSV由本次Chat2DB、Wren和Golden评分实际使用的 `enron_eval` MySQL权威快照导出。历史上用于建库的中间CSV包含MySQL反斜杠转义文本，不能保证跨导入方式得到完全相同的值；因此SOP不直接分发中间文件，而是分发正式评测数据库的规范导出。

Enron邮件内容可能包含真实姓名、邮箱和历史通信文本。本项目将其作为研究评测数据，不应将其中的地址用于联系、营销、身份识别或其他与NL2SQL评测无关的用途。正式公开前仍应由仓库维护者完成数据许可和隐私合规确认。

## 使用顺序

拉取仓库后，先验证CSV：

```bash
python3 scripts/verify_csv_files.py
```

再配置MySQL连接并导入：

```bash
cp config/database.env.example .env
# 修改为自己的MySQL连接信息后加载
source .env
python3 scripts/setup_mysql.py
```

已有 `enron_eval` 时，导入脚本默认停止，避免误删数据。只有明确需要重建时才使用：

```bash
python3 scripts/setup_mysql.py --rebuild
```

导入后可随时只读校验：

```bash
python3 scripts/verify_mysql_snapshot.py
```

## 指纹口径

`manifest.json`同时保存：

- 文件字节数和文件SHA256；
- CSV表头、记录数和各列导入后的NULL数量；
- 与行顺序无关的规范化内容指纹。

规范化指纹会把整数转换为JSON数字，把字面值 `\N` 转换为JSON `null`，同时保留真正的空字符串，然后计算每一行的SHA256；所有行摘要排序后连接，再计算一次SHA256。因此CSV行顺序变化不会影响数据内容指纹，但任何字段值、重复行数量、空字符串或NULL语义变化都会被发现。
