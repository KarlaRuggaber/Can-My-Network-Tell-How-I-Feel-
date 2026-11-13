#!/usr/bin/env bash
# Update the portal's data on the mini-PC. The heavy metric computation stays on the laptop:
#   1. pull new Parquet partitions and the runner's plans/logs from the mini-PC,
#   2. take the people configured in the portal (profiles.json) from the mini-PC,
#   3. run the export on the laptop (evaluation tables where present, else the metric code),
#   4. push the small day records to /var/lib/cmn-portal/cache on the mini-PC.
#   frontend/deploy/sync-gateway.sh            # once
#   frontend/deploy/sync-gateway.sh --watch 900 # every 15 minutes
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
DATA="${CMN_DATA:-$HOME/cmn-data}"
HOME_DIR="${CMN_HOME:-$DATA/frontend}"
WATCH=0
[ "${1:-}" = "--watch" ] && WATCH="${2:-900}"

once() {
  echo "== $(date '+%H:%M') pull captures and plans"
  for s in $SOURCES; do
    rsync -a -e "$RSYNC_SSH" "$GW:/opt/can-my-network/app_pcap_to_dsm5/app/processed_parquet/$s" "$DATA/processed_parquet/"
  done
  rsync -a -e "$RSYNC_SSH" --include '*.csv' --include '*.state.jsonl' --exclude 'gateway-samples.csv' --exclude '*' \
    "$GW:/var/lib/traffic-executor/" "$DATA/run/"
  echo "== people configured in the portal"
  mkdir -p "$HOME_DIR"
  if gw 'sudo test -f /var/lib/cmn-portal/home/profiles.json'; then
    gw 'sudo cat /var/lib/cmn-portal/home/profiles.json' > "$HOME_DIR/profiles.json.tmp" && mv "$HOME_DIR/profiles.json.tmp" "$HOME_DIR/profiles.json"
  fi
  echo "== export on the laptop"
  (cd "$FRONTEND/backend" && .venv/bin/python -m cmn_frontend.export --jobs 3 $SOURCES 2>&1 | grep -E '^[0-9:]+ [^ ]+: \{' || true)
  echo "== push day records"
  rsync -a --delete -e "$RSYNC_SSH" --rsync-path="sudo rsync" "$DATA/frontend_cache/" "$GW:/var/lib/cmn-portal/cache/"
  echo "== done $(date '+%H:%M')"
}

while true; do
  once
  [ "$WATCH" -gt 0 ] || break
  sleep "$WATCH"
done
