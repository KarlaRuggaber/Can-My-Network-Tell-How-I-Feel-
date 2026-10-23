# scheduler

Turns a profile (its §9 "Script specification") and a seed into the **ground-truth plan**: one row per scripted block, with absolute start/end times, device, activity and mix. The same plan drives the live runs (the runner executes it block by block) and, later, the synthetic snippet stitching. Every row has a `block_id`, which the runner writes into `ground_truth.csv`. A reported likelihood can therefore be traced back through the day's rows to the profile block that produced them.

This folder holds the scheduler only. It reads `traffic-runner/config/devices.csv` but never changes it, and it does not execute anything (there is no executor yet, see §6).

```
scheduler/
  profiles/              machine-readable §9 per profile (format: §2)
    student.yaml, 9to5-worker.yaml, insomnia-moderate.yaml
  scheduler/
    cli.py               python -m scheduler {plan,validate}
    catalog.py           activity IDs, devices, default durations/mixes, call/companion rules (activity-catalog §2/§3)
    dist.py              distribution notation (activity-catalog §1)
    spec.py              YAML loading, extends + patch, validation
    devices.py           devices.csv -> device names per dataset and role
    planner.py           day contexts, occurrences, conflict resolution
    output.py            plan CSV + runner commands
  tests/                 pytest
```

Python 3.11+, stdlib + PyYAML (tests: pytest).

## 1. Quick start

```bash
cd scheduler
python3 -m pytest -q
python3 -m scheduler validate
python3 -m scheduler plan --profile student --seed 42 --start 2026-10-26 --days 15 \
    --devices ../traffic-runner/config/devices.csv --dataset gw_student_a --out plan.csv
```

This writes `plan.csv` and `plan.commands.tsv`. A summary goes to stderr (rows, phases, dropped occurrences by reason, warnings).

| Option | Meaning |
|---|---|
| `--profile` | Name in `profiles/` (`student`, `9to5-worker`, `insomnia-moderate`) or a path to a `.yaml` |
| `--seed` | Instance seed. Same seed = same plan; different seeds = different instances of the profile |
| `--start` | First plan day = **warm-up day** (`YYYY-MM-DD`, Europe/Zurich) |
| `--days` | Total days in the plan, including warm-up and baseline (default 15 = 1 warm-up + 14) |
| `--baseline-days` | Clinical profiles only: this many days after the warm-up run the tier-0 profile they extend (catalog §6). Example: `--days 29 --baseline-days 14` = 1 warm-up + 14 baseline + 14 profile days on the same dataset |
| `--devices` | `traffic-runner/config/devices.csv` |
| `--dataset` | Dataset in `devices.csv`. Its `phone` and `laptop` rows become the plan's devices |
| `--out`, `--commands` | Plan CSV; runner commands (default `<out>.commands.tsv`) |

Exit code 0 = ok, 2 = usage, profile or devices error (message on stderr).

A clinical instance with its baseline (needs a dataset with two devices in `devices.csv`, e.g. `gw_insomnia_a`):

```bash
python3 -m scheduler plan --profile insomnia-moderate --seed 7 --start 2026-10-26 --days 29 --baseline-days 14 \
    --devices ../traffic-runner/config/devices.csv --dataset gw_insomnia_a --out insomnia_a.csv
```

## 2. YAML format

One file per profile in `profiles/`. Block IDs, windows, durations and mixes are copied 1:1 from the profile markdown's §9. Where the scheduler needs a value the markdown doesn't give, the YAML says so in a `# scheduler:` comment (listed in §7).

### 2.1 Top level

```yaml
profile: student                      # name in the plan's `profile` column
source: profiles/tier0-healthy/student.md
tier: 0
extends: null                         # clinical: name of the profile it patches (§2.6)
timezone: Europe/Zurich
window_days: 14                       # length of a window (per_window keys)
warmup_days: 1
start_weekday: Mon                    # the first window day should be this weekday (warning otherwise)
devices: [phone, laptop]              # roles; mapped to devices.csv rows by dataset + role
day_types: {lecture: [Mon, Tue, Wed, Thu], self_study: [Fri], weekend: [Sat, Sun]}
timetable: ...                        # optional, §2.2
anchors: ...                          # §2.3
away: [...]                           # §2.4
blocks: [...]                         # §2.5
```

