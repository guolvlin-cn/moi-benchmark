# Pi C0 latest-trial extraction

This extractor mirrors the Hermes v2 latest-attempt reporting shape for Pi.
It selects the latest batch per task, excludes `tune-mjcf`, and includes only
numeric verifier rewards. C0 audit/no-hit/lifecycle-gate fields are deliberately
not used as validity gates.

```bash
python3 astra/runs/pi-c0-all-jobs/analysis/v2/extract_pi_c0_trials.py \
  --root "/Users/chenyuwei/Documents/MOI benchmark/work/pi-c0-all-jobs" \
  --output-dir "/Users/chenyuwei/Documents/MOI benchmark/work/pi-c0-all-jobs/analysis/v2/output"
```

Outputs:

- `pi-c0-latest-verified-trials.csv`
- `pi-c0-latest-verified-no-pass.csv`
- `pi-c0-latest-verified-summary.json`
- `pi-c0-latest-verified-report.md`
