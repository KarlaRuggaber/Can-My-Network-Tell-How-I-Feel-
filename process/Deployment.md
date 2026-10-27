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
        tapcap@br-sim ──► /var/lib/tapcap/sim/ready/cap-<ms>.pcap   (since 16.10, watched by the ingest since 23.10)
                                   │  polled every 10 s
                                   ▼
        tapingest.service ── traffic-runner/config/devices.csv (IP → dataset, same list as the runner)
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
| Device map | `devices.csv` (IP → dataset), in git, the same file the runner containers are generated from | `/opt/can-my-network/traffic-runner/config/devices.csv` |
| Runner containers | `student_a_phone`, `student_a_laptop` (until 23.10: `student01_*`) (Karla, see `traffic-runner/README.md`), image `traffic-runner:0.1.0` | `/opt/can-my-network/traffic-runner` |
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

One row per device. Since 23.10 the ingest reads the runner's own file, `traffic-runner/config/devices.csv`, so there is only one list:

```csv
device,role,mac,ip,dataset
student_a_phone,phone,02:00:0a:2a:01:0b,10.42.1.11,gw_student_a
student_a_laptop,laptop,02:00:0a:2a:01:0c,10.42.1.12,gw_student_a
```

| Column | Meaning |
| --- | --- |
| `device` | Unique device name, also used in the ground-truth log |
| `role` | `phone` or `laptop` (used by the runner, ignored by the ingest) |
| `mac` | Fixed MAC. Only for documentation and matching `feed.ndjson`, the app works on IP |
| `ip` | Fixed IPv4, the actual lookup key |
| `dataset` | The person. Phone and laptop of one person share it. It becomes the folder name under `processed_parquet/` |

The file is validated when loaded (columns, valid IPv4, unique ip/device/mac, safe dataset name) and reloaded automatically when it changes. Lines starting with `#` are ignored. A change only applies to files ingested afterwards.

It lists the two runner containers (`student_a_phone`, `student_a_laptop` → `gw_student_a`; until 23.10 `student01_*` → `gw_student_01`). Traffic of all other devices, including the real phones on `eno1`, goes to `gw_unassigned`.

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
| SNI in hostnames (§5) | Patch `enrich_with_hostnames` + SNI column | Inbound lookup implemented (Section 7.7); SNI not added (not needed while DNS is visible, feed lacks the server IP) | Inbound: done. SNI: open, low priority |
| CDN hosts (not in the plan) | – | Broadcaster VOD hosts attributed to their service, e.g. `srf-vod-*.akamaized.net` → `srf.ch` (Section 7.9) | Done 25.10, extension of the thesis lists |
| Productivity list (not in the plan) | – | Shared domains count only tool hosts, e.g. `docs.google.com` but not `accounts.google.com` (Section 7.10) | Done 26.10, correction of the thesis list; changes thesis values, C2_F6 needs recalibration |
| Machine background (not in the plan) | – | Runner containers send OS/browser background around the clock; the app drops background hosts before all features (Section 7.11) | Done 26.10; changes UniqueSLD in 32 thesis datasets by 1–5 |
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

### 7.6 Runner integration and first pilot (23.10.2026)

Karla's runner (`traffic-runner/`, merged on 16.10) had been running on the gateway from a copy in `~/traffic-runner`, with its own capture `tapcap@br-sim` writing to `/var/lib/tapcap/sim/ready` ([HardwareSetup.md](HardwareSetup.md), [traffic-runner/README.md](../traffic-runner/README.md) §7). Two of her open points were for the ingest (README §9, items 1, 2 and 7):

