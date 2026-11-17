#!/usr/bin/env bash
# Build the UI on the laptop, copy the portal to the mini-PC and (re)start its container.
#   frontend/deploy/deploy-gateway.sh
# Needs: SSH to the mini-PC (Tailscale), passwordless sudo there, Docker with the app-app image.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

echo "== build the UI"
(cd "$FRONTEND/web" && npm run build >/dev/null && echo "web/dist built")

echo "== folders on the mini-PC"
gw 'sudo install -d -m 755 /opt/cmn-portal/frontend && sudo install -d -m 755 /var/lib/cmn-portal/cache && sudo install -d -m 700 /var/lib/cmn-portal/home && sudo install -d -m 700 /var/lib/cmn-whisper/models'

echo "== copy code (no venv, tests or node_modules)"
rsync -a --delete -e "$RSYNC_SSH" --rsync-path="sudo rsync" \
  --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude 'node_modules' \
  --include 'backend/***' --include 'shared/***' --include 'deploy/***' --include 'whisper/***' \
  --include 'web/' --include 'web/dist/***' --exclude '*' \
  "$FRONTEND/" "$GW:/opt/cmn-portal/frontend/"

echo "== build and start the container"
gw 'sudo docker compose -f /opt/cmn-portal/frontend/deploy/docker-compose.yml up -d --build 2>&1 | tail -3'
sleep 4
gw 'curl -fsS http://127.0.0.1:8600/api/health && echo'
echo "== dictation (the first start downloads the Whisper model, about 0.5 GB)"
for i in $(seq 1 60); do
  gw 'curl -fsS http://127.0.0.1:8601/health' 2>/dev/null | grep -q '"loaded":true' && break
  sleep 5
done
gw 'curl -fsS http://127.0.0.1:8601/health && echo' || echo "whisper not ready yet: sudo docker logs cmn-whisper"
