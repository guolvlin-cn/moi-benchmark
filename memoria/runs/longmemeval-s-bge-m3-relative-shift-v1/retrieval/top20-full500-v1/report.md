# LongMemEval-S Retrieval-only report

- Selected questions: 500
- Final successes: 500
- First-pass success rate: 100.00%
- P50/P95 latency: 292.6 / 423.3 ms
- Stability gate: **PASS**

## Evidence metrics (non-Abstention)

| Metric | @1 | @5 | @10 | @20 |
| --- | ---: | ---: | ---: | ---: |
| Recall | 0.3926 | 0.7954 | 0.9066 | 0.9734 |
| Hit | 0.6511 | 0.9106 | 0.9723 | 0.9957 |
| Complete recall | 0.1809 | 0.6681 | 0.8234 | 0.9404 |

MRR: 0.7607

## Stability checks

- PASS: snapshot_complete — 500/500 final records
- PASS: final_success — 500/500 successful
- PASS: first_pass_success — 100.00% >= 99.00%
- PASS: no_cross_user_or_question — 0 contaminated results
- PASS: metadata_complete — 0 missing metadata fields
- PASS: full_top_k — 500/500 returned Top-20
- PASS: latency_p95 — 423.3 ms <= 30000.0 ms
- PASS: retrieval_path_present — paths={'hybrid': 500}

## Retrieval paths

- hybrid: 500
