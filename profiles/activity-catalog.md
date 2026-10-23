# Activity Catalog (scripting reference)

Shared reference for turning profiles into scripted network traffic. Each profile's section 9 ("Script specification") schedules activities **by ID from this file**. Profiles never re-define how an activity is generated. If a profile needs a new activity, add it here first. See [ProfileStructure.md](ProfileStructure.md) for the schema and [symptom-network-mapping.md](symptom-network-mapping.md) for the symptom → feature side.

Goal of the scripted traffic (project objectives, [Notes.md](../Notes.md)): run daily routines on real devices through the gateway, record real traffic, and test whether the thesis pipeline (`app_pcap_to_dsm5`) recovers the scripted routine. **Only scripted behavior is recorded, using dedicated test accounts. No personal accounts or data.**

## 1. Scripting conventions

| Topic | Convention |
|---|---|
| Time zone | All profile times are **Europe/Zurich local time**. Run the ingest with `TZ=Europe/Zurich` (see [MasterThesisInc.md](../process/MasterThesisInc.md)). |
| Day boundary | The pipeline computes metrics per **calendar day (00:00–23:59)**. A night that crosses midnight is split across two days. Profile "nights" are labelled by the day they *start* on (night of Mon = Mon 22:00 → Tue 06:00). |
| Window | 14 consecutive days per profile instance, starting on a **Monday**, matching the thesis gate (M=14). Plus ≥1 warm-up day that is discarded (devices settle, caches fill). Clinical profiles: preceded by 14 days of their baseline on the same devices (recommended, see §6), because the thesis history metrics and the profiles' expected outputs assume it. |
| Devices | Each profile instance has its own **phone + laptop** with fixed MACs (iOS/Android "private Wi-Fi address" set to fixed) and fixed IPs. In `devices.csv` both devices map to **one** dataset, e.g. `gw_student_a`, because the pipeline treats one dataset as one person. |
| Dataset and device names | Dataset `gw_<profile>_<letter>` (`gw_student_a`, `gw_student_b`, `gw_insomnia_a`), devices `<profile>_<letter>_<role>` (`student_a_phone`, `student_a_laptop`). Only `[a-z0-9_]`. A dataset name must **not end with a digit** and must **not contain `onu` or `bras`**. Reason: the app groups datasets by stripping trailing digits (`group_prefix()`), so `gw_student_01` and `gw_student_02` would form one group, and the Early Signs page then concatenates a selected group into **one** daily record, i.e. two people become one. `onu`/`bras` would classify the dataset as ONU/BRAS instead of "Other". Baseline and clinical phase of one person share the dataset (§6); the phase comes from the ground-truth log, not from the name. |
| Asleep / idle | Device stays **connected**, no scripted activity. OS background traffic is left in the capture on purpose and removed by the ingest filter. This tests the filter. |
| Away | Device **disconnects from Wi-Fi** (Wi-Fi off, or the device physically leaves). Not the same as idle. |
| Randomness | Every distribution in a profile is sampled with a **seed per instance**. Same seed = same schedule (reproducible). Different seeds = different instances of the same profile. |
| Ground-truth log | Every executed activity gets one row: `start, end, device, activity_id, domains, profile, seed, block_id, status`. `start`/`end` are ISO-8601 with UTC offset (Europe/Zurich); `end` is the real end. `domains` lists the hosts of the main documents actually loaded (`;`-separated, after redirects). `status` is `ok`, `error` (nothing loaded, crash, interrupted) or `not_implemented` (stub, or no usable site in the mix). A row is also written for failed blocks; analyses must drop or flag rows that are not `ok`. This is needed to trace every reported likelihood back to the scripted behavior (project objective). |
| Cookie banners | Scripts **never accept** cookies. They reject optional cookies, also via the banner's settings dialog when the first level only offers "accept" (e.g. SRF Play: "Individuell verwalten" → "Nur Notwendige"). Where no reject option exists, the banner is left open and the page is used without consent. The rule is the same for all profiles, so its effect (fewer ad/tracker domains, lower UniqueSLD, less data volume) is a constant offset that is absorbed when C2_F1 is re-tuned on the baseline runs (§5.7). Every block starts in a fresh browser context, so the banner appears in every block. |
| Away vs. blocks | Blocks never run while the person is away. An occurrence that would fall into an away period is dropped (counts mean "while at home"). Away periods marked "replaces evening blocks" cancel all evening blocks of that day. |
| Overlaps | Two blocks on the **same device** run one after the other (the later-listed block starts when the earlier one ends; if it no longer fits its window, it is dropped). Blocks on different devices may run in parallel (e.g. phone checks during a stream), **except calls**: during a `video_call`/`voice_call`, no other foreground activity runs on any device, apart from `music_background` and the `gaming_session` a voice chat belongs to. |
| Frequency keys | `count` = per day, `per_week` = per calendar week, `per_window` / `keep_per_window` = per 14-day window, `days_per_week` / `nights_per_window` = how many days/nights get the block. `pages` and `dwell` override an activity's defaults. For `phone_check`, `pages` also decides how the block ends (§2). |
| Distribution notation | Written as quoted strings in YAML (e.g. `'N("06:30", 15m)'`) so the blocks stay valid YAML. `N(mean, sd)` normal, `U(a, b)` uniform, `a-b` uniform integer/duration range, `Poisson(λ)`. Times as `"HH:MM"`, durations as `15m`, `2h`. |

