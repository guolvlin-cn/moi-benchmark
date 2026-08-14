# Chat2DB与Wren二次重跑人工审核

本目录保存统一模型四组冻结结果中尚未完成的两组人工审核标注：

- Chat2DB：`chat2db_qwen37_20260813_3x`；
- Wren二次完整重跑：`wren_qwen37_20260812_rerun_r3`。

审核页面只列出自动评测至少一轮判错的题目，同一题三轮并排。完全正确计1分，部分正确计0.5分，错误计0分。标注是自动评分之外的附加判断，不覆盖冻结预测和自动评分。

`annotations.json` 会由本地审核页面自动生成并保存，同时记录两份冻结输入文件的路径、运行编号和SHA256，防止误用旧Wren批次标注。

启动命令：

```bash
.venv/bin/python scripts/review/human_review_server.py
```

访问：`http://127.0.0.1:8765/`
