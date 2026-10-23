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
| Container lifecycle | Containers idle with `sleep infinity`. A run is `scripts/run-activity.sh <device> ...` (a `docker compose exec` with stdin detached, see section 3). Each run starts a **new browser process with a fresh context**, so no DNS, HTTP or cookie state carries over between blocks (catalog §5.2). |
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
python3 -m runner run --device student01_phone --activity browse --duration 10m \
    --mix news,shopping --seed 42 --profile student --block-id b001 --dry-run
```

`--dry-run` replaces the browser with the fake driver and prints the planned sequence (pages, dwell, links). Nothing is loaded and nothing is logged.

A real run on a laptop (default Docker network, no fixed IP, traffic is **not** recorded):

```bash
docker build -t traffic-runner:0.1.0 .
docker run --rm --shm-size 1g -v "$PWD/logs:/logs" traffic-runner:0.1.0 \
    python3 -m runner run --device student01_laptop --activity phone_check --duration 2m \
    --mix news --seed 42 --profile test --block-id local001
docker run --rm traffic-runner:0.1.0 python3 -m pytest -q
```

## 3. Running activities

```bash
sudo scripts/run-activity.sh student01_phone \
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
| `phone_check` | ok | 1–3 pages from the mix, 20–90 s dwell each, scrolling. Ends when the pages are done or the duration is over. | 1–5 min |
| `browse` | ok | Page from the mix, 30–180 s dwell, scrolling, then 1–2 same-site links per page, each with its own dwell. Fills the block. | as block |
| `repeat_visit_loop` | ok | Picks 2–3 fixed pages, revisits one every 1–3 min. A **new browser process** per visit forces a fresh DNS query. | 10–30 min |
| `video_stream` | ok | Picks a playable `streaming` site with the RNG and plays at the **lowest quality**. The decoded resolution is logged to stderr. Runs to the end of the video or the block. **YouTube:** search for a term from `mixes.yaml`, play one of the first 5 results; 144p preference plus `setPlaybackQualityRange('tiny')`, re-applied every check. **SRF:** one of the first 5 on-demand videos on the Play SRF page, lowest video.js quality level (270p in the tests). | 30–120 min |
| `music_background` | ok | Plays the SRF 3 MP3 livestream (`mixes.yaml` → `audio.streams`) | as block |
| `idle_connected` | ok | No browser, only waits | as block |
| `messaging`, `social_post`, `video_call`, `voice_call` | stub | Writes `not_implemented` (needs test accounts or a call counterpart) | |
| `social_passive`, `work_block`, `study_block`, `gaming_session`, `crisis_resource_visit`, `sh_adjacent_lookup`, `away` | stub | Catalog only, writes `not_implemented` | |

**Mixes:**
- Sites with `login: true` are skipped, and their weight goes to the remaining categories (a warning names them).
- A mix that consists only of login categories (e.g. `messaging`) logs `not_implemented`.

**Cookie banners:** the runner never accepts. After each page load it polls up to 5 s for a reject button (`consent.reject_buttons`). If the first level only offers accept/settings, it opens a clearly named settings button (`consent.settings_buttons`, e.g. "Individuell verwalten") and rejects there ("Nur Notwendige", "Alle Anbieter ablehnen", ...). Tested on 2026-10-16:

| Result | Sites |
|---|---|
| Rejected | YouTube (desktop + mobile), SRF Play, NZZ, Tages-Anzeiger, Zalando, DuckDuckGo, Reddit, TikTok (mobile) |
| Banner stays open, page loads without consent | 20min, watson, Migros, Galaxus (only "Akzeptieren" plus a generic "Einstellungen") |

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
2026-10-16T18:02:11+02:00,2026-10-16T18:04:11+02:00,student01_phone,phone_check,www.20min.ch;www.reddit.com,student,42,b001,ok
```

| Column | Content |
|---|---|
| `start`, `end` | ISO-8601 with offset, Europe/Zurich. `end` is the real end, which can be earlier than start + duration (e.g. `phone_check` done, video over). |
| `domains` | Hosts of the main documents actually loaded, after redirects, in first-visit order, separated by `;`. For `music_background` it is the stream host. Third-party hosts (CDN, ads) are not listed. |
| `status` | `ok` = at least one page or stream loaded; `error` = exception, nothing loaded, SIGTERM/Ctrl-C or watchdog (duration + 90 s); `not_implemented` = stub or no usable site in the mix |

Every run that gets past argument checking writes a row, including on error or interrupt. The exception is a container stopped mid-run (`docker compose down`), which kills the exec'd process with SIGKILL.

## 5. devices.csv and adding a device

```csv
device,role,mac,ip,dataset
student01_phone,phone,02:00:0a:2a:01:0b,10.42.1.11,gw_student_01
student01_laptop,laptop,02:00:0a:2a:01:0c,10.42.1.12,gw_student_01
```

The file is the **interface with the ingest service**, which maps packets to a dataset by IP. On the gateway the ingest reads its own copy, `/etc/tapingest/devices.csv` (section 9, item 2). Do not change the format without agreeing on it first.

| Column | Rule (checked by `python -m runner validate` and `gen_compose.py`) |
|---|---|
| `device` | Unique, `[a-z0-9_]+`. Also used as the service and container name. |
| `role` | `phone` (Pixel 7 emulation: Android UA, mobile viewport, touch) or `laptop` (Desktop Chrome) |
| `mac` | Unique, lower-case, locally administered unicast (`02:…`) |
| `ip` | Unique, 10.42.1.10–10.42.1.254 |
| `dataset` | The simulated person; phone and laptop of one person share it |

To add a device:
1. Add a row to `config/devices.csv`.
2. Run `python3 scripts/gen_compose.py` (validates the file and regenerates `docker-compose.yml`).
3. Run `sudo docker compose up -d`.

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
| `music_background` (128 kbit/s MP3) | 2 MiB | 0.1 MiB | 2 MiB / 0.2 MiB | ≈ 1 MiB/min, steady |
| `idle_connected` | 0 | 0 | 0 / 0 | |

On the gateway (br-sim counters), `phone_check` and `browse` in parallel for 2 min transferred 25 MiB down and 1 MiB up.

Rough budget for full-length blocks:
- `music_background`: ≈ 60 MiB/h
- YouTube at 144p: ≈ 1–2 MiB/min after the page load
- Browsing: about 5–15 MiB per page view, much of it ads

A 14-day profile with several browsing blocks per day therefore reaches several GB. Check this against the hotspot plan before running profiles in real time.

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
sudo docker compose exec -T student01_phone python3 -m pytest -q < /dev/null
# H.264/AAC support of the amd64 Chromium (expect true true; SRF needs it):
sudo docker compose exec -T student01_phone python3 -c "from playwright.sync_api import sync_playwright as s; p = s().start(); b = p.chromium.launch(channel='chromium'); pg = b.new_page(); print([pg.evaluate('t => MediaSource.isTypeSupported(t)', t) for t in ('video/mp4; codecs=\"avc1.42E01E\"', 'audio/mp4; codecs=\"mp4a.40.2\"')]); b.close(); p.stop()" < /dev/null
```

### Step 7: acceptance

```bash
cd ~/traffic-runner
sudo scripts/run-activity.sh student01_phone  --activity phone_check --duration 2m --mix news,social_passive --seed 42 --profile student --block-id t001 &
sudo scripts/run-activity.sh student01_laptop --activity browse --duration 2m --mix news,shopping --seed 42 --profile student --block-id t002 &
wait
sudo grep -E '"src":"10\.42\.1\.1[12]"' /var/lib/tapcap/meta/feed.ndjson | tail -20
sudo bash -c 'tcpdump -nn -r "$(ls -t /var/lib/tapcap/sim/ready/*.pcap | head -1)" host 10.42.1.11 | head'
cat logs/ground_truth.csv
```

Then run each MVP activity for 2 minutes (`repeat_visit_loop`, `video_stream`, `music_background`, `idle_connected`), measure the data volume (section 6), and check a real phone on the AP throughout.

## 8. Known limitations

- **No WiFi layer.** Containers sit on a Linux bridge with static IPs. There is no 802.11, no DHCP and no association, so the feed has no `hostname` events for them. MACs are only visible on br-sim (as on eno1 for real devices).
- **No OS background traffic.** A container that is not running an activity is silent. `idle_connected` is therefore cleaner than a real idle phone, and the ingest filter for background traffic is not exercised by simulated devices.
- **Only Chromium.**
  - The runner uses the full Chromium build in new headless mode (`channel="chromium"`). The stripped headless shell is rejected outright by digitec, galaxus and zalando (`ERR_HTTP2_PROTOCOL_ERROR`, timeout).
  - Nothing hides automation: `navigator.webdriver` stays `true`. Reddit answers with a JavaScript challenge before the page. The browser passes it on its own, the URL then carries `js_challenge=1`, and the traffic includes the challenge round trip. CAPTCHAs are never solved; a site that shows one is simply logged as visited.
  - The phone role is an Android user agent on Chromium (an iPhone UA would contradict the Chrome TLS fingerprint).
  - The Playwright 1.63 Chromium decodes H.264/AAC. This was checked in the arm64 image (laptop) and in the amd64 image on the gateway on 2026-10-16.
