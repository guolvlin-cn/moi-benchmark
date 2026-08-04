#!/usr/bin/env bash
set -u

reward=0
recovery_c0='{"attempt":1,"expected_result":"astra-lifecycle-smoke:complete","resume_command":"/usr/local/bin/astra-smoke-workload","status":"complete"}'
recovery_f1='{"attempt":2,"expected_result":"astra-lifecycle-smoke:complete","resume_command":"/usr/local/bin/astra-smoke-workload","status":"complete"}'
if printf 'phase-1\n' | cmp -s - /app/progress.log \
    && printf 'phase-1-complete\n' | cmp -s - /tmp/astra-smoke/trigger \
    && printf 'astra-lifecycle-smoke:complete\n' | cmp -s - /app/result.txt \
    && {
        printf '%s\n' "$recovery_c0" | cmp -s - /app/recovery.json \
            || printf '%s\n' "$recovery_f1" | cmp -s - /app/recovery.json
    }; then
    reward=1
fi

printf '%s\n' "$reward" > /logs/verifier/reward.txt
