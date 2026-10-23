# Project Process Log: Can My Network Tell How I Feel?

**Team:** Karla Ruggaber, Thierry Suhner
**Supervisor:** Dr. Bruno Rodrigues
**Period:** 14.09.2026 – 15.01.2027
**Weekly supervisor meeting:** every Friday

## Key Dates

| Date       | Milestone                  |
|------------|----------------------------|
| 07.10.2026 | Zwischenpräsentation       |
| 02.12.2026 | Abgabe des Videos          |
| 06.12.2026 | Abgabe Präsentationsfolien |
| 08.12.2026 | Abschlusspräsentation      |
| 15.01.2027 | Projektdokumentation       |

---

<details>
<summary><b>Week 1</b> (14.09 – 20.09)</summary>

**Kick-off meeting:** Mo 14.09
- **Done:** Introduction to the project, scope
- **Next / open:** Handover of hardware
- **Blockers / notes:**

**Hardware-Handover:** Di 15.09
- all of the hardware is stored at the CS-Building

</details>

<details>
<summary><b>Week 2</b> (21.09 – 27.09)</summary>

**Call with Lukasz (Psychology Expert):** Thu 24.09
- Lukasz will be kept in the loop
- He will give iterative feedback on profiles and our work in general

**Supervisor meeting:** Fri 25.09
- **Done:** recap on meeting with Lukasz
- **Next / open:** start on thinking about profiles
- **Blockers / notes:**

</details>

<details open>
<summary><b>Week 3</b> (28.09 – 04.10)</summary>

**Supervisor meeting:** Fri 02.10
- **Done:** discussed outline for presentation / hardware setup
- **Next / open:** set up hardware, make presentation
- **Blockers / notes:**

What we did today: we worked the entire day on the hardware setup. The entire process is documented in the file process/HardwareSetup.md.

</details>

<details>
<summary><b>Week 4</b> (05.10 – 11.10) 🎯 Wed 07.10: Zwischenpräsentation</summary>

**Supervisor meeting:** Fri 09.10
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 5</b> (12.10 – 18.10)</summary>

**Supervisor meeting:** Fri 16.10
- **Done:**
- **Next / open:**
- **Blockers / notes:**

