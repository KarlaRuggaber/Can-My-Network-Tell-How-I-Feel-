# Deployment: Live Ingest and Analysis App on the Gateway

## 1. What we did and why

On 16.10.2026 we connected the capture gateway ([HardwareSetup.md](HardwareSetup.md)) to the thesis analysis app (`app_pcap_to_dsm5`). Before, the app only accepted PCAP files uploaded by hand. Now every 60-second capture file is turned into the app's data format within seconds, and the app runs on the gateway itself.

The work had three parts:

1. **Live ingest service (`tapingest`).** It reads every new capture file from tapcap, assigns each packet to a dataset (one dataset = one person) and writes the 5-minute Parquet partitions the app reads.
2. **App changes.** The parser moved into a shared module, so the upload page and the ingest produce identical rows. The app's caches now notice data that grows while the app is running.
3. **Deployment on the mini-PC.** We installed the ingest as a systemd service, installed Docker without letting it touch the firewall, and run the app in a container that is reachable only through an SSH tunnel.

The app code itself now lives in this repository, in [`app_pcap_to_dsm5/`](../app_pcap_to_dsm5/ORIGIN.md), and the gateway runs a `git clone` of it (Section 7.5).

This implements step 4.1 of [MasterThesisInc.md](MasterThesisInc.md) in a different form (live instead of nightly). The differences, and the parts of that plan that are still open, are listed in Section 4.

The work was done with the support of an AI assistant (Claude), which wrote and tested the code and ran the deployment commands on the mini-PC over SSH. Each step was checked against the real system, and the outputs quoted below come from it.

## 2. Architecture

```
 real devices ──WiFi── U7 Lite ── eno1 (10.42.0.1) ─┐
                                                     ├─ mini-PC: nftables NAT ── wlp2s0 ── Internet (hotspot)
 runner containers ─────────── br-sim (10.42.1.1) ─┘
                                   │
        tapcap@eno1   ──► /var/lib/tapcap/ready/cap-<ms>.pcap       (60 s files)
        tapcap@br-sim ──► /var/lib/tapcap/sim/ready/cap-<ms>.pcap   (since 16.10, not yet watched by the ingest)
                                   │  polled every 10 s
                                   ▼
        tapingest.service ── /etc/tapingest/devices.csv (IP → dataset)
                                   │  merge into 5-min windows
                                   ▼
        /opt/can-my-network/app_pcap_to_dsm5/app/processed_parquet/<dataset>/<dataset>__YYYYMMDD_HHMM.parquet
                                   │  bind mount
                                   ▼
        Docker container pcap-to-dsm5 (Streamlit, 127.0.0.1:8501, host network)
                                   │
        laptop: ssh -L 8501:localhost:8501  →  http://localhost:8501
```

### Components on the mini-PC

| Component | What | Where |
| --- | --- | --- |
| Code | `git clone` of this repository (owned by root), app in `app_pcap_to_dsm5/` | `/opt/can-my-network` |
| Python venv for the ingest | scapy 2.8.0, pandas 3.0.6, pyarrow 26.0.0, Python 3.14.4 | `/opt/can-my-network/app_pcap_to_dsm5/.venv` |
| Ingest service | `tapingest.service`, user `tapingest` (member of group `tapcap`), enabled at boot | `/etc/systemd/system/tapingest.service` |
| Device map | `devices.csv` (IP → dataset) | `/etc/tapingest/devices.csv` |
| Ingest state | SQLite list of processed capture files | `/var/lib/tapingest/state.sqlite` |
| App data | Parquet partitions, owned by `tapingest` | `/opt/can-my-network/app_pcap_to_dsm5/app/processed_parquet/` |
| App feature cache | Daily metric CSVs written by the app | `/opt/can-my-network/app_pcap_to_dsm5/app/feature_cache/` |
| App login | `secrets.toml` (username/password), mode 600, root | `/opt/can-my-network/app_pcap_to_dsm5/app/.streamlit/secrets.toml` |
| Docker | docker.io 29.1.3, compose 2.40.3, buildx 0.30.1, `iptables: false` | `/etc/docker/daemon.json` |
| App container | `pcap-to-dsm5`, image `app-app`, restart `unless-stopped`, host network | `app/docker-compose.yml` + `app/docker-compose.gateway.yml` |

## 3. How the ingest works

`tapingest` (`ingest/tapingest.py` in the app repo) runs as a loop:

