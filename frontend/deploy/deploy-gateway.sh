#!/usr/bin/env bash
# Build the UI on the laptop, copy portal v2 to the mini-PC and (re)start its containers (portal
# and dictation). v1 is not touched; switch-gateway.sh decides which one the tailnet URL shows.
#   frontend/deploy/deploy-gateway.sh
# Needs: SSH to the mini-PC (Tailscale), passwordless sudo there, Docker with the app-app image.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

echo "== build the UI"
(cd "$FRONTEND/web" && npm run build >/dev/null && echo "web/dist built")

echo "== folders on the mini-PC"
gw "sudo install -d -m 755 $PORTAL_DIR/frontend && sudo install -d -m 755 $PORTAL_CACHE && sudo install -d -m 700 $PORTAL_HOME && sudo install -d -m 700 /var/lib/cmn-whisper/models"
echo "== logins, people and assistant settings: copied from v1 on the first deploy only"
gw "if sudo test -z \"\$(sudo ls -A $PORTAL_HOME)\" && sudo test -d $V1_HOME; then sudo cp -a $V1_HOME/. $PORTAL_HOME/ && echo copied from $V1_HOME; else echo kept; fi"

echo "== copy code (no venv, tests or node_modules)"
rsync -a --delete -e "$RSYNC_SSH" --rsync-path="sudo rsync" \
  --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude 'node_modules' \
  --include 'backend/***' --include 'shared/***' --include 'deploy/***' --include 'whisper/***' \
  --include 'web/' --include 'web/dist/***' --exclude '*' \
  "$FRONTEND/" "$GW:$PORTAL_DIR/frontend/"

echo "== build and start the container"
gw "sudo docker compose -f $PORTAL_DIR/frontend/deploy/docker-compose.yml up -d --build 2>&1 | tail -4"
sleep 4
gw "curl -fsS http://127.0.0.1:$PORTAL_PORT/api/health && echo"
echo "== dictation (the first start downloads the Whisper model, about 0.5 GB)"
for i in $(seq 1 60); do
  gw 'curl -fsS http://127.0.0.1:8601/health' 2>/dev/null | grep -q '"loaded":true' && break
  sleep 5
done
gw 'curl -fsS http://127.0.0.1:8601/health && echo' || echo "whisper not ready yet: sudo docker logs cmn-whisper"
echo "== v2 runs on 127.0.0.1:$PORTAL_PORT; the tailnet URL shows: $(gw 'sudo tailscale serve status 2>/dev/null | grep -o "127.0.0.1:[0-9]*" | head -1')"
echo "   frontend/deploy/switch-gateway.sh v2   # show v2 and stop v1 (v1 can be started again)"