### 2.2 Timetable (drawn once per seed)

Values that are fixed for an instance and repeat every week, e.g. the student's lecture timetable:

```yaml
timetable:
  tags:                                # extra day types per weekday
    lecture_early: {choose: 2, of: lecture, else: lecture_late}
  values:                              # per weekday, used as timetable.<name>
    campus_start:  {lecture_early: "08:00", lecture_late: 'U("10:30", "14:00")'}
    campus_length: 'U(2h, 5h)'
```

Tags behave like day types in selectors. A value is either one distribution or a map keyed by day type, tag or weekday (the first matching key wins).

### 2.3 Anchors

```yaml
anchors:
  wake:                                # first scripted activity of day d
    - {day_types: [lecture_early], value: 'N("07:30", 30m)'}
  sleep:                               # night of day d: end of the last activity; times before 12:00 are on d+1
    - {days: [Sun, Mon, Tue, Wed, Thu], value: 'N("00:30", 45m)'}
```

For a value, the first matching rule wins. Clinical patches add `shift` rules, and all matching shifts are added up (§2.6). Wake and sleep are drawn once per day.

### 2.4 Away periods

```yaml
away:
  - {id: campus, day_types: [lecture], from: timetable.campus_start, length: timetable.campus_length,
     not_before: wake + 20m}
  - {id: going_out, days: [Thu, Fri, Sat], per_week: 1-2, from: 'N("20:00", 30m)', to: 'N("01:00", 45m)',
     replaces: evening, sleep_after_return: 15m-30m}
```

| Key | Meaning |
|---|---|
| `from`, `to` / `length` | Start and end (a `to` that is not after `from` is on the next day) or length |
| `not_before` | Earliest start, e.g. `wake + 20m` so the wake check is still at home |
| `replaces: evening` | Cancels all blocks with `group: evening` that day |
| `sleep_after_return` | That night's sleep anchor = return + this |
| selectors, frequency | as for blocks |

Both devices are away. The plan gets one `away` row per device.

### 2.5 Blocks

```yaml
blocks:                                # list order = priority for overlaps (§3)
  - {id: day_checks, day_types: all, count: 10-18, within: [wake, "20:00"], device: phone, activity: phone_check,
     duration: 1m-5m, mix: {messaging: .35, social_passive: .45, news: .1, search: .1}}
```

| Key | Meaning |
|---|---|
| `id` | Profile block ID, `[a-z][a-z0-9_]*`, unique within the profile |
| `day_types` / `days` / `nights` | Selector: day types and timetable tags (or `all`), weekdays, a night set (§2.6). All given ones must match |
| `group` | `evening`: cancelled by an away period with `replaces: evening` |
| placement | exactly one of: `at: T` (start at T); `from: T` + `duration`; `from: A, to: B` (**fill**: fills the window); `within: [A, B]` + `duration` (random start inside) |
| `count` | Occurrences per day (default 1). Integer, range `10-18`, or a distribution (`Poisson(2.5)`) with optional `clip: [2, 4]` |
| `per_week` | Occurrences per calendar week (Mon–Sun), at most one per day |
| `per_window`, `keep_per_window` | Occurrences per 14-day window, at most one per day |
| `days_per_week`, `nights_per_window` | How many days/nights get the block; `count` applies on each |
| `duration` | Duration or distribution. Default: the catalog default (`phone_check` 1–5 min, `messaging` 2–10 min, ...). Activities that run "as block" need it unless the block is a fill block |
| `device`, `activity` | Role (`phone`/`laptop`) and catalog §2 activity ID. The catalog's device column is enforced |
| `mix` | Catalog §3 categories with weights. Required for `phone_check`, `browse`, `repeat_visit_loop`; the other activities default to their own category (`study_block` → `study`, ...) |
| `pages`, `dwell` | Passed to the runner (`--pages`, `--dwell`). For `phone_check`, `pages` makes `duration` an upper bound (catalog §2) |
| `with: music_background` | Companion on the same device for the whole block (and each of its pieces) |
| `voice: true` | `gaming_session` with a parallel `voice_call` on `discord` |
| `platform` | Calls: `zoom`, `teams`, `jitsi` (`discord` for gaming voice) |
| `max_delay` | How far an `at`/`from`+`duration` block may slip behind an earlier block (default 30m) |
| `min_gap`, `not_before`, `night` | Clinical: minimum gap between a block's occurrences; earliest start (e.g. `sleep + 30m`); `night: true` = times before 12:00 are in the night after day d, and the block is not limited to wake–sleep |

