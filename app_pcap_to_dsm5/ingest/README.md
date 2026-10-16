# tapingest: live capture ingest

Turns the gateway's rotating capture files into the app's 5-minute Parquet partitions, so the
analysis pages work on live traffic instead of uploaded PCAPs.

```
tapcap@eno1   ─┐  /var/lib/tapcap/ready/*.pcap (60 s files)
tapcap@br-sim ─┘
        │
        ▼
tapingest ── devices.csv (IP → dataset)
        │
        ▼
app/processed_parquet/<dataset>/<dataset>__YYYYMMDD_HHMM.parquet  →  app pages 01/02/03
```

## What it does

- Polls the watch folders (`--poll`, default 10 s) for capture files it has not processed yet.
  Files modified in the last `--min-age` seconds are skipped, in case something is still writing them.
- `--since 2026-10-16T18:00` ignores older capture files, e.g. to start live ingest without
  back-processing every capture recorded so far.
- Parses every packet with `app/utils/pcap_etl.py`, the same parser the upload page uses, so live and
  uploaded data have identical columns. Timestamps are local time: run with `TZ=Europe/Zurich`.
- Drops background traffic that is not user behaviour (see "Background filter" below) and counts the
  dropped packets per rule.
- Assigns each packet to a dataset (one dataset = one person) via `devices.csv`: source IP first,
  then destination IP, then source/destination MAC (for DHCP broadcasts sent from `0.0.0.0`).
  Packets of unknown devices go to `gw_unassigned` (or are dropped with `--unmapped drop`).
- **Merges** rows into the 5-minute partition. A window spans several 60 s capture files, so a partition
  is read, extended and rewritten atomically (temp file + rename) instead of being overwritten.
- Adds a `Capture File` column. Re-processing a file first removes its old rows, so a crash or a
  manual re-run never duplicates packets.
- Records finished files in a SQLite state db (`--state`). A file is recorded only after all its rows
  are written. A truncated/corrupt file is ingested as far as readable and not retried.
- Updates `processed_parquet/known_ips.txt` like the upload page does.

## Background filter

Rules from `process/MasterThesisInc.md` §3 in the project repo. The first matching rule drops the packet:

| Rule | Drops | Why |
|---|---|---|
| `infra_device` | Everything to/from `--exclude-mac` / `--exclude-ip` (the access point) | UniFi controller and AP traffic would fill every quiet minute |
| (keep) | DHCP (UDP 67/68) of clients | Needed for C5_F1 re-associations. The gateway's broadcast offers/acks count as `broadcast` |
| `mdns`, `ssdp`, `ntp` | UDP 5353, 1900, 123 | Periodic device chatter, not behaviour |
| `broadcast` | Broadcast or multicast destination (255.255.255.255, LAN broadcast, 224.0.0.0/4) | Not attributable to a user action |
| `gateway_service` | To/from `--gateway-ip` except DNS (53): SSH, controller, ping … | Gateway services, not behaviour |
| `no_client` | Packets where neither side is a client in `--lan-net` | Not attributable to a device |

Everything else between a client and the internet is kept, including STUN to the internet (calls) and
Apple push (5223); whether always-on keep-alives should go is a decision for after looking at real nights.

Defaults: `--gateway-ip 10.42.0.1 --gateway-ip 10.42.1.1`, `--lan-net 10.42.0.0/24 --lan-net 10.42.1.0/24`.
`--no-filter` disables the filter (e.g. to compare with an upload of the same pcap).

Drop counts per capture file and rule are in the state db:

```bash
sudo sqlite3 /var/lib/tapingest/state.sqlite "select rule, sum(packets) from dropped group by rule"
```

## devices.csv

One row per device. Shared with the traffic runner (`traffic-runner/config/devices.csv` in the project
repo); do not change the format without agreeing on it.

```csv
device,role,mac,ip,dataset
student01_phone,phone,02:00:0a:2a:01:0b,10.42.1.11,gw_student_01
student01_laptop,laptop,02:00:0a:2a:01:0c,10.42.1.12,gw_student_01
```

| Column | Meaning |
|---|---|
| `device` | Unique device name (also used in the ground-truth log) |
| `role` | `phone` or `laptop` (used by the runner; ignored here) |
| `mac` | Fixed MAC; documentation/feed matching only, the app works on IP |
| `ip` | Fixed IPv4; the actual lookup key |
| `dataset` | The person. Phone and laptop of one person share it. Becomes the folder name in `processed_parquet/` |

The file is validated on load (columns, valid IPv4, unique ip/device/mac, safe dataset names) and reloaded
automatically when it changes. Rows starting with `#` are ignored. Changes apply to files ingested after
the reload; to re-assign old data, delete the affected dataset folders and the state db, then re-run.

Real devices (on `eno1`) can be added the same way once they have a fixed IP (a `dhcp-host=` reservation in dnsmasq).

## Run once (backfill, synthetic captures, tests)

```bash
TZ=Europe/Zurich python ingest/tapingest.py --watch /path/to/ready --devices devices.csv \
    --out app/processed_parquet --state /tmp/tapingest-state.sqlite --once
```

## Install on the gateway

```bash
sudo git clone <repo> /opt/app_pcap_to_dsm5_public
cd /opt/app_pcap_to_dsm5_public
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r ingest/requirements.txt

sudo useradd --system --no-create-home --shell /usr/sbin/nologin tapingest
sudo usermod -aG tapcap tapingest                      # read /var/lib/tapcap/ready
sudo install -d -o tapingest -g tapingest -m 755 app/processed_parquet
sudo install -d -m 755 /etc/tapingest
sudo cp ingest/devices.example.csv /etc/tapingest/devices.csv   # then edit

sudo cp ingest/tapingest.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tapingest
journalctl -u tapingest -f
```

Check the result:

```bash
ls app/processed_parquet/
sudo sqlite3 /var/lib/tapingest/state.sqlite \
  "select path, packets, rows_mapped, rows_unmapped, error from processed order by processed_at desc limit 5"
```

The app (`app/docker-compose.yml`) bind-mounts `app/processed_parquet`, so new datasets show up in its
dataset selection without a restart. Pages 01 and 02 notice new or rewritten partitions and recompute
the affected days.

## Limits

- Throughput: about 10k packets/s on an Apple M4 Pro (scapy). The mini-PC will be slower. A high-quality
  video stream is about 500–1000 packets/s, so a few devices in parallel are fine; watch the
  "still pending" count in the log. Backfilling many days of heavy synthetic traffic takes a while.
- `--max-rows` (default 300 000) bounds memory per batch.
- Only IPv4 is parsed (same as the upload page).
- Rows from different capture interfaces are matched only by IP, so simulated devices (`10.42.1.0/24`)
  and real devices (`10.42.0.0/24`) must not share addresses.
