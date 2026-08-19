# MOI final results: lenovo-bench

`results.jsonl` contains one canonical record per benchmark question. `judge-input.jsonl` is the common judge-ready contract and includes the answer, reference, and retrieved context. `judgements.jsonl` contains the selected frozen per-question score; `judge-attempts.jsonl` retains duplicate/error judge attempts.

The final score pass re-aggregates local artifacts and does not make new provider calls. Retry provenance and failures remain in each record's `attempts` field.

## Notes

- The formal 60-question unified FastGPT contract is the selected score contract; the project-self evaluation metrics are preserved separately because they use different denominators and claim rules.
- The unified contract has 60 final results and 60 valid judges; duplicate/error judge attempts for q068-q075 remain in judge-attempts.jsonl.
- Gold was author-reviewed with automated checks rather than independently dual-reviewed; retain that caveat when interpreting the score.
