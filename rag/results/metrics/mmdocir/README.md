# MOI final results: mmdocir

`results.jsonl` contains one canonical record per benchmark question. `judge-input.jsonl` is the common judge-ready contract and includes the answer, reference, and retrieved context. `judgements.jsonl` contains the selected frozen per-question score; `judge-attempts.jsonl` retains duplicate/error judge attempts.

The final score pass re-aggregates local artifacts and does not make new provider calls. Retry provenance and failures remain in each record's `attempts` field.

## Notes

- Page and layout retrieval attempts are joined to the full 1,658-question QA run by question_id.
- The page fraction@10 value is recomputed from top-10 hits and the prepared Gold page_ids; the source page metrics file did not persist a @10 field.
- Answer correctness 3.91/5 and faithfulness 0.7398 are carried-forward report metrics because no per-question LLM judge file was present; deterministic QA metrics are freshly re-aggregated.
- This remains MMDocIR adapted QA, not an official MMDocIR QA leaderboard.
