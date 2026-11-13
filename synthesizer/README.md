# synthesizer

Turns a ground-truth plan (`python -m scheduler plan`) into synthetic traffic, so that more instances of a profile (other seeds, other profiles) can be produced without running 14–29 days in real time. It stitches **recorded snippets** of the live runs:
- for each plan row it takes a snippet of the same activity, role and mix
- trims, chains or loops it to the planned duration
- shifts it to the planned start
- moves it to the target device's IP and MAC.

Idle stays empty and away is a gap. The result is a folder of 60-s capture files that the unchanged ingest (`tapingest --once`) turns into a dataset for the app, like a live run. Every packet stays traceable through `segments.csv` to its `block_id`, and from there to the profile block and the profile.

```
synthesizer/
  synthesizer/
    cli.py        python -m synthesizer {cut,coverage,build,trace}
    pcap.py       pcap reader/writer (stdlib)
    rewrite.py    client IP/MAC/port rewrite, checksums (stdlib)
    catalog.py    activity classes, heads, host -> mix category (activity-catalog §2/§3, runner mixes.yaml)
    library.py    cut ground truth + captures into snippets; library index
    select.py     plan rows -> snippet choices -> segments
    build.py      segments -> time-merged packets -> capture files, manifest, segments, devices file
    trace.py      ingested Parquet rows -> block_id (pandas)
  compare_day.py  the app's daily metrics of one day, live vs. synthetic (validation, §8)
  tests/          pytest (test_ingest.py runs the real ingest)
```

`cut`, `coverage` and `build` need only the standard library of Python 3.11+. `cut` reads the runner's `mixes.yaml` with PyYAML; pass `--no-mixes` to use only the built-in host table. `trace` and `tests/test_ingest.py` need the ingest's packages (`app_pcap_to_dsm5/ingest/requirements.txt`: scapy, pandas, pyarrow). PCAP handling is plain `struct`, because scapy builds only about 10–20k packets/s, and one Reddit hour is about 1.5 M packets. Building one day of 830k packets takes about 5 s.

## 1. Quick start

Snippets and synthetic data are several GB of PCAP. Keep them outside git and outside OneDrive, e.g. in `~/cmnthif-synth/`.

```bash
cd synthesizer
python3 -m pytest -q
# 1. library from a recorded run (captures copied from the gateway's /var/lib/tapcap/sim/ready, br-sim only)
python3 -m synthesizer cut --ground-truth ground_truth.csv --captures sim-ready/ --library ~/cmnthif-synth/library \
    --plan ../run-2026-10-25/gw_insomnia_a.csv --commands pilot.commands.tsv \
    --alias student01_phone=student_a_phone --alias student01_laptop=student_a_laptop
# 2. what a plan would be built from
python3 -m synthesizer coverage --plan plan.csv --library ~/cmnthif-synth/library [--day 2026-10-27]
# 3. one synthetic instance (or some of its days)
python3 -m synthesizer build --plan plan.csv --library ~/cmnthif-synth/library --dataset syn_insomnia_b \
    --out ~/cmnthif-synth/out/syn_insomnia_b [--day 2026-10-27] [--seed 7] [--strict]
# 4. ingest with the unchanged service code, own state and devices file, then check traceability
cd ../app_pcap_to_dsm5
TZ=Europe/Zurich .venv/bin/python ingest/tapingest.py --watch ~/cmnthif-synth/out/syn_insomnia_b/ready \
    --devices ~/cmnthif-synth/out/syn_insomnia_b/devices.csv --out app/processed_parquet \
    --state ~/cmnthif-synth/out/syn_insomnia_b/ingest.sqlite --once
cd ../synthesizer
python3 -m synthesizer trace --out ~/cmnthif-synth/out/syn_insomnia_b --parquet ../app_pcap_to_dsm5/app/processed_parquet/syn_insomnia_b
```

To make a new instance, make a plan with another seed against a live dataset's devices, e.g. `python -m scheduler plan --profile insomnia-moderate --seed 7 --dataset gw_insomnia_a …`. Then build it under a synthetic dataset name. Rules for the ingest:
- Never put synthetic files into the live watch folders (`/var/lib/tapcap/…`).
- Never ingest with the live `devices.csv`: the output uses the live devices' IPs.

Exit codes: 0 ok, 1 `trace` found untraced rows, 2 usage/input error.

## 2. Snippet library (`cut`)

