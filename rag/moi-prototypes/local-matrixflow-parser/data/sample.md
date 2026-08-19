# MatrixFlow 本地解析样例

这个文件用于验证独立模块是否真正调用 MatrixFlow Parse V3 Native。

## 目标

- 保留 Markdown 标题层级。
- 输出标准 documents。
- 记录产品解析器返回的 backend 和 parser version。

| 模块 | 作用 |
| --- | --- |
| SourceRouter | 根据文件类型选择解析来源 |
| AssembleV1 | 将 Pages 组装为标准 documents |