- **Streaming hosts:** media segments come from CDNs in no thesis list: YouTube from `googlevideo.com` (listed together with youtube.com in the catalog), SRF from `*.akamaized.net`, and the MP3 radio from `stream.srg-ssr.ch` → `srg-ssr.ch`. With the 5-min DNS map (catalog §5.1), long streams lose their STREAMING label anyway.
- **SRF live TV is not used.** Its player exposes no quality levels, so it would run at 540p (about 1.5–2 Mbit/s). `video_stream` plays SRF on-demand videos.
- **YouTube quality is best effort.** The quality API is unofficial. The first seconds sometimes run at 240p before 144p takes effect, and the decoded resolution is logged. Ads play as for any user without a login.
- **Fresh context every run.** Each block sees and rejects the cookie banner again. That is realistic for a clean device, but more consent traffic than a regular user generates.
- **Login content.** Login categories are skipped, and the stubs listed in section 3 apply.
- **Live pages change.** The sequence of start URLs and choices is reproducible. Link targets depend on the page content at that moment.
- **Redirects.** `domains` shows real hosts: `notion.so` → `www.notion.com` and `office.com` → `www.microsoft365.com`, both outside the thesis PRODUCTIVITY list.
- **Containers run as root** (Playwright image default; Chromium without its own sandbox). They are isolated on br-sim and can only reach DNS and the internet.

## 9. Open points

State 2026-10-16. The same list is in `process/process.md` (week 5).

**Ingest (tapingest, see `process/Deployment.md`)**
1. ~~**Watch the sim folder.**~~ Done 23.10 (Deployment.md §7.6). br-sim pcaps are in `/var/lib/tapcap/sim/ready/`. `tapingest` still watches only `/var/lib/tapcap/ready`, so the simulated devices do not reach the Parquet data yet. Add `--watch /var/lib/tapcap/sim/ready` (Deployment.md §8).
2. ~~**One devices.csv.**~~ Done 23.10: the ingest reads `config/devices.csv` from the clone (Deployment.md §7.6). The ingest reads `/etc/tapingest/devices.csv` (currently 4 example devices), the runner reads `config/devices.csv` (2 devices). Both must list the same devices.
   - Either generate the compose file from the ingest file, or copy it into `config/`.
   - The ingest format allows `#` comment lines. The runner's validator rejects them so far.
3. **Retention.** `/etc/tmpfiles.d/tapcap.conf` has age `2d` on `ready/`, so `systemd-tmpfiles-clean` deletes pcaps older than 2 days (only 170 files remained from 2 Oct on). This contradicts "nothing is deleted automatically" in HardwareSetup and Deployment. The sim folder has no age.
4. **Dataset names.** The app's `group_prefix()` strips trailing digits, so `gw_student_01` and `gw_student_02` are grouped as `gw_student` in the UI (MasterThesisInc §3 recommends names without trailing digits). The `devices.csv` format stays as it is, but the naming convention should be agreed.

**Runner**

5. **Chromium background traffic counts as PRODUCTIVITY.** Both containers open TLS connections to `android.clients.google.com`. The pipeline reduces this to `google.com`, which is in the PRODUCTIVITY list (C2_F6). Suppress it in the runner with launch flags before profiles run, or drop these hosts in the ingest.
6. **Cookie consent.** The runner rejects banners, or leaves them open where there is no reject button. Decide whether the simulated users should accept instead: that is closer to typical users and produces more third-party traffic, and therefore more UniqueSLD (catalog §5.7).
7. ~~**Gateway location.**~~ Done 23.10: the runner runs from `/opt/can-my-network/traffic-runner`, `logs/ground_truth.csv` carried over. `~/traffic-runner` is kept as a backup. The runner currently runs from a copy in `~/traffic-runner`. Since PR #1 is merged, it is also in the git clone `/opt/can-my-network/traffic-runner`. Switch to the clone so that updates are a `git pull`: `docker compose down` in the old folder, then `up -d` in the new one. Carry `logs/ground_truth.csv` over.
8. **YouTube quality on the laptop role.** On the gateway the laptop again played 240p in the first 2 minutes (the 144p preference applied only on the phone role). Check over a longer run whether it drops to 144p, otherwise force the quality via the player menu.

**Activity catalog**

9. **§2 `phone_check`.** 1–3 pages × ≤ 90 s is at most 4.5 min, but `student.md` schedules `wake_check` with `phone_check` for 5–15 min. The runner ends early and logs the real end. Proposal: add `pages` to such blocks, or allow more pages in the catalog.
10. **§1 log format.** `status` is new and should be added to the catalog.
11. **§3 audio source.** Add a login-free audio source for `music_background`, and decide whether `srg-ssr.ch` should count as STREAMING. An alternative is the srf.ch radio page (`/audio/radio-srf-3-live-hoeren`): it autoplays 192 kbit/s AAC from `*.akamaized.net` after a srf.ch page load.
