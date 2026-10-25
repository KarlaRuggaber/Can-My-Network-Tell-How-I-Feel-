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
  - Fixed the same day: inbound packets now get the hostname of their source. Rows without a domain 63.8 % → 0.3 %; streaming detection works for the first time on gateway data (0 → 5 742 rows on the 16.10 YouTube run). Thesis datasets unchanged. Details: [Deployment.md](Deployment.md) §7.7.
- **Next / open:**
  - SNI as second hostname source only if devices without visible DNS are used (needs the server IP in `feed.ndjson`)
  - Suppress Chromium background traffic in the runner
  - ~~Decide retention of raw pcaps~~ → decided 23.10: keep all (entry below)
  - ~~Dataset naming convention~~ → decided 23.10 (entry below); real devices in the device map
  - Scheduler; night test with an idle phone; remove temporary access on the gateway

**Decisions and catalog fixes (traffic runner):** Fri 23.10
- **Done:**
  - **Raw pcaps are kept.** Removed the 2-day age on `/var/lib/tapcap/ready` from `/etc/tmpfiles.d/tapcap.conf` (backup in `/root/tapgw-backup-20261023/`).
  - **Cookie banners:** never accept; reject, or leave the banner open where there is no reject option. Fixed as a convention in catalog §1. The effect on the metrics is a constant offset for all profiles. Only UniqueSLD/packet counts change, not the SOCIAL/STREAMING/PRODUCTIVITY lists.
  - **Dataset names:** convention `gw_<profile>_<letter>` with devices `<profile>_<letter>_<role>` (catalog §1). Reason: the app groups datasets by stripping trailing digits, and the Early Signs page concatenates a selected group into one daily record. So `gw_student_01` and `gw_student_02` would have been merged into one person.
  - **Catalog fixes**, in `activity-catalog.md`:
    - `phone_check` fills its duration unless `pages` is set. Before, a 5–15 min `wake_check` ended after at most ~4.5 min.
    - `status` added to the log format.
    - `music_background` source: SRF radio live pages, which count as srf.ch = STREAMING.
    - `work`/`study` sets: `notion.so` and `office.com` now redirect to `notion.com` / `m365.cloud.microsoft`, which are in no thesis list. They were replaced by list domains that load without login (github, gitlab, trello, asana, todoist, microsoft.com).
  - **Runner updated to match:** new `phone_check` rule, radio page playback, cookie rejection now also covers 20min. 108 tests pass. Live check on the laptop: radio page plays, `work`/`study` pages load, a 3-min `phone_check` opened 6 pages.
  - **Five more activities implemented**, all login-free: `social_passive`, `work_block`, `study_block` (incl. PDF downloads), `crisis_resource_visit`, `sh_adjacent_lookup`. Only `gaming_session`, `away` (scheduler) and the account-based activities remain stubs. 163 tests pass. Each one was run live once on the laptop.
  - **Calls and gaming:** new `peer-vm/` for a cloud VM outside the home network.
    - Self-hosted Jitsi (no login; meet.jit.si needs one) behind Caddy with Let's Encrypt for `<ip>.sslip.io`.
    - A peer service whose headless Chromium (fake camera/mic) joins the runner's room on request (token, HMAC room names), and leaves when the runner is gone.
    - A toy WebSocket game (20–60 small messages/s each way).
    - Runner: `video_call`, `voice_call` and `gaming_session` implemented; 175 tests pass.
    - Tested locally end to end: a 2-min video call sent 13 MB up / 9 MB down through our videobridge (UDP 10000), and no foreign hosts during calls.
    - Found while testing: Jitsi joins **without** camera/mic if the prejoin page is switched off in the URL (safeguard). It is now switched off on the server.
    - **Decided: the counterpart runs on the mini-PC (gateway mode) instead of a cloud VM.**
      - Network: own Docker network `peer` (br-peer, 10.43.0.0/24), no published ports, reached through the gateway's routing (nftables: only 443/tcp and 10000/udp from br-sim), name `peer.sim` via dnsmasq.
      - Tested locally: media goes to the videobridge at 10.43.0.13:10000 in both directions.
      - **Applied on the gateway the same day (HardwareSetup §16):**
        - network `peer`, nftables PEER rules, dnsmasq `peer.sim`, stack in `/opt/can-my-network/peer-vm`, `peer.env`
        - one fix along the way: prosody needs its config folders owned by uid 1000
      - **Live test:**
        - video and voice call in parallel plus gaming, all `ok`
        - ~25 000 media packets/min to the videobridge in the `sim` pcaps
        - `peer.sim` in the feed
      - **RAM:** with two parallel calls, 1.3 GB of 7.1 GB was left, so watch it once more persons run in parallel.
    - **For Thierry:** the scheduler should pass `--lookups` (`sh_adjacent_lookup`). `--platform` is accepted but has no effect.
  - **Test accounts (email only, no phone numbers).** Project mailbox `cmnthif@gmail.com` with plus addresses per persona.
    - **Slack:** workspace "CMNTHIF Test" with members Student/Maria/Ben/Carl and the official reply bot "CMNTHIF Partner".
    - **Reddit:** shared account u/CMNTHIF with the private subreddit r/CMNTHIF.
    - **Runner:** `messaging` (Slack web, desktop profile because Slack refuses phone browsers) and `social_post` (generated 1–3 MB image, only into r/CMNTHIF, target checked before and after posting) are implemented and load per-device login sessions.
    - **Sessions** are captured by hand on the laptop (`scripts/capture_session.py`) and stored root-only on the gateway.
    - **Bot service:** `peer-vm/slackbot`, host network.
  - **Pilot feedback (Thierry, 23.10):** in Maria's YouTube block the video stalled after 2 min with four browsers on the hotspot. The runner logged `error`, and 29 minutes of the block stayed silent.
    - `video_stream` now recovers: reload the same video, then up to three other videos. The replacements are drawn with the seed up front.
    - 217 tests.
    - Deploy during the live run: stop the executors, run `deploy.sh`, start them again.
    - **Live on the gateway (23.10, `student_a_phone`):**
      - `messaging`: 4 messages in 3 min, `ok`; the bot answers.
      - `social_post`: noise image posted to r/CMNTHIF, `ok`.
    - **Fixes found while testing:**
      - Slack's sign-in rejects Playwright browsers, so logins are captured in plain Chrome.
      - Phone Reddit ignores `?type=IMAGE`, so the image is attached via the toolbar button.
      - After posting, phones land on `/r/CMNTHIF/` instead of the post.
      - The bot needed the `message.im` event.
    - **Still to do:**
      - ~~Slack sessions for Ben, Maria and Carl~~: Slack's sign-in limit also hit Thierry on another network, so all four phones share Student's Slack login (decided 23.10, like the shared Reddit account; invisible in the encrypted traffic).
      - ~~Full deploy~~: done 23.10 after the pilot (executors stopped, `deploy.sh`, executors started).
  - **Devices for the clinical personas** in `traffic-runner/config/devices.csv`. Datasets are named after the profiles (decided 23.10); the persona names appear only as comments:

    | Persona | Profile | Dataset | IPs |
    |---|---|---|---|
    | Ben | `insomnia-moderate` | `gw_insomnia_a` | 10.42.1.21/.22 |
    | Maria | `mdd-severe-suicidality` | `gw_mdd_suicidality_a` | 10.42.1.31/.32 |
    | Carl | `social-anxiety-moderate` | `gw_social_anxiety_a` | 10.42.1.41/.42 |

    Checked: runner validator, ingest name rule, and the scheduler builds plans for all three.
  - **`--mic-share` for calls** (SAD profile: mic on only 10 % of the time). The call starts muted, then speaking turns of 3–15 s alternate with muted pauses drawn from the seed.
    - Two problems found while testing and fixed:
      - Jitsi keeps sending 50 silence packets/s after muting (fixed with Opus DTX, ~5 packets/s).
      - The peer left calls with a muted runner, because it judged presence by media (now judged by Jitsi's participant count).
    - Measured, voice call over 3 min:

      | Mic share | Upload | Packets up |
      |---|---|---|
      | 100 % | 55 kbit/s | 50/s |
      | 30 % | 25 kbit/s | 24/s |
      | 10 % | 5 kbit/s | 5/s |

    - Thierry can pass `--mic-share 0.1` from the plan.
  - **Deploy (after Thierry's note):** runner config is no longer mounted into the containers but baked into the image, so a `git pull` can no longer mix new config with old runner code. New `traffic-runner/scripts/deploy.sh` does pull, rebuild, recreate and tests in one step, and refuses while activities are running. Deployment.md §8 lists it.
  - **Finding:** `social_passive` on Reddit costs about 33 MiB/min because the feed auto-plays videos, so a 1–2 h block is 2–4 GB of hotspot volume. **Decided 23.10: accepted.** Real users get the same autoplay, and the data volume is not a problem.
- **Next / open:**
  - ~~Rename the devices~~ done 23.10: `student_a_phone`/`student_a_laptop` → `gw_student_a`; the validator enforces the convention.
  - ~~Deploy the new runner version~~ done 23.10. The ingest picked up the new device list without a restart, and a test run landed in `gw_student_a`.
  - ~~Suppress Chromium background traffic~~ done 23.10:
    - Push and updater hosts are blocked inside the browser.
    - Search integration and network time are switched off by a managed Chrome policy.
    - `repeat_visit_loop` uses a new context instead of a new browser.
    - Only one `accounts.google.com` request per browser start remains (runner README §8).
    - Real Chrome/Android devices send the same hosts; that is a case for the ingest filter.
  - ~~Scheduler~~ done 23.10 (entry below).
- **Blockers / notes:**
  - The SRF radio page offers no quality levels, so `music_background` streams 192 kbit/s (≈ 85 MiB/h).
  - The thesis lists do not know `notion.com` or `cloud.microsoft`, so real Notion/Office users would not count as productive. This is a limitation to mention in thesis-alignment.


**Scheduler, executor, push report and the run setup (Thierry):** Fri 23.10
- **Done:**
  - **Scheduler** (`scheduler/`, PRs #3–#5): profile + seed → ground-truth plan (one row per block, `block_id` traceable into the runner's log) and runner commands. YAML for all five profiles, clinical ones as patches on their tier-0 profile, `--baseline-days 14`. 430 tests. Details: [scheduler/README.md](../scheduler/README.md).
  - **Decisions:** warm-up on the Sunday before the window; day-to-day duration noise (±25 % student, ±15 % 9-to-5); calls placed first, work/study cut around them; fixed-start blocks may slip 30 min; MDD/SAD defaults (README §8), SAD home evenings split stream → gaming → social.
  - **Executor** (`python -m scheduler execute`): replays the commands live, never starts a block twice (state file), late blocks run with the remaining time. **Push report** (`python -m scheduler report`): daily at 08:00 and hourly on problems via ntfy; test push arrived.
  - **Run plans** for Ben (`gw_insomnia_a`, seed 1), Maria (`gw_mdd_suicidality_a`, seed 2) and Carl (`gw_social_anxiety_a`, seed 3): warm-up Sun 25.10, baseline 26.10–08.11, profile 09.11–22.11. On the gateway in `/var/lib/traffic-executor/`.
  - **Silent time:** with Karla's new activities only messaging and posting are stubs, 5 % / 3 % of the planned time (was 23 % / 11 %).
  - **Pilot** 16:00–17:00: the plans' busiest hour (two gaming sessions with voice chat, a stream, social, phone checks) on the six new devices. 12/12 blocks on time, 10 `ok`, 1 expected stub, 1 YouTube stall (`error`); data in all three datasets; memory 1.07–2.58 GB available, no OOM; CPU load up to 11. Pilot data moved aside. Details: [Deployment.md](Deployment.md) §7.8.
  - **Run switched on** at 17:04: three executors waiting for Sun 25.10, daily report 08:00 and hourly watch enabled; the first report arrived.
  - **Tailscale** (`can-my-network-gw`): SSH to the gateway from any network; only SSH is open on `tailscale0`. A real phone on the AP kept internet access.
- **Findings:**
  - **tapfeed kept a growing capture file in RAM** (`/tmp` is a tmpfs): 1.5 GB after 7 h on eno1, ~100 MB/min on br-sim during the pilot. Would have run the gateway out of memory in the first hour of the live run. Fixed the same day (PRs #6/#7): disk-backed `/tmp` per tapfeed instance plus an hourly tshark restart. The first install failed (`226/NAMESPACE`), so the feed was down for about one minute (16:09:40–16:10:30). Details: Deployment.md §7.8, HardwareSetup §17.
  - tshark's own memory also grows with traffic (410 MB after 30 min of the pilot). Decided: tshark restarts every 10 min (`TAPFEED_ROTATE=600`).
  - Capacity: with all three personas, 0–3 runs overlap most of the time, peaks of 7–8; CPU load reached 11 on 6 cores when the pilot's blocks started.
- **Next / open:**
  - Lukasz reviews the MDD profile before 09.11
  - Remove the temporary sudo rule after the setup
  - Runner (Karla): `video_stream` aborts the block when YouTube stalls; reload or pick another video instead
  - Synthesizer

**`social_post` moved from Reddit to Discord:** Sun 25.10
- **Done:**
  - Cause of the failed post at 18:24 (`gw_mdd_suicidality_a`): Reddit flagged the shared account u/CMNTHIF as automated ("confirm you're human, or register the account as an app within 6 days") and covered the post button. Not a gateway problem. Reddit's policy requires automated accounts to register as apps, and API access needs an approval without a timeline.
  - Decided: `social_post` posts through a webhook of a private Discord server (`discord.com` is in the thesis SOCIAL list, so the same social-upload metrics count it). The Reddit account gets registered as an app (label). Branch `social-post-discord`: `runner/discord.py`, ID and channel checks, browser opens the uploaded image afterwards, Reddit UI code removed; 226 runner tests pass; a probe against Discord got the normal `404 Unknown Webhook`. Details: traffic-runner README §8a.
  - Discord server "CMNTHIF" with `#uploads` and the webhook "CMNTHIF social_post" created; IDs in `accounts.yaml` (webhook `1563995536129007696`, channel `1563991267119988858`), checked against Discord. The webhook URL is in `traffic-runner/sessions/discord.webhook` on the gateway (mode 600, root), transferred from the clipboard without showing the token.
  - Catalog change decided by Thierry for the team (Karla was not available); she can still object in PR #12.
- **Next / open:**
  - Merge PR #12, deploy the runner between two blocks, test post
  - Delete the unused Reddit session files on the gateway (`*.reddit*.json`)

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