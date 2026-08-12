# LongMemEval-S Memoria Top-20 under Mem0 GPT-5 protocol

- Status: **COMPLETE**
- Accuracy: **91.40%** (457/500)
- Reader / Judge: `gpt-5` / `gpt-5`
- Mem0 protocol commit: `4b61c5d31b9c668a12b4f5e78064248a02c82d2b`
- Frozen retrieval SHA256: `fe6f179d8cd21cf71a204ebfaf4c62fff7db5ae434a61b69a3c9fdff334a1434`
- Missing Reader/Judge results remain incorrect in the full denominator.

| Category | Correct | Total | Accuracy |
| --- | ---: | ---: | ---: |
| single-session-user | 63 | 64 | 98.44% |
| single-session-assistant | 56 | 56 | 100.00% |
| single-session-preference | 25 | 30 | 83.33% |
| knowledge-update | 65 | 72 | 90.28% |
| temporal-reasoning | 123 | 127 | 96.85% |
| multi-session | 96 | 121 | 79.34% |
| Abstention | 29 | 30 | 96.67% |
| Non-abstention | 428 | 470 | 91.06% |

## Operations

- Reader: 500/500
- Judge: 500/500
- Reader usage: `{"calls": 500, "prompt_tokens": 26731212, "completion_tokens": 437783, "total_tokens": 27168995, "latency_ms": {"p50": 14763.469, "p95": 31063.69}}`
- Judge usage: `{"calls": 500, "prompt_tokens": 777527, "completion_tokens": 164473, "total_tokens": 942000, "latency_ms": {"p50": 4689.147, "p95": 10050.212}}`