**Time references** (`at`, `from`, `to`, `within`, `not_before`): `"HH:MM"` (always quoted: unquoted YAML reads `14:00` as the number 840, which the loader rejects), `'N("20:00", 30m)'`, `'U("10:30", "14:00")'`, `wake`, `sleep`, `baseline_sleep`, `timetable.<name>`, `away.<id>.start|end`, each optionally `± <duration>` (`sleep - 20m`).

**Distribution notation** (catalog §1): `N(mean, sd)` normal, clipped to mean ± 3 SD; `U(a, b)` uniform; `a-b` uniform range (`5-15m`, `1h-3h`; integers for counts); `Poisson(λ)`; mixtures `{p: [.8, .2], values: ['U(2m, 5m)', 'U(5m, 8m)']}`. Times as `"HH:MM"`, durations as `90s`, `15m`, `2h`.

### 2.6 Clinical profiles (patch on a tier-0 profile)

```yaml
profile: insomnia-moderate
tier: 2
extends: 9to5-worker                    # also the baseline for --baseline-days
night_sets:                             # nights of day d, drawn per calendar week
  symptomatic: {per_week: 'N(4, 1)', clip: [3, 5]}
patch:
  anchors:
    sleep: [{nights: symptomatic, shift: 'U(60m, 120m)'}]
  modify: {block_id: {key: value}}      # replace keys; a new frequency key replaces the old one; null removes a key
  add: [...]                            # new blocks, appended (lowest priority)
  remove: [block_or_away_id, ...]
  scale: {block_id: 0.9}                # multiplies the daily count (stochastic rounding)
  forbid: [{within: ["04:00", "05:30"], night: true}]   # no activity in this window
```

`baseline_sleep` is the sleep anchor before the patch's shifts (e.g. `presleep_extension` runs from `baseline_sleep` to `sleep`).

## 3. Scheduling rules

The rules of catalog §1, plus the decisions the catalog leaves open (marked ⚑; they are also in §7):

