# LongMemEval-S Memoria Top-20 对标 Zep 实验

- Status: **COMPLETE**
- Accuracy: **91.80%** (459/500)
- Reader / Judge: `gpt-5.4` / `gpt-5.4`
- API / reasoning: `responses` / `medium`
- Reader/Judge prompts: pinned Mem0 LongMemEval prompts
- Mem0 protocol commit: `4b61c5d31b9c668a12b4f5e78064248a02c82d2b`
- Frozen retrieval SHA256: `fe6f179d8cd21cf71a204ebfaf4c62fff7db5ae434a61b69a3c9fdff334a1434`
- Missing Reader/Judge results remain incorrect in the full denominator.

| Category | Correct | Total | Accuracy |
| --- | ---: | ---: | ---: |
| single-session-user | 63 | 64 | 98.44% |
| single-session-assistant | 56 | 56 | 100.00% |
| single-session-preference | 27 | 30 | 90.00% |
| knowledge-update | 66 | 72 | 91.67% |
| temporal-reasoning | 120 | 127 | 94.49% |
| multi-session | 98 | 121 | 80.99% |
| Abstention | 29 | 30 | 96.67% |
| Non-abstention | 430 | 470 | 91.49% |

## Operations

- Reader: 500/500
- Judge: 500/500
- Reader usage: `{"calls": 500, "prompt_tokens": 26731212, "completion_tokens": 256615, "reasoning_tokens": 157307, "total_tokens": 26987827, "latency_ms": {"p50": 7827.04, "p95": 19759.68}}`
- Judge usage: `{"calls": 500, "prompt_tokens": 771663, "completion_tokens": 83257, "reasoning_tokens": 60536, "total_tokens": 854920, "latency_ms": {"p50": 4832.817, "p95": 9467.521}}`
