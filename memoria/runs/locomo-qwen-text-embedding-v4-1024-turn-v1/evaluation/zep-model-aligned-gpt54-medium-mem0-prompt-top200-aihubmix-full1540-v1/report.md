# LoCoMo Memoria Top-200 对标 Zep 模型实验

- Status: **COMPLETE**
- Accuracy: **90.45%** (1393/1540)
- Reader/Judge: GPT-5.4, reasoning=medium, Responses API
- Reader/Judge Prompt and scoring protocol: pinned public Mem0 LoCoMo prompts
- Retrieval/context: frozen Memoria Raw-Turn Top-200, chronological presentation
- Alignment boundary: Zep published its model setup but not the prompts or detailed scoring rules used for the 94.7% run.
- This is a Zep model-aligned proxy under the Mem0 prompt protocol, not a reproduction of Zep's full pipeline.
- Failed or missing judgments remain in the strict denominator as wrong.

## By category

| Category | Correct | Total | Accuracy |
| --- | ---: | ---: | ---: |
| multi-hop | 253 | 282 | 89.72% |
| open-domain | 72 | 96 | 75.00% |
| single-hop | 770 | 841 | 91.56% |
| temporal | 298 | 321 | 92.83% |

## By Top-200 evidence state

| Evidence state | Correct | Total | Accuracy |
| --- | ---: | ---: | ---: |
| complete | 1112 | 1152 | 96.53% |
| missing | 107 | 191 | 56.02% |
| no_evidence | 4 | 4 | 100.00% |
| partial | 170 | 193 | 88.08% |
