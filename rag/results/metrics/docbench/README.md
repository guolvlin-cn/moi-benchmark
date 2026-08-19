# MOI final results: docbench

`results.jsonl` contains one canonical record per benchmark question. `judge-input.jsonl` is the common judge-ready contract and includes the answer, reference, and retrieved context. `judgements.jsonl` contains the selected frozen per-question score; `judge-attempts.jsonl` retains duplicate/error judge attempts.

The final score pass re-aggregates local artifacts and does not make new provider calls. Retry provenance and failures remain in each record's `attempts` field.

## Notes

- Canonical precedence is valid recovery round 3, then round 2, round 1, and finally a valid historical result; unresolved cases remain failed.
- The third retry attempted the four remaining ModelArts.81011 cases and failed 4/4; the runner's zero-success closeout error is retained as provenance, and no further retry is scheduled.
- The four unresolved questions remain in results.jsonl and judge-input.jsonl with unavailable final judgment and count in the full 1,102-question denominator.
- Contains-gold and Token F1 are freshly derived from the canonical answer/reference rows as deterministic lexical diagnostics; they are not semantic Judge scores.
- This is a current-corpus adapted recovery audit, not a replacement for the historical Native PDF ranking row.
