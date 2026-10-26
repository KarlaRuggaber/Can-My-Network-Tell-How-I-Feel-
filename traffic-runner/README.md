# traffic-runner

Scripted network traffic for the profiles. Each container is one simulated **device** (phone or laptop) with a fixed MAC and IP on its own virtual LAN on the gateway. On command it runs one activity from [`profiles/activity-catalog.md`](../profiles/activity-catalog.md) in a real Chromium, and it appends one ground-truth row per run. The traffic is routed and recorded exactly like that of the real devices.

This is only the runner. It does not cover the scheduler (profile → 14-day plan) or the ingest service (PCAP → Parquet).

## 1. Architecture

```
 real devices ──WiFi── AP ── eno1 (10.42.0.1) ─┐
                                                ├─ mini PC: nftables NAT ── wlp2s0 ── internet (hotspot)
 containers ───────── br-sim (10.42.1.1) ──────┘
                        ▲
            tapcap@br-sim + tapfeed@br-sim record here
```

| Item | Choice |
|---|---|
| Network | External Docker network `sim`, Linux bridge `br-sim`, 10.42.1.0/24, gateway 10.42.1.1 |
| Device identity | Fixed `ipv4_address` and `mac_address` per container, taken from `config/devices.csv` |
| Firewall and NAT | Docker runs with `"iptables": false`. All rules stay in `/etc/nftables.conf`. br-sim may reach DNS, ping and the internet, nothing else, and it is never forwarded to eno1. |
| DNS | `config/resolv.conf` (`nameserver 10.42.1.1`) is mounted over `/etc/resolv.conf`. Every lookup goes from the container IP straight to dnsmasq, so `log-queries` and tapfeed attribute it to the device. |
| Container lifecycle | Containers idle with `sleep infinity`. A run is `scripts/run-activity.sh <device> ...` (a `docker compose exec` with stdin detached, see section 3). Each run starts a **new browser process with a fresh context**, so no DNS, HTTP or cookie state carries over between blocks (catalog §5.2). Code **and config** are baked into the image (`COPY config`); only `logs/` and `/etc/resolv.conf` are mounted. A `git pull` alone therefore never changes the running runner. Deploy with `scripts/deploy.sh` (section 7). |
| Randomness | All randomness comes from `random.Random(f"{seed}/{block_id}")`. The same seed and block ID give the same sequence of choices. |

```
traffic-runner/
  Dockerfile               mcr.microsoft.com/playwright/python:v1.63.0-noble (pinned)
  requirements*.txt        pinned Python dependencies
  docker-compose.yml       GENERATED from devices.csv, do not edit
  config/
    devices.csv            simulated devices (interface with the ingest service)
    mixes.yaml             domain sets from catalog §3 + start URLs, video/audio sources, consent buttons
    roles.yaml             role -> Playwright device emulation
    resolv.conf            container DNS -> 10.42.1.1
  runner/
    cli.py                 python -m runner {run,validate,list}
    config.py              loading + validation
    context.py             RunContext: deadline, visited hosts, driver interface
    browser.py             Playwright driver (real network)
    fake.py                network-free driver + clock (tests, --dry-run)
    gtlog.py               ground-truth CSV with file lock
    activities/<id>.py     one module per activity
  scripts/gen_compose.py   devices.csv -> docker-compose.yml
  tests/                   pytest, no network needed
  gateway/                 proposed gateway files (section 7)
```

## 2. Quick start without the gateway (laptop)

```bash
cd traffic-runner
python3 -m pytest -q                       # needs PyYAML + pytest; no network, no Playwright
python3 -m runner validate
python3 -m runner list
python3 -m runner run --device student_a_phone --activity browse --duration 10m \
    --mix news,shopping --seed 42 --profile student --block-id b001 --dry-run
```

`--dry-run` replaces the browser with the fake driver and prints the planned sequence (pages, dwell, links). Nothing is loaded and nothing is logged.

A real run on a laptop (default Docker network, no fixed IP, traffic is **not** recorded):

```bash
docker build -t traffic-runner:0.1.0 .
docker run --rm --shm-size 1g -v "$PWD/logs:/logs" traffic-runner:0.1.0 \
    python3 -m runner run --device student_a_laptop --activity phone_check --duration 2m \
    --mix news --seed 42 --profile test --block-id local001
docker run --rm traffic-runner:0.1.0 python3 -m pytest -q
```

## 3. Running activities

```bash
sudo scripts/run-activity.sh student_a_phone \
    --activity phone_check --duration 300 --mix news,social_passive \
    --seed 42 --profile student --block-id b001
```

**Always detach stdin** when you call `docker compose exec` yourself: `docker compose exec -T <device> ... < /dev/null`. Even with `-T`, exec reads from the terminal. On the gateway (2026-10-16) this caused three problems:
- it swallowed the following lines of a pasted command block
- commands started with `&` (background) hung
- commands under `timeout` hung

`scripts/run-activity.sh` does this for you.

| Option | Meaning |
|---|---|
| `--device` | Device from `devices.csv`. Defaults to `$RUNNER_DEVICE`, which compose sets per container. A mismatch is refused. With `RUNNER_STRICT_IP=1` (set by compose), the container's IP must match `devices.csv`. |
| `--activity` | Activity ID from catalog §2 |
| `--duration` | `300`, `90s`, `5m` or `2h`. If omitted, it is drawn from the catalog default (e.g. `phone_check` 1–5 min). Activities that run "as block" require it. A value outside the default only triggers a warning, so 2-min tests work. |
| `--mix` | `news,social_passive` (equal weights) or `news:.2,social_passive:.4` (as in the profiles). Categories come from `config/mixes.yaml`. |
| `--seed`, `--profile`, `--block-id` | Logged as given. `seed` and `block-id` seed the RNG. |
| `--pages`, `--dwell` | Profile overrides of the catalog defaults (§1 "Frequency keys"), e.g. `--pages 2-4 --dwell 1m-3m` |
| `--lookups` | Number of DNS lookups for `sh_adjacent_lookup`, e.g. `--lookups 1-3` (profile key `lookups`) |
| `--platform` | Call platform from the scheduler's plan (zoom/teams/jitsi/discord). Accepted and ignored, because all calls use the peer VM's Jitsi |
| `--mic-share` | Calls only: share of the time the microphone is on, e.g. `0.1` or `10%` (profile option `mic_share`, social anxiety). The call starts muted; speaking turns of 3–15 s alternate with muted pauses drawn so the long-run share matches (0.1: pauses of ~81 s on average). Drawn from the seed. The camera is not affected |
| `--dry-run` | No network, prints the plan |

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | ok |
| 1 | error |
| 2 | usage or configuration error (no log row) |
| 3 | not_implemented |