## 2. Activity primitives

Generation method key: **browser** = automated Chromium (e.g. Playwright) loading real pages. **call** = WebRTC call in Chromium with fake camera/mic (`--use-fake-device-for-media-stream --use-fake-ui-for-media-stream`) against a counterpart **outside** the home network (second device on mobile data or a cloud VM), so the media flows through the gateway. **dns** = DNS lookup only, no connection.

| ID | Device | What the script does | Duration | Traffic shape | Notes |
|---|---|---|---|---|---|
| `phone_check` | phone | Open pages from the block's `mix` one after another, dwell 20–90 s each, scroll. **Without `pages`:** keep opening pages until the duration is used up (about 1–4 pages in the default 1–5 min, more in longer blocks). **With `pages`:** open exactly that many and end, possibly before the duration is over (`duration` is then an upper bound) | 1–5 min (default) | Short burst, downstream-heavy, many third-party domains per page | The basic unit for "checking the phone". Night bursts use this. A long `wake_check` (5–15 min) is a sequence of pages, not 1–3 pages with long pauses. |
| `browse` | any | Sequence of page visits from `mix`, dwell 30–180 s, scroll, follow 1–2 internal links | as block | Moderate, steady | General browsing (news, shopping, search). |
| `social_passive` | phone (laptop possible) | Scroll a feed (load more content every 5–15 s), open 0–2 videos | as block | Downstream-heavy, low upstream | Passive monitoring (social anxiety, depression). Runner: long blocks switch to another site of the mix every 3–10 min; a "video" is an internal link of the feed. Reddit's feed auto-plays videos (~33 MiB/min). |
| `social_post` | phone | Log into a test account, upload 1 photo (1–3 MB) or a story | 2–5 min | Upstream spike | Active social use. Needs test accounts. |
| `messaging` | phone | Send 3–10 text messages via web client (test accounts), 10–60 s apart; reply to incoming messages from the counterpart account | 2–10 min | Small, bidirectional, turn-taking | Counterpart account is scripted too, so there's real turn-taking. |
| `video_call` | phone or laptop | `call` on the specified platform, camera + mic on (fake media) | as block | Long bidirectional UDP flow, high upstream | Upstream-heavy: the main signal SAD reduces. |
| `voice_call` | phone or laptop | `call`, audio only | as block | Bidirectional, lower bitrate | Gaming voice chat and voice-only calls (e.g. camera-off calls in the SAD profile). |
| `video_stream` | laptop or phone | Play a video/livestream to the end or until block end (no login platforms by default) | 30–120 min | Long downstream flow, ≥2 h counts as long stream (C1_F3) | |
| `music_background` | laptop | Play an audio livestream in the background during another block: an SRF radio live page (`audio` set, §3) at its lowest quality level | as block | Low, continuous downstream (≈ 1–1.5 MiB/min) | The page load counts as `srf.ch` (STREAMING). The stream itself comes from `*.akamaized.net`, which is in no thesis list; with the 5-min DNS map (§5.1) only the start of the block is labelled STREAMING. |
| `work_block` | laptop | Web mail + documents + calendar: open mailbox, refresh every 2–5 min, edit a doc, open 2–5 work pages per hour | 60–120 min | Steady, many packets to productivity domains | Drives C2_F6 (productivity hits). Runner (no test accounts): public pages of PRODUCTIVITY domains instead of a mailbox; no document editing. |
| `study_block` | laptop | Like `work_block` but LMS + documents + scholarly search, PDF downloads (1–5 MB) | 45–120 min | Steady, download peaks | Runner: 1–3 PDFs per hour from a fixed list (`documents.pdfs`). |
| `gaming_session` | laptop | Open launcher/store pages, then hold a long low-bitrate bidirectional session; with `voice: true` a parallel `voice_call` | 60–120 min | Long, symmetric, small packets | **Approximation.** Real game traffic can't be scripted headless. Decide the implementation in the pilot (see §6). |
| `repeat_visit_loop` | phone | Reload / revisit the same 2–3 pages every 1–3 min, fresh DNS lookup each time | 10–30 min | Repetitive, low diversity, many identical DNS queries | Rumination dial. Drives C8_F4 (repeated-query ratio). |
| `crisis_resource_visit` | phone | Open 1–3 pages of help-seeking resources, dwell 1–4 min | 2–10 min | Short | Only in profiles with the suicidality overlay. |
| `sh_adjacent_lookup` | phone | **DNS lookup only** of placeholder names `sh-adjacent-NN.invalid`, no connection | seconds | 1–3 DNS queries | Placeholder for self-harm-adjacent content. No real harmful domains are ever contacted or written down. The ground-truth log lists the queried placeholder names in `domains`. |
| `idle_connected` | any | Nothing (device on Wi-Fi, screen off) | as block | OS background only | Default state when nothing is scheduled. |
| `away` | any | Disconnect from Wi-Fi | as block | None | |

