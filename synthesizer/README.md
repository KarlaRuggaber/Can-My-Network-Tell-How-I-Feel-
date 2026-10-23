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
- **Finding:** the app's pages 01 and 02 call `enrich_with_hostnames` on the whole **day** (all partitions concatenated), not per partition. In the app, the first lookup of a server IP therefore labels the whole day.
- On the synthetic day below, rows without an SLD were 0.1 % (map per day) vs. 9.6 % (map per 5-min partition).

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

## 8. Status (23.10.2026)

Library from Karla's tests (16.10, 23.10), the pilot (23.10, 16–17 h, `--profile pilot`) and the first `messaging`/`social_post` tests: **25 snippets**, 2.2 M packets, 1.4 GB.

**Synthetic day** `gw_insomnia_a` seed 1 plan, Tue 27.10 (baseline 9-to-5), built with `--seed 7` as `syn_insomnia_b`:
- 11 plan rows: 6 phone checks, 2 messaging, 1 stream, office as away.
- 831 747 packets in 137 files, 855 MB, built in 5 s.
- Real `tapingest.py --once` (unchanged): 831 389 rows, all in `syn_insomnia_b`, nothing in `gw_unassigned`, 322 packets dropped as background (mdns 129, gateway_service 167, broadcast 26), as live.
- `trace`: 0 untraced rows; per block, parquet rows = manifest packets minus the dropped background.

Coverage of the three live plans with this library (rows exact / fallback / none):

| Plan | Missing (no snippet) | Fallbacks | Heavy looping |
|---|---|---|---|
| `gw_insomnia_a` | – | `video_call` 8 (phone call, laptop snippet only) | `work_block` from one 2-min snippet (2 363 copies) |
| `gw_mdd_suicidality_a` | `study_block` 21, `crisis_resource_visit` 4 | `browse` 4, `video_call` 4, `sh_adjacent_lookup` 1 | `music_background` from one 2-min MP3 snippet |
| `gw_social_anxiety_a` | `study_block` 24 | `voice_call` 2 (`mic_share` 0.1 never recorded), `video_call` 3, `browse` 5 | `music_background` (1 683 copies) |

So today the synthesizer is shown to work end to end, but a full synthetic instance would mostly be loops of a few snippets. After the live run (25.10–22.11) the library holds about 2 000 blocks of exactly the planned activities and mixes, including SRF radio, study blocks and SAD calls.

## 9. Limitations (what is lost compared with a live run)

- **Frozen content.** Pages, ads, videos, server IPs and DNS answers are those of the recording, and they recur in every instance that uses the snippet (October CDN addresses in a "December" instance).
- **Repetition.** Loops repeat identical packets: periodicity, the same TCP sequence numbers and RTP counters on the same 5-tuple. Chaining hides this for page activities, not for streams, calls and games. The ingest reads none of these fields.
- **Perfect execution.** No live failures, late starts, missed blocks or runner stubs, unless a row has no snippet. The plan, not a ground-truth log, is what gets synthesized.
- **Recorded network conditions.** Bandwidth, hotspot and gateway load are those of the recording, not of the new combination of parallel blocks.
- **Companions.** Without a recorded group, host and companion are two independent recordings overlaid (no shared bandwidth). Their packets are traceable only to the pair, as live.
- **Bounded activities** end when their snippet ended, not after the new block's own page draws.
- **Fallbacks** (role, mix, `mic_share`) change what the profile scripted. They are flagged per row, and `--strict` turns them off.
- **ICMP errors** keep the client IP in their embedded original header (the ingest reads only the outer one; about 0.07 % of br-sim packets).
- **No new randomness inside a snippet.** Dwell times, scroll patterns and page choices are the recorded ones. Day-to-day variation comes from the plan (seed, noise) and from which snippets are drawn.
- **Same as live, not lost.**
  - Peer traffic 10.43.0.x is private, so the app does not count calls as outbound/upstream.
  - On 25.10 the repeated hour is merged in naive local time.
  - Chromium's start-up request to `accounts.google.com` is once per block (chains start at the first page, so it is not repeated).

## 10. Next steps

- After the live run: copy the run's br-sim captures over the AP LAN, not the hotspot. Copying the pilot over Tailscale went through the phone hotspot at about 1 MB/s. Then `cut` with the three plans (`--plan`) so mixes and `mic_share` are known.
- Validation: for a live day of seed 1, build it from the *other* days' snippets (leave one day out) and compare the app's daily metrics with the live day.
- `scheduler/README.md` §5 still says "Not done: the synthesizer"; update it when this is merged.