**Activities:**

| ID | Status | What the runner does | Catalog default |
|---|---|---|---|
| `phone_check` | ok | Pages from the mix one after another, 20–90 s dwell each, scrolling. Without `--pages` it keeps opening pages until the duration is used up; with `--pages` it opens exactly that many and may end early (catalog §2, since 23.10). | 1–5 min |
| `browse` | ok | Page from the mix, 30–180 s dwell, scrolling, then 1–2 same-site links per page, each with its own dwell. Fills the block. | as block |
| `repeat_visit_loop` | ok | Picks 2–3 fixed pages, revisits one every 1–3 min. A **new browser process** per visit forces a fresh DNS query. | 10–30 min |
| `video_stream` | ok | **Since 25.10 SRF only:** YouTube aborts playback after ~40 s in the gateway containers ("Ein Fehler ist aufgetreten", player state -1), so it is `playable: false` in `mixes.yaml` (process log, week 6). Picks a playable `streaming` site with the RNG and plays at the **lowest quality**. The decoded resolution is logged to stderr. Runs to the end of the video or the block. **YouTube:** search for a term from `mixes.yaml`, play one of the first 5 results; 144p preference plus `setPlaybackQualityRange('tiny')`, re-applied every check. **SRF:** one of the first 5 on-demand videos on the Play SRF page, lowest video.js quality level (270p in the tests). **Stalls** (no playback for about 45 s): reload the same video once, then switch to other videos, at most 4 times per block. The replacement videos are drawn with the seed up front. Only then the block fails. | 30–120 min |
| `music_background` | ok | Opens an SRF radio live page (SRF 1, SRF 3 or Virus, `mixes.yaml` → `audio.streams`, `kind: page`). The page load counts as srf.ch = STREAMING. The page exposes no quality levels, so it streams 192 kbit/s AAC. The SRG MP3 stream remains as a commented fallback (`kind: stream`). | as block |
| `idle_connected` | ok | No browser, only waits | as block |
| `social_passive` | ok | Scrolls a feed from the mix (jumps to the end every 5–15 s so more content loads). Opens 0–2 posts or videos per block via an internal link (30–120 s each), then returns to the feed. Switches to another site of the mix every 3–10 min (runner choice for long blocks). Default mix `social_passive` (Reddit, TikTok). | as block |
| `work_block` | ok | Keeps a home page of the `work` mix and reloads it every 2–5 min. Opens 2–5 other work pages per hour (dwell 1–5 min). Login-free approximation: no mail, calendar or document editing. | 60–120 min |
| `study_block` | ok | Like `work_block` with the `study` mix, plus 1–3 PDF downloads per hour from `mixes.yaml` → `documents.pdfs` (1.4–5.4 MB arXiv papers). Each download opens the paper page, then fetches the PDF in the browser. | 45–120 min |
| `crisis_resource_visit` | ok | 1–3 pages of the `crisis_help` mix, dwell 1–4 min; ends when done | 2–10 min |
| `sh_adjacent_lookup` | ok | 1–3 DNS lookups of `sh-adjacent-NN.invalid` placeholders, no browser, no connection. `domains` lists the queried names. | seconds |
| `video_call`, `voice_call` | ok | WebRTC call against the peer on the peer VM ([peer-vm/](../peer-vm/README.md)). The runner asks the peer to join a room derived from `profile/seed/block_id` and the token, then joins with a fake camera/mic (voice: audio only). It stays until the block ends; three failed connection checks in a row are an error. Every `--platform` runs on this self-hosted Jitsi. Needs `peer.env`, otherwise `not_implemented` | as block |
| `gaming_session` | ok | Store pages of the `gaming` mix (Steam, Riot) for 2–5 min (at most a quarter of the block), then the game page of the peer VM: a WebSocket game at 20–60 messages per second in each direction (tick drawn with the RNG). Voice chat is a separate `voice_call` row of the scheduler. Needs `peer.env` | 60–120 min |
| `messaging` | ok | Slack web in the project workspace: the persona's member account sends 3–10 messages, 10–60 s apart, to the bot "CMNTHIF Partner", which replies after 5–40 s (`peer-vm/slackbot`). Always uses a desktop browser profile, because Slack refuses phone browsers. Needs the device's Slack session (section "Test accounts"), otherwise `not_implemented` | 2–10 min |
| `social_post` | ok | **Discord since 25.10** (was Reddit, see §8a): one generated test image (1–3 MB of random pixels) through the webhook of the private server's `#uploads` channel, sent from the device container, then the browser opens the uploaded image. The webhook ID is checked before the upload and the channel in Discord's reply afterwards. Needs `sessions/discord.webhook` and the IDs in `config/accounts.yaml`, otherwise `not_implemented` | 2–5 min |
| `away` | stub | Catalog only, writes `not_implemented`. It belongs to the scheduler, where away means no runs. | |

**Mixes:**
- Sites with `login: true` are skipped, and their weight goes to the remaining categories (a warning names them).
- A mix that consists only of login categories (e.g. `messaging`) logs `not_implemented`.

**Cookie banners:** the runner never accepts. After each page load it polls up to 5 s for a reject button (`consent.reject_buttons`). If the first level only offers accept/settings, it opens a clearly named settings button (`consent.settings_buttons`, e.g. "Individuell verwalten") and rejects there ("Nur Notwendige", "Alle Anbieter ablehnen", ...). Tested on 2026-10-16:

| Result | Sites |
|---|---|
| Rejected | YouTube (desktop + mobile), SRF Play and SRF radio, NZZ, Tages-Anzeiger, 20min, Zalando, DuckDuckGo, Reddit, TikTok (mobile) |
| Banner stays open, page loads without consent | watson, Migros, Galaxus (only "Akzeptieren" plus a generic "Einstellungen") |