## 3. Domain sets (`mix` categories)

The pipeline reduces every hostname to its **last two labels** (`calendar.google.com` → `google.com`) and checks it against fixed lists in `app/metrics/common.py`. The column "Thesis list" shows which list a domain lands in. Only these lists move the C1/C2 social, streaming and productivity metrics.

| Category (`mix` key) | Domains | Thesis list | Login needed? |
|---|---|---|---|
| `messaging` | `web.whatsapp.com`, `web.telegram.org`, `discord.com` | SOCIAL (`whatsapp.com`, `telegram.org`, `discord.com`) | yes, test accounts |
| `social_passive` | `reddit.com`, `tiktok.com`, `instagram.com` | SOCIAL | reddit/tiktok no, instagram partly |
| `social_post` | `instagram.com`, `reddit.com` (test sub) | SOCIAL | yes |
| `call` platforms | `meet.jit.si` (private), `zoom.us` (work/study), `teams.microsoft.com` (work) | none (`jit.si`, `zoom.us`); `teams.microsoft.com` → `microsoft.com` = **PRODUCTIVITY** | jitsi no, zoom guest join, teams yes |
| `streaming` | `youtube.com` (+`googlevideo.com`), `play.srf.ch` (→ `www.srf.ch/play/tv`, on-demand videos; media from `*.akamaized.net`), `open.spotify.com`, `netflix.com` | STREAMING (`akamaized.net`: none) | youtube/srf no; spotify/netflix yes |
| `audio` (only `music_background`) | SRF radio live pages `www.srf.ch/audio/radio-srf-{1,3,virus}-live-hoeren` (stream from `*.akamaized.net`) | STREAMING for the page (`srf.ch`), none for the stream | no |
| `news` | `20min.ch`, `nzz.ch`, `watson.ch`, `tagesanzeiger.ch` | none (counts only for UniqueSLD) | no |
| `work` | without login: `github.com`, `gitlab.com` (→ `about.gitlab.com`), `trello.com`, `asana.com`, `todoist.com`; with login: `outlook.office.com`, `docs.google.com` | PRODUCTIVITY (all of them; `office.com`, `google.com` for the login ones) | first five no, last two yes |
| `study` | `unisg.ch`, `scholar.google.com`, `www.microsoft.com/de-ch/microsoft-365`; with login: university LMS (e.g. Canvas), `docs.google.com` | PRODUCTIVITY only via `google.com` / `microsoft.com`; `unisg.ch` and the LMS are in no list | partly |
| `search` | `duckduckgo.com` | none | no |
| `shopping` | `galaxus.ch`, `digitec.ch`, `zalando.ch`, `migros.ch` | none | no |
| `gaming` | `steampowered.com`, `riotgames.com`, `discord.com` (voice) | `discord.com` = SOCIAL | discord yes |
| `crisis_help` | `143.ch`, `147.ch`, `depression.ch` | CRISIS (`143.ch`, `147.ch`), MENTAL_HEALTH (`depression.ch`) | no |