| Step | What | Check |
| --- | --- | --- |
| 1 | `git pull` of the clone on the gateway (it was still at `5ea3fe0`) | `traffic-runner/` present, clone clean |
| 2 | Runner moved from `~/traffic-runner` to the clone: `docker compose down` in the copy, `logs/ground_truth.csv` carried over (7 lines), `up -d --no-build` in the clone. The copy matched the repo except the README. The image has a fixed tag and was not rebuilt | Both containers run from `/opt/can-my-network/traffic-runner` with the same IPs and MACs; `gen_compose.py --check` passes |
| 3 | `tapingest`: second `--watch /var/lib/tapcap/sim/ready`, `--devices` pointing to `traffic-runner/config/devices.csv` in the clone. Old copy `/etc/tapingest/devices.csv` removed (backup in `/root`) | Log: "Loaded 2 device(s)", both folders watched |
| 4 | Backfill: the 27 sim files since 16.10 (Karla's acceptance runs) were ingested in 17 s | Dataset `gw_student_01` with partitions 16.10 18:35–18:55 |

**Pilot.** `student01_phone` ran `browse` for 5 minutes (`--mix news,search --seed 7 --profile pilot --block-id p001`). The runner picked www.nzz.ch, rejected the cookie banner and opened two pages. Ground-truth log: `2026-10-23T08:48:31+02:00 – 08:53:32, browse, www.nzz.ch, ok`. The br-sim counters show about 16 MB of traffic.

| Check | Result |
| --- | --- |
| Dataset | `gw_student_01`, partitions 23.10 08:45 and 08:50 |
| Rows | 20 762, only the phone (10.42.1.11) and the gateway as DNS server |
| Inside the ground-truth block | 99.9 % of the rows (the rest are 17 packets until 08:53:48 while the browser closed) |
| DNS | 237 queries, 86 distinct names: `www.nzz.ch` and its asset hosts, plus many ad/tracking hosts |
| Domains in the app (its own `enrich_with_hostnames`) | Top SLDs: jwpsrv.com, nzz.ch, static-nzz.ch, googlesyndication.com, google.com, adnz.co … |
| Rows without a domain | **63.8 %** |

**Finding 1: incoming packets get no domain.** Outbound rows (phone → server, 7 341) have a domain in 100 % of cases, inbound rows (server → phone, 13 421) in only 1.3 %, although all of them come from servers whose domain is known from the outbound rows. The cause is the one described in MasterThesisInc §5: `enrich_with_hostnames` looks up only the destination IP. Every downlink-based metric (streaming, downstream volume per category) therefore sees almost nothing. Fixed the same day, see Section 7.7.

**Finding 2: one page visit creates many domains.** One news site produced 86 distinct DNS names, mostly ads and tracking. This confirms catalog pitfall §5.7: UniqueSLD (C2_F1, threshold < 40) will never fire on scripted days without re-tuning.

**Finding 3: Chromium background traffic.** The run contains `android.clients.google.com` and `accounts.google.com`, which the app reduces to `google.com`, a PRODUCTIVITY domain (C2_F6). This is Karla's runner point 5; it should be suppressed in the runner.

### 7.7 Hostnames for inbound packets (23.10.2026)

**Change** (commit `27b0cbe`, `app/metrics/common.py`). `enrich_with_hostnames` now looks up the remote side of each packet: the destination for outgoing packets, the **source** for incoming ones (public source, private destination). Rows without a private client keep the old behaviour (destination lookup). The thesis code looked up the destination only, so no inbound packet ever got a hostname, and `streaming_inbound_mask` (C1/C2 streaming metrics), which needs a domain on inbound rows, could never match on gateway data.

**Tests.** `app_pcap_to_dsm5/tests/test_hostnames.py` (4 cases: outbound and inbound get the server name, DNS rows keep their own name, public-to-public rows unchanged, data without a source column). All pass; on the old code exactly the inbound case fails. App pages 01, 02 and 03 run headless without errors on the pilot data.

**Effect, same data evaluated with the old and the new code:**

| Data | Measure | Old | New |
| --- | --- | --- | --- |
| Pilot 23.10 (browse nzz.ch) | Rows without SLD | 63.8 % | 0.3 % |
| | Inbound rows without SLD | 100 % | 0 % |
| | C2_F6 ProductivityHits | 436 | 875 |
| | F5_RevisitRatio | 0.9943 | 0.9979 |
| Karla's runs 16.10 (incl. YouTube) | Rows without SLD | 68.1 % | 0.3 % |
| | Streaming inbound rows | 0 | 5 742 |
| | C2_F5 PassiveActiveByteRatio | 0.0 | 1.76 |
| | C2_F7 / C7_F7 SocialOutgoingShareUp | 1.0 | 0.39 |
| | C2_F6 ProductivityHits | 1 761 | 3 519 |
| Thesis ONU datasets (game, instant-message, mail, video, web-browsing) | All measures | | **identical** |
| Thesis BRAS datasets | No IP columns, function returns early | | identical |

All other metric values of these days are unchanged. The thesis datasets are not affected because their captures have no private client addresses, so the thesis results stay reproducible. On gateway data the change is a deliberate methodology change compared to the thesis and must be reported as such. Two side effects to keep in mind: ProductivityHits roughly doubles, because the downlink from `google.com` now counts too (this includes Chromium's background traffic, runner point 5), and the share values C2_F7/C7_F7 were stuck at 1.0 before.

**SNI not added.** DNS already labels 99.7 % of the rows of the runner devices, so a second source would add almost nothing for them. `feed.ndjson` records client IP and SNI but **not the server IP**, so its names cannot be mapped to packets. Parsing the TLS ClientHello in the ingest would miss QUIC and ClientHellos split across segments (Chrome's post-quantum key share makes them larger than one segment). SNI becomes relevant for devices whose DNS the gateway does not see (DNS-over-HTTPS, iCloud Private Relay); then add `-e ip.dst` to `tapfeed` and join the feed in the ingest.

**Deployment.** `git pull` on the gateway, app image rebuilt, container recreated. The feature cache of the gateway data (one CSV, computed with the old lookup) was moved to `/var/tmp/feature_cache-before-hostfix-202610230709/`, because the cache only notices new data, not new code. Check on the gateway afterwards: inbound rows of the pilot without SLD 98.7 % → 0.5 %.

### 7.8 Scheduler, run setup, pilot and gateway fixes (23.10.2026)

On 23.10 the missing piece between the profiles and the runner was built and the gateway was prepared for the first live run, which starts on Sun 25.10. All code is in the repository, in Thierry's name; the gateway steps were run over SSH (user `kathy`, temporary sudo rule, Section 10). Times below are Zurich time (the gateway clock is UTC).

**Scheduler** ([scheduler/README.md](../scheduler/README.md), PRs #3–#5). `python -m scheduler plan` turns a profile (its §9 "Script specification", as YAML in `scheduler/profiles/`) and a seed into the ground-truth plan: one row per block with absolute start and end time, device, activity, mix and the runner's arguments. It writes `plan.csv` (the runner's ground-truth columns plus `phase`, `profile_block`, `flag`, …) and `plan.commands.tsv` (one `scripts/run-activity.sh …` call per block). Each row's `block_id` is written by the runner into `ground_truth.csv`, so a reported likelihood can be traced back to the profile block that produced it.

| Part | What it does |
| --- | --- |
| Profiles | `student`, `9to5-worker` (tier 0); `insomnia-moderate`, `mdd-severe-suicidality`, `social-anxiety-moderate` (tier 2, patches on their tier-0 profile) |
| Rules (catalog §1) | Only seeded randomness (one stream per day/block, so a baseline phase equals the tier-0 profile run alone with the same seed); Europe/Zurich via `zoneinfo` (DST-safe); nights belong to the day they start on; away periods drop blocks and cancel evenings; overlaps on one device run one after the other; calls are exclusive across devices (music and the gaming voice chat excepted); `count`, `per_week`, `per_window`, `days_per_week`, `nights_per_window`, `keep_per_window` |
| Clinical extras | `scale`/`duration_scale` ("baseline × f", f once per seed), skipped campus days (MDD), kept and replaced going-out evenings (SAD), conditions on the night's sleep onset, consecutive parts of an evening (SAD), the suicidality sequence (`flag=sensitive`) |
| Executor | `python -m scheduler execute` replays `plan.commands.tsv` live: absolute start times, one process per block (`sudo …/run-activity.sh`), devices in parallel; a state file written before each start, so a restart or reboot never starts a block twice; late blocks run with the remaining time or are recorded as missed |
| Push report | `python -m scheduler report` compares each block due in the window with `ground_truth.csv` and the state file, and checks executors, new Parquet partitions, memory, OOM kills, disk and services; pushes to an ntfy topic (README §5.2) |
| Tests | 430 (pytest): reproducibility, coverage of the requested days, every rule over several seeds and all profiles, executor restarts/late starts/DST, report cases |

**Decisions of 23.10** (Thierry; details in scheduler README §7–8):

| Topic | Decision |
| --- | --- |
| Window start | The warm-up is the **Sunday** before the 14-day window; `--start` must be a Sunday (`--any-start` for pilots) |
| Noise | One duration factor per day: U(0.75, 1.25) for the student, U(0.85, 1.15) for the 9-to-5 (the profiles' "±25 % / ±15 % on durations"); insomnia's night bursts are exempt (≤ 5 min threshold) |
| Overlaps | Calls are placed first; work and study blocks are cut around them. Blocks with a fixed start may slip by up to 30 min |
| Student campus | Late-lecture days start between 10:30 and 14:00 (the profile's 08:00–14:00 could start before waking) |
| MDD / SAD | The proposed defaults for the constructs their §9 leaves open (README §8); SAD's home evenings are split into consecutive parts by share (stream, gaming, social) |
| Run | All three clinical personas in parallel, each with 14 baseline days, seeds 1/2/3 |

**Runner interface.** The commands pass `--platform` (ignored by the runner, every call goes to the peer's Jitsi), `--lookups N` (drawn per row) and `--mic-share 0.1` for the SAD calls (runner since `dca94cd`). With Karla's activities of 23.10 only `messaging` and `social_post` are still stubs: 5 % of the student's and 3 % of the 9-to-5's planned activity time (before: 23 % and 11 %).

**The run** (plans generated against `traffic-runner/config/devices.csv`, files in `/var/lib/traffic-executor/` on the gateway):

| Dataset (persona) | Profile | Seed | Rows | Warm-up | Baseline (tier 0) | Profile phase |
| --- | --- | --- | --- | --- | --- | --- |
| `gw_insomnia_a` (Ben) | 9-to-5 worker → insomnia-moderate | 1 | 491 | Sun 25.10 | Mon 26.10 – Sun 08.11 | Mon 09.11 – Sun 22.11 |
| `gw_mdd_suicidality_a` (Maria) | student → mdd-severe-suicidality | 2 | 704 | Sun 25.10 | Mon 26.10 – Sun 08.11 | Mon 09.11 – Sun 22.11 |
| `gw_social_anxiety_a` (Carl) | student → social-anxiety-moderate | 3 | 825 | Sun 25.10 | Mon 26.10 – Sun 08.11 | Mon 09.11 – Sun 22.11 |

The warm-up Sunday is also the switch to winter time (a 25-hour day); the scheduler and the executor work with absolute times, so nothing special is needed. The MDD profile is to be reviewed by Lukasz before its phase starts on 09.11 (profile header).

**Capacity estimate** (before the pilot). Over the 29 days of the three plans, 0–3 browser runs overlap most of the time, 5 or more in about 1 % of the minutes, with peaks of 7–8 runs and at most 2 calls at once. With the memory figures of HardwareSetup §16 (base 3.5 GB, ~0.45 GB per run, ~0.45 GB of peer per call) the 7.1 GB would be exceeded for about 60 min in total, around noon and 22–24 h. The pilot was chosen to test this: it replays the plans' busiest hour.

**Installed on the gateway** (15:43–15:46):
- `git pull` of the clone (scheduler, report, units); `/var/lib/traffic-executor/` and `/var/log/traffic-executor/`
- the units from `scheduler/systemd/` in `/etc/systemd/system/`; `traffic-sample.timer` enabled (one memory sample per minute → `/var/lib/traffic-executor/gateway-samples.csv`)
- the three plans (`.csv` + `.commands.tsv`)
- `/etc/traffic-report.env` (mode 600) with a random ntfy topic; a test push arrived on Thierry's phone
- after the pilot (17:04): `traffic-executor@gw_insomnia_a`, `@gw_mdd_suicidality_a`, `@gw_social_anxiety_a` enabled (449, 670 and 777 blocks pending, first block Sun 25.10 08:05); `traffic-report.timer` (08:00 Zurich time) and `traffic-watch.timer` (hourly) enabled; the first real report arrived ("Gateway: all good")
- the plans on the gateway are byte-identical to plans generated from the current main (checked with SHA-1)

**Pilot** (16:00–17:00). `run-2026-10-25/make_pilot.py` (outside the repository) took the plans' busiest hour by memory load, Wed 04.11 20:55–21:55, and shifted it to today: 12 blocks on the six new devices, among them two gaming sessions with voice chat in parallel, a stream, `social_passive` and phone checks. Block IDs `pilot-<device>-…`, `--profile pilot`, own state file. It ran as a transient unit (`systemd-run --unit traffic-pilot`).

**Pilot results** (state file, ground-truth log, memory samples, Parquet data):

| Check | Result |
| --- | --- |
| Executor | 12 of 12 blocks started on time (0 late, 0 missed); parallel starts on three devices at 16:00 |
| Ground truth | 10 `ok`; 1 `not_implemented` (`messaging`, an expected stub); 1 `error`: YouTube `video_stream` on `mdd_suicidality_a_laptop` stopped after 2 min with "media stopped playing (state=stalled)", so 29 min of that block stayed silent (open issue 14) |
| Calls and gaming | Both gaming sessions with voice chat ran their full length (28 min and 59 min) |
| Data | All three datasets received partitions for 16:00–17:00 with only their own IPs: `gw_insomnia_a` 311 k rows / 331 MiB, `gw_mdd_suicidality_a` 878 k / 685 MiB, `gw_social_anxiety_a` 694 k / 152 MiB (Carl had only laptop blocks in this hour) |
| Memory | Available 1.07–2.58 GB, median 1.56 GB; swap use ~2 GB of 4 GB; no OOM kill |
| CPU | Load up to 11.3 on 6 cores when six blocks started at 16:00, then 3–7 |
| tapfeed temp files on disk | 906 MB (br-sim) and 422 MB (eno1) after the hour |

The gateway copes with the busiest hour of the three plans, with about 1 GB of headroom at the worst minute (after the tapfeed fix below). The pilot's Parquet data (only pilot traffic) was moved to `/var/tmp/pilot-20261023/processed_parquet/`, so it does not enter the three datasets' history; its executor files and logs are in `/var/tmp/pilot-20261023/executor/`. The pilot's ground-truth rows stay in the log with `profile=pilot`.

**Finding: tapfeed kept a growing capture file in RAM.** With nothing running, only 1.9 GB of memory was available at 15:40, and 1.27 GB at 15:56. The cause was not the runner: tapfeed's `tshark` (through `dumpcap`) stores every captured packet in a temporary pcapng in `/tmp`, which only grows, and `/tmp` on the gateway is a tmpfs, i.e. RAM.

| Time | Observation |
| --- | --- |
| 15:57 | `/tmp` held 1.6 GB: `wireshark_eno1….pcapng` 1.5 GB (tapfeed@eno1, running for 7 h), `wireshark_br-sim….pcapng` 144 MB; tshark itself 864 MB RSS |
| 15:58 | Restart of `tapfeed@eno1` and `tapfeed@br-sim`: the files are deleted on exit, available memory 1.3 → 3.7 GB |
| 16:01–16:02 | During the pilot the br-sim file grew by **~90–100 MB/min** (138 MB after 1.5 min, 248 MB after 2.5 min); available memory fell to 1.09 GB, swap use rose to 2.2 GB |
| 16:02 | Another restart of `tapfeed@br-sim` (a repeating restart timer was refused by the permission policy of the AI tooling, and not worked around) |

Without a fix, the live runs would have run the gateway out of memory within the first hour. It also explains part of the 3.5 GB "baseline" measured in HardwareSetup §16: the eno1 file had been growing since the last boot.

**Fix** (PRs #6 and #7, HardwareSetup §17):
- `TMPDIR` does not help: `dumpcap` has file capabilities (`cap_net_admin,cap_net_raw=eip`), and the C library ignores `TMPDIR` for such programs. Checked by running the new script as a separate process during the pilot: its temp file still went to `/tmp`.
- Drop-in `/etc/systemd/system/tapfeed@.service.d/tmp-on-disk.conf`: every tapfeed instance gets a disk-backed `/tmp` of its own, `/var/lib/tapfeed/<interface>` (`StateDirectory=tapfeed/%i`, `BindPaths=/var/lib/tapfeed/%i:/tmp`).
- `tapfeed`: tshark stops every `TAPFEED_ROTATE` seconds (default 1 h; its temp file is deleted on exit) and starts again at once. This bounds the disk use; the gap is well under a second, DNS is not affected. `TAPFEED_OUT` allows test runs without touching the real feed.
- First install at 16:09 failed: the drop-in created the folder in an `ExecStartPre`, but systemd sets up the bind mount before that runs, so both instances failed with `226/NAMESPACE`. With `StateDirectory` (created by systemd before the namespace) both were active again at 16:10. **The feed had a gap of about one minute (16:09:40–16:10:30).**
- Check: both instances active; temp files in `/var/lib/tapfeed/br-sim` and `/var/lib/tapfeed/eno1`, none in `/tmp`; SNI lines of the runner devices (10.42.1.x) arrive again; the gateway's files equal the repository (`cfd242a`). Backup of the old script: `/root/tapgw-backup-20261023-1409/`.
- Rollback: remove the drop-in, copy `tapfeed` back from the backup, `systemctl daemon-reload`, restart both instances.
- **tshark's own memory** grows too: after 30 min of the pilot 410 MB (br-sim) and 302 MB (eno1). The hourly restart frees it, but at peak load br-sim's tshark would reach about 0.8 GB before each restart. **Decided 23.10: restart every 10 min** (`Environment=TAPFEED_ROTATE=600` in the drop-in), which keeps it near 140 MB.

**Remote access.** Thierry installed Tailscale at 16:31 (Section 8, HardwareSetup §17): the gateway is `can-my-network-gw` (100.124.37.62) in his tailnet, tailscaled runs with `--netfilter-mode=off`, and `/etc/nftables.conf` opens only SSH on `tailscale0`. Tested from outside the hotspot (Thierry, and SSH from another network at 16:40).

**SSH from the AP network.** From a laptop on the AP's WiFi, `ssh kathy@10.42.0.1` failed with "Host key verification failed", because `known_hosts` lists the gateway under 172.20.10.10. Same machine, same keys (fingerprints compared). The hotspot address worked from both networks. Since the uplink uses DHCP (23.10 evening, HardwareSetup §17), the gateway no longer has a fixed hotspot address (it got 172.20.10.3); use Tailscale (`can-my-network-gw`, Section 8) for everything.

### 7.9 Broadcaster VOD hosts count as streaming (25.10.2026)

**Why.** Since 25.10 `video_stream` plays SRF only, because YouTube aborts playback in the automated containers (process log, week 6). SRF Play does not stream from `srf.ch` but from the Akamai CDN, `srf-vod-amd.akamaized.net`. The app reduces every host to its last two labels (`_sld`), so the video became `akamaized.net`, which no thesis list contains. Measured on Ben's SRF hour of the pilot (23.10, 16:00–17:00):

| Domain (SLD) | Downstream | Share |
| --- | --- | --- |
| `akamaized.net` (`srf-vod-amd…`) | 221.8 MB | 97.1 % |
| `srf.ch` | 4.2 MB | 1.8 % |
| rest (tracking, consent, statistics) | 2.4 MB | 1.1 % |

Only the 1.8 % counted as streaming. The streaming metrics (C1 long streaming sessions, C2_F5 passive/active) would have been almost blind for every SRF evening. The same would hold for a real household watching SRF Play, so it is also a limitation of the thesis lists.

**Change** (`808c2cc`, `app/metrics/common.py`): **an extension of the thesis lists.** `SERVICE_HOSTS` attributes known CDN hosts to their service when the SLD is computed: `srf-vod-*.akamaized.net` → `srf.ch`. All SLD-based lists (STREAMING, SOCIAL, …) therefore count it consistently, and `ResolvedHost` keeps the real host for tracing. Only measured hosts are listed. All of `akamaized.net` is deliberately **not** added: many sites load scripts and images from it (SRF's own player scripts come from `colibri-js.akamaized.net`), which would make every such page "streaming".

**Tests.** `app_pcap_to_dsm5/tests/test_hostnames.py`, 6 new cases: the SRF VOD host counts as `srf.ch` and as streaming downstream; `colibri-js.akamaized.net`, other Akamai hosts, a lookalike (`srf-vod-amd.akamaized.net.evil.example`, `xsrf-vod…`) and another CDN domain keep their SLD. 10 tests pass.

**Effect, same data with the old and the new code:**

| Data | Measure | Old | New |
| --- | --- | --- | --- |
| Pilot hour 23.10 (Ben, SRF) | Downstream counted as streaming | 4.2 MB (1.8 %) | 225.8 MB (98.9 %) |
| | Streaming inbound rows | 8 376 | 156 510 |
| | C2_F5 PassiveActiveByteRatio | 1.03 | 21.46 |
| | Other 77 day values | | unchanged |
| Thesis ONU datasets (video, web-browsing, game) | Streaming rows | | identical |

C1's long-session metric did not change because the pilot stream lasted 1 h (C1 counts sessions of ≥ 2 h); the MDD evenings (1.5–3 h) will show it.

**Deployment.** `git pull`, app image rebuilt, container recreated at 23:07; the feature cache was empty. Check in the container: `_service_sld("srf-vod-amd.akamaized.net") == "srf.ch"`, `colibri-js.akamaized.net` unchanged.

**Next.** Other broadcasters in the STREAMING list (ZDF, ARD, ORF) may use CDNs too; measure their video hosts before adding them as a second playable site, and add their hosts to `SERVICE_HOSTS` only from a measurement.

### 7.10 Productivity hits only from tool hosts (26.10.2026)

**Why.** C2_F6 counts packets to the PRODUCTIVITY list; few hits are read as a sign of anhedonia. The list contains `google.com`, `microsoft.com` and `live.com`, and the app reduces every host to its last two labels. So every Google or Microsoft address counted as productive work. The entries `docs.google.com` and `calendar.google.com` in the list could never match.

**Measured** (gateway, 25.10): Maria had **no** work or study block, yet 11 932 hits: `www.google.com` 5 913 (search, reCAPTCHA, ad frames embedded in pages), `accounts.google.com` 2 315, `news.google.com` 1 200, `region1.analytics.google.com` 1 065, `play.google.com` 432, `stun.l.google.com` 376 (WebRTC of the video call), ad/payment hosts ~600, `adsdk.microsoft.com` 107. In Stephan's ONU datasets the hits were Safe Browsing (`sb-ssl.google.com`), Chrome updates (`clients2.google.com`), Windows Update (`*.update.microsoft.com`), Windows telemetry (`*.events.data.microsoft.com`), Edge and Microsoft logins, without a single real productivity visit, even in the `mail-service` captures.

**Change** (`284ff87`, `app/metrics/common.py`, **a correction of the thesis list**): `productivity_mask()`. Within the shared domains only the label directly left of the domain decides:

| Domain | Counted hosts |
| --- | --- |
| `google.com` | docs, drive, mail, calendar, meet, keep, tasks, sheets, slides, forms, classroom, sites, script, scholar (study) |
| `microsoft.com` | teams, to-do, www (the runner's study mix opens `www.microsoft.com/…/microsoft-365` as its no-login Office stand-in) |
| `live.com` | outlook, mail |

All other list domains (`github.com`, `gitlab.com`, `trello.com`, `office.com`, `outlook.com`, …) are unchanged. Used by `criterion2`, `base_features` and the page 02 popover, which now lists the counted hosts.

**Tests.** `app_pcap_to_dsm5/tests/test_productivity.py`, 13 cases: tool hosts count; the background hosts of 25.10, `google.com` itself, `adsdk.microsoft.com`, `login.live.com` and lookalikes do not; a mixed day; data without `ResolvedHost`. 40 app tests pass.

**Effect:**

| Data | Activity | Old | New |
| --- | --- | --- | --- |
| Maria, Sun 25.10 | no work | 11 932 | 0 |
| Carl, Sun 25.10 | no work | 11 453 | 0 |
| Ben, Mon 26.10 | work block 08:00–12:00 | 7 012 | 6 335 (todoist 3 585, gitlab 2 316, …) |
| Thesis ONU datasets | – | 30 of 41 change, mostly to 0 (one keeps 14: `config.teams.microsoft.com`) | |

Unlike Sections 7.7 and 7.9, this **changes thesis values**. The thesis bands for C2_F6 (3 500 / 15 000, inverted) were set on the polluted counts: a no-work day now gives 0 hits and therefore μ = 0, while the background had given it a small μ. C2_F6 must be recalibrated on the baseline days (thesis-alignment B10).

**Deployment.** `git pull`, app image rebuilt, container recreated; the feature cache was empty. Check in the container: `docs.google.com` counts, `accounts.google.com` not, `github.com` unchanged.

### 7.11 Background traffic in the runners, background filter in the app (26.10.2026)

**Why.** On 25.10 the six planned runner containers sent 0 packets outside their blocks; every night 00–07 was empty. Real devices are never silent: in the thesis ONU captures 35 of 41 contain background (Windows Update, telemetry, Safe Browsing, Chrome updates, OCSP, NTP, cloud sync), on average ~28 packets per minute. The sleep and timing features (30-minute quiet period, active minutes, sessions, first activity) count every packet, so on a real device this background makes every night look awake, and the simulated data never tested it.

**Runner** (`e3fd6dd`, `43407f5`, `traffic-runner/README.md` §8b): every container's main process now sends low-rate background traffic around the clock, from the background hosts of the thesis captures (`config/background.yaml`). Laptop ~20 requests/h by day and ~5 at night, phone ~13 and ~4; a request is ~20–30 packets. 16 new tests (rates, trust roots, night factor, reproducibility, local HTTP server, failures never raise, the container survives a broken config). A smoke test from the gateway reached all 17 endpoints; the three Windows hosts needed Microsoft's root CAs (`config/microsoft-roots.pem`).

**App** (`e3fd6dd`, `app/metrics/common.py`): `BACKGROUND_HOST_PATTERNS` and `drop_background()`, applied right after `enrich_with_hostnames` in pages 01 and 02, so **no** feature counts machine background (packets and their DNS rows). Only housekeeping hosts: Windows update/telemetry/settings/NCSI/WNS, Chrome/Android time, updates, Safe Browsing, connectivity checks and FCM, Apple push and captive check, OCSP/CRL, NTP. Logins (`accounts.google.com`, `login.live.com`) and cloud sync stay. Packets without a known hostname cannot be classified and stay. Page 03 (network overview) still shows all traffic. 32 new cases in `tests/test_background.py`, among them: every runner background host is filtered; a night with background every 10 min gives a longest quiet period of 0.2 h and 64 active night minutes without the filter, and 7 h and 31 minutes (the real user activity) with it. 72 app tests pass.

The request named the sleep and timing features. The filter applies to all features, because a request the device sends on its own is not user behaviour for any of them (the same reasoning as the ingest filter, Section 3.1).

**Effect on the thesis datasets** (all 64, with/without the filter): background in 35 datasets, 0.02 % of all packets. No sleep or timing value changes (5-minute captures). `C2_F1_UniqueSLD` drops by 1–5 in 32 datasets (e.g. `ONU_capture_game_4` 22 → 18, `video_3` 24 → 19), `F1_DistinctSocial` changes in 12, the byte totals in 3. **This changes thesis values** (thesis-alignment B11).

**Effect on the gateway data.** Before, 25.10: 0 packets outside the blocks. First full night with background, 26.10 22:00 – 27.10 07:00 (all 8 containers on the new image since 26.10 ~12:15; measured 27.10 with `/var/tmp/night_measure.py` in the app image):

| Device | Packets/h (all) | Background packets/h | Background packets/h 00–06 | Hours with background (of 9) |
| --- | --- | --- | --- | --- |
| student_a_laptop | 239 | 239 | 143 | 9 |
| student_a_phone | 150 | 150 | 66 | 9 |
| insomnia_a_laptop | 228 | 180 | 98 | 9 |
| insomnia_a_phone | 7 334 | 84 | 59 | 9 |
| mdd_suicidality_a_laptop | 25 445 | 175 | 82 | 9 |
| mdd_suicidality_a_phone | 300 284 | 247 | 245 | 9 |
| social_anxiety_a_laptop | 92 285 | 181 | 77 | 9 |
| social_anxiety_a_phone | 233 870 | 137 | 36 | 9 |

Every device now has background in every hour of the night, as a real device would. Sleep features of the same window, with background and with the app's filter:

| Dataset | Night blocks in the window | Data | Active minutes 00–06 | Longest quiet period (h) | Sleep onset / wake (first 30-min gap 22–04) |
| --- | --- | --- | --- | --- | --- |
| gw_student_a | none (no plan) | with background | 57 | 0.37 | none |
| | | filtered | 0 | 9.0 | – (no data left) |
| gw_insomnia_a | phone 06:06–06:16 | with background | 59 | 0.66 | 03:22 / 04:02 |
| | | filtered | 15 | 1.39 | 00:26 / 01:49 |
| gw_mdd_suicidality_a | until 01:53 (phone), 23:16 (laptop) | with background | 79 | 0.48 | none |
| | | filtered | 42 | 1.28 | 00:38 / 01:12 |
| gw_social_anxiety_a | until 00:37 | with background | 73 | 0.64 | 02:18 / 02:56 |
| | | filtered | 48 | 1.05 | 01:01 / 02:02 |

With background, no dataset has a quiet half hour before 02:18, and Maria's night has none at all. This is the effect the filter is for. The student pair, which has no blocks, shows that the filter removes the generator's traffic completely (0 packets left, 9 h quiet).

**Limit found: shared IPs get the wrong hostname.** In the other datasets the filtered night is still not quiet: e.g. `insomnia_a_laptop` has no block after 17:30 but keeps ~48 packets/h. These are background requests the app labels with another name. `build_dns_map` maps each IP to the **first** name it was resolved for that day, for the whole day. Measured in gw_insomnia_a: `74.125.29.100` was first `google.com` (26.10 10:27); at night the generator reached it as `clients2.google.com` and `android.clients.google.com`. `74.125.29.94` (first `www.gstatic.com`) and `172.217.208.94` (first `www.google.ch`) served `ocsp.pki.goog`, and `2.16.168.46` (first a TikTok host, SOCIAL) served `www.msftconnecttest.com`. So these packets are neither filtered nor counted for the right service, on real devices as well. The fix would be a per-client, time-aware lookup (the latest answer the client received for that IP before the packet), open point below.

**Incident during the measurement.** The first run (timer 27.10 07:30) loaded two full days per dataset and was ended by the kernel's OOM killer at 4.9 GB (host-wide, reported as "OOM killer ended python3" in the 08:00 report). No runner or service was hit; all 84 blocks of the 24 h window were ok. The script now reads only DNS rows plus the window's files, reduces each 5-minute file at once, and runs with `docker run --memory 1500m` (later kills stayed inside the container, `CONSTRAINT_MEMCG`).

**Deployment.** App image rebuilt and recreated, feature cache moved to `/var/tmp/feature_cache-before-e3fd6dd`. Runner image built from `git archive` (249 tests pass in the image), then the rolling switch `tr-roll-runner2` recreates each container only while it is idle. The containers must be **recreated** (not only the image changed), because their command changed.

## 8. Operating the system

### Open the app

On the laptop (connected to the same hotspot as the gateway):

```bash
ssh -i ~/.ssh/minipc_deploy -N -L 8501:localhost:8501 kathy@can-my-network-gw   # Tailscale, from any network
```

The command prints nothing and keeps running. That is the open tunnel. Then open http://localhost:8501, log in, and select the `gw_*` datasets (type "Other"). Ctrl+C closes the tunnel.

### Remote access over Tailscale (from outside the hotspot)

The gateway's uplink is a phone hotspot, which accepts no incoming connections from the internet. [Tailscale](https://tailscale.com) connects outward from the gateway and puts it into a private network (tailnet) with your laptops, so SSH and the app tunnel work from anywhere. tailscaled runs with `--netfilter-mode=off`: `/etc/nftables.conf` stays the only firewall, and it allows only SSH on `tailscale0`.

Steps on the gateway, with the usual routine (backup first; after the firewall step a real phone must still have internet):

```bash
BK=/root/tapgw-backup-$(date +%Y%m%d-%H%M); sudo install -d -m 700 "$BK"; sudo cp -a /etc/nftables.conf "$BK/"
# 1. package from Tailscale's apt repository (if "resolute" is not listed yet on pkgs.tailscale.com, use the newest codename there)
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/resolute.noarmor.gpg | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/resolute.tailscale-keyring.list | sudo tee /etc/apt/sources.list.d/tailscale.list
sudo apt-get update && sudo apt-get install -y tailscale
# 2. firewall: the repo file has the tailscale0 SSH line (traffic-runner/gateway/nftables.conf)
cd /opt/can-my-network && git pull
diff /etc/nftables.conf traffic-runner/gateway/nftables.conf      # only the Tailscale lines are new
sudo nft -c -f traffic-runner/gateway/nftables.conf && sudo install -m 755 traffic-runner/gateway/nftables.conf /etc/nftables.conf
sudo systemctl restart nftables
# 3. join the tailnet: prints a login URL, open it on the laptop and log in with your Tailscale account
sudo tailscale up --netfilter-mode=off --accept-dns=false --hostname can-my-network-gw
tailscale status
systemctl is-active tapcap@eno1 tapfeed@eno1 dnsmasq nftables      # and test a real phone
# rollback: sudo tailscale down; sudo cp "$BK/nftables.conf" /etc/nftables.conf && sudo systemctl restart nftables
```

On the laptop: install Tailscale, log in to the same tailnet (invite Karla's account from the admin console), then:

```bash
ssh -i ~/.ssh/minipc_deploy kathy@can-my-network-gw
ssh -i ~/.ssh/minipc_deploy -N -L 8501:localhost:8501 kathy@can-my-network-gw     # app: http://localhost:8501
```

Do not enable Tailscale Serve or Funnel: they would publish services of the gateway. The run's push report (scheduler README §5.2) works without Tailscale.

### Check the status

Peer stack for the runner's calls and gaming (on the gateway since 23.10, [HardwareSetup.md §16](HardwareSetup.md)):

```bash
cd /opt/can-my-network/peer-vm && sudo docker compose ps          # caddy, jicofo, jvb, peer, prosody, web
sudo docker compose -f /opt/can-my-network/traffic-runner/docker-compose.yml exec -T student_a_phone \
  python3 -c "import ssl, urllib.request as u; print(u.urlopen('https://peer.sim/peer/health', context=ssl._create_unverified_context()).read().decode())" < /dev/null
cd /opt/can-my-network/peer-vm && sudo docker compose up -d --build   # after a pull that changed peer-vm/
```

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

Live runs (scheduler README §5):

```bash
systemctl status 'traffic-executor@*' --no-pager                 # one executor per dataset
cd /opt/can-my-network/scheduler
sudo python3 -m scheduler execute --commands /var/lib/traffic-executor/gw_insomnia_a.commands.tsv \
    --state /var/lib/traffic-executor/gw_insomnia_a.state.jsonl --status    # started, late, missed, next block
sudo python3 -m scheduler report --hours 24                       # the push report, printed only (no NTFY_URL in the shell)
systemctl list-timers 'traffic-*' --no-pager                      # sample (1 min), report (08:00), watch (hourly)
sudo du -sh /var/lib/tapfeed/*                                     # tshark's temp files (on disk since 23.10)
tailscale status
```

Note: the system clock of the gateway is **UTC**. `journalctl` and `date` show UTC, while the ingest log lines, the partitions and the app use Zurich time. SQLite's `localtime` also prints UTC on this machine.

### Add or change devices

Simulated devices: edit `traffic-runner/config/devices.csv` in the repo, run `python3 traffic-runner/scripts/gen_compose.py`, commit and push. On the gateway: `sudo git -C /opt/can-my-network pull`, then `cd /opt/can-my-network/traffic-runner && sudo docker compose up -d`. The ingest reloads the file on its next scan, no restart needed. Real devices are not in this file yet (a row there would also create a runner container); see open issue 10. If the access point is replaced, update `--exclude-mac` in the unit (MAC from `/var/lib/misc/dnsmasq.leases`). Real phones need a fixed IP first: add `dhcp-host=<mac>,<ip>` in dnsmasq, and set the phone's "Private Wi-Fi Address" to "Fixed" for the study network.

### Capture folders

The ingest watches `/var/lib/tapcap/ready` (tapcap@eno1, real devices) and, since 23.10, `/var/lib/tapcap/sim/ready` (tapcap@br-sim, runner containers). The two tapcap instances write to separate folders, so their `cap-<ms>.pcap` names cannot collide ([HardwareSetup.md §15](HardwareSetup.md)). A further folder is one more `--watch` line in the unit, then `sudo systemctl daemon-reload && sudo systemctl restart tapingest`.

### Deploy a new code version

Push to `main`, then on the gateway:

```bash
sudo git -C /opt/can-my-network pull
sudo git -C /opt/can-my-network log --oneline -1               # which version runs
sudo systemctl restart tapingest                               # if ingest/ changed
cd /opt/can-my-network/app_pcap_to_dsm5/app && sudo docker compose -f docker-compose.yml -f docker-compose.gateway.yml up -d --build   # if app/ changed
sudo /opt/can-my-network/traffic-runner/scripts/deploy.sh                                   # if traffic-runner/ changed
```

While blocks are running, use the rolling switch instead of `deploy.sh`: build the image from `git archive HEAD traffic-runner`, then `/var/tmp/roll-runner.sh` (as a `systemd-run` unit) recreates each container only while it is idle (Section 7.11).

The runner bakes code and config into its image, so a pull alone does not change it. `deploy.sh` rebuilds it, recreates the containers and runs its tests. It refuses while an activity is running (`FORCE=1` overrides). The ingest reads `traffic-runner/config/devices.csv` straight from the clone, so a changed device list applies to the ingest at the pull. Run `deploy.sh` right after such a pull.

If the update changes how metrics are computed (`app/metrics/`), also move the files in `app/feature_cache/` away: the cache is invalidated by new data, not by new code, and would keep serving the old values.

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

**Correction (16.10, fixed 23.10):** until 23.10, `/etc/tmpfiles.d/tapcap.conf` had the age `2d` on `/var/lib/tapcap/ready`, so `systemd-tmpfiles-clean` deleted captures older than two days ([HardwareSetup.md §15](HardwareSetup.md)). The age was removed on 23.10; neither folder is cleaned any more. Apart from that, nothing is deleted automatically, neither captures (`/var/lib/tapcap/ready`, 73 MB after the first day of light use) nor Parquet (616 KB after 25 minutes). 427 GB are free, so this is not urgent, but a retention policy is part of the open work.

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
| 18 | Integration | Runner traffic did not reach the Parquet data | Ingest watched only `/var/lib/tapcap/ready`; ingest and runner each had their own `devices.csv` | Second `--watch`, ingest reads the runner's `devices.csv` from the clone (Section 7.6) |
| 19 | Deployment | The clone on the gateway did not contain `traffic-runner/` | Nobody had pulled since 16.10; the runner ran from a copy | `git pull`, runner moved into the clone |
| 20 | Data | 63.8 % of the pilot's rows without a domain | App looks up hostnames by destination IP only, so inbound packets never get one | Remote-side lookup (Section 7.7): 0.3 % |
| 21 | App | After a metric change, the app would still show old values | The feature-cache CSV is only invalidated by newer partitions | Move `feature_cache/` away after metric changes (Section 8) |
| 22 | Memory | Only 1.9 GB available on an idle gateway; 90–100 MB/min less during the pilot | tapfeed's tshark keeps a growing temporary pcapng in `/tmp`, a tmpfs (RAM) | Disk-backed `/tmp` per tapfeed instance plus an hourly tshark restart (Section 7.8) |
| 23 | Memory | `TMPDIR` did not move tshark's temp file | `dumpcap` has file capabilities; the C library ignores `TMPDIR` for it | Bind mount of a disk folder over the service's `/tmp` instead |
| 24 | systemd | Both tapfeed instances failed with `226/NAMESPACE` after the first fix (feed down ~1 min) | `BindPaths` source created in `ExecStartPre`, but the namespace is set up before | `StateDirectory=tapfeed/%i`, which systemd creates first |
| 25 | Executor | The pilot file was refused: "block … appears twice" | Block IDs are unique per plan only; the pilot merged three plans | Pilot IDs include the device; the real run has one executor per plan |
| 26 | Access | `Host key verification failed` for `kathy@10.42.0.1` | `known_hosts` has the gateway under 172.20.10.10 | Same keys (compared); use 172.20.10.10, which works from the hotspot and from the AP network |
| 27 | Executor | `--status` refused while the executor ran ("state file is locked") | The status view opened the state file like an executor, with the lock | `--status` reads without the lock (fixed 23.10) |
| 28 | Report | The daily report would have arrived at 10:00 instead of 08:00 | `OnCalendar=08:00` is read in the system time zone, which is UTC on the gateway | `OnCalendar=*-*-* 08:00:00 Europe/Zurich` (also correct after the switch to winter time) |
| 29 | Gateway | "OOM killer ended python3" in the report of 27.10 08:00 | One-off night measurement loaded ~6 M packets with all columns (4.9 GB) | Measurement reads file by file, container capped at 1.5 GB (Section 7.11); no runner affected |

## 10. Security notes

- The app listens on localhost only; port 8501 is not opened in nftables. Access requires SSH access to the gateway.
- `secrets.toml` is mode 600 and not in any repository.
- The Parquet data contains client IPs and visited domain names. It stays on the gateway (no sync to laptops).
- **To remove after setup:** `/etc/sudoers.d/90-temp-deploy` and the `minipc-deploy` line in `/home/kathy/.ssh/authorized_keys`. Both give full root access without a password while they exist.
- SSH on the uplink (`wlp2s0`) is still allowed (HardwareSetup Section 13).
- **Tailscale** (set up 23.10, §8): only SSH is open on `tailscale0`, and tailscaled does not touch the firewall (`--netfilter-mode=off`). Anyone in the tailnet can try SSH; keep the tailnet to the project accounts.
- The temporary passwordless sudo rule was still in place on 23.10 and was used for the run setup. Remove it once the run is set up (item 2 below).
- The push report (scheduler README §5.2) sends counts, block IDs and gateway figures to an ntfy topic, but no domains or IPs. A long random topic name keeps it private. The topic is in `/etc/traffic-report.env` (root, mode 600).

## 11. Open issues and next steps

1. ~~Background filter~~ Done (Section 3.1). Still to decide after looking at real nights: always-on keep-alives such as Apple push (5223).
2. **Remove the temporary access** (Section 10).
3. ~~Own fork of the app repo~~ Done differently: app imported into this repository (Section 7.5). After a few days without problems, delete `/opt/app_pcap_to_dsm5_public`, `/var/tmp/tapingest-unfiltered-*` and `/root/tapingest.service.bak-*` on the gateway. The local `app_pcap_to_dsm5_public` clone and the `live-ingest-*.tar.gz` archives on Thierry's laptop are obsolete.
4. ~~br-sim integration~~ Done 23.10 (Section 7.6).
5. ~~First end-to-end pilot~~ Done 23.10 (Section 7.6): 99.9 % of the rows inside the ground-truth block, the visited site and its hosts in the DNS data.
6. **Validation 3–6** from MasterThesisInc §8 on real data: packet counts vs. `capinfos`, a known action at a noted time, plausible domain names, night silence of an unused phone.
7. ~~Hostnames for inbound packets~~ Done 23.10 (Section 7.7). Still open, only needed for devices without visible DNS: SNI as a second source (`-e ip.dst` in `tapfeed`, then join in the ingest).
8. **Throughput:** 1500–3500 packets/s on the mini-PC. Enough for a few devices; a high-quality video stream alone can reach 500–1000 packets/s. Watch "still pending" in the log during runner tests.
9. **Retention policy.** Decided 23.10: raw pcaps are kept in both folders (the `2d` age on `ready/` was removed, HardwareSetup §15). Still open: a policy for Parquet and for when the disk fills up.
10. **Real devices in the device map.** The ingest reads one `devices.csv`, which also generates runner containers. Real test phones need either a second `--devices` file or a role the runner's generator skips.
11. **Dataset names.** Done 23.10: `gw_<profile>_<letter>`, devices `<profile>_<letter>_<role>` (activity-catalog §1), because the app groups `gw_student_01` and `gw_student_02` as `gw_student`. The runner's devices are renamed (`student_a_*` → `gw_student_a`), and its validator enforces the rule. Data ingested before the rename stays under `gw_student_01`.
12. ~~Live run setup~~ Done 23.10 (Section 7.8): executors and report timers enabled, pilot data moved aside. The run starts Sun 25.10 with the warm-up day; watch the push reports.
13. **MDD review** by Lukasz before 09.11, when the MDD phase starts. A changed profile only needs a new plan; the baseline rows stay identical (same seed), so the executor continues.
14. **YouTube stalls end the block.** In the pilot, `video_stream` aborted with `state=stalled` after 2 min and the block's remaining 29 min stayed silent. Runner (Karla): reload or switch to another video on a stall instead of failing.
15. **CPU at peaks.** The load reached 11 (6 cores) while the pilot's six blocks started. Watch the push report's load figure; if pages time out at peaks, stop the UniFi controller during the run (an adopted AP keeps working).
16. ~~tapfeed rotation~~ Done 23.10: tshark restarts every 10 min (`TAPFEED_ROTATE=600` in the drop-in, Section 7.8).

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
    --watch /var/lib/tapcap/sim/ready \
    --devices /opt/can-my-network/traffic-runner/config/devices.csv \
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
# devices: the unit reads /opt/can-my-network/traffic-runner/config/devices.csv (same list as the runner)

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