1. **Find new files.** Every 10 s it lists the watch folders (`--watch`, repeatable) and takes every `.pcap`/`.pcapng` that is not yet in the state db. It skips files modified in the last 5 s (in case they are still being written) and, if set, files older than `--since`.
2. **Parse.** It reads the packets with the same function the app's upload page uses (`app/utils/pcap_etl.py`: `parse_packet_row`). Live and uploaded data therefore have identical columns: `Timestamp, Date, Hour, Protocol, Source IP, Destination IP, Source Port, Destination Port, TCP Flags, Length, IsDNS, DNS_QNAME, DNS_QTYPE, DNS_ANS_NAME, DNS_ANS_IPS`. Timestamps are naive local time, so the service runs with `TZ=Europe/Zurich`.
3. **Drop background traffic** (Section 3.1) and count the dropped packets per rule.
4. **Assign a dataset.** It looks up the source IP in `devices.csv`, then the destination IP, then the source and destination MAC (for DHCP broadcasts sent from `0.0.0.0`). A match gives the dataset (`gw_student_01` …). Packets of unknown devices go to `gw_unassigned` (`--unmapped`, or `drop`).
5. **Merge into 5-minute windows.** A window is fed by about 5 capture files of 60 s, so a partition is read, extended and rewritten, never just overwritten. Each row carries a `Capture File` column (the source pcap's name). Before adding a file's rows, the service removes rows that already carry that name. Processing a file twice (after a crash, or by hand) therefore never creates duplicates.
6. **Write atomically.** It writes to a temp file next to the partition and renames it. The app never sees a half-written file, because the temp name does not end in `.parquet`.
7. **Record the file as done**, only after all its rows are written. A truncated or corrupt file is ingested as far as readable, recorded with its error, and not retried.

### 3.1 Background filter

Added the same day (commit `05142cd0`), implementing the rules of [MasterThesisInc.md](MasterThesisInc.md) §3. The first matching rule drops the packet:

| Rule | Drops | Why |
| --- | --- | --- |
| `infra_device` | Everything to/from `--exclude-mac` (the U7 Lite, `8c:30:66:4c:df:d1`) or `--exclude-ip` | UniFi controller (8080), discovery and AP traffic would fill every quiet minute. By MAC because the AP gets its IP via DHCP |
| (keep) | DHCP (UDP 67/68) of clients | Needed for C5_F1 re-associations. The gateway's broadcast offers/acks count as `broadcast` |
| `mdns`, `ssdp`, `ntp` | UDP 5353, 1900, 123 | Periodic device chatter, not behaviour |
| `broadcast` | Broadcast or multicast destination (255.255.255.255, LAN broadcast, 224.0.0.0/4) | Not attributable to a user action (IGMP, UniFi discovery on 10001 …) |
| `gateway_service` | To/from `--gateway-ip` (10.42.0.1, 10.42.1.1) except DNS (53): SSH, ping … | Gateway services, not behaviour |
| `no_client` | Neither side is a client in `--lan-net` (10.42.0.0/24, 10.42.1.0/24) | Not attributable to a device |

Everything else between a client and the internet is kept, including STUN to the internet (calls) and Apple push on 5223. Whether always-on keep-alives should go is a decision for after looking at real nights. `--no-filter` disables the filter, e.g. to compare with an app upload of the same pcap.

**Tests.** A capture with one labelled packet per case (19 packets: 7 to keep, 12 to drop, one per rule plus variants) landed exactly as expected. That includes a DHCP discover from `0.0.0.0`, which reached the right dataset through the MAC fallback. The earlier equivalence tests still pass with and without the filter.

**Result on the gateway.** Today's data since 17:09 was rebuilt with the filter (the unfiltered version was moved to `/var/tmp/tapingest-unfiltered-202610161547/`). Of 66 869 packets in 38 capture files, 5 909 (~9 %) were dropped: `infra_device` 4 435, `broadcast` 1 191, `mdns` 277, `ntp` 6. The only LAN hosts left are the iPhone (10.42.0.174) and the gateway as DNS server, there is no traffic left on ports 8080/10001/5353, and all 334 DNS queries were kept.

It also keeps `processed_parquet/known_ips.txt` up to date, like the upload page does. `--max-rows` (default 300 000) closes a batch early to bound memory, and `--once` processes everything pending and exits (for backfills and synthetic data).

### devices.csv

One row per device. The same file is meant for the traffic runner (Karla's containers), so the format is fixed:

```csv
device,role,mac,ip,dataset
student01_phone,phone,02:00:0a:2a:01:0b,10.42.1.11,gw_student_01
student01_laptop,laptop,02:00:0a:2a:01:0c,10.42.1.12,gw_student_01
```

| Column | Meaning |
| --- | --- |
| `device` | Unique device name, also used in the ground-truth log |
| `role` | `phone` or `laptop` (used by the runner, ignored by the ingest) |
| `mac` | Fixed MAC. Only for documentation and matching `feed.ndjson`, the app works on IP |
| `ip` | Fixed IPv4, the actual lookup key |
| `dataset` | The person. Phone and laptop of one person share it. It becomes the folder name under `processed_parquet/` |

The file is validated when loaded (columns, valid IPv4, unique ip/device/mac, safe dataset name) and reloaded automatically when it changes. Lines starting with `#` are ignored. A change only applies to files ingested afterwards.

The deployed file still holds the four example devices (10.42.1.11/.12/.21/.22) of the planned runner containers. Because those do not exist yet, **all current traffic goes to `gw_unassigned`**.

### App changes (folder `app_pcap_to_dsm5/` in this repository)

| Commit (this repo) | Change |
| --- | --- |
| `9a5c97d` | Import of Stephan Nef's app, **unchanged** (upstream `12f44bc0`), without the thesis datasets, the feature cache and his `user_profiles.json`. See [`ORIGIN.md`](../app_pcap_to_dsm5/ORIGIN.md) |
| `2a168ed` | All our changes, see the list below |
| `1c541f6` | Paths for the clone on the gateway, `.gitignore` for runtime files |

`2a168ed` was developed on a local branch (`live-ingest` of a clone of the upstream repo) in four steps:

| Local commit | Change |
| --- | --- |
| `18afb6cc` | `ingest/` (service, unit, README, example devices.csv), shared parser `app/utils/pcap_etl.py`, cache fixes in pages 01/02, `TZ=Europe/Zurich` in `docker-compose.yml` |
| `cdaff706` | `--since` option |
| `33cfc2ce` | `app/docker-compose.gateway.yml` (host network, Streamlit on localhost only) |
| `05142cd0` | Background filter, MAC fallback for the device map |

All our changes compared to the thesis version, as one diff: `git diff 9a5c97d HEAD -- app_pcap_to_dsm5/`.

The cache fixes were needed because the app assumed that data never changes after upload:

- The feature-cache CSV was keyed by dataset names only. When the CSV covered all requested days, it was used without checking whether the data had changed.
- Several `st.cache_data` functions (file lists, day loaders, daily metrics) had no expiry and were keyed only by dataset and day.

Pages 01 and 02 now compute a cheap signature of the selected datasets (number of partition files + newest modification time, `app/utils/partitions.py`). The CSV is used only if it is newer than the newest partition. Day loaders are keyed on the modification times of that day's files, so unchanged days stay cached and only the changed day is reloaded. The "Refresh cached day metrics" button is no longer needed for live data.


## 4. Differences from the plan in MasterThesisInc.md §4.1

| Topic | Plan (MasterThesisInc §4.1) | Implemented | Status |
| --- | --- | --- | --- |
| Timing | Nightly batch (systemd timer 00:20) over the previous day | Continuous service, every new 60 s file within ~10 s | Done, live view in the app |
| Parser | tshark fields → pandas | The app's own scapy parser (shared module) | Identical to an upload by construction; validation 8.2 is covered by tests |
| Partitions overwritten | Avoided by processing whole days | Avoided by merging into existing partitions, idempotent via `Capture File` | Done |
| Identity | Split per client **MAC** (`/etc/tapgw/devices.json`) | Split per **IP**, MAC as fallback (`/etc/tapingest/devices.csv`, shared with the runner) | Done. Real devices need a fixed DHCP lease (`dhcp-host=`) |
| Background filter (§3) | Drop gateway services, AP/controller traffic, mDNS/SSDP/NTP, broadcasts | Implemented as specified (Section 3.1), AP excluded by MAC, drop counts per rule in the state db | Done |
| SNI in hostnames (§5) | Patch `enrich_with_hostnames` + SNI column | Not implemented | Open |
| Output location | `/var/lib/tapcap/parquet`, mounted read-only | `app/processed_parquet` in the repo, mounted read-write | Done. Read-write so the upload page keeps working |
| Hosting | Option A: app on the gateway via SSH tunnel | Option A, Docker, Streamlit bound to 127.0.0.1 | Done |
| Feature cache | Press "Refresh cached day metrics" | Detected automatically | Done |
| Validation §8 | Steps 1–6 | 1–2 done locally with synthetic captures; 3–6 not yet done on real data | Open |

## 5. Development and local testing

Before deployment, the code was tested on the laptop with synthetic capture files written by scapy. They were built like tapcap's output (60 s files crossing 5-minute boundaries, three mapped devices plus one unmapped, DNS queries and answers):

| Test | Result |
| --- | --- |
| Rows vs. parsing the same packets directly with the upload page's function | Identical, row by row |
| One file per batch (live-like) vs. all files in one batch | Identical partitions |
| Forget two files in the state db and ingest again | No duplicates |
| Truncated capture file | Read as far as possible, recorded, not retried |
| `--since` | Only files from the given minute onward are processed |
| App pages 01, 02, 03 headless (Streamlit AppTest) with two days, then a third day and more data for day two | No exceptions. The new day appears, day two is recomputed (29 760 packets, exactly as expected) |
| Same scenario with the original code | Pages stay on the old data: 2 days, CSV unchanged. Confirms the fix is needed |
| Throughput | ~10 600 packets/s on an Apple M4 Pro |

## 6. Phase: Deployment of the ingest service

### 6.1 Access and code transfer

- **Code** (first deployment, replaced by a git clone in Section 7.5): we could not push to the upstream repository, so the code was packed on the laptop with `git archive` into `live-ingest-cdaff706.tar.gz` (5.6 MB, without the 490 MB of thesis datasets in `app/processed_parquet` and `app/feature_cache`). It was copied with `scp` and unpacked to `/opt/app_pcap_to_dsm5_public`. Checksums matched on both sides.
- **SSH key:** a separate key without a passphrase, `~/.ssh/minipc_deploy` on Thierry's laptop, was added to kathy's `authorized_keys`. That lets the assistant run commands non-interactively.
- **Temporary sudo:** `/etc/sudoers.d/90-temp-deploy` (`kathy ALL=(ALL) NOPASSWD: ALL`) lets those commands use sudo without a password. **This file and the deploy key must be removed after setup** (Section 8).

### 6.2 Installation

The `ready/` folder (`750 tapcap:tapcap`) contains files with mode `644`, so membership in group `tapcap` is enough to read them. The check as the service user read the pcap magic bytes `d4 c3 b2 a1`.

A test run with `--once` over the last 10 minutes processed 10 files (4040 packets, ~3500 packets/s) into three partitions (16:55, 17:00, 17:05). The content was plausible: Zurich time, the real clients `10.42.0.174` and `10.42.0.184`, and 26 distinct DNS names (iCloud, Outlook …).

The service was installed with `--since 2026-10-16T17:09`, so it starts live and does not process the backlog of older captures. Later restarts do not need `--since`, because the state db remembers processed files.

**Result.** `tapingest` started at 17:09:59 and processes one file per minute (150–700 packets each, 0.1–0.3 s, 1500–3000 packets/s on the mini-PC). Memory use is about 140 MB, there were 0 restarts, and all 24 files processed by 17:33 had no errors.

## 7. Phase: Docker and the app

### 7.1 Docker without iptables

Docker normally inserts its own iptables rules and sets the `FORWARD` policy to `DROP`. On a router this would cut the routing of the real clients from `eno1` to the internet. Docker was therefore configured **before its first start**:

```json
{
  "iptables": false,
  "ip6tables": false
}
```

The full nftables ruleset was saved before the installation (`/root/nft-before-docker.txt`) and compared afterwards. It was **unchanged**, and `net.ipv4.ip_forward` stayed `1`. Firewall and NAT therefore remain entirely in `/etc/nftables.conf`. This also covers the Docker setup Karla's runner needs: she only has to create the `sim` network and add the `br-sim` rules.

### 7.2 Compose override for the gateway

Without Docker's iptables rules, containers on a Docker bridge have no NAT and thus no internet, and the image build needs it (`pip install`). `app/docker-compose.gateway.yml` therefore:

- builds and runs the app on the **host network** (`build.network: host`, `network_mode: host`, no port mapping);
- starts Streamlit with `--server.address=127.0.0.1`, so it listens on localhost only.

Port 8501 is not opened in nftables. The app is reachable **only through an SSH tunnel**, and the data never leaves the gateway, which matches the thesis' edge design.

The image `app-app` (981 MB, Python 3.11, Streamlit 1.66) was built on the gateway over the hotspot (~2 min of pip installs). The container sees `processed_parquet` through the existing bind mount. Its clock shows CEST because `TZ=Europe/Zurich` is set in `docker-compose.yml`.

### 7.3 Login

The app's login reads `username` and `password` from `app/.streamlit/secrets.toml`. Thierry created this file by hand (mode 600, root), so the credentials are not in any log or repository. The `.streamlit` folder is mounted read-only into the container.

### 7.4 Verification

- `curl http://127.0.0.1:8501/_stcore/health` → `ok` on the gateway
- `ss -ltnp` shows Streamlit on `127.0.0.1:8501` only
- From the laptop through the tunnel: health `ok`, start page HTTP 200
- The dataset `gw_unassigned` is visible in the app
- nftables still unchanged and `tapingest` still active after the container start

### 7.5 Move to the project repository

The app repository's `origin` is Stephan Nef's (`nefste/app_pcap_to_dsm5_public`), where we cannot push, and his last commit is final ("final pdf", 01.11.2025). Rather than a fork, we imported the app into this repository, with permission, so that docs, profiles, runner and app live in one place and the gateway needs one `git pull`.

**Import (three commits, see Section 3).** The first commit is his code unchanged, which we checked: the files match the upstream archive byte for byte, except the deliberate `ORIGIN.md` and the omitted `user_profiles.json`. The second commit brings in our 12 changed files one-to-one from the local branch. The third adapts the paths. Left out of the import:

- the thesis datasets (`app/processed_parquet`, ~490 MB) and the feature cache;
- `app/user_profiles.json`: it holds the author's personal profile (date of birth, daily routine), and the app recreates it (empty) on first start and rewrites it at runtime.

**`.gitignore` for runtime files.** On the gateway the ingest writes `processed_parquet/`, and the app writes `feature_cache/` and `user_profiles.json`, all inside the clone. These paths, plus `.venv/` and `secrets.toml`, are ignored, so the running system never blocks a `git pull`. One tracked file can still change at runtime: `app/fasl_config.json`, when someone saves a model configuration in the app. That is intended, since a recalibrated configuration belongs in git. Commit it from the gateway or copy it back before the next pull.

**Switch on the gateway (16.10.2026).**

1. Without downtime: `git clone` of this repository to `/opt/can-my-network` (as root), new venv in `app_pcap_to_dsm5/.venv`, ingest requirements installed. `git status` stayed clean with the venv present.
2. 16:04:29 UTC: `tapingest` stopped, app container removed.
3. `processed_parquet/` and `feature_cache/` moved (same filesystem, instant), `secrets.toml` copied (mode 600). The state db in `/var/lib/tapingest` stays where it is; it stores capture paths, which did not change.
4. New unit from the repo, with `--since 2026-10-16T17:09` and `--exclude-mac 8c:30:66:4c:df:d1` set. The old unit is kept as `/root/tapingest.service.bak-before-repo`. `tapingest` started.
5. The image build failed: pip could not fetch `setuptools` for `pydenticon`, apparently a network hiccup on the hotspot (the identical build had worked an hour earlier). To keep the downtime short, the container was started from the existing image (`up -d --no-build`). It was back at 16:06:28 UTC, so the app was down for about 2 minutes. Its code matched the repo: the hashes of all 32 code and config files in the image and in the clone were identical.
6. A second build attempt succeeded, and the container was recreated from the new image.

**Verification.**

- `tapingest` runs from `/opt/can-my-network/app_pcap_to_dsm5` with the filter and the AP MAC. All capture files since 17:09 are processed, none with errors, and the files written during the switch were picked up right after the restart.
- The partitions run from 17:05 to 18:05 without a gap except **17:55**. That window is empty on purpose: the iPhone was idle, the five minute files of that window held only 149–158 packets each, all AP and broadcast chatter, and the filter dropped all of them.
- The app answers on `127.0.0.1:8501`, also through the tunnel from the laptop, and mounts its data from the new folder.
- `git status` in the clone on the gateway is empty.

The old folder `/opt/app_pcap_to_dsm5_public` stays as a backup for now (it still contains the code archive's version and Stephan's `user_profiles.json`). The unfiltered data from before the filter is in `/var/tmp/tapingest-unfiltered-202610161547/`.

## 8. Operating the system

### Open the app

On the laptop (connected to the same hotspot as the gateway):

```bash
ssh -i ~/.ssh/minipc_deploy -N -L 8501:localhost:8501 kathy@172.20.10.10
```

The command prints nothing and keeps running. That is the open tunnel. Then open http://localhost:8501, log in, and select the `gw_*` datasets (type "Other"). Ctrl+C closes the tunnel.

### Check the status

```bash
systemctl is-active tapcap@eno1 tapfeed@eno1 tapingest docker
journalctl -u tapingest -f                                    # one "Ingested 1 file(s)" line per minute
sudo sqlite3 /var/lib/tapingest/state.sqlite \
  "select path, packets, rows_mapped, rows_unmapped, error from processed order by processed_at desc limit 5"
sudo sqlite3 /var/lib/tapingest/state.sqlite "select rule, sum(packets) from dropped group by rule"   # background filter
ls /opt/can-my-network/app_pcap_to_dsm5/app/processed_parquet/
sudo docker ps
sudo docker logs --tail 50 pcap-to-dsm5
```

Note: the system clock of the gateway is **UTC**. `journalctl` and `date` show UTC, while the ingest log lines, the partitions and the app use Zurich time. SQLite's `localtime` also prints UTC on this machine.

### Add or change devices

Edit `/etc/tapingest/devices.csv`. The service reloads it on the next scan, no restart needed. If the access point is replaced, update `--exclude-mac` in the unit (MAC from `/var/lib/misc/dnsmasq.leases`). Real phones need a fixed IP first: add `dhcp-host=<mac>,<ip>` in dnsmasq, and set the phone's "Private Wi-Fi Address" to "Fixed" for the study network.

### Add a second capture folder (br-sim)

`tapcap@br-sim` runs since 16.10 and writes to its own folder `/var/lib/tapcap/sim/ready`, so the two instances cannot collide ([HardwareSetup.md §15](HardwareSetup.md)). Add `--watch /var/lib/tapcap/sim/ready` to the `ExecStart` line and run:

```bash
sudo systemctl daemon-reload && sudo systemctl restart tapingest
```

### Deploy a new code version

Push to `main`, then on the gateway:

```bash
sudo git -C /opt/can-my-network pull
sudo git -C /opt/can-my-network log --oneline -1               # which version runs
sudo systemctl restart tapingest                               # if ingest/ changed
cd /opt/can-my-network/app_pcap_to_dsm5/app && sudo docker compose -f docker-compose.yml -f docker-compose.gateway.yml up -d --build   # if app/ changed
```

The clone is owned by root, so use `sudo git -C …` (as kathy, plain `git` refuses with "dubious ownership"). If `tapingest.service` in the repo changed, copy it again and re-apply the local settings (`--since`, `--exclude-mac`), see the appendix. If the image build fails on a pip download, retry it; the running container keeps working meanwhile.

### Re-process data

The service skips files that are already in the state db. To rebuild a dataset, for example after changing `devices.csv`:

```bash
sudo systemctl stop tapingest
sudo rm -r /opt/can-my-network/app_pcap_to_dsm5/app/processed_parquet/<dataset>
sudo rm /var/lib/tapingest/state.sqlite                     # or delete only the affected rows
# set --since in the unit to the first file you want, daemon-reload
sudo systemctl start tapingest
```

### Disk usage

**Correction (16.10):** `/etc/tmpfiles.d/tapcap.conf` has the age `2d` on `/var/lib/tapcap/ready`, so `systemd-tmpfiles-clean` deletes captures older than two days ([HardwareSetup.md §15](HardwareSetup.md)). The sim folder has no age. Apart from that, nothing is deleted automatically, neither captures (`/var/lib/tapcap/ready`, 73 MB after the first day of light use) nor Parquet (616 KB after 25 minutes). 427 GB are free, so this is not urgent, but a retention policy is part of the open work.

## 9. Problems and solutions

| # | Area | Problem | Cause | Solution |
| --- | --- | --- | --- | --- |
| 1 | Design | One 5-minute window is fed by ~5 capture files; the app's partition writer overwrites the file | The app assumed one upload per dataset | Merge into existing partitions, idempotent via `Capture File` |
| 2 | App | New data not visible in the app | Feature-cache CSV and `st.cache_data` keyed on names only | Signature of partition files; CSV only used when newer than the data |
| 3 | Design | Old captures since 02.10 would be processed first | No retention, ingest starts with an empty state | `--since` option |
| 4 | Testing | Test pcap generator crashed for large files | Port number > 65535 in the generator | Fixed the generator (not a service bug) |
| 5 | Access | `Permission denied (publickey)` despite the key being accepted | Key has a passphrase, no agent loaded, non-interactive SSH | Separate deploy key without passphrase |
| 6 | Access | `sudo: interactive authentication is required` | Temporary sudoers rule not yet created | Created `/etc/sudoers.d/90-temp-deploy` |
| 7 | Time | `date -d "10 min ago"` gave a time 2 h too early for `--since` | Gateway clock runs in UTC, `--since` is read as Zurich time | `TZ=Europe/Zurich date …` |
| 8 | Docker | `Could not get lock /var/lib/dpkg/lock-frontend` | `unattended-upgrades` was running | `apt-get -o DPkg::Lock::Timeout=600` |
| 9 | Docker | Default Docker would break routing for the clients | Docker's iptables rules and FORWARD DROP policy | `"iptables": false` before the first start; ruleset compared before/after |
| 10 | Docker | Container build would have no internet | No NAT for Docker bridges without iptables | Build and run on the host network (`docker-compose.gateway.yml`) |
| 11 | Usage | "The tunnel command just hangs" | `ssh -N` prints nothing by design | Leave it running, open the browser |
| 12 | Data | AP/controller traffic, IGMP, UniFi discovery and mDNS counted as activity (~9 % of packets) | No background filter in the first version | Filter (Section 3.1), AP by MAC; today's data rebuilt |
| 13 | Data | DHCP discovers come from `0.0.0.0` and could not be assigned by IP | The client has no IP yet | Device map falls back to the MAC |
| 14 | Code | No way to push our app changes | Upstream repository is not ours | App imported into this repository (Section 7.5) |
| 15 | Code | `git pull` on the gateway would conflict with live data | Ingest and app write inside the clone; upstream tracked `user_profiles.json` | `.gitignore` for runtime paths; `user_profiles.json` not imported |
| 16 | Docker | `No matching distribution found for setuptools` during the image build | pip download failed over the hotspot | Started the existing image (2 min downtime), retried the build |
| 17 | Data | Window 17:55 missing | Phone idle, all packets were background and dropped | Expected behaviour, no fix needed |

## 10. Security notes

- The app listens on localhost only; port 8501 is not opened in nftables. Access requires SSH access to the gateway.
- `secrets.toml` is mode 600 and not in any repository.
- The Parquet data contains client IPs and visited domain names. It stays on the gateway (no sync to laptops).
- **To remove after setup:** `/etc/sudoers.d/90-temp-deploy` and the `minipc-deploy` line in `/home/kathy/.ssh/authorized_keys`. Both give full root access without a password while they exist.
- SSH on the uplink (`wlp2s0`) is still allowed (HardwareSetup Section 13).

## 11. Open issues and next steps

1. ~~Background filter~~ Done (Section 3.1). Still to decide after looking at real nights: always-on keep-alives such as Apple push (5223).
2. **Remove the temporary access** (Section 10).
3. ~~Own fork of the app repo~~ Done differently: app imported into this repository (Section 7.5). After a few days without problems, delete `/opt/app_pcap_to_dsm5_public`, `/var/tmp/tapingest-unfiltered-*` and `/root/tapingest.service.bak-*` on the gateway. The local `app_pcap_to_dsm5_public` clone and the `live-ingest-*.tar.gz` archives on Thierry's laptop are obsolete.
4. **br-sim integration:** a second `--watch` folder, and one shared `devices.csv` for the runner and the ingest (e.g. the runner reads `/etc/tapingest/devices.csv`).
5. **First end-to-end pilot:** one runner container (e.g. `student01_phone`) runs `browse` for 5 minutes, and `gw_student_01` appears in the app with exactly those domains.
6. **Validation 3–6** from MasterThesisInc §8 on real data: packet counts vs. `capinfos`, a known action at a noted time, plausible domain names, night silence of an unused phone.
7. **SNI as a second hostname source** (MasterThesisInc §5 / `feed.ndjson`).
8. **Throughput:** 1500–3500 packets/s on the mini-PC. Enough for a few devices; a high-quality video stream alone can reach 500–1000 packets/s. Watch "still pending" in the log during runner tests.
9. **Retention policy** for captures and Parquet.

## 12. Appendix: configuration and commands

### tapingest.service (as deployed)

```ini
[Unit]
Description=tapingest: live PCAP -> 5-minute Parquet for the analysis app
After=network-online.target tapcap@eno1.service

[Service]
Type=simple
User=tapingest
Group=tapingest
SupplementaryGroups=tapcap
Environment=TZ=Europe/Zurich
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=/opt/can-my-network/app_pcap_to_dsm5
ExecStart=/opt/can-my-network/app_pcap_to_dsm5/.venv/bin/python ingest/tapingest.py \
    --watch /var/lib/tapcap/ready \
    --devices /etc/tapingest/devices.csv \
    --out /opt/can-my-network/app_pcap_to_dsm5/app/processed_parquet \
    --state /var/lib/tapingest/state.sqlite --since 2026-10-16T17:09 \
    --exclude-mac 8c:30:66:4c:df:d1
StateDirectory=tapingest
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=/opt/can-my-network/app_pcap_to_dsm5/app/processed_parquet

[Install]
WantedBy=multi-user.target
```

### docker-compose.gateway.yml

```yaml
services:
  app:
    build:
      network: host
    network_mode: host
    ports: !reset []
    command: ["streamlit", "run", "00_Home.py", "--server.port=8501", "--server.address=127.0.0.1"]
```

### Ingest installation

```bash
sudo apt install -y python3-venv sqlite3
sudo git clone https://github.com/KarlaRuggaber/Can-My-Network-Tell-How-I-Feel-.git /opt/can-my-network
cd /opt/can-my-network/app_pcap_to_dsm5
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r ingest/requirements.txt

sudo useradd --system --no-create-home --shell /usr/sbin/nologin tapingest
sudo usermod -aG tapcap tapingest
sudo install -d -o tapingest -g tapingest -m 755 app/processed_parquet
sudo install -d -m 755 /etc/tapingest
sudo cp ingest/devices.example.csv /etc/tapingest/devices.csv

# read check as the service user (expect the pcap magic d4 c3 b2 a1)
sudo -u tapingest bash -c 'f=$(ls -t /var/lib/tapcap/ready/*.pcap | head -1); head -c 4 "$f" | od -An -tx1'

# test run on the last 10 minutes (Zurich time!)
sudo -u tapingest env TZ=Europe/Zurich .venv/bin/python ingest/tapingest.py \
  --watch /var/lib/tapcap/ready --devices /etc/tapingest/devices.csv \
  --state /tmp/tapingest-test.sqlite --since "$(TZ=Europe/Zurich date -d '10 min ago' +%Y-%m-%dT%H:%M)" --once

# service, starting from now; set the AP's MAC (from /var/lib/misc/dnsmasq.leases)
sudo cp ingest/tapingest.service /etc/systemd/system/
sudo sed -i -e "s#--exclude-mac 00:00:00:00:00:00#--exclude-mac 8c:30:66:4c:df:d1#" \
  -e "s#--state /var/lib/tapingest/state.sqlite \\\\#--state /var/lib/tapingest/state.sqlite --since $(TZ=Europe/Zurich date +%Y-%m-%dT%H:%M) \\\\#" \
  /etc/systemd/system/tapingest.service
sudo systemctl daemon-reload
sudo systemctl enable --now tapingest
```

### Docker and app

```bash
sudo nft list ruleset > /root/nft-before-docker.txt
sudo install -d -m 755 /etc/docker
printf '{\n  "iptables": false,\n  "ip6tables": false\n}\n' | sudo tee /etc/docker/daemon.json
sudo apt-get install -y -o DPkg::Lock::Timeout=600 docker.io docker-compose-v2 docker-buildx
sudo nft list ruleset | diff /root/nft-before-docker.txt - && echo UNCHANGED

sudo nano /opt/can-my-network/app_pcap_to_dsm5/app/.streamlit/secrets.toml   # username = "…" / password = "…"
sudo chmod 600 /opt/can-my-network/app_pcap_to_dsm5/app/.streamlit/secrets.toml

cd /opt/can-my-network/app_pcap_to_dsm5/app
sudo docker compose -f docker-compose.yml -f docker-compose.gateway.yml up -d --build
curl -fsS http://127.0.0.1:8501/_stcore/health                   # expect: ok
```

### Temporary access (remove afterwards)

```bash
# laptop
ssh-keygen -t ed25519 -f ~/.ssh/minipc_deploy -N "" -C "minipc-deploy"
ssh-copy-id -i ~/.ssh/minipc_deploy.pub kathy@172.20.10.10
# gateway
echo 'kathy ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/90-temp-deploy && sudo chmod 440 /etc/sudoers.d/90-temp-deploy

# removal
sudo rm /etc/sudoers.d/90-temp-deploy
sed -i '/minipc-deploy$/d' ~/.ssh/authorized_keys
```
