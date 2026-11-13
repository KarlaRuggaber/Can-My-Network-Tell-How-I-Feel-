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
