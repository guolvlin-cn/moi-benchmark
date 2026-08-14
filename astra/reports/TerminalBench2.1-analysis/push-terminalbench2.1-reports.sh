#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$script_dir/../../.." rev-parse --show-toplevel)"

remote=""
branch=""
commit_message="docs(terminal-bench): update Astra Hermes PI reports"

usage() {
  cat <<'EOF'
Usage:
  bash astra/reports/TerminalBench2.1-analysis/push-terminalbench2.1-reports.sh \
    [--remote REMOTE] [--branch BRANCH] [--message MESSAGE]

Defaults:
  - Uses the current branch's configured upstream remote and branch.
  - Stages only the Terminal-Bench 2.1 report artifacts listed in this script.

Examples:
  bash astra/reports/TerminalBench2.1-analysis/push-terminalbench2.1-reports.sh
  bash astra/reports/TerminalBench2.1-analysis/push-terminalbench2.1-reports.sh \
    --remote origin --branch main --message "docs: refresh Terminal-Bench report"
EOF
}

while (($# > 0)); do
  case "$1" in
    --remote)
      remote="${2:?missing value for --remote}"
      shift 2
      ;;
    --branch)
      branch="${2:?missing value for --branch}"
      shift 2
      ;;
    --message)
      commit_message="${2:?missing value for --message}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$repo_root"

if ! git diff --cached --quiet; then
  echo "Refusing to run: unrelated staged changes already exist." >&2
  git diff --cached --name-status >&2
  exit 1
fi

upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
if [[ -z "$remote" ]]; then
  if [[ -z "$upstream" || "$upstream" != */* ]]; then
    echo "No upstream branch is configured; pass --remote and --branch." >&2
    exit 1
  fi
  remote="${upstream%%/*}"
fi
if [[ -z "$branch" ]]; then
  if [[ -n "$upstream" && "$upstream" == "$remote/"* ]]; then
    branch="${upstream#*/}"
  else
    branch="$(git branch --show-current)"
  fi
fi

if [[ -z "$branch" ]]; then
  echo "Detached HEAD is not supported; pass --branch from a checked-out branch." >&2
  exit 1
fi
if ! git remote get-url "$remote" >/dev/null 2>&1; then
  echo "Unknown Git remote: $remote" >&2
  exit 1
fi

report_files=(
  "astra/reports/terminalbench2.1-reproduction.md"
  "astra/reports/TerminalBench2.1-analysis/astra-hermes-pi-latest-83-task-comparison.md"
  "astra/reports/TerminalBench2.1-analysis/terminalbench2.1-astra-hermes-pi-product-metrics.csv"
  "astra/reports/TerminalBench2.1-analysis/terminalbench2.1-astra-hermes-pi-task-detail-appendix.csv"
  "astra/reports/TerminalBench2.1-analysis/generate-task-detail-appendix.mjs"
  "astra/reports/TerminalBench2.1-analysis/push-terminalbench2.1-reports.sh"
)

for report_file in "${report_files[@]}"; do
  if [[ ! -f "$report_file" ]]; then
    echo "Missing report artifact: $report_file" >&2
    exit 1
  fi
done

git fetch "$remote" "$branch"
if ! git merge-base --is-ancestor "$remote/$branch" HEAD; then
  echo "Remote branch $remote/$branch has commits not in the local branch." >&2
  echo "Rebase or merge explicitly, then rerun this script." >&2
  exit 1
fi

git add -- "${report_files[@]}"
if git diff --cached --quiet; then
  echo "No report changes to commit."
  exit 0
fi

echo "Staged report changes:"
git diff --cached --name-status

git commit -m "$commit_message"
git push "$remote" "HEAD:refs/heads/$branch"

echo "Published report commit to $remote/$branch."