| Input | |
|---|---|
| `--ground-truth` | runner's `traffic-runner/logs/ground_truth.csv`: the time ranges |
| `--captures` | tapcap's 60-s files `cap-<epoch_ms>.pcap` from **br-sim** (`/var/lib/tapcap/sim/ready`). eno1 captures contain the real devices, so don't use them |
| `--devices` | `traffic-runner/config/devices.csv`: device → IP, MAC, role. `--alias old=new` for devices renamed since the recording (`student01_*` → `student_a_*`, same IP) |
| `--plan`, `--commands` | Plan CSVs / runner command files of the recorded run, joined on `block_id`. The ground truth has no mix, `mic_share`, `pages` or `lookups` |

Rules:
- One snippet per ground-truth row with status `ok`, on its device IP. `error`, `not_implemented`, `idle_connected` and `away` rows give no snippet.
- Window: `[start, min(end + 30 s, next block's start on that device))`. The tail keeps the browser shutdown (pilot: packets up to 16 s after `end`). Blocks that overlap by up to 30 s are taken as back to back: `end` is logged after the browser has closed.
- Packets: every IPv4 packet with the device IP as source or destination. That includes DNS to/from 10.42.1.1 and the peer (10.43.0.x). ARP, IPv6 and other hosts are left out, and the ingest ignores them anyway.
- **Companions** (`…-voice`, `…-bg`) run on the host's device with the same IP, so their packets cannot be told apart. The live ground truth has the same limit. Host + companions are one **group snippet** (`companions` column). A non-companion overlap of more than 30 s marks both rows `ambiguous`, and they are skipped.
- `categories`: the mix categories the snippet *actually* loaded. They come from its `domains` (real hosts) by suffix match on `mixes.yaml` plus a few runner hosts (`peer.sim`, `srg-ssr.ch`, `arxiv.org`, `slack.com`). A host in two categories is narrowed to the activity's own one. The runner moves the weight of login sites and stubs elsewhere, so this can differ from the planned mix.
- `first_page_s`: time of the first DNS query for the main document's host. Chains of page activities start there (§3).
- Incremental: existing snippet IDs (`<start>-<device>-<activity>`) are kept, and new ground-truth rows are added.

```
library/index.csv           snippet_id, activity_id, companions, role, device, client_ip, client_mac, start, end,
                            duration_s, tail_s, first_page_s, packets, bytes, dns_queries, domains, categories,
                            mix, mic_share, pages, lookups, block_ids, profile, seed, captures, flags
library/snippets/<id>.pcap  original addresses and times
```

Capture gaps cannot be seen in the files: tapcap (dumpcap) only starts a new file when packets arrive. A tapcap restart shows up only in its journal. A snippet without packets is flagged `empty` and never used.

## 3. Selection and duration (`build`)

**Choice.** Each plan row gets `random.Random(f"{seed}/{block_id}")`, the same scheme as scheduler and runner. A row's choice therefore does not change when other rows change. The seed is the plan's seed, or `--seed`. Among the snippets of the same `activity_id`, the best match level is taken:

| Level (lexicographic) | Exact | Fallback flag in the manifest |
|---|---|---|
| role | same role (phone/laptop) | `role_fallback` |
| mix | every snippet category is in the plan mix | `mix_fallback`: partial overlap or unknown hosts, then any |
| options | calls: same `mic_share` (1.0 if none); `sh_adjacent_lookup`: same `lookups` | `options_fallback` |

`--strict` uses only exact matches. Other rows stay empty with `no_exact_snippet`. No snippet at all: `no_snippet`, nothing emitted (as for a runner stub).

Weights:
- Each snippet is weighted by the mean, over its hosts, of the plan weight of the host's category. With `news .4, social .4, search .2`, a TikTok snippet gets 0.4.
- That is multiplied by a duration factor:
  - Loops strongly prefer long snippets.
  - Chains prefer them mildly.
  - Bounded activities prefer snippets that are not longer than the plan.
- A plan row with companions (`companion_of`) uses a group snippet with the same activities. Without one, host and companion are built from solo snippets and overlaid on the device (`note=overlay`).

**Duration.** A snippet = head `[0, H)` + body `[H, duration)` + tail.

