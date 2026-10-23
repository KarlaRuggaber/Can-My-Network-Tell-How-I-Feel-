#!/bin/sh
# Deploy the runner on the gateway in one step: pull the clone, rebuild the image (code and
# config are baked in), recreate the containers, run the tests.
#
#   sudo /opt/can-my-network/traffic-runner/scripts/deploy.sh          # refuses while activities run
#   sudo FORCE=1 /opt/can-my-network/traffic-runner/scripts/deploy.sh  # interrupts running activities
#
# Run it after every git pull that changed traffic-runner/. A pull alone does not change the
# running runner (only the ingest reads config/devices.csv straight from the clone).
set -eu
cd "$(dirname "$0")/.."
repo=$(git rev-parse --show-toplevel)

# Recreating a container kills activities running in it; those blocks would get no log row.
running=""
for svc in $(docker compose ps --services --status running 2>/dev/null); do
    n=$(docker compose exec -T "$svc" python3 -c \
        "import glob; print(sum(b'runner\x00run' in open(f, 'rb').read() for f in glob.glob('/proc/[0-9]*/cmdline')))" \
        < /dev/null 2>/dev/null || echo 0)
    [ "$n" -gt 0 ] && running="$running $svc"
done
if [ -n "$running" ] && [ "${FORCE:-0}" != "1" ]; then
    echo "activities are running on:$running. Wait until they end, or use FORCE=1." >&2
    exit 1
fi

git -C "$repo" pull --ff-only
echo "version: $(git -C "$repo" log --oneline -1)"
docker compose build

# Renamed devices: the new containers need the IPs the old ones still hold, so remove the
# old ones first. Otherwise only containers whose image or settings changed are recreated.
if [ "$(docker compose ps --services | sort)" != "$(docker compose config --services | sort)" ]; then
    echo "device list changed: removing the old containers first"
    docker compose down --remove-orphans
fi
docker compose up -d --remove-orphans
docker compose ps

first=$(docker compose config --services | head -1)
docker compose exec -T "$first" python3 -m runner validate < /dev/null
docker compose exec -T "$first" python3 -m pytest -q -p no:cacheprovider < /dev/null | tail -1
