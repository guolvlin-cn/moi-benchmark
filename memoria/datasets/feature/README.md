# Memoria 特性实验数据集

本目录只保存 Memoria 特性正式实验的数据集定义，不保存过程验证数据。

```text
feature/
├── snapshot-rollback/
│   ├── snapshot-rollback-formal-v1.jsonl
│   ├── snapshot-rollback-formal-v1.schema.json
│   └── snapshot-rollback-formal-v1.md
├── branch-diff-merge/
│   ├── branch-diff-merge-formal-v1.jsonl
│   ├── branch-diff-merge-formal-v1.schema.json
│   └── branch-diff-merge-formal-v1.md
├── low-confidence-governance/
│   ├── low-confidence-governance-formal-v1.jsonl
│   ├── low-confidence-governance-formal-v1.schema.json
│   └── low-confidence-governance-formal-v1.md
└── duplicate-memory-handling/
    ├── duplicate-memory-handling-formal-v1.jsonl
    ├── duplicate-memory-handling-formal-v1.schema.json
    └── duplicate-memory-handling-formal-v1.md
```

每个数据集包含三份同名文件：

- `*.jsonl`：逐用例的可执行数据；
- `*.schema.json`：对应 JSON Schema；
- `*.md`：目标、构造方式、分类和判定规则。

共同约定：

- 记忆正文使用自然语言，不加入用例 ID 或检索锚点；
- 每个用例使用独立用户；
- 运行时记忆 ID 使用结构化别名绑定；
- 系统错误和普通失败都保留在正式分母中；
- 运行结果与数据集定义分离，不写回本目录。