- **Randomness:** only `random.Random(f"{seed}/<key>")`, with one stream per day, block, week, etc. (the runner uses `f"{seed}/{block_id}"`). Same seed gives the same plan, byte for byte. Changing one block does not reshuffle the others. Because the keys contain date and block, never the phase, the baseline days of a clinical plan are the same schedule as the tier-0 profile run alone with the same seed (tested).
- **Time zone:** profile times are Europe/Zurich wall times. Instants are computed in UTC and written with the local offset, so DST days (25.10.2026, 28.03.2027) get correct durations.
- **Day boundary:** day d owns the night after it (catalog: nights are labelled by the day they start on). Evening blocks may run past midnight. The plan covers `[start 00:00, start + days 00:00)` local time. A block that doesn't fit completely inside is dropped (⚑ the last night of a plan is cut). The first night (before the warm-up day) is empty.
- **Warm-up:** `--start` is the warm-up day (phase `warmup`). It is scheduled like any other day of its weekday, but it gets no per-window blocks. ⚑ A Monday `--start` makes the 14-day window start on a Tuesday (warning). Use the Sunday before (`--start 2026-10-25`) to start the window on a Monday.
- **Wake/sleep:** blocks of day d don't start before `wake(d)`. `within` and fill windows are clipped to `[wake, sleep]` unless `night: true`.
- **Away vs. idle:** idle = no row (the device stays connected; the ingest filter handles background traffic). Away = an `away` row. An occurrence that overlaps an away period is **dropped**, not moved (counts mean "while at home"). `replaces: evening` cancels the day's `group: evening` blocks.
- **Overlaps on one device:** blocks are placed in list order. A later-listed block that overlaps one already placed on the same device starts when that one ends. If it then no longer fits its window (`within`: the window; `at`/`from`+`duration`: ⚑ start + duration + `max_delay`, default 30 min), it is dropped. It never jumps over an away period.
- **Calls:** `video_call`, `voice_call` and `gaming_session` with `voice: true` are **exclusive across devices**. While one runs, nothing else runs on any device except `music_background` and the gaming session's own voice chat. ⚑ Calls are placed **before** all other blocks (appointments), then everything else in list order around them.
- **Splitting:** ⚑ fill blocks (`from` + `to`) and `work_block`/`study_block` don't move. They are cut around calls and earlier blocks (and trimmed by away periods); pieces shorter than 5 min are dropped. Example: `work_pm` 13:00–17:30 with a Teams call 14:00–14:40 becomes `…-work_pm-01a` 13:00–14:00 and `…-work_pm-01b` 14:40–17:30 ("13:00–17:30 laptop work, incl. 1–2 video calls").
- **Frequency:** `count` per eligible day. `per_week`: n per calendar week Mon–Sun. The days are drawn among the eligible weekdays of the whole week, also those outside the plan, so a partial week gets a pro-rated share. `per_window`/`keep_per_window`/`nights_per_window`: the same per 14-day window, counted from the first day after the warm-up. Night sets: n nights per calendar week.
- **Devices:** the profile's roles are mapped by `--dataset` + `role` to `devices.csv` rows. Every role must exist exactly once.

## 4. Plan format

`plan.csv`, sorted by start:

| Column | Content |
|---|---|
| `start`, `end` | Planned start/end, ISO-8601 with offset (`2026-10-26T07:02:20+01:00`) |
| `device` | Device name from `devices.csv` |
| `activity_id` | Catalog §2 ID; `away` for away periods (one row per device) |
| `domains` | Planned mix keys, `;`-separated (`messaging;social_passive;news`; calls: `call`; music: `audio`). The runner's log writes the real hosts in this column |
| `profile`, `seed` | Profile running on that day (the tier-0 name on baseline days), instance seed |
| `block_id` | `<yyyymmdd>-<profile block>-<nn>[a-z][-bg\|-voice]`, unique within the plan, e.g. `20261026-work_pm-01b`. Letters = pieces of a split block; `-bg`/`-voice` = companions |
| `mix` | Runner syntax `news:0.4,messaging:0.4` (empty for calls, music, away) |
| `duration` | Seconds (`--duration`) |
| `pages`, `dwell` | Runner overrides, where set |
| `platform` | Call platform |
| `day` | Day the block belongs to (a night block of day d can start on d+1) |
| `phase` | `warmup`, `baseline` or `profile` |
| `dataset`, `profile_block`, `companion_of` | Dataset; block ID in the profile YAML; host `block_id` of a companion |

The first eight columns are the runner's ground-truth columns (catalog §1) without `status`, so plan and log can be joined on `block_id`.

`plan.commands.tsv`: one line per plan row, `start<TAB>end<TAB>device<TAB>block_id<TAB>command`, where `command` is a runner call to run from `traffic-runner/` at `start`:

```
2026-10-26T07:02:20+01:00	2026-10-26T07:08:52+01:00	student_a_phone	20261026-wake_check-01	scripts/run-activity.sh student_a_phone --activity phone_check --duration 392 --mix messaging:0.4,social_passive:0.4,news:0.2 --seed 42 --profile student --block-id 20261026-wake_check-01
```

`away` rows are written as `#` comments: a container cannot leave the Wi-Fi, so live, "away" simply means no runs.

