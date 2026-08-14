# LoCoMo Memoria Top-200 Reader + Judge

- Status: **COMPLETE**
- Accuracy: **87.92%** (1354/1540)
- Reader/Judge protocol: Mem0 prompts, GPT-5, no judge evidence
- Failed or missing judgments remain in the strict denominator as wrong.

## By category

| Category | Correct | Total | Accuracy |
| --- | ---: | ---: | ---: |
| multi-hop | 246 | 282 | 87.23% |
| open-domain | 69 | 96 | 71.88% |
| single-hop | 748 | 841 | 88.94% |
| temporal | 291 | 321 | 90.65% |

## By Top-200 evidence state

| Evidence state | Correct | Total | Accuracy |
| --- | ---: | ---: | ---: |
| complete | 1094 | 1152 | 94.97% |
| missing | 92 | 191 | 48.17% |
| no_evidence | 4 | 4 | 100.00% |
| partial | 164 | 193 | 84.97% |
