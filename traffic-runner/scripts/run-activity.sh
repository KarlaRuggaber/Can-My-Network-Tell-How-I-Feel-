#!/bin/sh
# Run one activity on one simulated device:
#   sudo scripts/run-activity.sh <device> --activity ID --seed N --profile P --block-id B [...]
# stdin is detached (< /dev/null): `docker compose exec` reads the terminal even with -T,
# which swallows pasted lines and stops the command when it runs in the background (&)
# or under `timeout`.
set -eu
if [ $# -lt 1 ]; then
    echo "usage: $0 <device> --activity ID --seed N --profile P --block-id B [...]" >&2
    exit 2
fi
device=$1
shift
cd "$(dirname "$0")/.."
exec docker compose exec -T "$device" python3 -m runner run "$@" < /dev/null