Rules derived from the thesis lists:
- Use **`duckduckgo.com` for searches**. `google.com` is in the PRODUCTIVITY list, so every Google search would count as a productivity hit.
- Use **`20min.ch`/`nzz.ch` for news**, not `srf.ch`. `srf.ch` is in the STREAMING list.
- `teams.microsoft.com` counts as **productivity, not social** (two-label reduction). Use it only for work calls.
- WhatsApp app traffic (`*.whatsapp.net`) is in **no** list. Use WhatsApp Web (`web.whatsapp.com` → `whatsapp.com`).
- **Notion and Microsoft 365 left the listed domains** (checked 23.10.2026): `notion.so` redirects to `notion.com` / `app.notion.com`, `office.com` to `m365.cloud.microsoft`. Neither new domain is in a thesis list, so neither is used in `work`/`study`. For real users of these tools this is a limitation of the thesis lists (see thesis-alignment).
- The ground-truth log records the **real host after redirects** (e.g. `about.gitlab.com`). Check the two-label reduction of that host, not of the start URL.

## 4. Pipeline alignment: windows the metrics use

The thesis metrics look at fixed clock windows (active in `fasl_config.json` or proposed for the gateway config, see [thesis-alignment.md](thesis-alignment.md)). Profiles must place behavior inside these windows to be detectable:

| Window | Used by | Consequence for scripting |
|---|---|---|
| Night = **00:00–05:59**, day = rest (C4_F8: day = 06:00–21:59) | C1_F8 night/day packets, LateNightShare, C4_F8 night/day bytes | Night activity counts only after midnight. A late session 23:00–23:59 counts as *day*. |
| Sleep onset/wake = first idle gap **≥30 min within hours 22–04** of the calendar day | C4_F1 onset, C4_F2 wake after 04:00 | Gaps and wake-ups after 05:00 are not seen (see §5, item 4). |
| Nocturnal micro-sessions = sessions **≤5 min within 01:00–06:59**, 5-min gap rule | C4_F5, C4_F6 | Night bursts should mostly be **≤5 min** and separated by **≥5 min** (better ≥30 min) to count. |
| Daytime idle = minutes with no packets **08:00–17:59** | C4_F7 | Away days (office/campus) push the value far above the band (0–0.16), where μ = 0. C4_F7 therefore practically never contributes (thesis-alignment §2). |
| Sessions = 5-min idle gap | C2_F3, C1_F2, C2_F4 | Two activities less than 5 min apart merge into one session. |

