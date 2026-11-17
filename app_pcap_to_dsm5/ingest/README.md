# tapingest: live capture ingest

Turns the gateway's rotating capture files into the app's 5-minute Parquet partitions, so the
analysis pages work on live traffic instead of uploaded PCAPs.

```
tapcap@eno1   ─┐  /var/lib/tapcap/ready/*.pcap (60 s files)
tapcap@br-sim ─┘
        │
        ▼
tapingest ── devices files (MAC/IP → dataset)
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
- Assigns each packet to a dataset (one dataset = one person) via the devices files (`--devices`,
  repeatable): source MAC, source IP, destination MAC, destination IP. The device's own packets
  decide, and on each side the MAC wins over the IP, so a real device keeps its person when DHCP
  gives it a new address. An IP counts only if that side's MAC is the one registered for it (or the
  packet has no MAC), so an address handed to another, unregistered device is not credited to the
  registered person. Packets of unknown devices go to `gw_unassigned` (or are dropped with
  `--unmapped drop`).
- **Merges** rows into the 5-minute partition. A window spans several 60 s capture files, so a partition
  is read, extended and rewritten atomically (temp file + rename) instead of being overwritten.
- Adds a `Capture File` column. Re-processing a file first removes its old rows, so a crash or a
  manual re-run never duplicates packets.
- Records finished files in a SQLite state db (`--state`). A file is recorded only after all its rows
  are written. A truncated/corrupt file is ingested as far as readable and not retried.
- Updates `processed_parquet/known_ips.txt` like the upload page does.

## Background filter

Rules from [`process/MasterThesisInc.md`](../../process/MasterThesisInc.md) §3. The first matching rule drops the packet:

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
student_a_phone,phone,02:00:0a:2a:01:0b,10.42.1.11,gw_student_a
student_a_laptop,laptop,02:00:0a:2a:01:0c,10.42.1.12,gw_student_a
```

| Column | Meaning |
|---|---|
| `device` | Unique device name (also used in the ground-truth log) |
| `role` | `phone` or `laptop` (used by the runner; ignored here) |
| `mac` | The device's MAC on this network; the primary lookup key (phones: the fixed private Wi-Fi address) |
| `ip` | IPv4; lookup key when the packet's MAC is the registered one or missing |
| `dataset` | The person. Phone and laptop of one person share it. Becomes the folder name in `processed_parquet/` |

The file is validated on load (columns, valid IPv4, unique ip/device/mac, safe dataset names) and reloaded
automatically when it changes. Rows starting with `#` are ignored. Changes apply to files ingested after
the reload; to re-assign old data, delete the affected dataset folders and the state db, then re-run.

## Real devices (phones and laptops on the access point)

Not set up yet: during the live run (until 22.11.2026) the datasets are simulated profiles only. This
section is the checklist for the first real users.

**Why the MAC.** Real devices get their IP from dnsmasq (pool `10.42.0.100–200`, 12-hour leases), so an
IP can change or move to another device. The ingest therefore identifies a device by its MAC first and
uses the IP only when the packet's MAC is the registered one (see "What it does"). Phones use a
*private* Wi-Fi address instead of their hardware MAC; it is stable on one network only in the
"Fixed" mode, which each user has to set once.

**Where.** Real devices go into a **separate, gateway-local file**, `/etc/tapingest/devices.real.csv`,
never into `traffic-runner/config/devices.csv`: the runner creates one simulated container per row of
that file and only accepts the simulated network, and a real phone's MAC is personal data that does not
belong in git (`.gitignore` blocks `devices.real.csv`). Same format; template: `devices.real.example.csv`.

### Before the first user (once)

1. **Update the clone** so the gateway runs this ingest (MAC-first lookup, repeatable `--devices`):
   ```bash
   sudo git -C /opt/can-my-network pull --ff-only
   ```
   During a live run, agree on the time with whoever runs it: step 3 restarts the ingest.
