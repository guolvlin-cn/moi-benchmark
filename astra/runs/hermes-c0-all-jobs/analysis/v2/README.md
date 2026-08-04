# Hermes C0 latest-trial extraction

`extract_hermes_c0_trials.py` extracts a reusable Terminal-Bench C0 snapshot
from this work directory.

It applies these fixed rules:

1. Group records by `task_id` and select the latest parent batch directory
   timestamp (`YYYY-MM-DD__HH-MM-SS`).
2. Exclude `tune-mjcf`.
3. Retain only trials with a numeric verifier reward (`0` or `1`).
4. Keep verifier outcome, timeout, product lifecycle, runner lifecycle,
   trajectory quality, duration, tool calls, and token-telemetry quality as
   separate fields.

Run from the benchmark root:

```bash
python3 work/hermes-c0-all-jobs/analysis/v2/extract_hermes_c0_trials.py
```

Or use different input/output locations:

```bash
python3 work/hermes-c0-all-jobs/analysis/v2/extract_hermes_c0_trials.py \
  --root work/hermes-c0-all-jobs \
  --output-dir work/hermes-c0-all-jobs/analysis/v2/output
```

Outputs are regenerated on every run:

- `hermes-c0-latest-verified-trials.csv`: one latest, scored row per task.
- `hermes-c0-latest-verified-no-pass.csv`: the reward-0 subset.
- `hermes-c0-latest-verified-summary.json`: machine-readable aggregates.
- `hermes-c0-latest-verified-report.md`: human-readable summary.

## Token interpretation

The canonical token source is the terminal runner result in
`agent/hermes-run.json` (`usage.input_tokens` and `usage.output_tokens`). The
script cross-checks this against `result.json` when both are present.

`hermes-session.jsonl` is not used to reconstruct missing task totals: its
input fields do not consistently equal runner aggregates. It is only used as
evidence that model activity occurred. Missing usage remains missing; a `0/0`
record with model activity or `finish_reason='length'` is marked
`suspect_zero_after_model_activity` and excluded from aggregate token totals.
