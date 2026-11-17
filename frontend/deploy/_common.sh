# Shared settings for deploy-gateway.sh and sync-gateway.sh.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$(cd "$HERE/.." && pwd)"
[ -f "$HERE/gateway.env" ] && . "$HERE/gateway.env"
GW_HOST="${GW_HOST:-100.124.37.62}"
GW_USER="${GW_USER:-kathy}"
GW_KEY="${GW_KEY:-$HOME/.ssh/minipc_deploy}"
GW_KEY="${GW_KEY/#\~/$HOME}"
GW_HOST_ALIAS="${GW_HOST_ALIAS:-can-my-network-gw}"
SOURCES="${SOURCES:-gw_insomnia_a gw_mdd_suicidality_a gw_social_anxiety_a}"
SSH_OPTS=(-i "$GW_KEY" -o BatchMode=yes -o ConnectTimeout=20 -o HostKeyAlias="$GW_HOST_ALIAS")
GW="$GW_USER@$GW_HOST"
gw() { ssh "${SSH_OPTS[@]}" "$GW" "$@"; }
RSYNC_SSH="ssh ${SSH_OPTS[*]}"
# Where v2 lives on the mini-PC (keep in line with docker-compose.yml). v1 stays in /opt/cmn-portal
# (container cmn-portal, port 8600); both read the day records in /var/lib/cmn-portal/cache.
PORTAL_DIR=/opt/cmn-portal-v2
PORTAL_HOME=/var/lib/cmn-portal-v2/home
PORTAL_PORT=8610
PORTAL_CACHE=/var/lib/cmn-portal/cache
V1_HOME=/var/lib/cmn-portal/home