## 5. Known pipeline pitfalls (check in the pilot run)

These are about the *data* reaching the thesis. How the thesis then *scores* the data into criteria (membership bands, gate, config issues B1–B9) is in [thesis-alignment.md](thesis-alignment.md).

1. **DNS mapping is rebuilt per 5-min partition.** The IP → hostname map is built only from DNS answers *in the same 5-min file*. A 60-min stream whose DNS lookup happened in the first partition loses its domain label in the remaining 55 min. Fix: add the SNI enrichment from the gateway feed (planned in MasterThesisInc §3), or make clients re-resolve often (short DNS cache). Until then, long sessions are underrepresented in all domain-based metrics.
2. **DNS caching on the client.** Browsers and OSs cache DNS. Repeated visits may produce no new query. Scripts should start each block with a fresh browser context, and the ground-truth log must not assume one DNS query per visit.
3. **`chat_mask` includes port 443.** Almost all HTTPS traffic counts as "chat", so C2_F3 (chat sessions) and C2_F4 (upstream rate) are effectively *all-traffic* metrics. Calls and uploads still dominate upstream, so the SAD signal survives, but it isn't chat-specific.
4. **Wake detection only sees hours 22–04 of one calendar day.** Confirmed by reading the code: on a day with activity after midnight and again from 22:00, the "wake" is the first packet after 22:00 (≈ 1 080 min). `C4_F2` (weight 0.65) is therefore an artifact. See [thesis-alignment.md](thesis-alignment.md) B3 for the proposed fix.
5. **C9 (suicidality) is not in `fasl_config.json`**, and even if configured it could never pass the 6-of-14-days gate, because it is episodic. Proposal: show it as a separate flag (thesis-alignment B8). Self-harm and query patterns are URL paths and search terms, which are **invisible under HTTPS**, so only domain-level hits (`143.ch`, `147.ch`) can fire.
6. **Counts are packets, not visits.** C2_F6 thresholds (lo 3 500, hi 15 000) are packet counts to productivity domains. A work day must generate thousands of packets there, which a realistic `work_block` does, but calibrate in the pilot.
7. **Third-party domains inflate UniqueSLD.** One page load contacts 5–30 domains (CDNs, ads, analytics). The C2_F1 threshold (<40 unique SLDs = indicator) was tuned on Dataset B. Healthy scripted days will likely be far above 40, so re-tune on the baseline instances before comparing profiles.

## 6. Open decisions (before the first run)

- **Baseline period before each clinical profile:** the pipeline's history-based metrics (C4_F3 onset variability, C4_F4 sleep-duration z-score vs. 30 days) compare a dataset with **its own earlier days**. If a clinical profile runs alone, it is compared with itself, and these metrics can't show a deviation. Recommendation: run each clinical instance as **14 baseline days followed by 14 profile days on the same dataset** (same devices). This doubles the run time, but it is also exactly the project's "deviation from personal baseline" principle.
- **Real time vs. parallel:** 14 days per instance in real time. Running profiles in parallel needs one phone + laptop pair (or equivalent emulated device with its own MAC) per profile.
- **Phone automation:** real phone (Android + adb/Appium) vs. a laptop or Raspberry Pi emulating the phone with a mobile user agent. The real phone gives realistic background traffic but is harder to script.
- **Gaming:** how to approximate `gaming_session` (e.g. a browser-based multiplayer game, or a long WebRTC data channel to our own counterpart).
- **Call counterpart:** second device on mobile data vs. a cloud VM. It must be outside the home network.
- **Test accounts:** which platforms get test accounts (minimum: one messaging platform for `messaging`, one social platform for `social_post`).