**Live ingest and app deployment:** Fri 16.10
- **Done:**
  - Live ingest service `tapingest`: every 60 s capture from tapcap is converted into the app's 5-min Parquet partitions within ~10 s, assigned per IP via `devices.csv` (one dataset = one person). Runs as a systemd service on the gateway.
  - Thesis app adapted: shared PCAP parser (upload and ingest give identical rows); pages 01/02 now pick up data that grows while the app runs.
  - Docker installed on the gateway with `"iptables": false` (firewall verified unchanged). The app runs in a container on localhost only, reachable via SSH tunnel.
  - Approach for traffic generation decided: one scheduler (profile + seed → ground-truth plan), executed live by runner containers on a separate `br-sim` network, later synthetically by stitching recorded activity snippets into PCAPs.
  - Runner container (Karla) and scheduler started as parallel work items.
  - Background filter in the ingest (MasterThesisInc §3): AP/controller traffic, broadcasts, mDNS/SSDP/NTP and gateway services are dropped and counted per rule (~9 % of today's packets). Today's data rebuilt with it.
  - Thesis app imported into this repo (`app_pcap_to_dsm5/`, with permission; first commit unchanged, our changes on top). The gateway now runs a `git clone` of this repo, so updates are a `git pull`.
- **Next / open:**
  - Connect `br-sim` (second capture folder, shared `devices.csv`), first end-to-end pilot with one container
  - Remove temporary sudo rule and deploy key on the gateway; delete the old `/opt/app_pcap_to_dsm5_public` after a few days
  - Validation on real data (MasterThesisInc §8, steps 3–6)
- **Blockers / notes:** Full documentation: [Deployment.md](Deployment.md). Origin and licence note of the imported app: [`app_pcap_to_dsm5/ORIGIN.md`](../app_pcap_to_dsm5/ORIGIN.md).

**Traffic runner and br-sim network:** Fri 16.10
- **Done:**
  - **`traffic-runner/` (merged in PR #1)**
    - Docker image based on the official Playwright Python image 1.63.0, all versions pinned.
    - CLI that runs one activity from the activity catalog as a simulated phone or laptop with a fixed MAC/IP. It writes one ground-truth row per run (`start,end,device,activity_id,domains,profile,seed,block_id,status`) to a shared, file-locked CSV.
    - Randomness comes only from `seed` + `block_id`, so the same seed gives the same page sequence. A test checks this without network.
  - **Implemented activities:** `phone_check`, `browse`, `repeat_visit_loop`, `video_stream` (YouTube at 144p, SRF on-demand at its lowest level), `music_background` (SRF 3 MP3 stream) and `idle_connected`.
  - **Stubs:** the activities that need test accounts (`messaging`, `social_post`, calls) log `not_implemented`.
  - **Configuration:**
    - The domain sets of catalog §3 are in `config/mixes.yaml`.
    - `config/devices.csv` (same format as the ingest's `devices.csv`) is validated, and `docker-compose.yml` is generated from it.
  - **Local tests:** every activity ran for 2 min against real pages and wrote a correct log row; 96 offline tests pass. The measured data volume is in the runner README §6. A page view costs about 5–15 MiB, YouTube at 144p about 1–2 MiB/min.
  - **Fixes from the real runs:**
    - Chromium now runs in full new-headless mode; the stripped headless shell is blocked by digitec/galaxus/zalando.
    - Cookie banners are rejected in two steps and never accepted; SRF only starts its player after this choice.
    - Media that reports "playing" without data now counts as an error.
  - **Gateway, network part (with backups in `/root/tapgw-backup-20261016-1602/`):**
    - Docker network `sim` (bridge `br-sim`, 10.42.1.0/24).
    - nftables: DNS + ping from br-sim, forward br-sim → internet, no forwarding to eno1.
    - dnsmasq also serves DNS on 10.42.1.1.
  - **Gateway, capture part:**
    - `tapcap@br-sim` writes to its own folder `/var/lib/tapcap/sim/ready/`.
    - `tapfeed@br-sim` adds SNI only; DNS stays with tapfeed@eno1, so nothing is logged twice.
  - **Acceptance on the gateway:**
    - two containers ran in parallel, both `ok`
    - 181 SNI events from 10.42.1.11/.12 with the right MACs in `feed.ndjson`
    - 7k–11k packets per device and minute in the sim pcaps
    - a real phone kept internet access after every step
- **Next / open:**
  - **Ingest:**
    - Add `--watch /var/lib/tapcap/sim/ready` to `tapingest`, so the simulated devices actually reach the Parquet data.
    - Keep one `devices.csv` for runner and ingest. The runner does not accept `#` comment lines yet.
  - **Chromium background traffic:** Chromium connects to `android.clients.google.com`, which the pipeline counts as google.com = PRODUCTIVITY. Suppress it before running profiles; a follow-up session is proposed.
  - **Decide:** cookie consent (reject vs. accept), an audio source for `music_background` that is in the STREAMING list, and dataset names without trailing digits (`group_prefix()`).
  - **Gateway operation:**
    - Run the runner from the git clone in `/opt/can-my-network/traffic-runner` instead of the copy in `~/traffic-runner`, so updates are a `git pull`.
    - (done, 16.10 evening) The remaining activities were also run on the gateway, all `ok`:
      - `repeat_visit_loop`: 12 MiB
      - `music_background`: 2 MiB
      - YouTube video: 7 MiB, at 240p on the laptop role
      - `idle_connected`: 0
  - **Next milestone:** scheduler (profile + seed → plan) that calls `scripts/run-activity.sh`, then a first end-to-end pilot.
- **Blockers / notes:**
  - **Retention:** `/etc/tmpfiles.d/tapcap.conf` has age `2d` on `/var/lib/tapcap/ready`, so `systemd-tmpfiles-clean` deletes pcaps older than two days. This contradicts "nothing is deleted automatically" in HardwareSetup/Deployment. The sim folder has no age.
  - **Three problems on the gateway, all fixed:**
    - Ubuntu's `docker.io` pulled in `ubuntu-fan`, whose `bind-interfaces` clashed with `bind-dynamic` and stopped dnsmasq for about a minute (rolled back at once). Test dnsmasq with `systemd-helper checkconfig`, not plain `dnsmasq --test`.
    - `docker compose exec` reads the terminal and hung in pasted blocks; always use `< /dev/null` or `scripts/run-activity.sh`.
    - The terminal app on the laptop lacked the macOS "Local Network" permission ("No route to host").
  - **Documentation:**
    - [traffic-runner/README.md](../traffic-runner/README.md) (usage, gateway steps, data volume, limitations)
    - [HardwareSetup.md §15](HardwareSetup.md) (gateway changes)

</details>

<details>
<summary><b>Week 6</b> (19.10 – 25.10)</summary>

**Supervisor meeting:** Fri 23.10
- **Done:**
- **Next / open:**
- **Blockers / notes:**

**Runner integration and first end-to-end pilot:** Fri 23.10
- **Done:**
  - Runner moved into the git clone on the gateway; the ingest now watches the br-sim capture folder and reads the runner's `devices.csv` (one list for both).
  - First end-to-end pilot: `student01_phone` browsed www.nzz.ch for 5 min. Dataset `gw_student_01` appeared in the app; 99.9 % of its rows fall inside the ground-truth block, the visited site and its hosts are in the DNS data. Details: [Deployment.md](Deployment.md) §7.6.
- **Findings:**
  - 64 % of the pilot's rows have no domain: the app looks up hostnames by destination IP only, so inbound packets are never labelled (MasterThesisInc §5).
  - One news site produced 86 distinct DNS names (ads/tracking), so UniqueSLD (C2_F1) needs re-tuning for scripted days.
  - Chromium background requests (`android.clients.google.com`) count as `google.com` = PRODUCTIVITY.
- **Next / open:**
  - Fix the inbound hostname lookup (+ SNI as second source)
  - Suppress Chromium background traffic in the runner
  - Decide retention of raw pcaps (`ready/` keeps 2 days, `sim/ready/` forever)
  - Dataset naming convention (no trailing digits), real devices in the device map
  - Scheduler; night test with an idle phone; remove temporary access on the gateway

</details>

<details>
<summary><b>Week 7</b> (26.10 – 01.11)</summary>

**Supervisor meeting:** Fri 30.10
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 8</b> (02.11 – 08.11)</summary>

**Supervisor meeting:** Fri 06.11
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 9</b> (09.11 – 15.11)</summary>

**Supervisor meeting:** Fri 13.11
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 10</b> (16.11 – 22.11)</summary>

**Supervisor meeting:** Fri 20.11
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 11</b> (23.11 – 29.11)</summary>

**Supervisor meeting:** Fri 27.11
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 12</b> (30.11 – 06.12) 🎯 Wed 02.12: Abgabe des Videos · 🎯 Sun 06.12: Abgabe Präsentationsfolien</summary>

**Supervisor meeting:** Fri 04.12
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 13</b> (07.12 – 13.12) 🎯 Tue 08.12: Abschlusspräsentation</summary>

**Supervisor meeting:** Fri 11.12
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 14</b> (14.12 – 20.12)</summary>

**Supervisor meeting:** Fri 18.12
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 15</b> (21.12 – 27.12)</summary>

**Supervisor meeting:** Fri 25.12 (likely skipped: Christmas)
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 16</b> (28.12 – 03.01)</summary>

**Supervisor meeting:** Fri 01.01 (likely skipped: New Year)
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 17</b> (04.01 – 10.01)</summary>

**Supervisor meeting:** Fri 08.01
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 18</b> (11.01 – 17.01) 🎯 Fri 15.01: Projektdokumentation</summary>

**Supervisor meeting:** Fri 15.01
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>