# MOI final results (2026-08-17)

This directory contains one judge-ready folder per dataset:

- `wikieval/`
- `mmdocir/`
- `docbench/`
- `enterpriserag-bench/`
- `lenovo-bench/`

Use each dataset's `judge-input.jsonl` as the direct input to a judge. The corresponding `results.jsonl` preserves the selected answer/context together with per-question attempt provenance. `final-score-summary.json` records the post-consolidation score pass and denominator checks.

The score pass is a deterministic re-aggregation of already generated local per-question results and judge artifacts. It intentionally made zero new provider calls. It therefore does not claim a new LLM judgment where a source dataset had no per-question judge file; those cases are labelled in the dataset-level `metrics.json` and README.
