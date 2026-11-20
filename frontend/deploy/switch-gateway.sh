#!/usr/bin/env bash
# Choose which portal the tailnet URL (https://minipc.<tailnet>.ts.net) shows, and stop the other
# one to free its memory. Stopped containers stay stopped after a reboot ("unless-stopped") and keep
# their image, data and logins, so switching back is one command.
#   frontend/deploy/switch-gateway.sh v3            # show v3 (+ dictation), stop v1 and v2
#   frontend/deploy/switch-gateway.sh v2            # show v2 (+ dictation), stop v1 and v3
#   frontend/deploy/switch-gateway.sh v1            # show v1 (screenshots), stop v2, v3 and dictation
#   frontend/deploy/switch-gateway.sh v2 --keep     # show v2, leave the others running
#   frontend/deploy/switch-gateway.sh status
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

status() {
  gw 'sudo docker ps -a --filter name=cmn- --format "{{.Names}}: {{.Status}}"; sudo tailscale serve status 2>/dev/null | sed -n 1,3p'
}

target="${1:-status}"
keep="${2:-}"
case "$target" in
  v1) port=8600; start="cmn-portal"; other="cmn-portal-v2 cmn-portal-v3 cmn-whisper" ;;
  v2) port=$V2_PORT; start="cmn-portal-v2 cmn-whisper"; other="cmn-portal cmn-portal-v3" ;;
  v3) port=$PORTAL_PORT; start="cmn-portal-v3 cmn-whisper"; other="cmn-portal cmn-portal-v2" ;;
  status) status; exit 0 ;;
  *) echo "usage: $0 v1|v2|v3 [--keep] | status" >&2; exit 2 ;;
esac

echo "== start $start"
gw "sudo docker start $start >/dev/null"
for i in $(seq 1 30); do
  gw "curl -fsS http://127.0.0.1:$port/api/health >/dev/null" 2>/dev/null && break
  sleep 2
done
gw "curl -fsS http://127.0.0.1:$port/api/health >/dev/null" || { echo "$target does not answer on $port; nothing switched" >&2; exit 1; }
echo "== tailnet URL -> 127.0.0.1:$port"
gw "sudo tailscale serve --bg $port >/dev/null"
if [ "$keep" != "--keep" ]; then
  echo "== stop $other (back with: $0 <version>)"
  gw "sudo docker stop $other >/dev/null 2>&1 || true"
fi
status