2. **Create the real-devices file** (owner root, readable by the ingest's group, not by others):
   ```bash
   sudo install -d -m 755 /etc/tapingest
   sudo install -m 640 -o root -g tapingest /opt/can-my-network/app_pcap_to_dsm5/ingest/devices.real.example.csv /etc/tapingest/devices.real.csv
   sudo nano /etc/tapingest/devices.real.csv      # delete the example_phone line
   ```
3. **Give the ingest the second file.** `sudo systemctl edit --full tapingest`, then add this line
   right below the existing `--devices /opt/can-my-network/traffic-runner/config/devices.csv \` line:
   ```
       --devices /etc/tapingest/devices.real.csv \
   ```
   Then:
   ```bash
   sudo systemctl restart tapingest
   journalctl -u tapingest -n 5 --no-pager      # "Loaded N device(s) from .../devices.csv, /etc/tapingest/devices.real.csv"
   ```
4. **Create the reservations file for dnsmasq** (empty for now):
   ```bash
   echo "# fixed addresses of registered real devices: dhcp-host=<mac>,<ip>,<device>" | sudo tee /etc/dnsmasq.d/tapgw-hosts.conf
   ```

### Per user and device

1. **Consent.** The person agrees in writing to having their device's traffic recorded and analysed, and
   knows how to leave (see "Removing a user").
2. **Fixed private address on the device**, while it is connected to the project WiFi:
   - iPhone/iPad (iOS 18+): Settings → Wi-Fi → (i) next to the network → Private Wi-Fi Address →
     **Fixed**. iOS 17 and older: leave "Private Wi-Fi Address" switched **on** (on = fixed per network).
   - Android: Settings → Wi-Fi → the network → Privacy → **Use randomized MAC** (persistent; on some
     phones "Use device MAC"). Not "non-persistent".
   - Mac (macOS 15+): System Settings → Wi-Fi → Details… next to the network → Private Wi-Fi address → **Fixed**.
   - Windows: Settings → Network → Wi-Fi → the network → Random hardware addresses → **Off**.

   The device may reconnect. Do not choose "Off"/hardware address on phones unless needed: "Fixed" is
   stable here and still not trackable across other networks.
3. **Read the address** (`xx:xx:xx:xx:xx:xx`): on the same screen ("Wi-Fi Address"), or on the gateway
   from the lease the device just got (hostname in the last-but-one column):
   ```bash
   cat /var/lib/misc/dnsmasq.leases
   ```
4. **Choose the names and the IP:**
   - dataset = the person: `gw_<name>_<letter>`, lower case, not ending in a digit (e.g. `gw_anna_a`).
     All devices of one person share it.
   - device = unique name, `[a-z0-9_]`, e.g. `anna_a_phone`; role `phone` or `laptop`.
   - IP = a free address **outside** the pool, `10.42.0.10–99`, unique.
5. **Register** (one line per device) and **reserve the address**, with the same MAC, IP and device:
   ```bash
   echo "anna_a_phone,phone,a2:4f:12:34:56:78,10.42.0.21,gw_anna_a" | sudo tee -a /etc/tapingest/devices.real.csv
   echo "dhcp-host=a2:4f:12:34:56:78,10.42.0.21,anna_a_phone" | sudo tee -a /etc/dnsmasq.d/tapgw-hosts.conf
   sudo /usr/share/dnsmasq/systemd-helper checkconfig && sudo systemctl restart dnsmasq
   ```
   Always run `checkconfig` first and restart only if it passes: a broken dnsmasq config means no
   DNS/DHCP for every real device (HardwareSetup problem 19). The ingest picks up the changed devices
   file by itself; no restart.
6. **Check:**
   - On the device: Wi-Fi off and on. `cat /var/lib/misc/dnsmasq.leases` shows the MAC with the reserved IP.
   - After a few minutes, new partitions for the person:
     ```bash
     ls -t /opt/can-my-network/app_pcap_to_dsm5/app/processed_parquet/gw_anna_a | head -3
     ```
   - In the portal (frontend), add the person under People and devices with the dataset as source.

### Changes later

- **The device shows up as unknown** (its traffic goes to `gw_unassigned`; in the leases a new MAC with
  the device's hostname): the private address changed (setting back on "Rotating", network forgotten,
  phone reset). Set "Fixed" again, then replace the old MAC in **both** files (devices file and
  `tapgw-hosts.conf`), `checkconfig`, restart dnsmasq.
- **New phone:** same as a new device; delete the old phone's lines in both files.
- **Shared devices** (family laptop, TV) cannot be split by person on the network: do not register them
  for a person. Give them a household dataset (e.g. `gw_household_a`) that is not analysed as a person,
  or leave them unregistered.

### Removing a user

1. Delete the person's lines in `/etc/tapingest/devices.real.csv` and `/etc/dnsmasq.d/tapgw-hosts.conf`,
   `checkconfig`, restart dnsmasq.
2. Delete their data and results:
   - partitions: `sudo rm -r /opt/can-my-network/app_pcap_to_dsm5/app/processed_parquet/gw_anna_a`
   - the portal's day records: `/var/lib/cmn-portal/cache/gw_anna_a` on the gateway and
     `$CMN_DATA/frontend_cache/gw_anna_a` on the laptop that computes them (frontend README)
   - their person profile in the portal (People and devices)
3. The raw captures in `/var/lib/tapcap/ready` still contain their traffic (raw pcaps are kept); delete
   them or let them expire according to the retention you agreed with the person.

### Not built yet (needed for real use)

- **Device names in the portal:** the frontend reads device names only from
  `traffic-runner/config/devices.csv` (`CMN_DEVICES`), so real devices appear without names in "When
  the devices were online". Fix: let the frontend read `/etc/tapingest/devices.real.csv` as well.
- **Warning for unknown devices:** nothing reports a registered person's device that suddenly appears
  with a new address. Fix: a check in the daily report (new MACs in the leases that are in no devices
  file, and the size of `gw_unassigned`).
- **IPv6:** the LAN serves IPv4 only. If IPv6 is ever enabled, devices change their IPv6 addresses
  daily; the MAC-first lookup covers that, but `pcap_etl` and the metrics only read IPv4.
- **Mobile data (outlook):** away from the home WiFi the gateway sees nothing. A WireGuard VPN from the
  phone to the gateway, recorded on `wg0`, would close that gap without code changes; the full plan is
  in [process/MobileDataVPN.md](../../process/MobileDataVPN.md).
- **More robust identity (outlook):** one WiFi password per person (UniFi "Private Pre-Shared Keys",
  each mapped to its own VLAN and subnet) would identify a person even with rotating addresses. It needs
  VLAN interfaces, DHCP ranges and firewall rules per person on the gateway and a lookup by subnet.

## Run once (backfill, synthetic captures, tests)

```bash
TZ=Europe/Zurich python ingest/tapingest.py --watch /path/to/ready --devices devices.csv \
    --out app/processed_parquet --state /tmp/tapingest-state.sqlite --once
```

## Install on the gateway

```bash
sudo git clone https://github.com/KarlaRuggaber/Can-My-Network-Tell-How-I-Feel-.git /opt/can-my-network
cd /opt/can-my-network/app_pcap_to_dsm5
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r ingest/requirements.txt

sudo useradd --system --no-create-home --shell /usr/sbin/nologin tapingest
sudo usermod -aG tapcap tapingest                      # read /var/lib/tapcap/ready
sudo install -d -o tapingest -g tapingest -m 755 app/processed_parquet
# devices: the unit reads ../traffic-runner/config/devices.csv from the same clone,
# the list the runner containers are generated from; real devices in a second file (see above)

sudo cp ingest/tapingest.service /etc/systemd/system/   # then set --exclude-mac to the AP's MAC
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

Update later with `cd /opt/can-my-network && sudo git pull`, then `sudo systemctl restart tapingest`.
`processed_parquet/`, `feature_cache/`, `.venv/`, `user_profiles.json` and `secrets.toml` are ignored by git,
so the running system never blocks a pull.

## Limits

- Throughput: about 10k packets/s on an Apple M4 Pro (scapy). The mini-PC will be slower. A high-quality
  video stream is about 500–1000 packets/s, so a few devices in parallel are fine; watch the
  "still pending" count in the log. Backfilling many days of heavy synthetic traffic takes a while.
- `--max-rows` (default 300 000) bounds memory per batch.
- Only IPv4 is parsed (same as the upload page).
- Rows from different capture interfaces are matched only by IP, so simulated devices (`10.42.1.0/24`)
  and real devices (`10.42.0.0/24`) must not share addresses.
