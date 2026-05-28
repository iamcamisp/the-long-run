#!/usr/bin/env bash
# Weekly run for *The Long Run*: generate this week's issue, render, commit, push.
# Wired to a cron (Mondays). Logs to refresh.log.
set -euo pipefail

cd "$(dirname "$0")"
exec >> refresh.log 2>&1
echo "===== $(date '+%Y-%m-%d %H:%M:%S') run start ====="

python3 generate_issue.py "$@"

if [[ -n "$(git status --porcelain)" ]]; then
  git add -A
  git commit -q -m "Issue: week of $(date '+%Y-%m-%d')"
  git push -q
  echo "pushed."
else
  echo "no changes."
fi
echo "===== run done ====="
