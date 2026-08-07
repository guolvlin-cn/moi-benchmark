# 数据准备

将以下6个UTF-8 CSV放入本机的 `data/private/`。该目录已被 Git 忽略，不会提交到 GitHub：

| 文件 | 目标表 | 字段顺序 | 预期行数 |
|---|---|---|---:|
| `enron_email.csv` | `enron_email` | `id, people, mailbox, nnn` | 10401 |
| `enron_emailinfo.csv` | `enron_emailinfo` | `id, messageid, date, subject, from, to, xfrom, xto, body` | 10401 |
| `enron_emailorig.csv` | `enron_emailorig` | `id, nth, subject, from, to, xfrom, xto` | 1161 |
| `enron_emailto.csv` | `enron_emailto` | `id, nthto, to` | 71670 |
| `enron_emailxto.csv` | `enron_emailxto` | `id, nthxto, xto` | 72349 |
| `enron_source.csv` | `enron_source` | `id, source_file_id, source_name, xfilename, xfolder, xorigin` | 10401 |

`enron_emailinfo.body` 可能包含逗号、双引号和多行正文。导入工具必须支持标准CSV引用和多行字段，不能简单按物理文本行拆分。

如果文件来自 MOI 导出，也可以保留 `enron_email__kb_*.csv` 这类名称；当每张表只有一个匹配文件时，`scripts/database/import_mysql.py` 会自动识别。

本项目不在 Git 中保存真实 CSV。数据库快照一致性以 `snapshot/expected_counts.json` 和导入脚本输出的行数为准。
