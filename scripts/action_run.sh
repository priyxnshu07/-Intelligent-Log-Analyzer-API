#!/usr/bin/env bash
# Used by action.yml. Reads settings from environment variables (never from
# text pasted into the script), writes a Markdown report to the job summary and
# exits non-zero only when the chosen threshold is reached.
set -u

LOG_PATH="${LOGDOCTOR_LOG_PATH:-}"
FAIL_ON="${LOGDOCTOR_FAIL_ON:-}"
MAX_LINES="${LOGDOCTOR_MAX_LINES:-50000}"
REPORT="${LOGDOCTOR_REPORT:-log-report.md}"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/null}"

if [ -z "$LOG_PATH" ] || [ ! -f "$LOG_PATH" ]; then
  echo "logdoctor: log file not found: ${LOG_PATH:-<empty path>}" >&2
  exit 2
fi
case "$FAIL_ON" in ""|warning|error|critical) ;; *) echo "logdoctor: fail-on must be warning, error or critical" >&2; exit 2;; esac

python -m logdoctor "$LOG_PATH" --markdown --max-lines "$MAX_LINES" > "$REPORT" || exit 2
{ echo "## Log Doctor"; echo; cat "$REPORT"; } >> "$SUMMARY"
python -m logdoctor "$LOG_PATH" --max-lines "$MAX_LINES" --top 5

if [ -n "$FAIL_ON" ]; then
  python -m logdoctor "$LOG_PATH" --max-lines "$MAX_LINES" --fail-on "$FAIL_ON" > /dev/null
  status=$?
  if [ "$status" -eq 1 ]; then echo "logdoctor: found a problem at or above '$FAIL_ON' level" >&2; fi
  exit "$status"
fi
exit 0