## 5. How the plan is consumed

**Live (runner, executor still to be written).** The executor reads `plan.commands.tsv`. It waits until each `start` (absolute times, so a restart can skip what is past) and launches the command in the background, because blocks on different devices overlap (and companions start together with their host). It doesn't wait for a command before starting the next one. The runner appends one row per block to `traffic-runner/logs/ground_truth.csv` with the real end and `status`. After the run, join log and plan on `block_id`:
- missing rows = not executed
- `status` ≠ `ok` = failed or stub
- `end` earlier than planned = `phone_check` done or video over

As long as calls, messaging, `social_passive`, `work_block`, `study_block` and `gaming_session` are stubs in the runner, their rows log `not_implemented` and produce no traffic. For live runs this is the main gap between plan and data.

**Synthetic (later).** The synthesizer reads `plan.csv` directly. For each row it takes a recorded snippet of the same `activity_id`, role and `mix` (from the live runs' PCAPs, cut by the ground-truth rows). It trims or loops the snippet to `duration`, shifts it to `start` and rewrites the addresses to the device's IP/MAC from `devices.csv`. Nothing is added outside planned rows: idle stays empty and away is a gap. The synthetic PCAPs then go through the same ingest (`tapingest --once`) as the live ones. Every packet stays traceable to a `block_id` → profile block → profile, which is the traceability the project objective asks for.

**Analysis.** Per day: `day`/`phase` say which phase (warm-up days are discarded; baseline vs. profile come from `phase`, not from the dataset name, catalog §1). `profile_block` connects the app's per-day metrics to the profile's §9.

## 6. Status

| Profile | YAML | Notes |
|---|---|---|
| `tier0-healthy/student` | ✓ | §7 S1–S5 |
| `tier0-healthy/9to5-worker` | ✓ | §7 W1–W2 |
| `tier2-clinical/insomnia-moderate` | ✓ | §7 I1–I5; `daytime_fatigue` (off in the profile) not scripted |
| `tier2-clinical/mdd-severe-suicidality` | — | needs decisions, §8 |
| `tier2-clinical/social-anxiety-moderate` | — | needs decisions, §8 |

Not done: an executor (§5), and the synthesizer.

## 7. Ambiguities in the profile markdown (decisions needed)

Each item says what the scheduler does now. All are small to change.

**Catalog §1 / all profiles**
- **C1 Window start.** "14 days starting on a Monday, plus ≥1 warm-up day", while the requested CLI starts on Monday with the first day as warm-up, so the window starts Tuesday. Now: warning only. Decide: warm-up on the Sunday before (`--start` = Sunday), or treat the warm-up as day 0 of the window.
- **C2 Overlap priority vs. calls.** "The later-listed block starts when the earlier one ends" would push every work call out of the work blocks. Now: calls first, fill and work/study blocks cut around them (§3).
- **C3 Anchored blocks.** `at:` blocks have no window, so "dropped if it no longer fits its window" is undefined. Now: they may slip by 30 min (`max_delay`). Measured over 20 seeds, strict pushing would leave 45 % of the student's days without a `bedtime_check` (with the slip: 10 %, mostly going-out nights, C4) and 13 % of the worker's (with the slip: 0 %).
- **C4 Partial overlap with away.** Now: dropped, fill blocks trimmed. Side effect: after going out, `sleep = return + 15–30m` and `bedtime_check` at `sleep − 15/20m` often starts before the return and is dropped.
- **C5 "Evening blocks"** (for "replaces evening blocks") are not defined. Now: the blocks under the `# evening` comment in §9 (`group: evening`); `bedtime_check` is not one.
- **C6 Noise lines** ("±25 % on durations", "±15 % on volume"): no extra jitter is applied beyond the ranges and SDs in the blocks. Should durations get an extra ±25 %?
- **C7 Last night.** Activity after midnight of the last plan day is dropped (it would count for a day outside the plan anyway).
- **C8 Calls in the runner.** `platform` has no runner option and calls are stubs. Camera/mic options will be needed (see §8, SAD).

**Student**
- **S1 Campus start on late-lecture days.** The profile says `U("08:00", "14:00")` for all days, but the late-lecture wake is N(09:30, 30m), so campus could start before waking. Now: `U("10:30", "14:00")` on late days, 08:00 on early days, and never earlier than wake + 20 min (`not_before`).
- **S2 Early-lecture days.** Wake N(07:30, 30m) can be after the 08:00 campus start. Now: campus starts at max(08:00, wake + 20m).
- **S3 `evening_stream` has no count:** exactly one per evening, also on gaming evenings (it then runs after the gaming session, if it still fits before sleep).
- **S4 `study_home` "after campus":** starts at the campus return. On a day without campus it doesn't run (relevant for MDD's skipped lecture days).
- **S5 Going out on Fri/Sat:** sleep = return + 15–30 min replaces the Fri/Sat anchor N(01:30, 30m), even when the return is earlier.