| Method | Activities | What happens |
|---|---|---|
| `bounded` | `crisis_resource_visit`, `sh_adjacent_lookup`, `messaging`, `social_post`, `phone_check` with `pages` | as recorded, cut at the planned duration (the duration is an upper bound, catalog §2) |
| `chain` | `browse`, `social_passive`, `phone_check`, `work_block`, `study_block` | snippet A, then **bodies of further snippets** drawn with the same weights (B, C, or A again), each with new client ports. H = 50 ms before the first page's DNS query, so each body is a new page without a second browser start |
| `loop` | `video_stream`, calls, `gaming_session`, `music_background`, `repeat_visit_loop`, groups | A, then A's body again with the **same ports**: one continuous flow. H = 60 s (stream), 20 s (call), 25 % (gaming: store pages are at most ¼ of the block), 30 s otherwise |
| `trim` | a fill activity whose snippet is longer than planned | cut at the planned duration |

A body shorter than 30 s is never chained or looped (`short` in `match`). After the last piece comes the tail of the last snippet used. All pieces stop at the next block on the same device, so a block's packets never run into the next one.

## 4. Time and DST

Everything is absolute time: integer µs since the epoch.
- A packet's new time = the plan's `start` (ISO with offset) + the packet's offset from its snippet's recorded start. Relative timing is exact to the µs.
- Snippets recorded in summer time can be used in winter time, because there is no wall-clock arithmetic anywhere.
- The ingest turns epoch time into naive Europe/Zurich time. On 25.10 the hour 02:00–03:00 therefore occurs twice and lands in the same 5-min partitions, exactly as with live data (tested: `test_dst_day_uses_absolute_time`, `test_ingest_accepts_a_synthetic_day`).
- `--day` selects plan rows by the plan's `day` column. A night block of day d can run after midnight, as live.

## 5. Rewriting

