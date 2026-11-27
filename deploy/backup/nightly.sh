#!/usr/bin/env bash
# Runs backup.sh every day at BACKUP_HOUR_UTC (default 02:00 UTC). Failures are logged loudly
# and retried the next night; monitor the logs for "BACKUP FAILED".
set -uo pipefail
hour="${BACKUP_HOUR_UTC:-2}"
while true; do
  now=$(date -u +%s)
  next=$(date -u -d "$(date -u +%Y-%m-%d) ${hour}:00" +%s)
  if [ "$next" -le "$now" ]; then next=$((next + 86400)); fi
  sleep $((next - now))
  /usr/local/bin/backup.sh || echo "BACKUP FAILED at $(date -u)"
done
