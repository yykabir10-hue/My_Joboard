#!/usr/bin/env bash
# Daily headless job scrape + email digest. This is what cron runs.
#
#   crontab -e
#   30 7 * * *  /home/<you>/ai-job-search/tools/daily_run.sh
#
# Deliberately does NOT source ~/.bashrc: cron runs with a minimal environment,
# and a script that only works because of an interactive shell's PATH is a
# script that works when you test it and fails at 07:30. PATH is set explicitly
# below instead.
#
# Credentials come from .env in the repo root (gitignored, chmod 600).
# Run with --dry-run to scrape and render without sending mail.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# bun lives in ~/.bun/bin for a user-local install; ~/.local/bin covers gh and
# anything else installed without sudo.
export PATH="$HOME/.bun/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

DATE="$(date +%F)"
POOL="job_scraper/pools/${DATE}.json"
LOG_DIR="job_scraper/logs"
LOG="${LOG_DIR}/${DATE}.log"
LOCK="/tmp/ai-job-search-daily.lock"

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

mkdir -p "$LOG_DIR" "$(dirname "$POOL")"

# A slow portal must never let a second run start on top of the first - two
# concurrent writers would race on seen_jobs.json.
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date -Is) another run holds the lock; exiting" >>"$LOG"
  exit 0
fi

exec >>"$LOG" 2>&1
# ${DRY_RUN:+...} tests for non-EMPTY, and "0" is non-empty - it labelled every
# real run as a dry run. Compare the value explicitly.
LABEL=""
[[ "$DRY_RUN" == "1" ]] && LABEL=" (dry run)"
echo "=== $(date -Is) starting${LABEL} ==="

if ! command -v bun >/dev/null; then
  echo "FATAL: bun not on PATH ($PATH)"
  exit 1
fi

# --update-seen is what makes tomorrow's run report only genuinely new jobs, so
# it is deliberately skipped on a dry run: marking jobs as seen without ever
# mailing them would mean the next real run reports 0 new and those postings are
# never shown at all. A dry run must be repeatable and leave no trace.
SEEN_FLAG=(--update-seen)
[[ "$DRY_RUN" == "1" ]] && SEEN_FLAG=()

if python3 tools/run_scrape.py --out "$POOL" "${SEEN_FLAG[@]}" --timeout 120; then
  echo "scrape ok -> $POOL"
else
  echo "FATAL: scrape failed"
  exit 1
fi

if [[ "$DRY_RUN" == "1" ]]; then
  python3 tools/send_digest.py "$POOL" --html-out "${LOG_DIR}/${DATE}.html"
  echo "=== $(date -Is) done (dry run, nothing sent) ==="
  exit 0
fi

if python3 tools/send_digest.py "$POOL"; then
  echo "digest sent"
else
  echo "WARNING: digest send failed; pool is still at $POOL"
  exit 1
fi

# Keep a month of logs and pools; unbounded growth in a daily job is a slow leak.
find "$LOG_DIR" -name '*.log' -mtime +30 -delete 2>/dev/null || true
find "$LOG_DIR" -name '*.html' -mtime +30 -delete 2>/dev/null || true
find job_scraper/pools -name '*.json' -mtime +30 -delete 2>/dev/null || true

echo "=== $(date -Is) done ==="