- **Client only.** The snippet device's IP → the target IP; its MAC → the target MAC (from `devices.csv` by the plan's `device`, or `--target-devices`). The gateway (10.42.1.1 and its MAC), the peer and all servers stay as recorded.
- **DNS needs no payload change.** Queries go to dnsmasq on 10.42.1.1, and answers carry server IPs, which are kept. Query, answer and the flows that use the answer move together. `DNS_QNAME`, `DNS_QTYPE`, `DNS_ANS_NAME` and `DNS_ANS_IPS` are identical to the recording (tested against the app's `parse_packet_row`).
- **Ports.** A chained body uses client ports shifted by a bijection on 1024–65535, so its packets look like new connections. Ports below 1024 never change.
- **Checksums.** br-sim records most container packets with an offloaded checksum: the field holds only the pseudo-header sum. Of 30k packets checked on 23.10, every TCP/UDP checksum was either valid or exactly this partial form. A full recompute would change the data, so each packet keeps its state:
  - A valid checksum stays valid (RFC 1624 incremental update).
  - A partial one becomes the new addresses' pseudo-header sum.
  - The IPv4 header checksum stays valid.
  - UDP checksum 0 stays 0. Non-first fragments get only the IP header fixed.

## 6. DNS → IP map (catalog §5.1)

DNS packets stay at their recorded offset from the block start, so a lookup and the flows it labels move together. Whether a flow's DNS answer falls in the same 5-min partition depends on where the block starts relative to the 5-min grid, as it does live.
- Chained/looped bodies replay the lookups that happened in the body. `repeat_visit_loop` keeps its fresh lookup per visit.
- A looped stream whose body has no DNS keeps its label only where live would too.
- **App lookup (since 27.10, `4cc8e49`):** the app names a packet after the latest DNS answer that the **same client** received for the remote IP **before** the packet (IPs answered with only one name: day-wide map). Synthetic data fits this: answers are moved to the target IP together with the client side of the flows, and they keep their offset before the packets they label. A looped body without DNS keeps the name of the last answer before it, like a live stream without re-resolution.
- On the synthetic day below (23.10, before that change), rows without an SLD were 0.1 % with the day-wide map vs. 9.6 % with a map per 5-min partition.

## 7. Output

```
<out>/ready/cap-<epoch_ms>.pcap   60-s files on the UTC minute grid (like tapcap); minutes without packets have no file
<out>/devices.csv                 target devices -> --dataset (for the ingest only)
<out>/manifest.csv                one row per plan row: block_id, day, phase, profile, profile_block, activity_id, device,
                                  planned start/end, duration_s, method, match, snippets, copies, packets, bytes,
                                  emitted start/end, companion_of, flag, note
<out>/segments.csv                device, ip, t_from_us, t_to_us (+ local ISO), block_ids, snippet_id, part
                                  (main/body/tail), source offsets, copy, packets, bytes
<out>/synth.json                  arguments, plan + library hashes, version, counts
```

- File mtimes are left at write time, i.e. chronological. Don't set them to the capture time: the ingest skips files whose mtime is in the future.
- **Dataset names**: `syn_<profile>_<letter>` (`syn_insomnia_b`). The rules are checked: `[a-z0-9_]`, starting with a letter, not ending in a digit (the app's `group_prefix()` would merge them), no `onu`/`bras`, and never a live dataset from `devices.csv`.
- **Traceability**: packet (client IP, time) → `segments.csv` → `block_id` → plan row (`profile_block`, `profile`, `phase`). Segments on one device never overlap, except host + companion (group) and overlays. That is the granularity of the live ground truth. `trace` counts the Parquet rows per block and compares them with the manifest. Rows in the repeated DST hour are counted separately, because their naive local time is ambiguous.

## 8. Status and validation (13.11.2026)

### Library

The library was cut on the gateway on 13.11 from three live-run days, into `/var/lib/synth/library`, with a copy on Karla's laptop in `~/cmnthif-synth/library`.

| | |
|---|---|
| Days | Tue 27.10 (lecture/office day), Fri 30.10 (self-study, home office, calls), Wed 11.11 (clinical phase) |
| Snippets | 203 (69 + 82 + 52) |
| Size | 31 M packets, 33 GB |

- **One `cut` per day.** `cut` reads every capture file between the earliest and the latest window it is given. The three days in one call would read all 16 days in between, about 180 GB instead of 33 GB.
- **Light on the gateway.** Run with `nice`/`ionice`, the cut took about 4 minutes, and available memory stayed around 3.5 GB.
- **Copy to the laptop.** Over Tailscale, rate-limited to 5 MB/s so that the live run keeps its uplink. The snippets that a build needs can be copied first: run `plan_all` on the index and pass the list to `rsync --files-from`.

Coverage of the three live plans over all run days:

| Plan | Missing (no snippet) | Fallbacks |
|---|---|---|
| `gw_insomnia_a` | `browse` 9 | `video_call` 8 (phone calls, only laptop call snippets) |
| `gw_mdd_suicidality_a` | `browse` 4, `sh_adjacent_lookup` 1 | `video_call` 4 |
| `gw_social_anxiety_a` | `browse` 5 | `video_call` 3, `voice_call` 2, `social_passive` 3 |

- **Now exact:** `study_block` (with `music_background`) and the SAD `voice_call` with `mic_share 0.1`, which were missing on 23.10.
- **Still missing:** `browse`, because none of the three days had a `browse` block.
- **No heavy looping any more:** at most a few hundred copies of 70–100 snippets per activity, instead of thousands of copies of one snippet.

### Validation: rebuilding the live day Wed 28.10 (leave one day out)

**Question:** does a synthetic day give the same daily metrics as the live day it imitates? 28.10 is not in the library, so it is built only from other days' snippets.

**How it was built**
- **Day blocks:** the plan rows of day 28.10 of each live plan (seed 1), built from the library: `build --day 2026-10-28`.
- **Blocks after midnight:** the calendar day 28.10 starts with the late blocks of plan day **27.10** that run past midnight (Maria 3 until 00:50, Carl 2 until 01:16, Ben none). They were built separately (`syn_*_bn`). Their snippets come from a copy of the index **without the 27.10 snippets** (134 left); otherwise these blocks could pick their own recording. A first run without them lacked the whole night, and every sleep metric was off.
- **Ingest:** the unchanged `tapingest.py --once`, with the same pandas 3.0.6 and pyarrow 26.0.0 as the gateway.
- **Traceability:** `trace` found 0 untraced rows (12.9 M rows).

| Persona | Plan rows (28.10 + night) | Matches | Rows on 28.10 live / synthetic |
|---|---|---|---|
| Ben (`gw_insomnia_a`) | 11 + 0 | 8 exact, 1 `role_fallback` (phone call), 2 away | 1.30 M / 1.38 M |
| Maria (`gw_mdd_suicidality_a`) | 30 + 3 | all exact | 5.72 M / 5.47 M |
| Carl (`gw_social_anxiety_a`) | 31 + 2 | all exact | 5.34 M / 4.17 M |

**How the metrics were compared**
- `compare_day.py` runs the app's own per-day pipeline without Streamlit: `enrich_with_hostnames`, `drop_background`, `compute_daily_base_record`, `Criterion1..9`. It is the same code as the "all days" table on the Network Metrics page, and it fits on an 8 GB laptop (peak 2.5 GB).
- Both sides get the same empty history, so only same-day metrics are compared.
- Not compared: metrics that need a baseline (14/30-day z-scores and variances) and the criterion likelihoods of Early Signs. They need several synthetic days.

```bash
python synthesizer/compare_day.py --day 2026-10-28 \
    --pair ~/cmnthif-synth/processed_parquet/gw_mdd_suicidality_a ~/cmnthif-synth/merged/syn_mdd_suicidality_b+bn
```

Result (live / synthetic, relative difference). Metrics that are 0 or N/A on both sides are left out.

| Metric | Ben | Maria | Carl |
|---|---|---|---|
| Longest inactivity (h) | 12.6 / 12.6 | 7.11 / 7.11 | 5.66 / 5.65 |
| Sleep onset delay from 22:00 (min) | – | 171 / 171 | 197 / 197 |
| Wake time after 04:00 (min) | – | 1080 / 1080 | 1080 / 1080 |
| Active night minutes 00–05 | 1 / 1 | 25 / 25 | 25 / 26 |
| First activity after 04:00 (min) | 360 / 360 | 478 / 478 | 416 / 416 |
| Daytime idle ratio 08–18 | 1 / 1 | 0.648 / 0.648 | 0.652 / 0.653 |
| Unique domains (eTLD+1) | 107 / 100 (−7 %) | 162 / 150 (−7 %) | 156 / 140 (−10 %) |
| Distinct social domains | 107 / 100 (−7 %) | 162 / 150 (−7 %) | 156 / 137 (−12 %) |
| Social outgoing share | 0.032 / 0.030 (−8 %) | 0.021 / 0.023 (+8 %) | 0.023 / 0.025 (+8 %) |
| Down/up byte ratio | 36.5 / 33.7 (−8 %) | 47.8 / 43.5 (−9 %) | 45.1 / 38.5 (−15 %) |
| Chat sessions (5-min gap) | 8 / 5 (−38 %) | 16 / 16 | 14 / 14 |
| Median chat reply latency (s) | 2 / 2 | 2 / 2 | 2 / 2 |
| Upstream chat rate (bps) | 9430 / 8720 (−8 %) | 14 900 / 13 900 (−7 %) | 9910 / 9250 (−7 %) |
| Interdaily stability (IS) | 1.09 / 0.96 (−12 %) | 0.54 / 0.61 (+13 %) | 0.642 / 0.643 |
| Intradaily variability (IV) | 0.155 / 0.062 (−60 %) | 0.131 / 0.122 (−7 %) | 0.127 / 0.127 |
| Hourly CV | 2.19 / 2.05 (−6 %) | 1.63 / 1.42 (−13 %) | 1.40 / 1.32 (−6 %) |
| Inter-request Fano factor | 34 900 / 34 900 | 10 900 / 10 800 (−1 %) | 9330 / 9200 (−1 %) |
| DNS burst rate / h | 4.2 / 7.3 (+72 %) | 14.5 / 16.2 (+12 %) | 13.8 / 13.7 (−1 %) |
| Late-night share (packets 00–05) | 0.002 / 0.003 (+90 %) | 0.224 / 0.151 (−33 %) | 0.118 / 0.066 (−44 %) |
| Night/day traffic ratio (bytes) | 0.003 / 0.004 (+55 %) | 0.297 / 0.197 (−34 %) | 0.151 / 0.080 (−47 %) |
| Passive/active byte ratio | 7.2 / 17.1 (+138 %) | 0.69 / 2.26 (+230 %) | 1.50 / 1.87 (+25 %) |
| Productivity-site hits | 0 / 0 | 11 700 / 5940 (−49 %) | 3500 / 11 500 (+229 %) |
| Mean social-session duration (s) | 676 / 1750 (+160 %) | 1150 / 1300 (+12 %) | 1450 / 1450 |
| Self-harm forum metric (reddit.com packets, no URLs) | 63 600 / 12 600 (−80 %) | 1.09 M / 1.27 M (+16 %) | 757 k / 712 k (−6 %) |
| POST + chat messages / day (proxy) | 107 k / 126 k (+19 %) | 691 k / 751 k (+9 %) | 562 k / 436 k (−22 %) |

**What matches.** The metrics that the plan determines:
- **Sleep and timing** are equal within one minute: longest inactivity, sleep onset, wake time, active night minutes, first activity, daytime idle ratio.
- **Domain metrics** are within about 12 %: unique and social domains, social outgoing share, down/up ratio.
- **Chat** behaviour is within 8 %: reply latency, upstream rate.
- **Rhythm** is within 13 % for Maria and Carl: inter-request Fano, IS, IV, hourly CV.

**What differs, and why.**
- **Snippet content (§9 "frozen content").** These metrics depend on *which* recording was drawn, not on the plan:
  - passive/active byte ratio: which videos and feeds
  - productivity hits: which study snippet, with how many Office pages
  - late-night share and night/day ratio: how heavy the night's social feeds were
  - mean social-session duration and the reddit-based C9 proxy (Ben)

  More snippets per activity (the full library after 22.11) spread these out, but they remain the main source of difference between a synthetic and a live day.
- **Ben's sparse day.** Ben's 28.10 is mostly away (office day) with nine short blocks, so a single block moves his ratios: IV −60 %, DNS burst rate +72 %, chat sessions 8 vs. 5. The messaging blocks are `bounded`: they end when their snippet ended, not after the planned number of messages.
- **Packet totals** are 4–22 % lower synthetically for Maria and Carl. Idle stays empty, without the runner's background traffic, and bounded activities end early (§9). The app drops that background before the features, so the metrics above are not affected.

**Lessons for building instances**
- **A calendar day needs two plan days.** Build plan day *d* together with the after-midnight blocks of *d−1*. A per-day build of only day *d* loses the night.
- **Leave-one-out must also exclude the previous day.** When a validation day's night blocks belong to a library day, build them from an index without that day.

## 9. Limitations (what is lost compared with a live run)

- **Frozen content.** Pages, ads, videos, server IPs and DNS answers are those of the recording, and they recur in every instance that uses the snippet (October CDN addresses in a "December" instance).
- **Repetition.** Loops repeat identical packets: periodicity, the same TCP sequence numbers and RTP counters on the same 5-tuple. Chaining hides this for page activities, not for streams, calls and games. The ingest reads none of these fields.
- **Perfect execution.** No live failures, late starts, missed blocks or runner stubs, unless a row has no snippet. The plan, not a ground-truth log, is what gets synthesized.
- **Recorded network conditions.** Bandwidth, hotspot and gateway load are those of the recording, not of the new combination of parallel blocks.
- **Companions.** Without a recorded group, host and companion are two independent recordings overlaid (no shared bandwidth). Their packets are traceable only to the pair, as live.
- **Bounded activities** end when their snippet ended, not after the new block's own page draws.
- **Fallbacks** (role, mix, `mic_share`) change what the profile scripted. They are flagged per row, and `--strict` turns them off.
- **ICMP errors** keep the client IP in their embedded original header (the ingest reads only the outer one; about 0.07 % of br-sim packets).
- **Runner background traffic (since 26.10, `e3fd6dd`).** Live, the containers send OS/browser background requests all the time, also while idle. In synthetic data idle stays empty, and background appears only inside blocks, as far as it was recorded there (snippets before 26.10 have none). The app drops this traffic before computing features (`drop_background`), so the metrics should not change, but raw packet counts, ingest totals and quiet minutes differ from live.
- **No new randomness inside a snippet.** Dwell times, scroll patterns and page choices are the recorded ones. Day-to-day variation comes from the plan (seed, noise) and from which snippets are drawn.
- **Same as live, not lost.**
  - Peer traffic 10.43.0.x is private, so the app does not count calls as outbound/upstream.
  - On 25.10 the repeated hour is merged in naive local time.
  - Chromium's start-up request to `accounts.google.com` is once per block (chains start at the first page, so it is not repeated).

## 10. Next steps

- **`browse` snippets.** Add a run day with `browse` blocks to the library (`cut` is incremental; one `cut` per day).
- **Full library after 22.11.** Cut all run days, on the gateway once the executors are stopped (no run to disturb), or from captures copied with a USB disk.
- **Several synthetic days in a row** (e.g. a whole baseline week). Then the baseline metrics (14/30-day) and the Early Signs criterion likelihoods can be compared too.
- **More validation days**, including a clinical-phase day.
