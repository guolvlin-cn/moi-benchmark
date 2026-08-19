# MOI final results: wikieval

`results.jsonl` contains one canonical record per benchmark question. `judge-input.jsonl` is the common judge-ready contract and includes the answer, reference, and retrieved context. `judgements.jsonl` contains the selected frozen per-question score; `judge-attempts.jsonl` retains duplicate/error judge attempts.

The final score pass re-aggregates local artifacts and does not make new provider calls. Retry provenance and failures remain in each record's `attempts` field.

## Notes

- Selected the completed 50-question MOI run; no retry was present for this dataset.
- RAGAS scores are frozen diagnostic judge artifacts; the deterministic source metrics remain primary.
