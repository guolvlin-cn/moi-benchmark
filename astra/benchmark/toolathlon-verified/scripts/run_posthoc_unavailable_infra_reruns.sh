#!/usr/bin/env bash
set -uo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "ERROR: run with sudo -E so frozen credentials and Docker are available." >&2
  exit 77
fi

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 ABSOLUTE_OUTPUT_ROOT [--dry-run]" >&2
  exit 64
fi

output_root=$(readlink -m -- "$1")
dry_run=()
if [[ $# -eq 2 ]]; then
  if [[ $2 != "--dry-run" ]]; then
    echo "ERROR: the only optional argument is --dry-run." >&2
    exit 64
  fi
  dry_run=(--dry-run)
fi

case "$output_root" in
  /home/vagrant/moi-benchmark/*|/tmp/*) ;;
  *)
    echo "ERROR: output root must be below /home/vagrant/moi-benchmark or /tmp." >&2
    exit 64
    ;;
esac

repo_root="/home/vagrant/moi-benchmark"
source_root="/home/vagrant/dataset/Toolathlon"
m1_root="${repo_root}/astra/results/toolathlon-minimal-e2e-tool-events-v10"
m2_root="${repo_root}/astra/results/toolathlon-m2-first-batch-v4"
m3_root="${repo_root}/astra/results/toolathlon-m3-remaining-batch-v1"
script_root="${repo_root}/astra/benchmark/toolathlon-verified/scripts"
freeze_root="${repo_root}/astra/benchmark/toolathlon-verified/freeze"
policy="${repo_root}/astra/benchmark/toolathlon-verified/config/posthoc-unavailable-infra-rerun-policy.v1.json"

(
  cd -- "$script_root"
  sha256sum -c posthoc-unavailable-infra-rerun.sha256
) || {
  echo "ERROR: post-hoc rerun script checksum root is not valid." >&2
  exit 79
}

(
  cd -- "$freeze_root"
  sha256sum -c m0.sha256
) || {
  echo "ERROR: M0 checksum root is not valid." >&2
  exit 79
}

python3 -c 'import json,sys; value=json.load(open(sys.argv[1], encoding="utf-8")); raise SystemExit(0 if value.get("state") == "GO" else 1)' \
  "${freeze_root}/credential-manifest.json" || {
    echo "ERROR: runtime credential fingerprint manifest is not GO." >&2
    exit 78
  }

python3 "${script_root}/check_astra_model_precondition.py" || exit $?

cd -- "$repo_root"
python3 "${script_root}/run_posthoc_unavailable_infra_reruns.py" \
  --repo-root "$repo_root" \
  --source-root "$source_root" \
  --output-root "$output_root" \
  --m1-root "$m1_root" \
  --m2-root "$m2_root" \
  --m3-root "$m3_root" \
  --policy "$policy" \
  "${dry_run[@]}"
