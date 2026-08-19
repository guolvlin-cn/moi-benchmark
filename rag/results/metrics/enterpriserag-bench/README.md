# MOI final results: enterpriserag-bench

`results.jsonl` contains one canonical record per benchmark question. `judge-input.jsonl` is the common judge-ready contract and includes the answer, reference, and retrieved context. `judgements.jsonl` contains the selected frozen per-question score; `judge-attempts.jsonl` retains duplicate/error judge attempts.

The final score pass re-aggregates local artifacts and does not make new provider calls. Retry provenance and failures remain in each record's `attempts` field.

## Notes

- Recovered-evaluation is the canonical answer result because all 500 questions have a successful recovered result and valid frozen judge.
- Initial transport availability remains visible: 417/500 on the first pass and 83 questions recovered by retry.
- The score is for the current-corpus adapted 722-document slice, not the official full EnterpriseRAG-Bench corpus.