SRF Play only starts its player after a choice. Whether the simulated users should *accept* instead (closer to typical users, more ad/tracker traffic) is a design decision for the team (section 9).

**Reproducibility:**
- Each iteration draws everything it needs from the RNG **before** it touches the network.
- Choices that depend on page content (which link to follow, scroll pattern) use a sub-RNG seeded by one draw.
- So a slow or failing page never shifts the rest of the sequence.
- `tests/test_reproducibility.py` runs every activity twice with the fake driver and compares the calls one by one.

## 4. Ground-truth log

`/logs/ground_truth.csv` is the `./logs/ground_truth.csv` file next to `docker-compose.yml`. It is shared by all containers and protected by `flock`. Columns follow catalog §1, plus `status`:

```csv
start,end,device,activity_id,domains,profile,seed,block_id,status
2026-10-16T18:02:11+02:00,2026-10-16T18:04:11+02:00,student_a_phone,phone_check,www.20min.ch;www.reddit.com,student,42,b001,ok
```

| Column | Content |
|---|---|
| `start`, `end` | ISO-8601 with offset, Europe/Zurich. `end` is the real end, which can be earlier than start + duration (e.g. `phone_check` done, video over). |
| `domains` | Hosts of the main documents actually loaded, after redirects, in first-visit order, separated by `;`. For `music_background` it is the stream host. Third-party hosts (CDN, ads) are not listed. |
| `status` | `ok` = at least one page or stream loaded; `error` = exception, nothing loaded, SIGTERM/Ctrl-C or watchdog (duration + 90 s; the row is written before the browser closes, and a close that hangs for 60 s ends the run's process group, since 26.10); `not_implemented` = stub or no usable site in the mix |

Every run that gets past argument checking writes a row, including on error or interrupt. The exception is a container stopped mid-run (`docker compose down`), which kills the exec'd process with SIGKILL.

## 5. devices.csv and adding a device

```csv
device,role,mac,ip,dataset
student_a_phone,phone,02:00:0a:2a:01:0b,10.42.1.11,gw_student_a
student_a_laptop,laptop,02:00:0a:2a:01:0c,10.42.1.12,gw_student_a
```

The file is the **interface with the ingest service**, which maps packets to a dataset by IP. On the gateway the ingest reads this same file from the git clone (section 9, item 2). Lines starting with `#` are comments. Do not change the format without agreeing on it first.

| Column | Rule (checked by `python -m runner validate` and `gen_compose.py`) |
|---|---|
| `device` | Unique, `[a-z0-9_]+`, convention `<profile>_<letter>_<role>` (catalog §1). Also used as the service and container name. |
| `role` | `phone` (Pixel 7 emulation: Android UA, mobile viewport, touch) or `laptop` (Desktop Chrome) |
| `mac` | Unique, lower-case, locally administered unicast (`02:…`) |
| `ip` | Unique, 10.42.1.10–10.42.1.254 |
| `dataset` | The simulated person; phone and laptop of one person share it. Convention `gw_<profile>_<letter>` (catalog §1): no digit at the end and no `onu`/`bras`, otherwise the app merges or misclassifies datasets |

To add a device:
1. Add a row to `config/devices.csv`.
2. Run `python3 scripts/gen_compose.py` (validates the file and regenerates `docker-compose.yml`).
3. Commit and push. Then on the gateway: `sudo /opt/can-my-network/traffic-runner/scripts/deploy.sh`.

The ingest reads `devices.csv` straight from the clone and applies a change right after the `git pull`. Deploy the runner right after the pull as well, so that containers and ingest use the same device list.

`pytest` fails if `docker-compose.yml` is out of date.

## 6. Resources and data volume

- **Per container:** `shm_size: 1gb` (Chromium), `mem_limit: 2g`, `cpus: 2.0`. The gateway has 6 cores and 7.1 GiB RAM (about 4.8 GiB free), so plan for **2–3 devices browsing in parallel**.
- **The uplink is the phone hotspot.**
  - Keep video tests short. The runner already asks YouTube for 144p.
  - Base image: about 2 GB once. Load it from a laptop instead of pulling over the hotspot (section 7, step 6).

How to measure a run: br-sim TX = downstream to the containers, RX = upstream.

```bash
b=$(cat /sys/class/net/br-sim/statistics/tx_bytes); r=$(cat /sys/class/net/br-sim/statistics/rx_bytes)
# ... run the activity ...
echo "down $(( ($(cat /sys/class/net/br-sim/statistics/tx_bytes)-b)/1048576 )) MiB, up $(( ($(cat /sys/class/net/br-sim/statistics/rx_bytes)-r)/1048576 )) MiB"
```

Measured on 2026-10-16, locally (laptop, Docker Desktop) and on the gateway. All values are container eth0 counters unless noted, so they include page loads, consent dialogs and ads.

| Activity, 2 min | Down (laptop) | Up (laptop) | Gateway, 2026-10-16 (down / up) | Notes |
|---|---|---|---|---|
| `phone_check` news,social_passive (phone) | 11–34 MiB | 0.3–1.2 MiB | 25 MiB / 1 MiB together with `browse` (br-sim counters) | 1 page (NZZ) = 11 MiB; NZZ + Reddit = 34 MiB |
| `browse` news,shopping (laptop) | 6–16 MiB | 0.5–0.8 MiB | see above | depends heavily on the site |
| `repeat_visit_loop` news (phone) | 5–8 MiB | 0.3–0.4 MiB | 12 MiB / 1.4 MiB (20min + watson) | 2 visits |
| `video_stream` YouTube (laptop) | 3–8 MiB | 0.3–0.6 MiB | 7 MiB / 0.6 MiB (240p) | phone 144p; laptop 144p–240p |
| `video_stream` SRF | 10–26 MiB | 0.4–0.6 MiB | not run | 270p; the player buffers ahead at the start |
| `music_background` | 2 MiB (MP3) / 4.9 MiB (SRF radio page) | 0.1–0.3 MiB | 2 MiB / 0.2 MiB (MP3, 16.10) | MP3 128 kbit/s ≈ 1 MiB/min; radio page 192 kbit/s ≈ 1.4 MiB/min plus page load |
| `social_passive` TikTok (phone, 3 min) | 7.2 MiB | 1.1 MiB | – | feed and one video page |
| `social_passive` Reddit (laptop) | 66 MiB | 1.6 MiB | – | **feed auto-plays videos** (muted autoplay is Chrome's default, so real users see the same) |
| `work_block` (3 min) | 2.5 MiB | 0.2 MiB | – | one home page |
| `crisis_resource_visit` (3 min) | 19 MiB | 0.7 MiB | – | 143.ch, 147.ch |
| `sh_adjacent_lookup` | 3 KiB | 0 | – | DNS only |
| `study_block` PDF | +1.4 to 5.4 MB per download | | – | 1–3 per hour |
| `video_call` (laptop, 2 min) | 9.4 MiB | 13 MiB | – | upload-heavy ≈ 0.9 Mbit/s up; ~2 MiB of the download is the Jitsi page |
| `voice_call` (90 s) | 2.5 MiB | 0.5 MiB | – | ≈ 40 kbit/s audio plus the page |
| `voice_call` 3 min, `--mic-share` 1.0 / 0.3 / 0.1 | – | 55 / 25 / 5 kbit/s | – | 50 / 24 / 5 packets/s up. Muted = Opus DTX, ~5 packets/s |
| `gaming_session` game phase | ≈ 60 kbit/s | ≈ 50 kbit/s | – | small packets both ways; the store pages dominate the volume |
| `idle_connected` | 0 | 0 | 0 / 0 | |

On the gateway (br-sim counters), `phone_check` and `browse` in parallel for 2 min transferred 25 MiB down and 1 MiB up.

Rough budget for full-length blocks:
- `music_background`: ≈ 85 MiB/h (radio page), ≈ 60 MiB/h (MP3 fallback)
- YouTube at 144p: ≈ 1–2 MiB/min after the page load
- Browsing: about 5–15 MiB per page view, much of it ads

A 14-day profile with several browsing blocks per day therefore reaches several GB. `social_passive` on Reddit is the most expensive activity (~33 MiB/min with auto-playing feed videos). A 1–2 h block costs 2–4 GB. Accepted on 23.10, because real users see the same autoplay. Check this against the hotspot plan before running profiles in real time.

## 7. Gateway setup (run step by step, with checks)

**Status 2026-10-16: steps 2–7 are applied on the gateway.**
- Docker was already installed by a colleague.
- Backups are in `/root/tapgw-backup-20261016-1602/`.
- Acceptance passed:
  - two devices in parallel, both `ok`
  - 181 SNI events from 10.42.1.11/.12 with the right MACs in `feed.ndjson`
  - 7k–11k packets per device and minute in `/var/lib/tapcap/sim/ready/`
  - a real phone kept internet access after every step

Reading `/etc/nftables.conf` and the dnsmasq, tapcap and tapfeed files on 2026-10-16 showed what has to change:

| Area | Finding | Consequence |
|---|---|---|
| NAT | Already `oifname wlp2s0 masquerade` for every source | Only input and forward rules for br-sim are needed |
| dnsmasq | Uses `bind-interfaces` | Fails on an interface that does not exist yet. Switch to `bind-dynamic`, which is mutually exclusive with `bind-interfaces`. |
| tapcap file names | `cap-<epoch_ms>.pcap` with no interface in the name | Two instances writing to the same `ready/` could collide, and the rename overwrites. Proposal: tapcap@br-sim writes to **`/var/lib/tapcap/sim/{tmp,ready}`**. |
| tapfeed | Writes a fixed `feed.ndjson` and follows the dnsmasq journal for DNS | A second instance would log every DNS query twice. Proposal: `TAPFEED_DNS=0` for the br-sim instance, so DNS stays with tapfeed@eno1 (which sees 10.42.1.x too) and br-sim adds only SNI. Both append to the same `feed.ndjson` (one `printf` per line, appends are atomic). |
| Docker | Not installed (since installed by a colleague: Ubuntu `docker.io` 29.1.3 with `"iptables": false`) | `/etc/docker/daemon.json` must exist **before** the package is installed. dockerd starts right after installation, and with the default `"iptables": true` it sets the FORWARD policy to DROP, which would cut off the real devices. |

Back up before every step. After every step, check that a **real phone on the AP still has internet** and that `tapcap@eno1` is still running.

### Step 0: copy files and record the baseline

```bash
# on the laptop (hotspot LAN, no mobile data):
scp -r traffic-runner kathy@172.20.10.10:~/
# on the gateway:
BK=/root/tapgw-backup-$(date +%Y%m%d-%H%M); sudo install -d -m 700 "$BK"; echo "$BK"
systemctl is-active tapcap@eno1 tapfeed@eno1 dnsmasq nftables
```

### Step 1: Docker with `"iptables": false`

```bash
sudo install -d -m 755 /etc/docker
sudo install -m 644 ~/traffic-runner/gateway/daemon.json /etc/docker/daemon.json
sudo apt-get update && sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
# checks
sudo docker info --format '{{.ServerVersion}}'
sudo nft list tables             # expect only "table inet filter" and "table inet nat" (nothing from Docker)
systemctl is-active tapcap@eno1 tapfeed@eno1 dnsmasq nftables
```

Docker 29.x is available for Ubuntu 26.04 (`resolute`) in the official repo. Installing it downloads about 100 MB over the hotspot.

### Step 2: the `sim` network

```bash
sudo docker network create -o com.docker.network.bridge.name=br-sim \
    --subnet 10.42.1.0/24 --gateway 10.42.1.1 sim
ip -br addr show br-sim          # 10.42.1.1/24 (DOWN until a container is attached: normal)
```

### Step 3: nftables

```bash
sudo cp -a /etc/nftables.conf "$BK/"
diff /etc/nftables.conf ~/traffic-runner/gateway/nftables.conf     # review: only SIM lines are new
sudo nft -c -f ~/traffic-runner/gateway/nftables.conf               # syntax check
sudo install -m 755 ~/traffic-runner/gateway/nftables.conf /etc/nftables.conf
sudo systemctl restart nftables
sudo nft list ruleset | grep -n br-sim
# rollback: sudo cp "$BK/nftables.conf" /etc/nftables.conf && sudo systemctl restart nftables
```

### Step 4: dnsmasq

`bind-interfaces` must be replaced by `bind-dynamic` in **every** file that sets it. The two options are mutually exclusive. Besides `tapgw.conf`, the `ubuntu-fan` package (pulled in by Ubuntu's `docker.io` package) ships `/etc/dnsmasq.d/ubuntu-fan` with `bind-interfaces`. `bind-dynamic` also binds per interface, so the fan networks stay protected.

Test with the systemd helper, not with plain `dnsmasq --test`:
- The helper loads `/etc/dnsmasq.d` a second time with other options. Plain `dnsmasq --test` passed on 2026-10-16 while the real start failed with `cannot set --bind-interfaces and --bind-dynamic`.
- `ubuntu-fan` is a package conffile. If an upgrade asks about it, keep the local version.

```bash
sudo cp -a /etc/dnsmasq.d/tapgw.conf /etc/dnsmasq.d/ubuntu-fan "$BK/" 2>/dev/null
sudo sed -i 's/^bind-interfaces$/bind-dynamic/' /etc/dnsmasq.d/*
sudo install -m 644 ~/traffic-runner/gateway/dnsmasq-sim.conf /etc/dnsmasq.d/sim.conf
sudo grep -rn "bind-" /etc/dnsmasq.d/        # only bind-dynamic may remain
sudo /usr/share/dnsmasq/systemd-helper checkconfig && echo "CHECK OK" && sudo systemctl restart dnsmasq
sudo ss -lnup 'sport = :53'                  # expect 10.42.0.1:53 and 10.42.1.1:53
# rollback: sudo cp "$BK"/{tapgw.conf,ubuntu-fan} /etc/dnsmasq.d/ && sudo rm /etc/dnsmasq.d/sim.conf && sudo systemctl restart dnsmasq
```

The restart leaves the real devices without DNS for about 1 s.

### Step 5: capture on br-sim

```bash
sudo cp -a /usr/local/bin/tapfeed /etc/tmpfiles.d/tapcap.conf "$BK/"
diff /usr/local/bin/tapfeed ~/traffic-runner/gateway/tapfeed        # only the TAPFEED_DNS switch
sudo install -m 755 ~/traffic-runner/gateway/tapfeed /usr/local/bin/tapfeed.new
sudo mv /usr/local/bin/tapfeed.new /usr/local/bin/tapfeed           # rename: running bash keeps the old file
sudo tee -a /etc/tmpfiles.d/tapcap.conf < ~/traffic-runner/gateway/tapcap-sim.tmpfiles.conf > /dev/null
sudo systemd-tmpfiles --create /etc/tmpfiles.d/tapcap.conf
sudo install -D -m 644 ~/traffic-runner/gateway/tapcap@br-sim.override.conf /etc/systemd/system/tapcap@br-sim.service.d/override.conf
sudo install -D -m 644 ~/traffic-runner/gateway/tapfeed@br-sim.override.conf /etc/systemd/system/tapfeed@br-sim.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart tapfeed@eno1                                 # same behaviour, new script
sudo systemctl enable --now tapcap@br-sim tapfeed@br-sim
systemctl is-active tapcap@eno1 tapfeed@eno1 tapcap@br-sim tapfeed@br-sim
sudo journalctl -u tapcap@br-sim -n 5 --no-pager
```

### Updates (after step 6)

Every later version is deployed with one command. It pulls the clone, rebuilds the image (code and config are baked in), recreates the containers and runs the tests:

```bash
sudo /opt/can-my-network/traffic-runner/scripts/deploy.sh
```

Safety checks built into the script:
- **Running activities:** the script refuses while an activity is running in a container, because recreating the container would kill it and its block would get no log row. `FORCE=1` overrides this.
- **Renamed devices:** if the device list changed, the script removes the old containers first, because the new ones need the same IPs.

### Step 6: image and containers

To avoid pulling the 2 GB base image over the hotspot, load it from a laptop on another network:

```bash
# laptop, home WiFi:
docker pull --platform linux/amd64 mcr.microsoft.com/playwright/python:v1.63.0-noble
docker save --platform linux/amd64 mcr.microsoft.com/playwright/python:v1.63.0-noble | gzip > pw-1.63.0-amd64.tar.gz
# laptop on the hotspot (local hop, no mobile data):
scp pw-1.63.0-amd64.tar.gz kathy@172.20.10.10:~/
# gateway:
gunzip -c ~/pw-1.63.0-amd64.tar.gz | sudo docker load
cd ~/traffic-runner
sudo docker compose build        # only the small pip layer (pinned packages)
sudo docker compose up -d
sudo docker compose ps
sudo docker compose exec -T student_a_phone python3 -m pytest -q < /dev/null
# H.264/AAC support of the amd64 Chromium (expect true true; SRF needs it):
sudo docker compose exec -T student_a_phone python3 -c "from playwright.sync_api import sync_playwright as s; p = s().start(); b = p.chromium.launch(channel='chromium'); pg = b.new_page(); print([pg.evaluate('t => MediaSource.isTypeSupported(t)', t) for t in ('video/mp4; codecs=\"avc1.42E01E\"', 'audio/mp4; codecs=\"mp4a.40.2\"')]); b.close(); p.stop()" < /dev/null
```

### Step 7: acceptance

```bash
cd ~/traffic-runner
sudo scripts/run-activity.sh student_a_phone  --activity phone_check --duration 2m --mix news,social_passive --seed 42 --profile student --block-id t001 &
sudo scripts/run-activity.sh student_a_laptop --activity browse --duration 2m --mix news,shopping --seed 42 --profile student --block-id t002 &
wait
sudo grep -E '"src":"10\.42\.1\.1[12]"' /var/lib/tapcap/meta/feed.ndjson | tail -20
sudo bash -c 'tcpdump -nn -r "$(ls -t /var/lib/tapcap/sim/ready/*.pcap | head -1)" host 10.42.1.11 | head'
cat logs/ground_truth.csv
```

Then run each MVP activity for 2 minutes (`repeat_visit_loop`, `video_stream`, `music_background`, `idle_connected`), measure the data volume (section 6), and check a real phone on the AP throughout.

### Step 8: peer stack for calls and gaming (gateway mode)

**Status: applied on 23.10.** Calls and gaming are live; details and measurements in `process/HardwareSetup.md` §16.

The counterpart for `video_call`, `voice_call` and `gaming_session` runs on the mini-PC itself (`peer-vm/`, gateway mode, see its README). As always: back up first, check after each step, and test a real phone after the nftables and dnsmasq steps.

```bash
BK=/root/tapgw-backup-$(date +%Y%m%d-%H%M); sudo install -d -m 700 "$BK"
# 1) own Docker network for the peer stack
sudo docker network create -o com.docker.network.bridge.name=br-peer --subnet 10.43.0.0/24 --gateway 10.43.0.1 peer
# 2) nftables: br-sim -> br-peer only 443/tcp (Caddy) and 10000/udp (videobridge); see peer-vm/gateway/nftables-peer.patch.txt
sudo cp -a /etc/nftables.conf "$BK/"          # then add the PEER lines, check with: sudo nft -c -f /etc/nftables.conf
sudo systemctl restart nftables
# 3) dnsmasq: peer.sim -> 10.43.0.10
sudo cp -a /etc/dnsmasq.d "$BK/dnsmasq.d"
sudo install -m 644 /opt/can-my-network/peer-vm/gateway/dnsmasq-peer.conf /etc/dnsmasq.d/peer.conf
sudo /usr/share/dnsmasq/systemd-helper checkconfig && sudo systemctl restart dnsmasq
# 4) start the stack (pulls ~1 GB of Jitsi images once)
cd /opt/can-my-network/peer-vm && sudo ./setup.sh --gateway && sudo docker compose up -d --build
# 5) runner: the three lines printed by setup.sh into peer.env, then deploy
sudo install -m 600 /dev/null /opt/can-my-network/traffic-runner/peer.env   # then add the lines
sudo /opt/can-my-network/traffic-runner/scripts/deploy.sh
```

Checks after step 5:
- a 2-min `video_call` and `gaming_session` via `scripts/run-activity.sh`
- `sim/ready` pcaps contain `10.42.1.x ↔ 10.43.0.13` UDP 10000
- the feed shows SNI `peer.sim`
- `free -h` during a call
- the `tapcap@br-sim` drop counters stay 0

## 8. Known limitations

- **No WiFi layer.** Containers sit on a Linux bridge with static IPs. There is no 802.11, no DHCP and no association, so the feed has no `hostname` events for them. MACs are only visible on br-sim (as on eno1 for real devices).
- **No OS background traffic.** A container that is not running an activity is silent. `idle_connected` is therefore cleaner than a real idle phone, and the ingest filter for background traffic is not exercised by simulated devices.
- **Browser background traffic is switched off** (since 23.10). Even on a blank page, Playwright's Chromium (a "Chrome for Testing" build with Google API keys) contacts six Google hosts on its own. Five of them count as `google.com` = PRODUCTIVITY (C2_F6). Measured in the net-log, per 90 s:

  | Host | Source | Now |
  |---|---|---|
  | `android.clients.google.com`, `mtalk.google.com` | push channel (GCM) | `--host-resolver-rules` → `~NOTFOUND`, no DNS query leaves the container |
  | `update.googleapis.com` | component updater | same |
  | `www.google.com` (`/`, `/async/folae`) | built-in search integration | policy `DefaultSearchProviderEnabled=false` |
  | `clients2.google.com/time` | network time | policy `BrowserNetworkTimeQueriesEnabled=false` |
  | `accounts.google.com/ListAccounts` | sign-in check, **once per browser start** | remains; no switch found (`BrowserSignin=0` does not stop it) |

  The policies are in `config/chromium-policy.json`. The Dockerfile installs them in `/etc/opt/chrome_for_testing/policies/managed/`, the only folder this build reads. Pages still reach `www.google.com` and `accounts.google.com` normally (e.g. reCAPTCHA, Google login), because neither host is blocked. To keep the remaining start-up request rare, `repeat_visit_loop` opens a new browser *context* per revisit instead of a new browser. A new context has its own DNS cache, so every visit still triggers a fresh lookup.
- **Only Chromium.**
  - The runner uses the full Chromium build in new headless mode (`channel="chromium"`). The stripped headless shell is rejected outright by digitec, galaxus and zalando (`ERR_HTTP2_PROTOCOL_ERROR`, timeout).
  - Nothing hides automation: `navigator.webdriver` stays `true`. Reddit answers with a JavaScript challenge before the page. The browser passes it on its own, the URL then carries `js_challenge=1`, and the traffic includes the challenge round trip. CAPTCHAs are never solved; a site that shows one is simply logged as visited.
  - The phone role is an Android user agent on Chromium (an iPhone UA would contradict the Chrome TLS fingerprint).
  - The Playwright 1.63 Chromium decodes H.264/AAC. This was checked in the arm64 image (laptop) and in the amd64 image on the gateway on 2026-10-16.
- **Streaming hosts:** media segments come from CDNs in no thesis list: YouTube from `googlevideo.com` (listed together with youtube.com in the catalog), SRF from `*.akamaized.net`, and the SRF radio pages from `*.akamaized.net` (the MP3 fallback from `srg-ssr.ch`). With the 5-min DNS map (catalog §5.1), long streams lose their STREAMING label anyway.
- **SRF live TV is not used.** Its player exposes no quality levels, so it would run at 540p (about 1.5–2 Mbit/s). `video_stream` plays SRF on-demand videos.
- **YouTube quality is best effort.** The quality API is unofficial. The first seconds sometimes run at 240p before 144p takes effect, and the decoded resolution is logged. Ads play as for any user without a login.
- **Fresh context every run.** Each block sees and rejects the cookie banner again. That is realistic for a clean device, but more consent traffic than a regular user generates.
- **Muted microphone = Opus DTX.** Jitsi's default keeps sending 50 silence packets/s after muting, about 20 kbit/s on the wire. Both call URLs enable Opus DTX (`config.audioQuality.enableOpusDtx`), so a muted mic sends ~5 packets/s, like Zoom or Teams when muted. Without this, `--mic-share` would barely lower the upstream.
- **Calls and gaming run against our own VM.**
  - Every call platform (Zoom, Teams, Jitsi, Discord voice) is the self-hosted Jitsi on the peer VM, because the real platforms need accounts. Their hosts are in no thesis list, like jit.si and zoom.us; only teams.microsoft.com would have counted as PRODUCTIVITY.
  - The game is a toy WebSocket game with the traffic pattern of browser games (small, frequent, symmetric). It is not a real game title.
- **Login content.** Login categories are skipped, and the stubs listed in section 3 apply. `work_block` and `study_block` are login-free approximations: public pages of PRODUCTIVITY domains instead of a mailbox, calendar or LMS, and no document editing. `social_passive` opens "videos" by following an internal link of the feed; without login it cannot tell video posts from other posts.
- **Live pages change.** The sequence of start URLs and choices is reproducible. Link targets depend on the page content at that moment.
- **Redirects.** `domains` shows real hosts: `notion.so` → `www.notion.com` and `office.com` → `www.microsoft365.com`, both outside the thesis PRODUCTIVITY list.
- **Containers run as root** (Playwright image default; Chromium without its own sandbox). They are isolated on br-sim and can only reach DNS and the internet.

## 8a. Test accounts (messaging, social_post)

Decided 23.10: email only, no phone numbers.

**The accounts.** One project mailbox `cmnthif@gmail.com` with plus addresses (`cmnthif+<tag>@gmail.com`). The tags are in `config/accounts.yaml`.

| Platform | Account | Used by |
|---|---|---|
| **Slack** | own workspace "CMNTHIF Test": Admin plus members Student, Maria, Ben, Carl, and the official app "CMNTHIF Partner" (reply bot) | `messaging` |
| **Discord** (since 25.10) | private server "CMNTHIF" with one channel `#uploads` and one webhook; no user account in the runner | `social_post` |
| ~~Reddit~~ (until 25.10) | shared account u/CMNTHIF, private subreddit r/CMNTHIF. Reddit flagged the account as automated on 25.10 (see "Why not Reddit" below) | – |

Passwords and 2FA codes live only in the team's password manager. The runner works with **sessions**:
- Each session is the login state of one device, captured once by hand. It holds cookies and local storage, never a password.
- **Location:** `traffic-runner/sessions/<device>.<platform>.json` (+ `.meta.json`) on the gateway, root-only, not in git, mounted read-only into the containers.
- Each block still starts in a fresh browser context; only the login comes from the file.

**Capture a session on the laptop.** Playwright 1.63.0 is needed once:

```bash
python3 -m venv traffic-runner/.venv-capture
traffic-runner/.venv-capture/bin/pip install playwright==1.63.0 PyYAML==6.0.3
traffic-runner/.venv-capture/bin/playwright install chromium
traffic-runner/.venv-capture/bin/python traffic-runner/scripts/capture_session.py --device mdd_suicidality_a_phone --platform slack
```

The script opens your normal Google Chrome with a temporary, empty profile. Slack's sign-in check rejects browsers started by Playwright (plain "Error" after the robot check), so the login happens in a plain Chrome window.
- You log in by hand. For Slack, use the persona's plus address and the email code, then open the DM with "CMNTHIF Partner" (the URL must contain `/D…`; channels are `/C…`).
- When you press Enter, the script connects to the window over localhost, saves the session and deletes the temporary profile. If the wrong tab is open, it tells you and waits again.
- Slack blocks email sign-ins for a while after too many attempts ("Try again in a few minutes"). Wait about an hour without retrying; every new try can restart the block.

**Live-tested 23.10 on the gateway** (Reddit, history): both activities log `ok`. On phones, Reddit ignores `?type=IMAGE` (the runner attaches the image through the toolbar's image button) and goes to `/r/CMNTHIF/` after posting, which counts as success. The bot needs the Slack event `message.im` (Event Subscriptions) and the scopes `im:history` and `chat:write`.

A session captured in desktop Chrome works in the runner's headless browser (checked 23.10: the Slack DM with its message box, the Reddit submit page logged in on the Pixel 7 profile).

**Which sessions are needed:**

| Activity | Devices | Sessions |
|---|---|---|
| `messaging` | the phones of all 4 datasets | **since 23.10 one shared Slack login (member Student), copied to all four phones.** Separate logins per persona were blocked by Slack's sign-in limit ("too many attempts to submit an email address") on two networks. Which member sends is not visible in the encrypted traffic. A persona's own session can replace the copy at any time (same file name, no redeploy) |
| `social_post` | the phones of student, Maria, Carl (the 9-to-5/insomnia profiles do not post) | **no session since 25.10**: one Discord webhook for all phones (below) |

**Copy to the gateway**, from the laptop:

```bash
scp traffic-runner/sessions/*.json kathy@172.20.10.10:/tmp/
ssh kathy@172.20.10.10 'sudo install -d -m 700 /opt/can-my-network/traffic-runner/sessions && sudo install -m 600 /tmp/*_phone.*.json /opt/can-my-network/traffic-runner/sessions/ && rm /tmp/*_phone.*.json'
```

Delete the laptop copies afterwards, or keep them only in the git-ignored `sessions/` folder.

**Bot tokens** go into the peer stack's `.env` on the gateway, typed in without echo:

```bash
read -rsp "Slack app token (xapp-…): " A; echo; read -rsp "Slack bot token (xoxb-…): " B; echo
printf 'SLACK_APP_TOKEN=%s\nSLACK_BOT_TOKEN=%s\n' "$A" "$B" | sudo tee -a /opt/can-my-network/peer-vm/.env > /dev/null; unset A B
cd /opt/can-my-network/peer-vm && sudo docker compose up -d --build slackbot && sudo docker compose logs --tail 3 slackbot
```

**Expiry and revoking:**
- A session that expired or was signed out makes the run fail with "session expired: capture it again".
- To revoke all sessions: Slack admin → member → sign out of all sessions; Discord → server settings → Integrations → Webhooks → delete the webhook (a new one has a new ID: update `accounts.yaml`).

**At the end of the project:** delete the Slack workspace, the app, the Discord server, the Reddit account and subreddit, and the sessions and webhook file on the gateway.

### Discord webhook for `social_post` (since 25.10)

**Why not Reddit.** On 25.10 Reddit showed the shared account "We detected automated activity on your account": confirm a human, or register the account as an app within 6 days to keep posting. The post button was covered, so `social_post` failed (`logs/debug/reddit-post-20261025-182521.png`). Reddit's [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy) says automated accounts must register as apps and must not circumvent the label, and API access needs an explicit approval (no self-service since 11.2025). Confirming "human" would be untrue for this account; an API approval was not realistic within the 6 days. Discord webhooks are Discord's own mechanism for automated posts (no bot user, no approval), and `discord.com` is in the thesis SOCIAL list, so the upload counts for the same social-upload metrics (C2_F7/C7_F7). The Reddit account is registered as an app (label only); `social_passive` still reads Reddit without login.

**How it works** (`runner/discord.py`): the device container posts the image with `?wait=true` as `multipart/form-data` (stdlib only), `allowed_mentions` empty. The webhook URL must carry `discord.webhook_id`, Discord's reply must name `discord.channel_id` and contain the attachment with the exact size; anything else is an `error`, nothing is posted elsewhere. One retry after a rate limit of ≤ 10 s. Afterwards the browser opens the attachment on `cdn.discordapp.com` and stays 20–60 s, like looking at the post. Tests: `tests/test_discord.py` (URL checks incl. lookalike hosts, webhook file, multipart parsed like a server, rate limit, errors), `tests/test_accounts.py`, `tests/test_cli.py`. A probe against a non-existent webhook on 25.10 got Discord's normal `404 Unknown Webhook` JSON (no Cloudflare block of the user agent).

**Set up once:**
1. In Discord (desktop or web): create a server "CMNTHIF" (private, nobody else invited) with a text channel `#uploads`.
2. Channel settings → Integrations → Webhooks → New Webhook ("CMNTHIF social_post") → Copy Webhook URL.
3. IDs: the webhook ID is the number in the URL (`…/webhooks/<id>/<token>`). Channel ID: Discord settings → Advanced → Developer Mode on, then right-click `#uploads` → Copy Channel ID. Put both into `config/accounts.yaml` (`discord.webhook_id`, `discord.channel_id`; not secret), commit, push.
4. On the gateway, store the URL without echo (it contains the token):

```bash
read -rsp "Discord webhook URL: " U; echo
printf '%s\n' "$U" | sudo install -m 600 /dev/stdin /opt/can-my-network/traffic-runner/sessions/discord.webhook; unset U
sudo git -C /opt/can-my-network pull && cd /opt/can-my-network/traffic-runner && sudo docker compose build && sudo docker compose up -d
sudo scripts/run-activity.sh mdd_suicidality_a_phone --activity social_post --duration 2m --seed 1 --profile test --block-id discord-test1
```

The test post must appear in `#uploads`, and the last line of `logs/ground_truth.csv` must read `…,social_post,discord.com;cdn.discordapp.com,test,1,discord-test1,ok`.

**Done 25.10:** server, channel and webhook created, IDs checked against Discord (GET on the webhook), URL stored from the clipboard with `pbpaste | ssh … 'sudo sh -c "umask 077; cat > …/sessions/discord.webhook"'` (on macOS zsh, `read -p` is not a prompt, and `sudo install /dev/stdin` writes an empty file under sudo-rs). Test post at 20:58 `ok`, 1.43 MB upstream to `discord.com` in the capture.

## 9. Open points

State 2026-10-16. The same list is in `process/process.md` (week 5).

**Ingest (tapingest, see `process/Deployment.md`)**
1. **Watch the sim folder (done 23.10).** `tapingest` also watches `/var/lib/tapcap/sim/ready` (Deployment.md §7.6).
2. **One devices.csv (done 23.10).** The ingest reads this runner's `config/devices.csv` from the clone; `/etc/tapingest/devices.csv` is no longer used (Deployment.md §7.6). Both sides accept `#` comment lines.
3. **Retention (done 23.10).** The age `2d` on `/var/lib/tapcap/ready` was removed from `/etc/tmpfiles.d/tapcap.conf`, so raw pcaps are kept. Backup: `/root/tapgw-backup-20261023/`.
4. **Dataset names (done 23.10).** Convention `gw_<profile>_<letter>` / `<profile>_<letter>_<role>` (catalog §1). The devices are renamed (`student_a_phone`, `student_a_laptop` → `gw_student_a`), and the validator rejects dataset names that do not start with `gw_`, end with a digit or contain `onu`/`bras`. Data ingested before the rename (acceptance runs, pilot) stays under `gw_student_01`.

**Runner**

5. **Chromium background traffic (done 23.10).** See section 8, "Browser background traffic". One start-up request to `accounts.google.com` per browser start remains. The same hosts also come from real Chrome browsers and Android phones, where an ingest filter would be the place to handle them.
6. **Cookie consent (decided 23.10).** Never accept; reject or leave the banner open (catalog §1).
7. **Gateway location (done 23.10).** The runner runs from the git clone `/opt/can-my-network/traffic-runner`; `logs/ground_truth.csv` was carried over, and `~/traffic-runner` is kept as a backup. Updates: `sudo traffic-runner/scripts/deploy.sh` (section 7, "Updates"). Since 23.10, config is baked into the image instead of mounted, so a pull without a deploy no longer mixes new config with old code (Thierry's note).
8. **YouTube quality on the laptop role.** On the gateway the laptop again played 240p in the first 2 minutes (the 144p preference applied only on the phone role). Check over a longer run whether it drops to 144p, otherwise force the quality via the player menu.

**Activity catalog**

9. **Catalog fixes (done 23.10).** Several fixes:
   - `phone_check` fills its duration unless `pages` is set (§2).
   - `status` is part of the log format (§1).
   - `music_background` uses the SRF radio pages (§3 `audio`).
   - The `work`/`study` sets avoid notion.so and office.com, which now redirect to domains outside the thesis lists (§3).