**9-to-5 worker**
- **W1 Leaving for the office** N(07:30, 20m) can be before wake + wake check (wake N(06:30, 15m) clipped at +3 SD = 07:15). Now: `not_before: wake + 20m`.
- **W2 `work_call` inside work hours:** cut into the work blocks (C2).

**Insomnia**
- **I1 Symptomatic nights:** `N(4, 1) clipped to [3, 5]` per calendar week, rounded, placed on random nights Mon–Sun.
- **I2 Symptomatic night after an evening out:** the +60–120 min shift is added to the return-based sleep time.
- **I3 `presleep_extension` "from baseline_sleep to sleep":** a fill block, so it runs in the gaps around `evening_checks` and `bedtime_check` on the phone. Otherwise it would overlap the bedtime check, which also follows the shifted anchor.
- **I4 Night bursts:** `pages: 1-3` together with the 2–8 min duration means the duration is an upper bound (catalog §2).
- **I5 Weekend wake shift** applies on all weekends of the profile phase, not on baseline days.

## 8. MDD and SAD: what is missing

Their §9 patches use constructs without defined semantics. Proposed defaults are in brackets; the YAMLs are written once these are confirmed.

**Both**
- `"baseline × U(a, b)"` on a count range: draw the baseline value, multiply, round stochastically [factor drawn once per seed, steady state].
- §5 targets that §9 doesn't script (MDD domain diversity −40–50 %, SAD weekend delta) [§9 is authoritative; check §5 in the run].

**MDD severe + suicidality**
- `campus: {attend_share: 0.5}` [each lecture day skipped with p = 0.5; on a skipped day only `day_checks` in the daytime, no `study_home`].
- `early_waking` / `night_passive` `only_if` (sleep onset of *which* night) [the night before the morning; days are drawn among the days that meet the condition].
- `then: "idle_connected until wake"` [nothing scheduled until `wake`; `wake_check` still runs].
- `rumination` `count_per_day` and window 14:00–02:00 [`count`; clipped to sleep].
- `evening_stream` `may_cross_midnight` [may pass midnight, still ends by sleep].
- `suicidality_overlay` sequence: back to back? probabilities per step? `lookups: 1-3` has no runner option; `log_flag: sensitive` [plan column `flag`].
- `weekend_anchors` "same distributions as ... after the modifications above" [weekend wake N(09:30, 30m), Fri/Sat sleep N(00:30, 45m), then the shifts].

**Social anxiety**
- `group_call` `camera: false`, `mic: "on only 10% of the time"` [becomes `voice_call`; the mic share has no runner option].
- `going_out` `keep_per_window: 0-1` + `home_instead_of_out` `replaces: going_out` [draw the baseline's going-out evenings, keep 0–1, the others become home evenings].
- `split: {video_stream: .5, gaming_session: .3, social_passive: .2}`: (a) one activity per evening by weight, or (b) consecutive parts by share [b].
- Which baseline evening blocks still run on a home evening [laptop evening blocks replaced, phone evening blocks kept, sleep = end of the home block].
